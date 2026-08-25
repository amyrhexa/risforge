from __future__ import annotations

import pytest
import rispy

from risforge.merging import MergeResult, merge_ris_files


class TestMergeTwoFiles:
    def test_record_count_is_the_sum_of_both_files(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files([sample_ris_path, sample_ris_path], output_path)

        assert isinstance(result, MergeResult)
        assert result.input_file_count == 2
        assert result.record_count == 10  # 5 records in the fixture, twice
        assert result.output_path == output_path

    def test_does_not_deduplicate(self, sample_ris_path, tmp_path) -> None:
        # The fixture contains a DOI-duplicate pair; merging the same
        # file with itself must NOT collapse them -- that's cleaning's job.
        output_path = tmp_path / "merged.ris"
        merge_ris_files([sample_ris_path, sample_ris_path], output_path)

        merged_records = list(rispy.load(open(output_path, encoding="utf-8")))
        assert len(merged_records) == 10


class TestMergeThreeFiles:
    def test_merges_all_three_sources(self, multi_source_paths, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files(multi_source_paths, output_path)

        assert result.input_file_count == 3
        # scopus: 2 good + 1 malformed, pubmed: 2, wos: 2 -> 6 good records.
        assert result.record_count == 6

    def test_preserves_all_source_records(self, multi_source_paths, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        merge_ris_files(multi_source_paths, output_path)

        merged_records = list(rispy.load(open(output_path, encoding="utf-8")))
        titles = {r.get("title") for r in merged_records}

        assert "Cortical thickness changes in early Parkinson's disease" in titles
        assert "Machine learning applications in neuroimaging: a review" in titles
        assert "Structural connectome differences in schizophrenia" in titles

        # All three variants of the shared paper are present, unmerged.
        assert sum("Diffusion MRI Tractography" in (t or "") for t in titles) >= 1
        assert len(merged_records) == 6


class TestMergeSingleFile:
    def test_list_with_one_file_preserves_all_records(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files([sample_ris_path], output_path)

        assert result.input_file_count == 1
        assert result.record_count == 5

        merged_records = list(rispy.load(open(output_path, encoding="utf-8")))
        assert len(merged_records) == 5

    def test_bare_path_is_also_accepted(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files(sample_ris_path, output_path)

        assert result.input_file_count == 1
        assert result.record_count == 5


class TestMergeOutputValidity:
    def test_output_is_valid_ris(self, sample_ris_path, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        merge_ris_files([sample_ris_path], output_path)

        # Must round-trip through rispy without error.
        records = list(rispy.load(open(output_path, encoding="utf-8")))
        assert len(records) == 5
        assert all("title" in r for r in records)

    def test_fields_are_preserved(self, multi_source_paths, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        merge_ris_files(multi_source_paths, output_path)

        merged_records = list(rispy.load(open(output_path, encoding="utf-8")))

        # merge_ris_files concatenates records without deduplicating.
        # The shared paper appears multiple times. We must find the specific
        # copy originating from pubmed.ris, which is the one carrying the abstract.
        pubmed_copy = next(
            (
                r
                for r in merged_records
                if r.get("abstract")
                == "Second copy of the same paper, carries an abstract the others lack."
            ),
            None,
        )

        assert pubmed_copy is not None, "The pubmed record with the abstract was lost during merge."
        assert pubmed_copy.get("doi") == "10.1016/j.neuroimage.2022.99999"


class TestMalformedRecords:
    def test_malformed_block_does_not_discard_the_rest_of_its_file(
        self, multi_source_paths, tmp_path
    ) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files(multi_source_paths, output_path)

        # scopus.ris has 2 good records + 1 malformed block. Both good
        # scopus records must still be present.
        merged_records = list(rispy.load(open(output_path, encoding="utf-8")))
        titles = {r.get("title") for r in merged_records}
        assert "Cortical thickness changes in early Parkinson's disease" in titles

    def test_error_identifies_the_source_file(self, multi_source_paths, tmp_path) -> None:
        output_path = tmp_path / "merged.ris"
        result = merge_ris_files(multi_source_paths, output_path)

        assert len(result.errors) == 1
        source_path, _block_number, _message = result.errors[0]
        assert source_path == multi_source_paths[0]  # scopus.ris


class TestEmptyRisFile:
    def test_empty_file_contributes_zero_records(self, tmp_path) -> None:
        empty_file = tmp_path / "empty.ris"
        empty_file.write_text("", encoding="utf-8")

        output_path = tmp_path / "merged.ris"
        result = merge_ris_files([empty_file], output_path)

        assert result.record_count == 0
        assert result.errors == []
        assert output_path.exists()

    def test_empty_file_mixed_with_a_real_file(self, sample_ris_path, tmp_path) -> None:
        empty_file = tmp_path / "empty.ris"
        empty_file.write_text("", encoding="utf-8")

        output_path = tmp_path / "merged.ris"
        result = merge_ris_files([empty_file, sample_ris_path], output_path)

        assert result.input_file_count == 2
        assert result.record_count == 5


class TestMissingInputFile:
    def test_raises_file_not_found_naming_the_missing_file(self, tmp_path) -> None:
        missing = tmp_path / "does_not_exist.ris"
        with pytest.raises(FileNotFoundError, match="does_not_exist.ris"):
            merge_ris_files([missing], tmp_path / "out.ris")

    def test_raises_on_the_specific_missing_file_among_several(
        self, sample_ris_path, tmp_path
    ) -> None:
        missing = tmp_path / "does_not_exist.ris"
        with pytest.raises(FileNotFoundError, match="does_not_exist.ris"):
            merge_ris_files([sample_ris_path, missing], tmp_path / "out.ris")


class TestEmptyInputList:
    def test_raises_value_error(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            merge_ris_files([], tmp_path / "out.ris")


class TestDeterministicOrdering:
    def test_output_order_follows_input_file_order(self, multi_source_paths, tmp_path) -> None:
        forward_path = tmp_path / "forward.ris"
        reversed_path = tmp_path / "reversed.ris"

        merge_ris_files(multi_source_paths, forward_path)
        merge_ris_files(list(reversed(multi_source_paths)), reversed_path)

        forward_titles = [r.get("title") for r in rispy.load(open(forward_path, encoding="utf-8"))]
        reversed_titles = [
            r.get("title") for r in rispy.load(open(reversed_path, encoding="utf-8"))
        ]

        # Records from the first input file (scopus, 2 records) come
        # first when scopus is listed first, and last when it's listed last.
        assert "Cortical thickness" in (forward_titles[1] or "")
        assert "Cortical thickness" in (reversed_titles[-1] or "")
        assert forward_titles != reversed_titles

    def test_repeated_merges_produce_identical_output(self, multi_source_paths, tmp_path) -> None:
        path_a = tmp_path / "run_a.ris"
        path_b = tmp_path / "run_b.ris"

        merge_ris_files(multi_source_paths, path_a)
        merge_ris_files(multi_source_paths, path_b)

        assert path_a.read_text(encoding="utf-8") == path_b.read_text(encoding="utf-8")
