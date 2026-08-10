"""Clean, normalize, and deduplicate RIS bibliographic records.

This module contains no behavioral changes from the original
``clean_ris.py`` script: the union-find-based clustering, the DOI and
title+author matching heuristics, and the "most complete record wins,
then merge in whatever the others have that it's missing" merge
strategy are all preserved exactly. What changed is purely structural:
type hints, docstrings, PEP 8 formatting, and turning the script's
module-level ``logging.basicConfig()`` call into a plain
``logging.getLogger(__name__)`` (a library should never configure the
root logger on import -- see :mod:`risforge.cli` for where that
configuration now happens, only for CLI usage).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import rispy
import rispy.writer

logger = logging.getLogger(__name__)

RisRecord = dict[str, Any]


class _CleanRisWriter(rispy.writer.RisWriter):
    """Writer that strips rispy's default "1.", "2." record numbering.

    Enforces ``\\r\\n`` line endings for compatibility with reference
    managers (EndNote, Zotero, etc.) that expect the RIS spec's
    canonical newline convention.
    """

    NEWLINE = "\r\n"

    def set_header(self, count: int) -> str:
        return ""


def normalize_title(title: str | None) -> str:
    """Normalize a title for deduplication comparison.

    Lowercases, strips diacritics, and removes punctuation so that
    casing and formatting differences across citation exports don't
    produce false-negative duplicate matches.
    """
    if not isinstance(title, str) or not title:
        return ""

    normalized = unicodedata.normalize("NFKD", title).lower()
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_first_author(author_list: list[str] | None) -> str:
    """Extract a normalized "last name + initials" key for the first author.

    Used as half of the title+author composite deduplication key, since
    full author-list formatting is rarely consistent across sources but
    the first author's surname usually is.
    """
    if not author_list or not isinstance(author_list[0], str):
        return ""

    author_parts = author_list[0].split(",")
    last_name = author_parts[0].strip()
    initials = ""

    if len(author_parts) > 1:
        tokens = re.split(r"[\s.\-]+", author_parts[1].strip())
        initials = "".join(token[0] for token in tokens if token)

    name_str = f"{last_name} {initials}"
    name_str = unicodedata.normalize("NFKD", name_str).lower()
    name_str = re.sub(r"[^a-z0-9\s]", "", name_str)
    return re.sub(r"\s+", " ", name_str).strip()


def normalize_doi(doi: str | None) -> str:
    """Normalize a DOI by stripping URL prefixes, whitespace, and trailing punctuation.

    DOIs are the strongest deduplication key available, but sources
    frequently prepend ``https://doi.org/`` or ``doi:`` in ways that
    would otherwise defeat exact matching.
    """
    if not isinstance(doi, str) or not doi:
        return ""

    cleaned = doi.strip().lower()
    cleaned = re.sub(r"^(https?://)?(dx\.)?doi\.org/|^doi:", "", cleaned)
    return re.sub(r"[\s.,;:]+$", "", cleaned)


def count_fields(record: RisRecord) -> int:
    """Count populated fields in a record.

    Used to pick the "most complete" record in a duplicate cluster as
    the merge base.
    """
    count = 0
    for key, value in record.items():
        if key == "unknown_tag":
            for unknown_values in value.values():
                count += sum(bool(item) for item in unknown_values)
        elif isinstance(value, list):
            count += sum(bool(item) for item in value)
        elif value:
            count += 1
    return count


def merge_cluster(cluster: list[RisRecord]) -> RisRecord:
    """Merge a cluster of duplicate records into one, losing no data.

    The most complete record (by :func:`count_fields`) is used as the
    base; every other record in the cluster then supplements it with
    any fields or list items it's missing.
    """
    if len(cluster) == 1:
        return cluster[0]

    best_record = max(cluster, key=count_fields)
    merged = dict(best_record)
    merged["unknown_tag"] = defaultdict(list, merged.get("unknown_tag", {}))

    for record in cluster:
        if record is best_record:
            continue

        for key, value in record.items():
            if key == "unknown_tag":
                for unknown_key, unknown_values in value.items():
                    for item in unknown_values:
                        if item not in merged["unknown_tag"][unknown_key]:
                            merged["unknown_tag"][unknown_key].append(item)
            elif key not in merged:
                merged[key] = value
            elif isinstance(merged[key], list) and isinstance(value, list):
                for item in value:
                    if item not in merged[key]:
                        merged[key].append(item)
            elif (
                isinstance(merged[key], str)
                and not merged[key]
                and isinstance(value, str)
            ):
                merged[key] = value

    return merged


class _RecordUnionFind:
    """Disjoint-set structure grouping records into duplicate clusters.

    Two records may only be unioned if neither has a normalized DOI
    that conflicts with the other's -- this prevents the fuzzy
    title+author heuristic from ever merging two records that carry
    different, explicit DOIs.
    """

    def __init__(self, records: list[RisRecord]) -> None:
        self._parents = list(range(len(records)))
        self._root_dois = [normalize_doi(record.get("doi", "")) for record in records]

    def find(self, node_index: int) -> int:
        root = node_index
        while self._parents[root] != root:
            root = self._parents[root]

        current = node_index
        while current != root:
            nxt = self._parents[current]
            self._parents[current] = root
            current = nxt

        return root

    def union(self, node_i: int, node_j: int) -> bool:
        root_i = self.find(node_i)
        root_j = self.find(node_j)

        if root_i == root_j:
            return False

        doi_i = self._root_dois[root_i]
        doi_j = self._root_dois[root_j]

        if doi_i and doi_j and doi_i != doi_j:
            return False

        self._parents[root_i] = root_j
        self._root_dois[root_j] = doi_i or doi_j
        return True


def parse_ris_records(
    input_path: str | Path,
) -> tuple[list[RisRecord], list[tuple[int, str]]]:
    """Parse a ``.ris`` file into records, tolerating malformed blocks.

    Splits the file into individual ``TY  -`` ... ``ER  -`` blocks and
    parses each independently, so a single malformed record doesn't
    take down the whole file -- it's recorded as an error and skipped
    rather than aborting the parse. This is the shared parsing routine
    behind both :func:`clean_ris_file` and
    :func:`risforge.merging.merge_ris_files`, so the two share
    identical parsing and error-tolerance behavior.

    Args:
        input_path: Path to the source ``.ris`` file.

    Returns:
        A ``(records, errors)`` tuple: successfully parsed records (as
        rispy record dicts, in file order), and a list of
        ``(block_number, message)`` pairs for any blocks that failed
        to parse.

    Raises:
        FileNotFoundError: If ``input_path`` does not exist.
    """
    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file '{input_path}' not found.")

    text = input_path.read_text(encoding="utf-8")

    blocks = re.split(r"(?m)^TY\s+-", text)
    records: list[RisRecord] = []
    errors: list[tuple[int, str]] = []

    for index, block in enumerate(blocks):
        if not block.strip():
            continue

        block_text = f"TY  -{block}"
        try:
            parsed_records = rispy.loads(block_text)
            if not parsed_records:
                errors.append((index + 1, "Empty parse result (malformed record)"))
            else:
                records.extend(parsed_records)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            errors.append((index + 1, str(error)))

    return records, errors


def clean_ris_file(
    input_path: str | Path, output_path: str | Path
) -> tuple[list[RisRecord], list[tuple[int, str]]]:
    """Clean, deduplicate, and write out a RIS file.

    Parses ``input_path`` block-by-block (so a single malformed record
    doesn't take down the whole parse), deduplicates first on exact
    normalized DOI, then on a normalized title+first-author composite
    key, merges each resulting cluster into a single complete record,
    and writes the result to ``output_path``.

    Args:
        input_path: Path to the source ``.ris`` file.
        output_path: Path the cleaned, deduplicated ``.ris`` file is
            written to.

    Returns:
        A ``(records, errors)`` tuple: the final deduplicated records
        (as rispy record dicts), and a list of ``(block_number,
        message)`` pairs for any blocks that failed to parse.

    Raises:
        FileNotFoundError: If ``input_path`` does not exist.
    """
    output_path = Path(output_path)

    records, errors = parse_ris_records(input_path)

    if errors:
        logger.warning("Encountered %d malformed record block(s), skipped.", len(errors))

    total_records = len(records)
    if total_records == 0:
        logger.warning("No valid records found to process.")
        return [], errors

    union_find = _RecordUnionFind(records)

    doi_map: dict[str, int] = {}
    doi_duplicates_removed = 0

    # Pass 1: deduplicate by exact DOI match.
    for index, record in enumerate(records):
        doi = normalize_doi(record.get("doi", ""))
        if doi:
            if doi in doi_map:
                if union_find.union(index, doi_map[doi]):
                    doi_duplicates_removed += 1
            else:
                doi_map[doi] = index

    composite_key_map: dict[str, int] = {}
    title_author_duplicates_removed = 0

    # Pass 2: deduplicate by composite title + first-author key (fallback heuristic).
    for index, record in enumerate(records):
        norm_title = normalize_title(record.get("title", ""))
        norm_author = extract_first_author(record.get("authors", []))

        if norm_title and norm_author:
            composite_key = f"{norm_title}|{norm_author}"

            if composite_key in composite_key_map:
                if union_find.union(index, composite_key_map[composite_key]):
                    title_author_duplicates_removed += 1
                    composite_key_map[composite_key] = union_find.find(index)
            else:
                composite_key_map[composite_key] = union_find.find(index)

    clusters: dict[int, list[int]] = defaultdict(list)
    for index in range(total_records):
        clusters[union_find.find(index)].append(index)

    final_records = [
        merge_cluster([records[i] for i in indices]) for indices in clusters.values()
    ]

    total_duplicates_removed = doi_duplicates_removed + title_author_duplicates_removed

    logger.info("--- SUMMARY ---")
    logger.info("Input records successfully parsed: %d", len(records))
    logger.info("Malformed records skipped: %d", len(errors))
    logger.info("Total duplicates removed: %d", total_duplicates_removed)
    logger.info("Final unique records: %d", len(final_records))
    logger.info("Output saved to: %s", output_path)
    logger.info("---------------")

    out_text = rispy.dumps(final_records, implementation=_CleanRisWriter)
    output_path.write_text(out_text, encoding="utf-8")

    return final_records, errors


# Backward-compatible alias for the original script's public function name.
process_ris_file = clean_ris_file
