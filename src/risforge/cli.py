"""Command-line interface for risforge.

This is where the original scripts' "just run me directly" behavior
now lives, generalized into subcommands so a single installed
``risforge`` command replaces having three separate scripts each
hardcoding its own paths:

    risforge merge scopus.ris pubmed.ris wos.ris merged.ris
    risforge clean input.ris output_clean.ris
    risforge enrich input.ris output_enriched.ris --email you@example.com
    risforge pipeline input.ris --email you@example.com
    risforge pipeline scopus.ris pubmed.ris wos.ris --email you@example.com --output final.ris

``merge`` only combines files (no dedup, no enrichment).
``pipeline`` accepts one or more input files; with more than one, it
merges them automatically before cleaning and enriching -- there's no
need to run ``merge`` separately first unless you want the merged
file itself.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from risforge.cleaning import clean_ris_file
from risforge.enrichment import RisEnricher
from risforge.merging import merge_ris_files
from risforge.pipeline import risforge

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


def _cmd_merge(args: argparse.Namespace) -> int:
    try:
        result = merge_ris_files(args.inputs, args.output)
    except (ValueError, FileNotFoundError) as error:
        logger.error("%s", error)
        return 1
    except (OSError, RuntimeError) as error:
        logger.error("Merge failed: %s", error)
        return 1

    logger.info(
        "Merged %d record(s) from %d file(s) into %s.",
        result.record_count,
        result.input_file_count,
        result.output_path,
    )
    return 1 if result.errors and args.strict else 0


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
    inputs: list[str] = args.inputs

    if len(inputs) > 1:
        dedup_path = args.dedup_output or _default_multi_output(inputs, "clean.ris")
        enriched_path = args.output or _default_multi_output(inputs, "enriched.ris")
        merge_path = args.merge_output  # None is fine -- risforge() applies its own default.
    else:
        dedup_path = args.dedup_output or _default_sibling(inputs[0], "_clean")
        enriched_path = args.output or _default_sibling(inputs[0], "_enriched")
        merge_path = None  # Unused: a single input never triggers a merge step.

    try:
        result = risforge(
            input_paths=inputs,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email=args.email,
            merge_path=merge_path,
            fail_report_path=args.fail_report,
        )
    except FileNotFoundError as error:
        logger.error("Input file missing: %s", error)
        return 1
    except (OSError, ValueError, RuntimeError) as error:
        logger.error("Pipeline failed: %s", error)
        return 1

    if result.merge_path is not None:
        logger.info(
            "Merged %d input file(s) into %d record(s) at %s before deduplication.",
            result.input_file_count,
            result.merged_record_count,
            result.merge_path,
        )
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


def _default_multi_output(inputs: list[str], filename: str) -> Path:
    """Deterministic default output path when the pipeline has multiple inputs.

    Deliberately does not derive from any single input's filename
    (see :func:`risforge.pipeline._default_merge_path` for the same
    reasoning) -- it places a fixed, descriptive filename next to the
    first input file instead.
    """
    return Path(inputs[0]).parent / filename


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser (exposed for testing/docs)."""
    parser = argparse.ArgumentParser(
        prog="risforge",
        description="Merge, clean, deduplicate, and enrich RIS bibliographic files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Combine multiple RIS files into one. Does NOT deduplicate or enrich.",
    )
    merge_parser.add_argument(
        "inputs",
        nargs="+",
        help="Two or more input RIS file paths to combine (a single file is also accepted).",
    )
    merge_parser.add_argument("output", help="Output merged RIS file path.")
    merge_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with a non-zero status if any records failed to parse.",
    )
    _add_common_args(merge_parser)
    merge_parser.set_defaults(func=_cmd_merge)

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
        "pipeline",
        help="Run merge (if multiple inputs) then clean then enrich in one step.",
    )
    pipeline_parser.add_argument(
        "inputs",
        nargs="+",
        help=(
            "One or more input RIS files. A single file skips merging; "
            "two or more are merged automatically before deduplication."
        ),
    )
    pipeline_parser.add_argument(
        "--email",
        required=True,
        help="Contact email for Crossref/OpenAlex/Unpaywall polite-pool access.",
    )
    pipeline_parser.add_argument(
        "--merge-output",
        dest="merge_output",
        default=None,
        help=(
            "Path for the intermediate merged file, used only when multiple "
            "inputs are given (default: merged.ris next to the dedup output)."
        ),
    )
    pipeline_parser.add_argument(
        "--dedup-output",
        dest="dedup_output",
        default=None,
        help=(
            "Path for the intermediate cleaned file (default: <input>_clean.ris "
            "for a single input, clean.ris next to the first input for multiple)."
        ),
    )
    pipeline_parser.add_argument(
        "--output",
        default=None,
        help=(
            "Path for the final enriched file (default: <input>_enriched.ris "
            "for a single input, enriched.ris next to the first input for multiple)."
        ),
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
