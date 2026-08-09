"""Orchestrates the clean -> enrich pipeline for a RIS file.

This is a generalization of the original ``help.py``. The workflow is
identical (clean/dedupe, then enrich), but two things changed:

1. File paths are now parameters instead of hardcoded to a specific
   machine's ``/home/<user>/Desktop`` -- a package published to PyPI
   has to run on other people's filesystems.
2. It's a plain importable function returning a result object, with
   :mod:`risforge.cli` providing the "run this as a script with these
   fixed paths" behavior that ``help.py`` used to hardcode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from risforge.cleaning import clean_ris_file
from risforge.enrichment import RisEnricher

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Outcome of a full clean+enrich pipeline run."""

    cleaned_record_count: int
    cleaning_errors: list[tuple[int, str]]
    enrichment_stats: dict[str, Any] = field(default_factory=dict)


def run_pipeline(
    input_path: str | Path,
    dedup_path: str | Path,
    enriched_path: str | Path,
    email: str,
    fail_report_path: str | Path = "failed_records.json",
) -> PipelineResult:
    """Run the two-phase clean -> enrich pipeline end to end.

    Args:
        input_path: Raw ``.ris`` export to process.
        dedup_path: Where the cleaned/deduplicated intermediate file
            is written.
        enriched_path: Where the final enriched ``.ris`` file is
            written.
        email: Contact email passed to Crossref/OpenAlex/Unpaywall
            (required by their usage policies).
        fail_report_path: Where a JSON report of unresolved records is
            written, if any.

    Returns:
        A :class:`PipelineResult` summarizing both phases.

    Raises:
        FileNotFoundError: If ``input_path`` does not exist.
    """
    logger.info("Starting RIS bibliographic pipeline...")

    logger.info("Phase 1: Deduplicating %s", input_path)
    records, errors = clean_ris_file(input_path, dedup_path)
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
    )
