"""Example: combine several database exports into one enriched RIS file.

Run from the repo root with real .ris files:

    python examples/multi_source_pipeline.py you@example.com \\
        scopus.ris pubmed.ris wos.ris

Demonstrates both the all-in-one pipeline call and running merge/clean
as separate, inspectable steps.
"""

from __future__ import annotations

import sys

from risforge import clean_ris_file, merge_ris_files, risforge


def run_full_pipeline(email: str, input_paths: list[str]) -> None:
    """Merge, clean, and enrich in a single call."""
    result = risforge(
        input_paths=input_paths,
        dedup_path="clean.ris",
        enriched_path="enriched.ris",
        email=email,
        merge_path="merged.ris",  # optional: omit to use the default location
    )

    print(f"Input files: {result.input_file_count}")
    print(f"Merged records (duplicates included): {result.merged_record_count}")
    print(f"Unique records after cleaning: {result.cleaned_record_count}")
    print(f"Enriched: {result.enrichment_stats['enriched']}/{result.enrichment_stats['processed']}")


def run_steps_separately(email: str, input_paths: list[str]) -> None:
    """The same result, one stage at a time -- useful for inspecting
    the merged-but-not-yet-deduplicated file, e.g. to sanity-check how
    many records came from each source before cleaning collapses them.
    """
    merge_result = merge_ris_files(input_paths, "merged.ris")
    print(f"Merged {merge_result.record_count} records from {merge_result.input_file_count} files.")

    records, errors = clean_ris_file("merged.ris", "clean.ris")
    print(f"{len(records)} unique records after deduplication ({len(errors)} parse errors).")

    from risforge import RisEnricher

    stats = RisEnricher(email=email).enrich_file("clean.ris", "enriched.ris")
    print(f"Enriched {stats['enriched']}/{stats['processed']} records.")


def main() -> None:
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <contact_email> <input1.ris> [input2.ris ...]")
        raise SystemExit(1)

    email, input_paths = sys.argv[1], sys.argv[2:]
    run_full_pipeline(email, input_paths)


if __name__ == "__main__":
    main()
