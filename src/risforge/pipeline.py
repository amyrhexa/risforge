"""Orchestrates the merge (optional) -> clean -> enrich pipeline.

This is a generalization of the original ``help.py``. The core
workflow is unchanged (clean/dedupe, then enrich), but it now also
accepts *multiple* input files:

    one input   -> clean_ris_file() -> RisEnricher.enrich_file()
    2+ inputs   -> merge_ris_files() -> clean_ris_file() -> RisEnricher.enrich_file()

The merge step only happens for multiple inputs -- a single input goes
straight to cleaning, exactly like the original single-file pipeline,
with no intermediate merged file created.

Public API
----------
:func:`risforge` is the preferred entry point (named after the
package, per the desired public API). :func:`run_pipeline` is kept as
a plain backward-compatible alias/wrapper for existing callers of the
pre-0.2.0 API -- including callers who used the original
``input_path=`` keyword argument, which :func:`risforge` renamed to
``input_paths`` to reflect that it now accepts more than one file.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from risforge.cleaning import clean_ris_file
from risforge.enrichment import RisEnricher
from risforge.merging import MergeResult, merge_ris_files

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Outcome of a full merge(optional) -> clean -> enrich pipeline run.

    The first three fields (``cleaned_record_count``,
    ``cleaning_errors``, ``enrichment_stats``) are unchanged from the
    pre-0.2.0 release -- existing code reading those attributes, or
    constructing a ``PipelineResult`` positionally with just those
    three values, continues to work unmodified. The remaining fields
    are additive.
    """

    cleaned_record_count: int
    cleaning_errors: list[tuple[int, str]]
    enrichment_stats: dict[str, Any] = field(default_factory=dict)

    # Added in 0.2.0 for multi-input pipelines. All have safe defaults
    # so existing positional/keyword construction is unaffected.
    input_file_count: int = 1
    merged_record_count: int | None = None
    merge_path: Path | None = None
    dedup_path: Path | None = None
    enriched_path: Path | None = None


def _normalize_input_paths(
    input_paths: str | Path | Sequence[str | Path],
) -> list[Path]:
    """Coerce the flexible ``input_paths`` argument into a concrete path list."""
    if isinstance(input_paths, (str, Path)):
        return [Path(input_paths)]

    paths = [Path(p) for p in input_paths]
    if not paths:
        raise ValueError("risforge() requires at least one input path.")
    return paths


def _default_merge_path(dedup_path: str | Path) -> Path:
    """Default location for the intermediate merged file.

    Deliberately does not derive from any single input file's name --
    with several different sources being combined, a name like
    ``scopus_merged.ris`` would misleadingly suggest the merge only
    covers that one source. Instead it's placed next to ``dedup_path``
    with a fixed, descriptive name.
    """
    return Path(dedup_path).with_name("merged.ris")


def risforge(
    input_paths: str | Path | Sequence[str | Path],
    dedup_path: str | Path,
    enriched_path: str | Path,
    email: str,
    merge_path: str | Path | None = None,
    fail_report_path: str | Path = "failed_records.json",
) -> PipelineResult:
    """Run the full merge(optional) -> clean -> enrich pipeline end to end.

    Given a single input file, this behaves exactly like the original
    single-file pipeline: clean, then enrich, no merge step. Given two
    or more input files, they're first combined with
    :func:`risforge.merging.merge_ris_files` into an intermediate file,
    which is then cleaned and enriched exactly as a single input would
    be.

    Args:
        input_paths: One raw ``.ris`` export, or several. A bare path,
            or a sequence of one path, skips merging entirely.
        dedup_path: Where the cleaned/deduplicated intermediate file
            is written.
        enriched_path: Where the final enriched ``.ris`` file is
            written.
        email: Contact email passed to Crossref/OpenAlex/Unpaywall
            (required by their usage policies).
        merge_path: Where the intermediate merged file is written,
            when multiple inputs are given. Defaults to a ``merged.ris``
            file next to ``dedup_path`` (see :func:`_default_merge_path`).
            Ignored for a single input, since no merge step runs.
        fail_report_path: Where a JSON report of unresolved records is
            written, if any.

    Returns:
        A :class:`PipelineResult` summarizing every phase that ran.

    Raises:
        ValueError: If ``input_paths`` is empty.
        FileNotFoundError: If any input file does not exist. The
            error message identifies which one.
    """
    paths = _normalize_input_paths(input_paths)
    dedup_path = Path(dedup_path)
    enriched_path = Path(enriched_path)

    logger.info("Starting RIS bibliographic pipeline...")

    merge_result: MergeResult | None = None
    if len(paths) > 1:
        resolved_merge_path = (
            Path(merge_path) if merge_path is not None else _default_merge_path(dedup_path)
        )
        logger.info("Phase 0: Merging %d input files into %s", len(paths), resolved_merge_path)
        merge_result = merge_ris_files(paths, resolved_merge_path)
        logger.info(
            "Phase 0 complete: merged %d record(s) from %d file(s).",
            merge_result.record_count,
            merge_result.input_file_count,
        )
        clean_input: str | Path = resolved_merge_path
    else:
        clean_input = paths[0]

    logger.info("Phase 1: Deduplicating %s", clean_input)
    records, errors = clean_ris_file(clean_input, dedup_path)
    logger.info("Phase 1 complete: generated %d clean records.", len(records))
    if errors:
        logger.warning("Encountered %d parsing errors during Phase 1.", len(errors))

    logger.info("Phase 2: Initializing metadata enrichment via APIs")
    enricher = RisEnricher(email=email)
    stats = enricher.enrich_file(
        input_path=dedup_path,
        output_path=enriched_path,
        fail_report_path=fail_report_path,
    )
    logger.info(
        "Phase 2 complete: enriched %d/%d records.",
        stats.get("enriched", 0),
        stats.get("processed", 0),
    )

    logger.info("Pipeline execution finished successfully.")
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
    """Backward-compatible alias for :func:`risforge` (pre-0.2.0 API).

    Retained unchanged -- same parameter name (``input_path``,
    singular), same single-file-only behavior -- for existing code
    written against the 0.1.x release. New code should prefer
    :func:`risforge`, which accepts this same single-file call exactly
    as before, or multiple files.
    """
    return risforge(
        input_paths=input_path,
        dedup_path=dedup_path,
        enriched_path=enriched_path,
        email=email,
        fail_report_path=fail_report_path,
    )
