"""Command-line interface for risforge."""

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
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug-level logging.",
    )


def _default_sibling(input_path: str | Path, suffix: str) -> Path:
    path = Path(input_path)
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def _default_multi_output(inputs: list[str], filename: str) -> Path:
    return Path(inputs[0]).parent / filename


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
    except FileNotFoundError as error:
        logger.error("%s", error)
        return 1
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
        merge_path = args.merge_output
    else:
        dedup_path = args.dedup_output or _default_sibling(inputs[0], "_clean")
        enriched_path = args.output or _default_sibling(inputs[0], "_enriched")
        merge_path = None

    try:
        result = risforge(
            input_paths=inputs,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email=args.email,
            merge_path=merge_path,
            fail_report_path=args.fail_report,
            cache_name=args.cache_name,
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


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="risforge",
        description="Merge, clean, deduplicate, and enrich RIS bibliographic files.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Combine multiple RIS files into one. Does NOT deduplicate or enrich.",
    )
    merge_parser.add_argument("inputs", nargs="+")
    merge_parser.add_argument("output")
    merge_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any records failed to parse.",
    )
    _add_common_args(merge_parser)
    merge_parser.set_defaults(func=_cmd_merge)

    clean_parser = subparsers.add_parser("clean", help="Deduplicate and normalize a RIS file.")
    clean_parser.add_argument("input")
    clean_parser.add_argument("output")
    clean_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any records failed to parse.",
    )
    _add_common_args(clean_parser)
    clean_parser.set_defaults(func=_cmd_clean)

    enrich_parser = subparsers.add_parser(
        "enrich",
        help="Enrich a RIS file with metadata from scholarly APIs.",
    )
    enrich_parser.add_argument("input")
    enrich_parser.add_argument("output")
    enrich_parser.add_argument("--email", required=True)
    enrich_parser.add_argument("--fail-report", default="failed_records.json")
    enrich_parser.add_argument("--cache-name", default=".api_cache")
    _add_common_args(enrich_parser)
    enrich_parser.set_defaults(func=_cmd_enrich)

    pipeline_parser = subparsers.add_parser(
        "pipeline",
        help="Run merge (if multiple inputs), clean, and enrich in one step.",
    )
    pipeline_parser.add_argument("inputs", nargs="+")
    pipeline_parser.add_argument("--email", required=True)
    pipeline_parser.add_argument("--merge-output", default=None)
    pipeline_parser.add_argument("--dedup-output", default=None)
    pipeline_parser.add_argument("--output", default=None)
    pipeline_parser.add_argument("--fail-report", default="failed_records.json")
    pipeline_parser.add_argument("--cache-name", default=".api_cache")
    _add_common_args(pipeline_parser)
    pipeline_parser.set_defaults(func=_cmd_pipeline)

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
