"""Cleaning, normalization, and deduplication for RIS records."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import rispy
import rispy.writer

from risforge.exceptions import RisParsingError

logger = logging.getLogger(__name__)

RisRecord = dict[str, Any]

_RECORD_START = re.compile(r"(?m)^TY\s+-")


class CleanRisWriter(rispy.writer.RisWriter):
    """RIS writer without record numbering and with CRLF line endings."""

    NEWLINE = "\r\n"

    def set_header(self, count: int) -> str:
        return ""


_CleanRisWriter = CleanRisWriter


def normalize_title(title: str | None) -> str:
    """Normalize a title for deduplication comparison."""
    if not isinstance(title, str) or not title:
        return ""

    normalized = unicodedata.normalize("NFKD", title).lower()
    normalized = re.sub(r"[^a-z0-9\s]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_first_author(author_list: list[str] | None) -> str:
    """Extract a normalized first-author key: surname plus initials."""
    if not author_list or not isinstance(author_list[0], str):
        return ""

    parts = author_list[0].split(",")
    last_name = parts[0].strip()

    initials = ""
    if len(parts) > 1:
        tokens = re.split(r"[\s.\-]+", parts[1].strip())
        initials = "".join(token[0] for token in tokens if token)

    name = f"{last_name} {initials}"
    name = unicodedata.normalize("NFKD", name).lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_doi(doi: str | None) -> str:
    """Normalize a DOI by removing URL prefixes and trailing punctuation."""
    if not isinstance(doi, str) or not doi:
        return ""

    cleaned = doi.strip().lower()
    cleaned = re.sub(r"^(https?://)?(dx\.)?doi\.org/|^doi:", "", cleaned)
    return re.sub(r"[\s.,;:]+$", "", cleaned)


def count_fields(record: RisRecord) -> int:
    """Count populated fields in a record."""
    total = 0

    for key, value in record.items():
        if key == "unknown_tag":
            for values in value.values():
                total += sum(bool(item) for item in values)
        elif isinstance(value, list):
            total += sum(bool(item) for item in value)
        elif value:
            total += 1

    return total


def _copy_record(record: RisRecord) -> RisRecord:
    """Copy a record deeply enough for safe cluster merging."""
    copied: RisRecord = {}

    for key, value in record.items():
        if key == "unknown_tag":
            copied[key] = defaultdict(
                list,
                {tag: list(items) for tag, items in value.items()},
            )
        elif isinstance(value, list):
            copied[key] = list(value)
        else:
            copied[key] = value

    return copied


def merge_cluster(cluster: list[RisRecord]) -> RisRecord:
    """Merge duplicate records into one record without losing fields."""
    if len(cluster) == 1:
        return cluster[0]

    best = max(cluster, key=count_fields)
    merged = _copy_record(best)

    unknown = merged.get("unknown_tag")
    if unknown is None:
        unknown = defaultdict(list)
        merged["unknown_tag"] = unknown

    for record in cluster:
        if record is best:
            continue

        for key, value in record.items():
            if key == "unknown_tag":
                for tag, items in value.items():
                    target = unknown.setdefault(tag, [])
                    for item in items:
                        if item not in target:
                            target.append(item)
            elif key not in merged or not merged[key]:
                merged[key] = list(value) if isinstance(value, list) else value
            elif isinstance(merged[key], list) and isinstance(value, list):
                for item in value:
                    if item not in merged[key]:
                        merged[key].append(item)

    return merged


class RecordUnionFind:
    """Disjoint-set structure for clustering duplicate records."""

    def __init__(self, records: list[RisRecord]) -> None:
        self._parents = list(range(len(records)))
        self._root_dois = [normalize_doi(record.get("doi", "")) for record in records]

    def find(self, index: int) -> int:
        root = index
        while self._parents[root] != root:
            root = self._parents[root]

        current = index
        while current != root:
            next_index = self._parents[current]
            self._parents[current] = root
            current = next_index

        return root

    def union(self, first: int, second: int) -> bool:
        root_first = self.find(first)
        root_second = self.find(second)

        if root_first == root_second:
            return False

        doi_first = self._root_dois[root_first]
        doi_second = self._root_dois[root_second]

        if doi_first and doi_second and doi_first != doi_second:
            return False

        self._parents[root_first] = root_second
        self._root_dois[root_second] = doi_first or doi_second
        return True


_RecordUnionFind = RecordUnionFind


def _read_ris_text(input_path: Path) -> str:
    """Read a RIS file as UTF-8 text, stripping a BOM if present."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file '{input_path}' not found.")

    try:
        return input_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise RisParsingError(
            f"Could not read '{input_path}' as UTF-8 text. "
            "The file may be saved in a different encoding; re-save it as UTF-8."
        ) from error


