"""Minimal example: clean, then enrich, a RIS export.

Run from the repo root with a real .ris file:

    python examples/basic_usage.py raw_export.ris you@example.com
"""

from __future__ import annotations

import sys

from risforge import run_pipeline


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <input.ris> <contact_email>")
        raise SystemExit(1)

    input_path, email = sys.argv[1], sys.argv[2]

    result = run_pipeline(
        input_path=input_path,
        dedup_path="clean.ris",
        enriched_path="enriched.ris",
        email=email,
    )

    print(f"Cleaned records: {result.cleaned_record_count}")
    print(f"Parse errors: {len(result.cleaning_errors)}")
    print(
        f"Enriched: {result.enrichment_stats['enriched']}/{result.enrichment_stats['processed']}"
    )


if __name__ == "__main__":
    main()
