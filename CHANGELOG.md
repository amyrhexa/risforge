# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

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
