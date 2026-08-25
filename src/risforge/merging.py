"""Merge multiple RIS files into one file without deduplication."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from risforge.cleaning import RisRecord, parse_ris_records, write_ris_records

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of merging one or more RIS files."""

    input_file_count: int
    record_count: int
    errors: list[tuple[Path, int, str]] = field(default_factory=list)
    output_path: Path = field(default_factory=Path)


def merge_ris_files(
    input_paths: str | Path | Sequence[str | Path],
    output_path: str | Path,
) -> MergeResult:
    """Combine RIS files into one output file.

    This does not deduplicate and does not enrich.
    """
    if isinstance(input_paths, (str, Path)):
        input_paths = [input_paths]

    paths = [Path(path) for path in input_paths]

    if not paths:
        raise ValueError("merge_ris_files() requires at least one input path.")

    output_path = Path(output_path)

    all_records: list[RisRecord] = []
    all_errors: list[tuple[Path, int, str]] = []

    for path in paths:
        logger.info("Reading %s", path)

        records, errors = parse_ris_records(path)

        if errors:
            logger.warning("Skipped %d malformed record block(s) in %s.", len(errors), path)

        all_errors.extend((path, block_number, message) for block_number, message in errors)
        all_records.extend(records)

        logger.debug("Parsed %d record(s) from %s.", len(records), path)

    write_ris_records(all_records, output_path)

    logger.info(
        "Merge complete: input_files=%d records=%d malformed_blocks=%d output=%s",
        len(paths),
        len(all_records),
        len(all_errors),
        output_path,
    )

    return MergeResult(
        input_file_count=len(paths),
        record_count=len(all_records),
        errors=all_errors,
        output_path=output_path,
    )
