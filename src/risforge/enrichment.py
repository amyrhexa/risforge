"""Enrich RIS citation records by aggregating metadata from scholarly APIs."""

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
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from risforge.cleaning import parse_ris_records

logger = logging.getLogger(__name__)

TITLE_MATCH_THRESHOLD = 0.90
CACHE_EXPIRE_DAYS = 7
REQUEST_TIMEOUT_SECONDS = 10

# FIX: Added capture group around the DOI pattern so match.group(1) works.
DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)

RISPY_FIELD_MAP: dict[str, str] = {
    "doi": "doi",
    "title": "title",
    "authors": "authors",
    "journal": "secondary_title",
    "publisher": "publisher",
    "year": "year",
    "date": "date",
    "volume": "volume",
    "issue": "number",
    "start_page": "start_page",
    "end_page": "end_page",
    "abstract": "abstract",
    "issn": "issn",
    "url": "urls",
    "pdf_url": "file_attachments1",
    "keywords": "keywords",
}

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
    """Enriches RIS citation records with metadata from scholarly APIs."""

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
        self.session.headers.update({"User-Agent": f"risforge/1.0 (mailto:{self.email})"})

    def extract_doi(self, record: dict[str, Any]) -> str | None:
        """Extract a DOI from a record's DOI or URL fields."""
        doi = record.get("doi", "")

        if isinstance(doi, list):
            doi = doi[0] if doi else ""

        if not doi:
            urls = record.get("urls", "")
            doi = " ".join(str(url) for url in urls) if isinstance(urls, list) else str(urls)

        if not isinstance(doi, str):
            doi = str(doi)

        match = DOI_PATTERN.search(doi)
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
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
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

    def fetch_crossref_metadata(self, doi: str) -> dict[str, Any]:
        """Fetch authoritative bibliographic metadata from Crossref."""
        url = f"https://api.crossref.org/works/{quote(doi)}?mailto={self.email}"

        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
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
                    pages = page_string.split("-", 1)
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
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            self.stats["api_calls"]["openalex"] += 1

            if response.status_code == 200:
                payload = response.json()

                concepts = [
                    concept.get("display_name")
                    for concept in payload.get("concepts", [])
                    if concept.get("level", 99) <= 1 and concept.get("display_name")
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
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
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
            response = self.session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            self.stats["api_calls"]["unpaywall"] += 1

            if response.status_code == 200:
                payload = response.json()
                best_oa = payload.get("best_oa_location")

                if best_oa and best_oa.get("url_for_pdf"):
                    return {"pdf_url": best_oa.get("url_for_pdf")}
        except (requests.RequestException, ValueError, KeyError) as error:
            logger.warning("Unpaywall failed for %s: %s", doi, error)

        return {}

    def enrich_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Aggregate metadata from all providers and fill gaps in one record."""
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
        """Enrich every record in a RIS file and write the result."""
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
                "Encountered %d malformed record block(s) in %s, skipped.",
                len(parse_errors),
                input_path,
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
            # Use default rispy dumping here as enrichment doesn't strictly
            # require the custom writer, but keeping it consistent is fine.
            import rispy

            rispy.dump(enriched_records, file)

        if self.failed_records:
            with fail_report_path.open("w", encoding="utf-8") as file:
                json.dump(self.failed_records, file, indent=2)

        logger.info("Complete. Stats: %s", json.dumps(self.stats, indent=2))

        return self.stats
