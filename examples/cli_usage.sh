#!/usr/bin/env bash
# Example CLI session for risforge.
set -euo pipefail

INPUT="raw_export.ris"
EMAIL="you@example.com"

# Step 1: clean and deduplicate
risforge clean "$INPUT" clean.ris

# Step 2: enrich with metadata from Crossref/OpenAlex/Semantic Scholar/Unpaywall
risforge enrich clean.ris enriched.ris --email "$EMAIL"

# Or, equivalently, both steps in one command:
# risforge pipeline "$INPUT" --email "$EMAIL"
