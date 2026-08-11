# risforge

**Clean, deduplicate, and enrich RIS bibliographic files for systematic reviews.**

`risforge` takes one or more raw `.ris` exports from Scopus, Web of
Science, PubMed, EndNote, or any other reference manager and:

1. **Merges** them (if there's more than one) — combining every
   record from every source file into one file, records intact,
   duplicates untouched.
2. **Cleans & deduplicates** it — normalizing titles, DOIs, and author
   names, then clustering duplicate records (by exact DOI, and by a
   title + first-author fallback) and merging each cluster into one
   complete, data-loss-free record.
3. **Enriches** it — filling in missing abstracts, journal names,
   volumes/issues/pages, ISSNs, keywords, and open-access PDF links by
   querying [Crossref](https://www.crossref.org/), [OpenAlex](https://openalex.org/),
   [Semantic Scholar](https://www.semanticscholar.org/), and
   [Unpaywall](https://unpaywall.org/). Existing fields are never
   overwritten — only gaps are filled.

These are three distinct operations, and it's worth being precise
about what each one does and doesn't do:

| Stage | Does | Does not |
|---|---|---|
| **merge** | Combine records from multiple files into one | Decide whether two records are the same paper |
| **clean** | Deduplicate, and merge each duplicate cluster's metadata | Add any new information from outside the file |
| **enrich** | Fill in *missing* metadata from external APIs | Overwrite metadata you already have |

It's built for the kind of unglamorous but essential prep work that
comes before title/abstract screening in a systematic review: getting
one clean, complete, deduplicated `.ris` file out of a pile of messy,
overlapping database exports — whether that's one export or several.

## Features

- **Multi-source merging** — combine exports from Scopus, PubMed, Web
  of Science, and any other source into one file before deduplicating,
  either as a standalone step or automatically as part of the pipeline.
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
- **Optional desktop GUI** — a cross-platform PySide6 app (`risforge-gui`)
  for drag-and-drop use, with no command line required.

## Installation

```bash
pip install risforge
```

Requires Python 3.10+.

There's also an optional desktop GUI, for researchers who'd rather not use
the command line:

```bash
pip install "risforge[gui]"
risforge-gui
```

It's a thin PySide6 interface over this same package -- see
[docs/gui.md](docs/gui.md) for the full walkthrough. The base install above
never pulls in GUI dependencies.

## Quick start

### Command line

```bash
# Clean and deduplicate only
risforge clean raw_export.ris clean.ris

# Enrich an already-clean file
risforge enrich clean.ris enriched.ris --email you@example.com

# One file, clean -> enrich in one call
risforge pipeline raw_export.ris --email you@example.com
```

#### Merging multiple sources

```bash
# Merge only -- combines records, does NOT deduplicate or enrich
risforge merge scopus.ris pubmed.ris wos.ris merged.ris

# Then deduplicate the merged file separately, if you want to inspect
# the merged-but-not-deduplicated file first
risforge clean merged.ris clean.ris
```

Or let the pipeline do all three steps automatically — merge, then
clean, then enrich — when you give it more than one input file:

```bash
risforge pipeline \
    scopus.ris \
    pubmed.ris \
    wos.ris \
    --email you@example.com \
    --output final.ris
```

A single input file skips the merge step entirely, exactly like the
one-file case above — no intermediate merged file is created. With
multiple inputs, an intermediate merged file *is* created (by default,
`merged.ris` alongside the other outputs); control its location
explicitly with `--merge-output` if you want it somewhere specific:

```bash
risforge pipeline a.ris b.ris c.ris \
    --merge-output merged.ris \
    --dedup-output clean.ris \
    --output enriched.ris \
    --email you@example.com
```

The `pipeline` subcommand writes `<input>_clean.ris` and
`<input>_enriched.ris` next to your input file by default for a single
input, or `clean.ris` / `enriched.ris` next to the first input for
multiple inputs (since there's no single input filename to derive a
sensible default from); pass `--dedup-output` / `--output` to control
that explicitly.

An email address is required by Crossref, OpenAlex, and Unpaywall's
"polite pool" usage policies — it's sent as a contact address in your
requests, never stored or transmitted anywhere else.

### Python API

```python
from risforge import risforge

# One file: clean -> enrich, no merge step.
result = risforge(
    input_paths="raw_export.ris",
    dedup_path="clean.ris",
    enriched_path="enriched.ris",
    email="you@example.com",
)

# Several files: merge -> clean -> enrich, automatically.
result = risforge(
    input_paths=[
        "scopus.ris",
        "pubmed.ris",
        "wos.ris",
    ],
    dedup_path="clean.ris",
    enriched_path="enriched.ris",
    email="you@example.com",
)

print(result.input_file_count)       # 3
print(result.merged_record_count)    # e.g. 9000, before deduplication
print(result.cleaned_record_count)   # e.g. 6200, after deduplication
print(result.enrichment_stats)       # {'processed': 6200, 'enriched': 5800, ...}
```

The three stages are also directly usable on their own, if you'd
rather run them individually or inspect the intermediate files:

```python
from risforge import merge_ris_files, clean_ris_file, RisEnricher

# Merge only -- no deduplication happens here.
merge_result = merge_ris_files(
    ["scopus.ris", "pubmed.ris", "wos.ris"], "merged.ris"
)
print(merge_result.record_count)  # e.g. 9000 -- duplicates still present

# Clean/deduplicate the merged file.
records, errors = clean_ris_file("merged.ris", "clean.ris")
print(len(records))  # e.g. 6200 -- duplicates collapsed

# Enrich the cleaned file.
enricher = RisEnricher(email="you@example.com")
stats = enricher.enrich_file("clean.ris", "enriched.ris")
print(f"Enriched {stats['enriched']}/{stats['processed']} records")
```

> `run_pipeline()` (the pre-0.2.0 name, single file only) still works
> unchanged and is kept for backward compatibility. New code should
> prefer `risforge()`, which accepts everything `run_pipeline()` did,
> plus multiple input files.

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
- **My merged file has way more records than I expected** — that's
  expected too. `merge_ris_files()` (and the merge step inside
  `risforge()`) never deduplicates; if the same paper is in three of
  your source files, it appears three times in the merged output.
  Run `clean_ris_file()` (or let the pipeline continue to its clean
  phase) to collapse duplicates.

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
