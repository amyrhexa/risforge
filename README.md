# risforge

**Clean, deduplicate, and enrich RIS bibliographic files for systematic reviews.**

`risforge` takes a raw `.ris` export from Scopus, Web of Science, PubMed,
EndNote, or any other reference manager and:

1. **Cleans & deduplicates** it — normalizing titles, DOIs, and author
   names, then clustering duplicate records (by exact DOI, and by a
   title + first-author fallback) and merging each cluster into one
   complete, data-loss-free record.
2. **Enriches** it — filling in missing abstracts, journal names,
   volumes/issues/pages, ISSNs, keywords, and open-access PDF links by
   querying [Crossref](https://www.crossref.org/), [OpenAlex](https://openalex.org/),
   [Semantic Scholar](https://www.semanticscholar.org/), and
   [Unpaywall](https://unpaywall.org/). Existing fields are never
   overwritten — only gaps are filled.

It's built for the kind of unglamorous but essential prep work that
comes before title/abstract screening in a systematic review: getting
one clean, complete, deduplicated `.ris` file out of a pile of messy,
overlapping database exports.

## Features

- **DOI-first deduplication** with a normalized title + first-author
  fallback for records that lack a DOI, using union-find clustering so
  transitively-linked duplicates across three, four, or more sources
  all collapse into one record.
- **Zero data loss on merge** — the most complete record in a
  duplicate cluster is used as the base, and every other record in the
  cluster supplements it with whatever fields it's missing.
- **Non-destructive enrichment** — only empty fields are filled;
  anything you (or an upstream export) already populated is left
  alone.
- **Resilient HTTP** — automatic retries with exponential backoff on
  429/5xx responses, and a 7-day on-disk response cache so re-running
  a pipeline doesn't re-hit the same APIs for records you've already
  enriched.
- **Library or CLI** — use it as `import risforge` in a script/notebook,
  or as a single `risforge` command.

## Installation

```bash
pip install risforge
```

Requires Python 3.10+.

## Quick start

### Command line

```bash
# Clean and deduplicate only
risforge clean raw_export.ris clean.ris

# Enrich an already-clean file
risforge enrich clean.ris enriched.ris --email you@example.com

# Both steps in one call
risforge pipeline raw_export.ris --email you@example.com
```

The `pipeline` subcommand writes `<input>_clean.ris` and
`<input>_enriched.ris` next to your input file by default; pass
`--dedup-output` / `--output` to control that explicitly.

An email address is required by Crossref, OpenAlex, and Unpaywall's
"polite pool" usage policies — it's sent as a contact address in your
requests, never stored or transmitted anywhere else.

### Python API

```python
from risforge import clean_ris_file, RisEnricher, run_pipeline

# Clean + deduplicate only
records, errors = clean_ris_file("raw_export.ris", "clean.ris")
print(f"{len(records)} unique records, {len(errors)} parse errors")

# Enrich only
enricher = RisEnricher(email="you@example.com")
stats = enricher.enrich_file("clean.ris", "enriched.ris")
print(f"Enriched {stats['enriched']}/{stats['processed']} records")

# Both, in one call
result = run_pipeline(
    input_path="raw_export.ris",
    dedup_path="clean.ris",
    enriched_path="enriched.ris",
    email="you@example.com",
)
print(result.cleaned_record_count, result.enrichment_stats)
```

## Configuration

`RisEnricher` accepts a few constructor arguments beyond `email`:

```python
RisEnricher(
    email="you@example.com",
    cache_name=".api_cache",   # base filename for the on-disk HTTP cache
    session=None,              # inject your own requests.Session (mainly for testing)
)
```

`enrich_file()` also accepts `fail_report_path` (where unresolved-DOI
records are written as JSON) and `request_delay_seconds` (delay
between records; defaults to 0.1s to stay within provider rate limits).

## Troubleshooting

- **"Unresolved DOI via Title Matching" in the failure report** — the
  record had no DOI and its title didn't match any Crossref result
  above the 90% similarity threshold closely enough to resolve one.
  These records are returned unmodified rather than guessed at.
- **Enrichment seems slow** — each record makes up to 5 API calls
  (1 for DOI resolution if needed, 4 for metadata) with a small delay
  between records. Re-running against the same input is fast, since
  responses are cached for 7 days.
- **A field I already had got left alone even though enrichment "ran"** —
  that's intentional. Enrichment only fills empty fields; it never
  overwrites existing data.

## Contributing

1. Clone the repo and install in editable mode with dev dependencies:
   ```bash
   pip install -e ".[dev]"
   ```
2. Run the test suite:
   ```bash
   pytest
   ```
3. Open a PR. Please include tests for any behavioral change, and note
   any deduplication/merge/enrichment logic changes explicitly in
   `CHANGELOG.md` — this package's core value is *predictability* for
   systematic review workflows, so silent behavior changes are treated
   as bugs.

## License

MIT — see [LICENSE](LICENSE).
