"""Enrich RIS citation records by aggregating metadata from scholarly APIs.

Behavior is unchanged from the original ``enrich_ris.py``: the same
four providers (Crossref, OpenAlex, Semantic Scholar, Unpaywall) are
queried in the same order, existing fields are still never
overwritten (only gaps are filled), and the same retry/backoff and
7-day response cache are used.

Two structural changes were made, both in service of the same goal --
letting this be imported as a library, not just run as a script:

1. The module no longer attaches a ``StreamHandler`` to its logger at
   import time. A library should never configure logging as a side
   effect of being imported; the calling application (or
   :mod:`risforge.cli`) decides where log records go.
2. :class:`RisEnricher` now accepts an optional pre-built ``session``,
   so tests (and callers with their own HTTP session/retry policy) can
   inject one instead of always getting a fresh
   ``requests_cache.CachedSession`` pointed at a file on disk.

One genuine bug from the original script *was* fixed here, not just
restructured: the original ``RIS_MAPPING`` (and ``extract_doi``)
addressed record fields by RIS tag mnemonic (``"DO"``, ``"TI"``,
``"T2"``, ...). But ``rispy`` -- both the parser and the writer --
represents records by *logical* field name (``"doi"``, ``"title"``,
``"secondary_title"``, ...), not by tag. Writing to ``record["DO"]``
therefore silently created a key rispy's writer doesn't recognize, and
``rispy.dump()`` dropped it on write (emitting a ``UserWarning: label
`DO` not exported`` in the process). In practice, every field the
original enricher "added" never actually made it into the output
file, and ``extract_doi()`` could never find a DOI that was already
present on the record either, since it looked for ``"DO"`` instead of
``"doi"``. :data:`RISPY_FIELD_MAP` below uses rispy's real field
names, and :meth:`RisEnricher.extract_doi` reads ``"doi"``/``"urls"``.

A second bug was found and fixed the same way: :meth:`RisEnricher.enrich_file`
used to call ``rispy.load()`` directly on the whole input file in one
pass. ``rispy`` (as of 0.10.0) has its own bug where it tracks the
"last tag seen" as parser-wide state that is never reset between
records -- so a single stray blank or otherwise non-tag-pattern line
positioned early in one record, right after a record boundary, can
make it try to extend a field from the *previous* record onto the new
record's (fresh, and therefore missing that key) dict, raising a
``KeyError`` for whatever field that happened to be and aborting the
entire file's enrichment. ``risforge.cleaning.parse_ris_records()``
already sidesteps this by parsing each record block independently (a
fresh parser instance per block, so there's no cross-record state to
leak) -- ``enrich_file()`` now reuses that same function instead of
calling ``rispy.load()`` itself, which both fixes the crash and means
a malformed record is tolerated and reported exactly the way
:func:`risforge.cleaning.clean_ris_file` already tolerates and reports
one, rather than each module handling malformed input differently.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import requests_cache
import rispy
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from risforge.cleaning import parse_ris_records

TITLE_MATCH_THRESHOLD = 0.90
CACHE_EXPIRE_DAYS = 7

logger = logging.getLogger(__name__)

# Maps our enrichment payload's logical keys to rispy's actual record
# field names (NOT RIS tag mnemonics -- see the module docstring).
RISPY_FIELD_MAP: dict[str, str] = {
    "doi": "doi",
    "title": "title",
    "authors": "authors",
    "journal": "secondary_title",  # rispy has no single canonical "journal" field;
    "publisher": "publisher",  # secondary_title (T2) is where journal names live
    "year": "year",  # in the vast majority of real-world RIS exports.
    "date": "date",
    "volume": "volume",
    "issue": "number",
    "start_page": "start_page",
    "end_page": "end_page",
    "abstract": "abstract",
    "issn": "issn",
    "url": "urls",  # rispy stores URLs as a list (RIS "UR" is a list-type tag).
    "pdf_url": "file_attachments1",  # RIS "L1", used for PDF links in Zotero/EndNote.
    "keywords": "keywords",
}

# rispy fields that are always lists, regardless of what the source API gives us.
_LIST_TYPE_FIELDS = {"authors", "keywords", "urls"}


def _build_default_session(cache_name: str) -> requests.Session:
    """Build the package's default cached, retrying HTTP session."""
    session = requests_cache.CachedSession(
        cache_name,
        expire_after=CACHE_EXPIRE_DAYS * 86400,
        allowable_codes=[200, 404],
    )
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    return session


