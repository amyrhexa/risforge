# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-10

### Added
- **Multi-file support**: `risforge.merging` is a new module with
  `merge_ris_files()`, which combines two or more `.ris` files into
  one. Merging is strictly separate from deduplication — it never
  decides whether two records describe the same paper; it just
  concatenates every record from every input, in order. Run
  `clean_ris_file()` on the result to deduplicate.
- `risforge()` — the new preferred pipeline entry point (named after
  the package). Accepts either a single input file (behaves exactly
  like the 0.1.x pipeline: clean, then enrich, no merge step) or
  multiple input files (merge, then clean, then enrich, automatically).
- `risforge merge` CLI subcommand — merge-only, no dedup, no enrichment:
  `risforge merge scopus.ris pubmed.ris wos.ris merged.ris`.
- `risforge pipeline` now accepts one or more input files:
  `risforge pipeline scopus.ris pubmed.ris wos.ris --email you@example.com --output final.ris`.
  A new `--merge-output` flag controls where the intermediate merged
  file is written for multi-input runs.
- `PipelineResult` gained `input_file_count`, `merged_record_count`,
  `merge_path`, `dedup_path`, and `enriched_path` fields, all with
  defaults so existing code reading/constructing `PipelineResult` is
  unaffected.
- `risforge.cleaning.parse_ris_records()` — the block-by-block RIS
  parsing logic that was previously inlined in `clean_ris_file()`
  is now a standalone, reusable function. `merge_ris_files()` uses it
  too, so both modules tolerate malformed records identically. No
  behavior change to `clean_ris_file()` itself.
- Test fixtures under `tests/fixtures/multi_source/` (scopus/pubmed/wos-style
  files sharing one duplicate paper with different completeness levels)
  and 41 new tests covering merging, the multi-input pipeline, and
  backward compatibility.

### Changed
- Nothing about existing single-file behavior changed. A single-input
  call to `risforge()` (or `run_pipeline()`) produces byte-identical
  output to the 0.1.x pipeline — no merge step runs, no intermediate
  merged file is created.

### Backward compatibility
- `run_pipeline()` is retained with its exact original signature
  (`input_path=`, singular) and behavior, for existing 0.1.x callers —
  including the keyword-argument call shape documented in the 0.1.0
  README. It's implemented as a thin wrapper around `risforge()`
  rather than a bare `run_pipeline = risforge` alias, specifically
  *because* `risforge()` renamed its own first parameter to
  `input_paths` (plural) to reflect that it now accepts multiple
  files — a bare alias would have silently broken any caller using
  `run_pipeline(input_path=...)` as a keyword argument.
- `PipelineResult`'s original three fields (`cleaned_record_count`,
  `cleaning_errors`, `enrichment_stats`) keep their original names,
  types, and field order, so both attribute access and positional
  construction from 0.1.x code continue to work.
- No changes to the deduplication algorithm, the enrichment providers,
  or RIS normalization rules.

## [0.1.0] - 2026-08-09

### Added
- Initial public release, packaging the original `clean_ris.py`,
  `enrich_ris.py`, and `help.py` scripts as an installable library +
  CLI (`risforge`).
- `risforge.clean_ris_file()` — DOI and title+author based
  deduplication with union-find clustering and non-destructive record
  merging.
- `risforge.RisEnricher` — metadata enrichment via Crossref, OpenAlex,
  Semantic Scholar, and Unpaywall, with HTTP response caching and
  retry/backoff.
- `risforge.run_pipeline()` — runs cleaning then enrichment in one
  call.
- `risforge` console script with `clean`, `enrich`, and `pipeline`
  subcommands.

### Changed
- File paths are now function/CLI arguments instead of being
  hardcoded to a specific machine (the original `help.py` hardcoded
  `/home/amyr/Desktop/...` paths).
- Library modules no longer call `logging.basicConfig()` or attach
  handlers at import time; only the CLI entry point configures
  logging. This was a bug for library use: importing the original
  modules silently reconfigured the root logger for any application
  that imported them.

### Notes
- No dedup/merge/enrichment logic changed. This release is a
  structural and packaging change, not a rewrite of the underlying
  algorithms.

