"""Command-line interface for risforge.

This is where the original scripts' "just run me directly" behavior
now lives, generalized into three subcommands so a single installed
``risforge`` command replaces having three separate scripts each
hardcoding its own paths:

    risforge clean input.ris output_clean.ris
    risforge enrich input.ris output_enriched.ris --email you@example.com
    risforge pipeline input.ris --email you@example.com
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from risforge.cleaning import clean_ris_file
from risforge.enrichment import RisEnricher
from risforge.pipeline import run_pipeline

logger = logging.getLogger("risforge")


def _configure_logging(verbose: bool) -> None:
    """Configure logging for CLI usage only.

    Library modules never do this themselves (see the module
    docstrings in :mod:`risforge.cleaning` and
    :mod:`risforge.enrichment`) -- only the CLI entry point, which is
    the one context where it's actually risforge's call to make.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug-level logging."
    )


def _cmd_clean(args: argparse.Namespace) -> int:
    try:
        records, errors = clean_ris_file(args.input, args.output)
    except FileNotFoundError as error:
        logger.error("%s", error)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        logger.error("Cleaning failed: %s", error)
        return 1

    logger.info("Successfully processed %d unique records.", len(records))
    return 1 if errors and args.strict else 0


def _cmd_enrich(args: argparse.Namespace) -> int:
    try:
        enricher = RisEnricher(email=args.email, cache_name=args.cache_name)
        stats = enricher.enrich_file(
            input_path=args.input,
            output_path=args.output,
            fail_report_path=args.fail_report,
        )
    except (OSError, ValueError, RuntimeError) as error:
        logger.error("Enrichment failed: %s", error)
        return 1

    logger.info("Enriched %d/%d records.", stats["enriched"], stats["processed"])
    return 0


def _cmd_pipeline(args: argparse.Namespace) -> int:
    dedup_path = args.dedup_output or _default_sibling(args.input, "_clean")
    enriched_path = args.output or _default_sibling(args.input, "_enriched")

    try:
        result = run_pipeline(
            input_path=args.input,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email=args.email,
            fail_report_path=args.fail_report,
        )
    except FileNotFoundError as error:
        logger.error("Input file missing: %s", error)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        logger.error("Pipeline failed: %s", error)
        return 1

    logger.info(
        "Pipeline finished: %d cleaned records, %d/%d enriched.",
        result.cleaned_record_count,
        result.enrichment_stats.get("enriched", 0),
        result.enrichment_stats.get("processed", 0),
    )
    return 0


def _default_sibling(input_path: str | Path, suffix: str) -> Path:
    path = Path(input_path)
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser (exposed for testing/docs)."""
    parser = argparse.ArgumentParser(
        prog="risforge",
        description="Clean, deduplicate, and enrich RIS bibliographic files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    clean_parser = subparsers.add_parser(
        "clean", help="Deduplicate and normalize a RIS file."
    )
    clean_parser.add_argument("input", help="Input RIS file path.")
    clean_parser.add_argument("output", help="Output cleaned RIS file path.")
    clean_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with a non-zero status if any records failed to parse.",
    )
    _add_common_args(clean_parser)
    clean_parser.set_defaults(func=_cmd_clean)

    enrich_parser = subparsers.add_parser(
        "enrich", help="Enrich a RIS file with metadata from scholarly APIs."
    )
    enrich_parser.add_argument("input", help="Input RIS file path.")
    enrich_parser.add_argument("output", help="Output enriched RIS file path.")
    enrich_parser.add_argument(
        "--email",
        required=True,
        help="Contact email for Crossref/OpenAlex/Unpaywall polite-pool access.",
    )
    enrich_parser.add_argument(
        "--fail-report",
        dest="fail_report",
        default="failed_records.json",
        help="Where to write unresolved-DOI records (default: %(default)s).",
    )
    enrich_parser.add_argument(
        "--cache-name",
        dest="cache_name",
        default=".api_cache",
        help="Base filename for the on-disk HTTP response cache.",
    )
    _add_common_args(enrich_parser)
    enrich_parser.set_defaults(func=_cmd_enrich)

    pipeline_parser = subparsers.add_parser(
        "pipeline", help="Run clean then enrich in one step."
    )
    pipeline_parser.add_argument("input", help="Input RIS file path.")
    pipeline_parser.add_argument(
        "--email",
        required=True,
        help="Contact email for Crossref/OpenAlex/Unpaywall polite-pool access.",
    )
    pipeline_parser.add_argument(
        "--dedup-output",
        dest="dedup_output",
        default=None,
        help="Path for the intermediate cleaned file (default: <input>_clean.ris).",
    )
    pipeline_parser.add_argument(
        "--output",
        default=None,
        help="Path for the final enriched file (default: <input>_enriched.ris).",
    )
    pipeline_parser.add_argument(
        "--fail-report",
        dest="fail_report",
        default="failed_records.json",
        help="Where to write unresolved-DOI records (default: %(default)s).",
    )
    _add_common_args(pipeline_parser)
    pipeline_parser.set_defaults(func=_cmd_pipeline)

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point (registered as the ``risforge`` console script)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
