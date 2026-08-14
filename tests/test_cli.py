from __future__ import annotations

import pytest

from risforge import cli as cli_module
from risforge.cli import build_parser
from risforge.enrichment import RisEnricher
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

    The `pipeline` CLI command defaults `--fail-report` to a relative
    "failed_records.json". Without this, that file would land in
    whatever the pytest working directory happens to be (the repo
    root) instead of a throwaway tmp_path.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def mock_enrichment(monkeypatch):
    """Route every RisEnricher built inside risforge.cli through a mocked session."""
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

    # Patch the RisEnricher looked up by risforge.pipeline, since
    # `risforge pipeline` delegates to risforge.pipeline.risforge().
    from risforge import pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module, "RisEnricher", _factory)
    monkeypatch.setattr(cli_module, "RisEnricher", _factory)
    return session


class TestBuildParser:
    def test_clean_subcommand_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["clean", "in.ris", "out.ris"])
        assert args.command == "clean"
        assert args.input == "in.ris"
        assert args.output == "out.ris"

    def test_enrich_requires_email(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["enrich", "in.ris", "out.ris", "--email", "you@example.com"])
        assert args.email == "you@example.com"

    def test_pipeline_defaults_are_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["pipeline", "in.ris", "--email", "you@example.com"])
        assert args.dedup_output is None
        assert args.output is None
        assert args.merge_output is None

    def test_pipeline_accepts_a_single_input(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["pipeline", "in.ris", "--email", "you@example.com"])
        assert args.inputs == ["in.ris"]

    def test_pipeline_accepts_multiple_inputs(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "pipeline",
                "scopus.ris",
                "pubmed.ris",
                "wos.ris",
                "--email",
                "you@example.com",
                "--output",
                "final.ris",
            ]
        )
        assert args.inputs == ["scopus.ris", "pubmed.ris", "wos.ris"]
        assert args.output == "final.ris"

    def test_merge_subcommand_parses_inputs_and_trailing_output(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["merge", "scopus.ris", "pubmed.ris", "wos.ris", "merged.ris"])
        assert args.command == "merge"
        assert args.inputs == ["scopus.ris", "pubmed.ris", "wos.ris"]
        assert args.output == "merged.ris"

    def test_merge_subcommand_accepts_a_single_input(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["merge", "one.ris", "out.ris"])
        assert args.inputs == ["one.ris"]
        assert args.output == "out.ris"

    def test_all_subcommands_are_registered(self) -> None:
        parser = build_parser()
        subparser_choices = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
        assert set(subparser_choices) == {"merge", "clean", "enrich", "pipeline"}


class TestCleanCommandExecution:
    def test_clean_command_runs_against_fixture(self, sample_ris_path, tmp_path) -> None:
        parser = build_parser()
        output_path = tmp_path / "clean.ris"
        args = parser.parse_args(["clean", str(sample_ris_path), str(output_path)])

        exit_code = args.func(args)

        assert exit_code == 0
        assert output_path.exists()


class TestMergeCommandExecution:
    def test_merge_command_combines_files_without_deduplicating(
        self, sample_ris_path, tmp_path
    ) -> None:
        parser = build_parser()
        output_path = tmp_path / "merged.ris"
        args = parser.parse_args(
            ["merge", str(sample_ris_path), str(sample_ris_path), str(output_path)]
        )

        exit_code = args.func(args)

        assert exit_code == 0
        assert output_path.exists()
        # 5 records in the fixture, twice, with no deduplication.
        assert output_path.read_text(encoding="utf-8").count("TY  - JOUR") == 10

    def test_merge_then_clean_end_to_end_via_cli(self, sample_ris_path, tmp_path) -> None:
        parser = build_parser()
        merged_path = tmp_path / "merged.ris"
        clean_path = tmp_path / "clean.ris"

        merge_args = parser.parse_args(
            ["merge", str(sample_ris_path), str(sample_ris_path), str(merged_path)]
        )
        assert merge_args.func(merge_args) == 0

        clean_args = parser.parse_args(["clean", str(merged_path), str(clean_path)])
        assert clean_args.func(clean_args) == 0
        assert clean_path.read_text(encoding="utf-8").count("TY  - JOUR") == 3

    def test_missing_input_returns_nonzero_exit_code(self, tmp_path) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["merge", str(tmp_path / "does_not_exist.ris"), str(tmp_path / "out.ris")]
        )
        assert args.func(args) == 1


class TestPipelineCommandExecution:
    def test_single_input_pipeline_runs(self, sample_ris_path, mock_enrichment, tmp_path) -> None:
        parser = build_parser()
        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"
        args = parser.parse_args(
            [
                "pipeline",
                str(sample_ris_path),
                "--email",
                "you@example.com",
                "--dedup-output",
                str(dedup_path),
                "--output",
                str(enriched_path),
            ]
        )

        exit_code = args.func(args)

        assert exit_code == 0
        assert dedup_path.exists()
        assert enriched_path.exists()

    def test_multi_input_pipeline_merges_automatically(
        self, multi_source_paths, mock_enrichment, tmp_path
    ) -> None:
        parser = build_parser()
        merge_path = tmp_path / "merged.ris"
        dedup_path = tmp_path / "clean.ris"
        enriched_path = tmp_path / "enriched.ris"
        args = parser.parse_args(
            [
                "pipeline",
                *[str(p) for p in multi_source_paths],
                "--email",
                "you@example.com",
                "--merge-output",
                str(merge_path),
                "--dedup-output",
                str(dedup_path),
                "--output",
                str(enriched_path),
            ]
        )

        exit_code = args.func(args)

        assert exit_code == 0
        assert merge_path.exists()
        assert dedup_path.exists()
        assert enriched_path.exists()
        # 6 merged -> 4 unique after dedup.
        assert dedup_path.read_text(encoding="utf-8").count("TY  - JOUR") == 4

    def test_multi_input_pipeline_uses_sensible_defaults_without_explicit_output(
        self, multi_source_paths, mock_enrichment, tmp_path
    ) -> None:
        # Copy fixtures into tmp_path so default output paths land somewhere writable.
        import shutil

        local_paths = []
        for source in multi_source_paths:
            dest = tmp_path / source.name
            shutil.copy(source, dest)
            local_paths.append(dest)

        parser = build_parser()
        args = parser.parse_args(
            [
                "pipeline",
                *[str(p) for p in local_paths],
                "--email",
                "you@example.com",
            ]
        )

        exit_code = args.func(args)

        assert exit_code == 0
        assert (tmp_path / "clean.ris").exists()
        assert (tmp_path / "enriched.ris").exists()

    def test_missing_input_returns_nonzero_exit_code(self, tmp_path) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "pipeline",
                str(tmp_path / "does_not_exist.ris"),
                "--email",
                "you@example.com",
            ]
        )
        assert args.func(args) == 1