def parse_ris_records(
    input_path: str | Path,
) -> tuple[list[RisRecord], list[tuple[int, str]]]:
    """Parse RIS records block by block, tolerating malformed blocks."""
    input_path = Path(input_path)
    text = _read_ris_text(input_path)

    records: list[RisRecord] = []
    errors: list[tuple[int, str]] = []

    for block_number, block in enumerate(_RECORD_START.split(text), start=1):
        if not block.strip():
            continue

        block_text = f"TY  -{block}"

        try:
            parsed = rispy.loads(block_text)
        except (ValueError, TypeError, KeyError, AttributeError, IndexError) as error:
            errors.append((block_number, str(error)))
            continue

        if parsed:
            records.extend(parsed)
        else:
            errors.append((block_number, "Empty parse result"))

    return records, errors


def write_ris_records(records: list[RisRecord], output_path: str | Path) -> None:
    """Write records to disk using the project's canonical RIS writer."""
    output_path = Path(output_path)
    text = rispy.dumps(records, implementation=CleanRisWriter)
    output_path.write_text(text, encoding="utf-8")


def clean_ris_file(
    input_path: str | Path,
    output_path: str | Path,
) -> tuple[list[RisRecord], list[tuple[int, str]]]:
    """Clean, deduplicate, and write a RIS file."""
    input_path = Path(input_path)
    output_path = Path(output_path)

    records, errors = parse_ris_records(input_path)

    if errors:
        logger.warning("Skipped %d malformed record block(s) in %s.", len(errors), input_path)

    if not records:
        logger.warning("No valid records found in %s. Writing empty output.", input_path)
        write_ris_records([], output_path)
        return [], errors

    union_find = RecordUnionFind(records)

    doi_map: dict[str, int] = {}
    doi_duplicates_removed = 0

    for index, record in enumerate(records):
        doi = normalize_doi(record.get("doi", ""))
        if not doi:
            continue

        if doi in doi_map:
            if union_find.union(index, doi_map[doi]):
                doi_duplicates_removed += 1
        else:
            doi_map[doi] = index

    composite_key_map: dict[str, int] = {}
    title_author_duplicates_removed = 0

    for index, record in enumerate(records):
        title = normalize_title(record.get("title", ""))
        author = extract_first_author(record.get("authors", []))

        if not title or not author:
            continue

        composite_key = f"{title}|{author}"

        if composite_key in composite_key_map:
            if union_find.union(index, composite_key_map[composite_key]):
                title_author_duplicates_removed += 1
            composite_key_map[composite_key] = union_find.find(index)
        else:
            composite_key_map[composite_key] = union_find.find(index)

    clusters: dict[int, list[int]] = defaultdict(list)
    for index in range(len(records)):
        clusters[union_find.find(index)].append(index)

    final_records = [merge_cluster([records[i] for i in indices]) for indices in clusters.values()]

    write_ris_records(final_records, output_path)

    total_duplicates_removed = doi_duplicates_removed + title_author_duplicates_removed

    logger.info(
        "Deduplication complete: input=%d malformed=%d duplicates_removed=%d output=%s",
        len(records),
        len(errors),
        total_duplicates_removed,
        output_path,
    )

    return final_records, errors


# Backward-compatible alias.
process_ris_file = clean_ris_file
