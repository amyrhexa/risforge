from __future__ import annotations

from risforge.cli import build_parser


class TestBuildParser:
    def test_clean_subcommand_parses(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["clean", "in.ris", "out.ris"])
        assert args.command == "clean"
        assert args.input == "in.ris"
        assert args.output == "out.ris"

    def test_enrich_requires_email(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["enrich", "in.ris", "out.ris", "--email", "you@example.com"]
        )
        assert args.email == "you@example.com"

    def test_pipeline_defaults_are_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["pipeline", "in.ris", "--email", "you@example.com"])
        assert args.dedup_output is None
        assert args.output is None


class TestCleanCommandExecution:
    def test_clean_command_runs_against_fixture(self, sample_ris_path, tmp_path) -> None:
        parser = build_parser()
        output_path = tmp_path / "clean.ris"
        args = parser.parse_args(["clean", str(sample_ris_path), str(output_path)])

        exit_code = args.func(args)

        assert exit_code == 0
        assert output_path.exists()