class RisEnricher:
    """Enriches RIS citation records with metadata from scholarly APIs.

    Args:
        email: Contact email sent to Crossref/OpenAlex/Unpaywall as
            required by their "polite pool" usage terms.
        cache_name: Base filename for the on-disk HTTP response cache
            (only used when ``session`` is not provided).
        session: Optional pre-built ``requests.Session`` (or
            ``requests_cache.CachedSession``). Mainly useful for
            testing -- pass a mocked session to avoid real network
            calls. When omitted, a cached, retrying session is built
            automatically.
    """

    def __init__(
        self,
        email: str,
        cache_name: str | Path = ".api_cache",
        session: requests.Session | None = None,
    ) -> None:
        self.email = email
        self.stats: dict[str, Any] = {
            "processed": 0,
            "enriched": 0,
            "failed": 0,
            "skipped_malformed": 0,
            "api_calls": {
                "crossref": 0,
                "openalex": 0,
                "semanticscholar": 0,
                "unpaywall": 0,
            },
        }
        self.failed_records: list[dict[str, Any]] = []
        self.session = session or _build_default_session(str(cache_name))
        self.session.headers.update(
            {"User-Agent": f"risforge/1.0 (mailto:{self.email})"}
        )

    # --- Core identification -------------------------------------------------

    def extract_doi(self, record: dict[str, Any]) -> str | None:
        """Extract and validate a DOI from a rispy record's doi/urls fields."""
        doi = record.get("doi", "")

        if not doi:
            urls = record.get("urls", "")
            doi = " ".join(urls) if isinstance(urls, list) else urls

        if not isinstance(doi, str):
            doi = str(doi)

        match = re.search(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", doi, re.IGNORECASE)
        return match.group(1).lower() if match else None

    def string_similarity(self, source_text: str, target_text: str) -> float:
        """Fuzzy-match ratio between two strings (used for title matching)."""
        if not source_text or not target_text:
            return 0.0
        return SequenceMatcher(None, source_text.lower(), target_text.lower()).ratio()

    def resolve_doi_by_title(self, title: str) -> str | None:
        """Fall back to a Crossref title search when a record has no DOI."""
        if not title:
            return None

        url = (
            f"https://api.crossref.org/works?query.title={quote(title)}"
            f"&select=DOI,title&rows=3&mailto={self.email}"
        )
        try:
            response = self.session.get(url, timeout=10)
            self.stats["api_calls"]["crossref"] += 1

            if response.status_code == 200:
                items = response.json().get("message", {}).get("items", [])
                for item in items:
                    api_titles = item.get("title", [""])
                    api_title = api_titles[0] if api_titles else ""

                    if self.string_similarity(title, api_title) >= TITLE_MATCH_THRESHOLD:
                        doi_value = item.get("DOI")
                        if doi_value:
                            return str(doi_value).lower()

        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("Title resolution failed for '%s': %s", title, error)

        return None

    # --- API integrations ------------------------------------------------------

    def fetch_crossref_metadata(self, doi: str) -> dict[str, Any]:
        """Fetch authoritative bibliographic metadata from Crossref."""
        url = f"https://api.crossref.org/works/{quote(doi)}?mailto={self.email}"
        try:
            response = self.session.get(url, timeout=10)
            self.stats["api_calls"]["crossref"] += 1

            if response.status_code == 200:
                payload = response.json().get("message", {})

                titles = payload.get("title", [""])
                article_title = titles[0] if titles else ""

                authors_list = []
                for author_data in payload.get("author", []):
                    family = author_data.get("family", "")
                    given = author_data.get("given", "")
                    author_str = f"{family}, {given}".strip(", ")
                    if author_str:
                        authors_list.append(author_str)

                containers = payload.get("container-title", [""])
                journal_title = containers[0] if containers else ""

                issued_parts = payload.get("issued", {}).get("date-parts", [[None]])
                published_year = None
                if issued_parts and issued_parts[0] and issued_parts[0][0] is not None:
                    published_year = str(issued_parts[0][0])

                page_string = payload.get("page", "")
                start_page, end_page = None, None
                if page_string:
                    pages = page_string.split("-")
                    start_page = pages[0] if pages else None
                    end_page = pages[1] if len(pages) > 1 else None

                issns = payload.get("ISSN", [""])
                issn_value = issns[0] if issns else None

                return {
                    "title": article_title,
                    "authors": authors_list,
                    "journal": journal_title,
                    "publisher": payload.get("publisher"),
                    "year": published_year,
                    "volume": payload.get("volume"),
                    "issue": payload.get("issue"),
                    "start_page": start_page,
                    "end_page": end_page,
                    "issn": issn_value,
                }

        except (requests.RequestException, ValueError, KeyError, IndexError) as error:
            logger.warning("Crossref failed for %s: %s", doi, error)

        return {}

    def fetch_openalex_metadata(self, doi: str) -> dict[str, Any]:
        """Fetch open-access status and subject concepts from OpenAlex."""
        url = f"https://api.openalex.org/works/doi:{quote(doi)}?mailto={self.email}"
        try:
            response = self.session.get(url, timeout=10)
            self.stats["api_calls"]["openalex"] += 1

            if response.status_code == 200:
                payload = response.json()
                concepts = [
                    c.get("display_name")
                    for c in payload.get("concepts", [])
                    if c.get("level", 99) <= 1 and c.get("display_name")
                ]
                oa_url = payload.get("open_access", {}).get("oa_url")
                return {
                    "keywords": concepts,
                    "pdf_url": oa_url,
                    "url": payload.get("id"),
                }

        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("OpenAlex failed for %s: %s", doi, error)

        return {}

    def fetch_semanticscholar_metadata(self, doi: str) -> dict[str, Any]:
        """Fetch parsed abstract text from Semantic Scholar."""
        url = (
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{quote(doi)}"
            f"?fields=abstract,referenceCount,citationCount"
        )
        try:
            response = self.session.get(url, timeout=10)
            self.stats["api_calls"]["semanticscholar"] += 1

            if response.status_code == 200:
                payload = response.json()
                return {"abstract": payload.get("abstract")}

        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("Semantic Scholar failed for %s: %s", doi, error)

        return {}

    def fetch_unpaywall_pdf(self, doi: str) -> dict[str, Any]:
        """Fetch the best open-access PDF location from Unpaywall."""
        url = f"https://api.unpaywall.org/v2/{quote(doi)}?email={self.email}"
        try:
            response = self.session.get(url, timeout=10)
            self.stats["api_calls"]["unpaywall"] += 1

            if response.status_code == 200:
                payload = response.json()
                best_oa = payload.get("best_oa_location")
                if best_oa and best_oa.get("url_for_pdf"):
                    return {"pdf_url": best_oa.get("url_for_pdf")}

        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("Unpaywall failed for %s: %s", doi, error)

        return {}

    # --- Processing logic --------------------------------------------------------

    def enrich_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Aggregate metadata from all providers and fill gaps in one record.

        Existing fields are never overwritten -- only empty/missing
        fields are populated, so user-curated data always wins.
        """
        self.stats["processed"] += 1

        doi = self.extract_doi(record)
        title = record.get("title")

        if not doi and title:
            doi = self.resolve_doi_by_title(str(title))

        if not doi:
            self.stats["failed"] += 1
            self.failed_records.append(
                {"original_title": title, "reason": "Unresolved DOI via Title Matching"}
            )
            return record

        enriched_data: dict[str, Any] = {"doi": doi}

        crossref_metadata = self.fetch_crossref_metadata(doi)
        scholar_metadata = self.fetch_semanticscholar_metadata(doi)
        openalex_metadata = self.fetch_openalex_metadata(doi)
        unpaywall_metadata = self.fetch_unpaywall_pdf(doi)

        enriched_data.update(crossref_metadata)
        enriched_data.update(scholar_metadata)
        enriched_data.update(openalex_metadata)

        if unpaywall_metadata.get("pdf_url"):
            enriched_data["pdf_url"] = unpaywall_metadata["pdf_url"]

        modified = False
        for logical_key, rispy_field in RISPY_FIELD_MAP.items():
            new_value = enriched_data.get(logical_key)
            if not new_value:
                continue

            if not record.get(rispy_field):
                if rispy_field in _LIST_TYPE_FIELDS:
                    record[rispy_field] = (
                        new_value if isinstance(new_value, list) else [str(new_value)]
                    )
                else:
                    record[rispy_field] = (
                        new_value if isinstance(new_value, str) else str(new_value)
                    )
                modified = True

        if modified:
            self.stats["enriched"] += 1

        return record

    def enrich_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        fail_report_path: str | Path = "failed_records.json",
        request_delay_seconds: float = 0.1,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Enrich every record in a RIS file and write the result.

        Args:
            input_path: Source ``.ris`` file to enrich.
            output_path: Destination for the enriched ``.ris`` file.
            fail_report_path: Where to write a JSON report of records
                whose DOI could not be resolved. Only written if at
                least one record failed.
            request_delay_seconds: Delay between records, to stay
                within provider rate limits beyond the built-in retry
                policy.
            progress_callback: Optional callback invoked as
                ``progress_callback(processed_count, total_count)``
                after each record is processed. Added for callers
                (such as a GUI) that want to report determinate
                progress during a potentially slow, network-bound
                operation, without polling or duplicating this loop
                elsewhere. Never called when omitted -- zero behavior
                change for existing callers.

        Returns:
            The accumulated ``self.stats`` dict.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)
        fail_report_path = Path(fail_report_path)

        logger.info("Loading %s...", input_path)
        try:
            records, parse_errors = parse_ris_records(input_path)
        except (OSError, TypeError, ValueError) as error:
            logger.error("Failed to parse RIS file: %s", error)
            return self.stats

        if parse_errors:
            logger.warning(
                "Encountered %d malformed record block(s) in %s, skipped: %s",
                len(parse_errors),
                input_path,
                "; ".join(f"block {n}: {msg}" for n, msg in parse_errors),
            )
        self.stats["skipped_malformed"] = len(parse_errors)

        total = len(records)
        enriched_records = []
        for index, record in enumerate(records):
            enriched_records.append(self.enrich_record(record))
            if progress_callback is not None:
                progress_callback(index + 1, total)
            if request_delay_seconds:
                time.sleep(request_delay_seconds)

        with output_path.open("w", encoding="utf-8") as file:
            rispy.dump(enriched_records, file)

        if self.failed_records:
            with fail_report_path.open("w", encoding="utf-8") as file:
                json.dump(self.failed_records, file, indent=2)

        logger.info("Complete. Stats: %s", json.dumps(self.stats, indent=2))
        return self.stats
