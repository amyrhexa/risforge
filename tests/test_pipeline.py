from __future__ import annotations

import pytest

from risforge import pipeline as pipeline_module
from risforge.enrichment import RisEnricher
from risforge.pipeline import PipelineResult, risforge, run_pipeline
from tests.test_enrichment import (
    CROSSREF_PAYLOAD,
    OPENALEX_PAYLOAD,
    SEMANTIC_SCHOLAR_PAYLOAD,
    UNPAYWALL_PAYLOAD,
    _MockSession,
)


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    """Run every test in this file from a scratch directory.

    Several tests call risforge()/run_pipeline() without an explicit
    fail_report_path, which defaults to a relative "failed_records.json".
    Without this, that file would land in whatever the pytest working
    directory happens to be (the repo root) instead of a throwaway
    tmp_path -- this keeps the repo clean regardless.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def mock_enrichment(monkeypatch):
    """Route every RisEnricher built inside risforge.pipeline through a mocked session.

    Reuses the exact mocked session/payloads from test_enrichment.py
    (per the project's testing convention: never touch the real
    network in tests) by monkeypatching the ``RisEnricher`` name that
    :mod:`risforge.pipeline` looks up, rather than adding a
    test-only constructor parameter to the public pipeline API.
    """
    session = _MockSession(
        {
            "api.crossref.org/works/10": CROSSREF_PAYLOAD,
            "api.openalex.org": OPENALEX_PAYLOAD,
            "api.semanticscholar.org": SEMANTIC_SCHOLAR_PAYLOAD,
            "api.unpaywall.org": UNPAYWALL_PAYLOAD,
        }
    )

    def _factory(email: str, **_kwargs) -> RisEnricher:
        return RisEnricher(email=email, session=session)

    monkeypatch.setattr(pipeline_module, "RisEnricher", _factory)
    return session


class TestMultiInputPipeline:
    def test_merges_cleans_and_enriches(
        self, multi_source_paths, mock_enrichment, tmp_path
    ) -> None:
        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"

        result = risforge(
            input_paths=multi_source_paths,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email="test@example.com",
        )

        # merge: 6 records in (2+2+2, one malformed block skipped).
        assert result.input_file_count == 3
        assert result.merged_record_count == 6
        assert result.merge_path is not None
        assert result.merge_path.exists()

        # clean: the shared paper collapses -> 4 unique records.
        assert result.cleaned_record_count == 4
        assert dedup_path.exists()

        # enrich: ran against the cleaned file.
        assert result.enrichment_stats["processed"] == 4
        assert enriched_path.exists()
        assert result.dedup_path == dedup_path
        assert result.enriched_path == enriched_path

    def test_merge_then_clean_collapses_duplicate_metadata_via_merge_cluster(
        self, multi_source_paths, mock_enrichment, tmp_path
    ) -> None:
        import rispy

        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"

        risforge(
            input_paths=multi_source_paths,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email="test@example.com",
        )

        cleaned_records = list(rispy.load(open(dedup_path, encoding="utf-8")))
        shared_paper = next(r for r in cleaned_records if "Tractography" in (r.get("title") or ""))
        # abstract came from pubmed.ris, keywords came from wos.ris --
        # merge_cluster() is what combines them into the one surviving record.
        assert shared_paper["abstract"] == (
            "Second copy of the same paper, carries an abstract the others lack."
        )
        assert shared_paper["keywords"] == [
            "diffusion MRI",
            "tractography",
            "deep learning",
        ]

    def test_enrichment_only_fills_missing_fields(
        self, multi_source_paths, mock_enrichment, tmp_path
    ) -> None:
        import rispy

        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"

        risforge(
            input_paths=multi_source_paths,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email="test@example.com",
        )

        enriched_records = list(rispy.load(open(enriched_path, encoding="utf-8")))
        shared_paper = next(r for r in enriched_records if "Tractography" in (r.get("title") or ""))
        # Kept from the original cleaned record, not overwritten by the
        # mocked Crossref payload's different title/journal:
        assert shared_paper["title"] == "Deep Learning for Diffusion MRI Tractography"
        # Filled in because it was missing after cleaning:
        assert shared_paper["abstract"] == (
            "Second copy of the same paper, carries an abstract the others lack."
        )


class TestSingleInputPipeline:
    def test_skips_merge_entirely(self, sample_ris_path, mock_enrichment, tmp_path) -> None:
        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"

        result = risforge(
            input_paths=sample_ris_path,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email="test@example.com",
        )

        assert result.input_file_count == 1
        assert result.merged_record_count is None
        assert result.merge_path is None
        assert result.cleaned_record_count == 3

    def test_single_item_list_also_skips_merge(
        self, sample_ris_path, mock_enrichment, tmp_path
    ) -> None:
        result = risforge(
            input_paths=[sample_ris_path],
            dedup_path=tmp_path / "clean.ris",
            enriched_path=tmp_path / "enriched.ris",
            email="test@example.com",
        )

        assert result.merge_path is None

    def test_no_merged_file_written_to_disk(
        self, sample_ris_path, mock_enrichment, tmp_path
    ) -> None:
        risforge(
            input_paths=sample_ris_path,
            dedup_path=tmp_path / "clean.ris",
            enriched_path=tmp_path / "enriched.ris",
            email="test@example.com",
        )

        assert list(tmp_path.glob("*merged*")) == []


class TestPipelineResultBackwardCompatibility:
    def test_original_three_fields_still_construct_positionally(self) -> None:
        result = PipelineResult(3, [("1", "bad block")])
        assert result.cleaned_record_count == 3
        assert result.cleaning_errors == [("1", "bad block")]
        assert result.enrichment_stats == {}
        # New fields have sane defaults for old-style construction.
        assert result.input_file_count == 1
        assert result.merged_record_count is None


class TestRunPipelineBackwardCompatibility:
    def test_run_pipeline_still_works_with_original_keyword_names(
        self, sample_ris_path, mock_enrichment, tmp_path
    ) -> None:
        # Exact call shape documented in the pre-0.2.0 README.
        result = run_pipeline(
            input_path=sample_ris_path,
            dedup_path=tmp_path / "clean.ris",
            enriched_path=tmp_path / "enriched.ris",
            email="test@example.com",
        )
        assert result.cleaned_record_count == 3

    def test_run_pipeline_only_ever_accepts_a_single_file(self) -> None:
        import inspect

        signature = inspect.signature(run_pipeline)
        assert "input_path" in signature.parameters
        assert "input_paths" not in signature.parameters

    def test_risforge_is_the_preferred_new_name(self) -> None:
        import inspect

        signature = inspect.signature(risforge)
        assert "input_paths" in signature.parameters


class TestMissingInputRaises:
    def test_risforge_raises_file_not_found_for_missing_input(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            risforge(
                input_paths=tmp_path / "does_not_exist.ris",
                dedup_path=tmp_path / "clean.ris",
                enriched_path=tmp_path / "enriched.ris",
                email="test@example.com",
            )

    def test_risforge_raises_value_error_for_empty_input_list(self, tmp_path) -> None:
        with pytest.raises(ValueError):
            risforge(
                input_paths=[],
                dedup_path=tmp_path / "clean.ris",
                enriched_path=tmp_path / "enriched.ris",
                email="test@example.com",
            )
