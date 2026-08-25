from __future__ import annotations

from typing import Any

import rispy

from risforge.enrichment import RisEnricher


class _MockResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _MockSession:
    """Minimal stand-in for requests.Session/CachedSession.

    Routes GET requests to canned payloads by matching a substring in
    the URL, so tests never touch the network.
    """

    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []

    def get(self, url: str, timeout: int = 10) -> _MockResponse:
        self.calls.append(url)
        for fragment, payload in self.routes.items():
            if fragment in url:
                return _MockResponse(200, payload)
        return _MockResponse(404, {})


CROSSREF_PAYLOAD = {
    "message": {
        "title": ["Deep Learning For Diffusion MRI"],
        "author": [{"family": "Smith", "given": "John"}],
        "container-title": ["NeuroImage"],
        "publisher": "Elsevier",
        "issued": {"date-parts": [[2021]]},
        "volume": "230",
        "issue": "4",
        "page": "117-129",
        "ISSN": ["1053-8119"],
    }
}
OPENALEX_PAYLOAD = {
    "id": "https://openalex.org/W123",
    "concepts": [{"level": 0, "display_name": "Neuroscience"}],
    "open_access": {"oa_url": "https://example.org/paper.pdf"},
}
SEMANTIC_SCHOLAR_PAYLOAD = {"abstract": "An abstract from Semantic Scholar."}
UNPAYWALL_PAYLOAD = {"best_oa_location": {"url_for_pdf": "https://example.org/oa-version.pdf"}}


def _make_enricher() -> tuple[RisEnricher, _MockSession]:
    session = _MockSession(
        {
            "api.crossref.org/works/10": CROSSREF_PAYLOAD,
            "api.openalex.org": OPENALEX_PAYLOAD,
            "api.semanticscholar.org": SEMANTIC_SCHOLAR_PAYLOAD,
            "api.unpaywall.org": UNPAYWALL_PAYLOAD,
        }
    )
    enricher = RisEnricher(email="test@example.com", session=session)
    return enricher, session


class TestExtractDoi:
    def test_extracts_from_doi_field(self) -> None:
        enricher, _session = _make_enricher()
        record = {"doi": "10.1016/j.neuroimage.2021.00001"}
        assert enricher.extract_doi(record) == "10.1016/j.neuroimage.2021.00001"

    def test_extracts_doi_embedded_in_urls_field(self) -> None:
        enricher, _session = _make_enricher()
        record = {"urls": ["https://doi.org/10.1016/j.neuroimage.2021.00001"]}
        assert enricher.extract_doi(record) == "10.1016/j.neuroimage.2021.00001"

    def test_returns_none_when_absent(self) -> None:
        enricher, _session = _make_enricher()
        assert enricher.extract_doi({}) is None


class TestStringSimilarity:
    def test_identical_strings(self) -> None:
        enricher, _session = _make_enricher()
        assert enricher.string_similarity("Same Title", "same title") == 1.0

    def test_empty_strings(self) -> None:
        enricher, _session = _make_enricher()
        assert enricher.string_similarity("", "Something") == 0.0


class TestEnrichRecord:
    def test_fills_only_empty_fields(self) -> None:
        enricher, _session = _make_enricher()
        record = {
            "doi": "10.1016/j.neuroimage.2021.00001",
            "title": "User-curated title, should not be overwritten",
        }

        result = enricher.enrich_record(record)

        assert result["title"] == "User-curated title, should not be overwritten"
        assert result["secondary_title"] == "NeuroImage"  # was empty, now filled
        assert result["abstract"] == "An abstract from Semantic Scholar."
        assert enricher.stats["enriched"] == 1

    def test_list_type_fields_are_stored_as_lists(self) -> None:
        enricher, _session = _make_enricher()
        record = {"doi": "10.1016/j.neuroimage.2021.00001"}

        result = enricher.enrich_record(record)

        assert result["authors"] == ["Smith, John"]
        assert isinstance(result["keywords"], list)
        assert isinstance(result["urls"], list)

    def test_unresolvable_record_is_tracked_as_failed(self) -> None:
        enricher, _session = _make_enricher()
        record = {"title": "", "doi": ""}

        result = enricher.enrich_record(record)

        assert result == {"title": "", "doi": ""}
        assert enricher.stats["failed"] == 1
        assert enricher.failed_records[0]["reason"] == "Unresolved DOI via Title Matching"


