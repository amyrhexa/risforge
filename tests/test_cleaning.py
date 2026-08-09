from __future__ import annotations

import pytest

from risforge.cleaning import (
    clean_ris_file,
    count_fields,
    extract_first_author,
    merge_cluster,
    normalize_doi,
    normalize_title,
)


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
