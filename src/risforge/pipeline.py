"""Pipeline orchestration: merge (optional), clean, enrich."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from risforge.cleaning import clean_ris_file
from risforge.enrichment import RisEnricher
from risforge.merging import MergeResult, merge_ris_files

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a full merge/clean/enrich pipeline run."""

    cleaned_record_count: int
    cleaning_errors: list[tuple[int, str]]
    enrichment_stats: dict[str, Any] = field(default_factory=dict)

    input_file_count: int = 1
    merged_record_count: int | None = None
    merge_path: Path | None = None
    dedup_path: Path | None = None
    enriched_path: Path | None = None


def _normalize_input_paths(
    input_paths: str | Path | Sequence[str | Path],
) -> list[Path]:
    """Convert flexible input-path arguments into a list of paths."""
    if isinstance(input_paths, (str, Path)):
        return [Path(input_paths)]

    paths = [Path(path) for path in input_paths]

    if not paths:
        raise ValueError("risforge() requires at least one input path.")

    return paths


def _default_merge_path(dedup_path: str | Path) -> Path:
    """Return the default merged-file path next to the cleaned file."""
    return Path(dedup_path).with_name("merged.ris")


def _notify_stage(callback: Callable[[str, str], None] | None, stage: str, status: str) -> None:
    if callback is not None:
        callback(stage, status)


def risforge(
    input_paths: str | Path | Sequence[str | Path],
    dedup_path: str | Path,
    enriched_path: str | Path,
    email: str,
    merge_path: str | Path | None = None,
    fail_report_path: str | Path = "failed_records.json",
    on_stage: Callable[[str, str], None] | None = None,
    enrichment_progress: Callable[[int, int], None] | None = None,
    cache_name: str | Path | None = None,
) -> PipelineResult:
    """Run merge (if needed), clean, and enrich in one pipeline."""
    paths = _normalize_input_paths(input_paths)
    dedup_path = Path(dedup_path)
    enriched_path = Path(enriched_path)

    logger.info("Starting RIS pipeline with %d input file(s).", len(paths))

    merge_result: MergeResult | None = None

    if len(paths) > 1:
        resolved_merge_path = (
            Path(merge_path) if merge_path is not None else _default_merge_path(dedup_path)
        )

        _notify_stage(on_stage, "merge", "started")
        merge_result = merge_ris_files(paths, resolved_merge_path)
        _notify_stage(on_stage, "merge", "completed")

        clean_input: Path = resolved_merge_path
    else:
        clean_input = paths[0]

    _notify_stage(on_stage, "clean", "started")
    records, errors = clean_ris_file(clean_input, dedup_path)
    _notify_stage(on_stage, "clean", "completed")

    if errors:
        logger.warning("Cleaning completed with %d parse error(s).", len(errors))

    _notify_stage(on_stage, "enrich", "started")

    enricher = RisEnricher(email=email, cache_name=cache_name or ".api_cache")
    stats = enricher.enrich_file(
        input_path=dedup_path,
        output_path=enriched_path,
        fail_report_path=fail_report_path,
        progress_callback=enrichment_progress,
    )

    _notify_stage(on_stage, "enrich", "completed")

    logger.info(
        "Pipeline complete: cleaned=%d enriched=%d/%d",
        len(records),
        stats.get("enriched", 0),
        stats.get("processed", 0),
    )

    return PipelineResult(
        cleaned_record_count=len(records),
        cleaning_errors=errors,
        enrichment_stats=stats,
        input_file_count=len(paths),
        merged_record_count=merge_result.record_count if merge_result else None,
        merge_path=merge_result.output_path if merge_result else None,
        dedup_path=dedup_path,
        enriched_path=enriched_path,
    )


def run_pipeline(
    input_path: str | Path,
    dedup_path: str | Path,
    enriched_path: str | Path,
    email: str,
    fail_report_path: str | Path = "failed_records.json",
) -> PipelineResult:
    """Backward-compatible single-file pipeline API."""
    return risforge(
        input_paths=input_path,
        dedup_path=dedup_path,
        enriched_path=enriched_path,
        email=email,
        fail_report_path=fail_report_path,
    )