class TestEnrichFile:
    def test_end_to_end_with_mocked_session(self, tmp_path) -> None:
        input_path = tmp_path / "clean.ris"
        output_path = tmp_path / "enriched.ris"

        with open(input_path, "w", encoding="utf-8") as f:
            rispy.dump(
                [{"type_of_reference": "JOUR", "doi": "10.1016/j.neuroimage.2021.00001"}],
                f,
            )

        enricher, _session = _make_enricher()
        stats = enricher.enrich_file(input_path=input_path, output_path=output_path)
        assert output_path.exists()
        assert stats["processed"] == 1
        assert stats["enriched"] == 1


class TestEnrichFileMalformedInput:
    """Regression tests for a rispy 0.10.0 bug: RisParser tracks the

    "last tag seen" as state that persists across record boundaries
    within a single ``rispy.load()``/``rispy.loads()`` call. A stray
    blank (or otherwise non-tag-pattern) line positioned early in one
    record -- right after a record boundary -- could make it try to
    extend a field from the *previous* record onto the new record's
    dict, which doesn't have that key yet, raising KeyError and
    aborting the whole file. Reproduces identically on every platform
    (verified on Linux); it is not a Windows-specific issue, just a
    RIS-content issue that happened to be triggered first by files
    tested on Windows. enrich_file() now parses via
    risforge.cleaning.parse_ris_records() (block-isolated, immune to
    this) instead of calling rispy.load() directly on the whole file.
    """

    def test_stray_blank_line_after_record_boundary_does_not_crash(self, tmp_path) -> None:
        # Record 1 ends with an "LA" (language) tag as its last real
        # field before ER. Record 2 has a stray blank line immediately
        # after "TY", before its own first tag -- this is exactly the
        # combination that crashed rispy.load() with KeyError('language').
        ris_text = (
            "TY  - JOUR\n"
            "AU  - Smith, John\n"
            "TI  - First paper\n"
            "LA  - English\n"
            "DO  - 10.1000/first\n"
            "ER  - \n"
            "\n"
            "TY  - JOUR\n"
            "\n"
            "AU  - Doe, Jane\n"
            "TI  - Second paper\n"
            "DO  - 10.1000/second\n"
            "ER  - \n"
        )
        input_path = tmp_path / "malformed.ris"
        input_path.write_text(ris_text, encoding="utf-8")

        enricher, _session = _make_enricher()
        # Must not raise KeyError.
        stats = enricher.enrich_file(str(input_path), str(tmp_path / "out.ris"))

        assert stats["processed"] == 2

    def test_genuinely_unparseable_block_is_skipped_and_counted(self, tmp_path) -> None:
        ris_text = (
            "TY  - JOUR\n"
            "AU  - Smith, John\n"
            "TI  - Valid paper\n"
            "DO  - 10.1000/valid\n"
            "ER  - \n"
            "\n"
            "TY  - JOUR\n"
            "AU  - Broken, Record\n"
            "TI  - Missing ER terminator entirely\n"
        )
        input_path = tmp_path / "genuinely_malformed.ris"
        input_path.write_text(ris_text, encoding="utf-8")

        enricher, _session = _make_enricher()
        stats = enricher.enrich_file(str(input_path), str(tmp_path / "out.ris"))

        assert stats["processed"] == 1
        assert stats["skipped_malformed"] == 1

    def test_utf8_bom_is_handled_transparently(self, tmp_path) -> None:
        ris_text = "TY  - JOUR\nAU  - Smith, John\nTI  - BOM paper\nDO  - 10.1000/bom\nER  - \n"
        input_path = tmp_path / "bom.ris"
        input_path.write_bytes(b"\xef\xbb\xbf" + ris_text.encode("utf-8"))

        enricher, _session = _make_enricher()
        stats = enricher.enrich_file(str(input_path), str(tmp_path / "out.ris"))

        assert stats["processed"] == 1

    def test_non_utf8_file_gives_a_clear_error_without_crashing(self, tmp_path) -> None:
        input_path = tmp_path / "bad_encoding.ris"
        input_path.write_bytes(b"TY  - JOUR\nTI  - Bad \xff\xfe byte sequence\nER  - \n")

        enricher, _session = _make_enricher()
        # enrich_file()'s existing contract: parsing failures are
        # logged and it returns the (unmodified) stats rather than
        # raising, exactly as it already did for a missing input file.
        stats = enricher.enrich_file(str(input_path), str(tmp_path / "out.ris"))

        assert stats["processed"] == 0
