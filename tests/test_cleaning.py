from __future__ import annotations

import pytest

from risforge.cleaning import (
    clean_ris_file,
    count_fields,
    extract_first_author,
    merge_cluster,
    normalize_doi,
    normalize_title,
    parse_ris_records,
)
from risforge.exceptions import RisParsingError


class TestNormalizeTitle:
    def test_lowercases_and_strips_punctuation(self) -> None:
        assert normalize_title("Deep Learning: For dMRI!") == "deep learning for dmri"

    def test_collapses_whitespace(self) -> None:
        assert normalize_title("A   Study   Of   Things") == "a study of things"

    def test_non_string_input_returns_empty(self) -> None:
        assert normalize_title(None) == ""
        assert normalize_title(123) == ""  # type: ignore[arg-type]


class TestNormalizeDoi:
    def test_strips_url_prefix(self) -> None:
        assert normalize_doi("https://doi.org/10.1016/j.foo.2021") == "10.1016/j.foo.2021"

    def test_strips_doi_colon_prefix(self) -> None:
        assert normalize_doi("doi:10.1016/j.foo.2021") == "10.1016/j.foo.2021"

    def test_strips_trailing_punctuation(self) -> None:
        assert normalize_doi("10.1016/j.foo.2021.") == "10.1016/j.foo.2021"

    def test_empty_input(self) -> None:
        assert normalize_doi("") == ""
        assert normalize_doi(None) == ""


class TestExtractFirstAuthor:
    def test_extracts_last_name_and_initials(self) -> None:
        assert extract_first_author(["Smith, John A."]) == "smith ja"

    def test_handles_missing_given_name(self) -> None:
        assert extract_first_author(["Smith"]) == "smith"

    def test_empty_list_returns_empty(self) -> None:
        assert extract_first_author([]) == ""
        assert extract_first_author(None) == ""


class TestCountFields:
    def test_counts_scalars_and_list_items(self) -> None:
        record = {"title": "X", "authors": ["A", "B"], "abstract": ""}
        assert count_fields(record) == 3  # title + 2 authors, empty abstract not counted

    def test_counts_unknown_tags(self) -> None:
        record = {"unknown_tag": {"N1": ["note one"], "N2": []}}
        assert count_fields(record) == 1


class TestMergeCluster:
    def test_single_record_returned_unchanged(self) -> None:
        record = {"title": "Solo"}
        assert merge_cluster([record]) is record

    def test_merges_missing_fields_from_weaker_record(self) -> None:
        best = {"title": "Paper", "authors": ["Smith, J."], "unknown_tag": {}}
        weaker = {"title": "Paper", "abstract": "An abstract.", "unknown_tag": {}}
        merged = merge_cluster([best, weaker])
        assert merged["abstract"] == "An abstract."
        assert merged["authors"] == ["Smith, J."]

    def test_does_not_overwrite_existing_nonempty_field(self) -> None:
        best = {"title": "Paper", "abstract": "Original", "unknown_tag": {}}
        weaker = {"title": "Paper", "abstract": "Different", "unknown_tag": {}}
        merged = merge_cluster([best, weaker])
        assert merged["abstract"] == "Original"


class TestCleanRisFile:
    def test_deduplicates_and_writes_output(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "clean.ris"

        records, errors = clean_ris_file(sample_ris_path, output_path)

        # 5 input records -> 2 duplicate pairs merged -> 3 final records.
        assert len(records) == 3
        assert errors == []
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8").strip() != ""

    def test_doi_duplicate_merges_abstract(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "clean.ris"
        records, _errors = clean_ris_file(sample_ris_path, output_path)

        tractography_record = next(
            r for r in records if "tractography" in r.get("title", "").lower()
        )
        assert "abstract" in tractography_record

    def test_missing_input_raises(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            clean_ris_file(tmp_path / "does_not_exist.ris", tmp_path / "out.ris")


class TestParseRisRecordsEncoding:
    """Regression tests for encoding-related parsing robustness.

    These are not Windows-specific fixes (see the equivalent tests in
    test_enrichment.py for the actual crash this was found alongside),
    but a UTF-8 BOM in particular is disproportionately common in
    files saved by Windows text editors and some reference managers,
    so it's worth covering explicitly here too.
    """

    def test_utf8_bom_is_stripped_transparently(self, tmp_path) -> None:
        ris_text = "TY  - JOUR\nAU  - Smith, John\nTI  - BOM paper\nER  - \n"
        path = tmp_path / "bom.ris"
        path.write_bytes(b"\xef\xbb\xbf" + ris_text.encode("utf-8"))

        records, errors = parse_ris_records(path)

        assert len(records) == 1
        assert records[0]["title"] == "BOM paper"
        assert errors == []

    def test_non_utf8_bytes_raise_a_clear_parsing_error(self, tmp_path) -> None:
        path = tmp_path / "bad_encoding.ris"
        path.write_bytes(b"TY  - JOUR\nTI  - Bad \xff\xfe byte sequence\nER  - \n")

        with pytest.raises(RisParsingError, match="bad_encoding.ris"):
            parse_ris_records(path)

    def test_parsing_error_is_also_a_value_error(self, tmp_path) -> None:
        # RisParsingError intentionally also subclasses ValueError so
        # every existing `except (..., ValueError, ...)` call site
        # (CLI, pipeline, GUI worker) already catches it with no
        # changes required at those call sites.
        path = tmp_path / "bad_encoding.ris"
        path.write_bytes(b"\xff\xfe\x00\x01")

        with pytest.raises(ValueError):
            parse_ris_records(path)


class TestParseRisRecordsCrossRecordStateBug:
    """Regression test for the rispy 0.10.0 cross-record state bug.

    See risforge.enrichment's module docstring and
    tests/test_enrichment.py::TestEnrichFileMalformedInput for the
    full explanation. clean_ris_file() was never actually vulnerable
    to this (each record block is parsed independently), but this
    test pins that guarantee down explicitly so a future refactor
    can't accidentally reintroduce the whole-file single-parse
    pattern that enrich_file() used to use.
    """

    def test_stray_blank_line_after_record_boundary_does_not_crash(self, tmp_path) -> None:
        ris_text = (
            "TY  - JOUR\n"
            "AU  - Smith, John\n"
            "TI  - First paper\n"
            "LA  - English\n"
            "ER  - \n"
            "\n"
            "TY  - JOUR\n"
            "\n"
            "AU  - Doe, Jane\n"
            "TI  - Second paper\n"
            "ER  - \n"
        )
        path = tmp_path / "malformed.ris"
        path.write_text(ris_text, encoding="utf-8")

        records, errors = parse_ris_records(path)  # must not raise KeyError

        assert len(records) == 2
