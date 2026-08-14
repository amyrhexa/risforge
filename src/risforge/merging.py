"""Combine multiple RIS files into a single RIS file.

This module has exactly one responsibility: concatenating every record
from every input file into one output file, in input order. It
deliberately does **not** deduplicate (that's
:func:`risforge.cleaning.clean_ris_file`'s job) and does **not**
enrich (that's :class:`risforge.enrichment.RisEnricher`'s job). If the
same paper appears in three input files, it appears three times in
this module's output -- by design. See the intended pipeline order in
:func:`risforge.pipeline.risforge`:

    merge_ris_files() -> clean_ris_file() -> RisEnricher.enrich_file()

Parsing is delegated to :func:`risforge.cleaning.parse_ris_records`,
so merging tolerates malformed individual records exactly the way
cleaning does: a bad block in one input file is skipped and reported,
never treated as a reason to drop that file's other records, or any
other input file's records.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import rispy

from risforge.cleaning import RisRecord, _CleanRisWriter, parse_ris_records

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Outcome of merging one or more RIS files into one.

    Attributes:
        input_file_count: Number of input files merged.
        record_count: Total number of records written to the merged
            output (the sum of successfully parsed records across all
            inputs -- duplicates across or within files are *not*
            collapsed here).
        errors: ``(source_path, block_number, message)`` triples for
            any malformed blocks skipped, across all input files.
        output_path: Where the merged ``.ris`` file was written.
    """

    input_file_count: int
    record_count: int
    errors: list[tuple[Path, int, str]] = field(default_factory=list)
    output_path: Path = field(default_factory=Path)


def merge_ris_files(
    input_paths: str | Path | Sequence[str | Path],
    output_path: str | Path,
) -> MergeResult:
    """Combine one or more RIS files into a single RIS file.

    Every record from every input is preserved, in input order.
    Duplicates across (or within) files are intentionally *not*
    removed -- run :func:`risforge.cleaning.clean_ris_file` on the
    result for that. This function does not modify record contents at
    all, so any custom or unrecognized RIS tags that ``rispy`` parsed
    into a record's ``unknown_tag`` mapping pass through untouched.

    Args:
        input_paths: One or more source ``.ris`` files, merged in the
            order given. A single path (bare, or as a one-item
            sequence) is accepted too -- in that case the file is
            effectively normalized/rewritten through rispy with no
            records added or removed.
        output_path: Where the combined ``.ris`` file is written.

    Returns:
        A :class:`MergeResult` summarizing the operation.

    Raises:
        ValueError: If ``input_paths`` is empty.
        FileNotFoundError: If any input file does not exist. The
            error message identifies which file was missing.
    """
    if isinstance(input_paths, (str, Path)):
        input_paths = [input_paths]

    paths = [Path(p) for p in input_paths]
    if not paths:
        raise ValueError("merge_ris_files() requires at least one input path.")

    output_path = Path(output_path)

    all_records: list[RisRecord] = []
    all_errors: list[tuple[Path, int, str]] = []

    for path in paths:
        logger.info("Reading %s...", path)
        # parse_ris_records raises FileNotFoundError naming this exact
        # path if it's missing, so callers always know which input failed.
        records, errors = parse_ris_records(path)

        if errors:
            logger.warning(
                "Encountered %d malformed record block(s) in %s, skipped.",
                len(errors),
                path,
            )
        all_errors.extend((path, block_number, message) for block_number, message in errors)
        all_records.extend(records)
        logger.info("%s: %d record(s) parsed.", path, len(records))

    logger.info("--- MERGE SUMMARY ---")
    logger.info("Input files: %d", len(paths))
    logger.info("Total records merged: %d", len(all_records))
    logger.info("Malformed records skipped: %d", len(all_errors))
    logger.info("Output saved to: %s", output_path)
    logger.info("---------------------")

    out_text = rispy.dumps(all_records, implementation=_CleanRisWriter)
    output_path.write_text(out_text, encoding="utf-8")

    return MergeResult(
        input_file_count=len(paths),
        record_count=len(all_records),
        errors=all_errors,
        output_path=output_path,
    )
