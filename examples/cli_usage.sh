#!/usr/bin/env bash
# Example CLI sessions for risforge.
set -euo pipefail

EMAIL="you@example.com"

# --- Single source -----------------------------------------------------

INPUT="raw_export.ris"

# Step 1: clean and deduplicate
risforge clean "$INPUT" clean.ris

# Step 2: enrich with metadata from Crossref/OpenAlex/Semantic Scholar/Unpaywall
risforge enrich clean.ris enriched.ris --email "$EMAIL"

# Or, equivalently, both steps in one command:
# risforge pipeline "$INPUT" --email "$EMAIL"

# --- Multiple sources ----------------------------------------------------

# Merge only -- combines records from all three files, does NOT
# deduplicate or enrich. Useful if you want to inspect the merged file
# before deciding how to clean it.
risforge merge scopus.ris pubmed.ris wos.ris merged.ris
risforge clean merged.ris clean_from_merge.ris

# Or let the pipeline merge, clean, and enrich automatically in one step:
risforge pipeline scopus.ris pubmed.ris wos.ris \
    --email "$EMAIL" \
    --output final.ris

# With explicit control over every intermediate file:
risforge pipeline scopus.ris pubmed.ris wos.ris \
    --merge-output merged.ris \
    --dedup-output clean.ris \
    --output enriched.ris \
    --email "$EMAIL"
