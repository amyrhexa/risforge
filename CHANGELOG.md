# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versioning follows [Semantic Versioning](https://semver.org/).

## [0.4.0] - 2026-08-25
### Changed
- Comprehensive codebase refactor: improved type hinting, modularized GUI widgets, and stabilized the test suite.
- Consolidated packaging into a single `risforge` PyPI package with an optional `[gui]` extra, replacing the split `risforge-gui` package.
- Unified RIS writer across merge, clean, and enrichment stages.

### Fixed
- Resolved DOI extraction regex capture group errors in enrichment.
- Fixed GUI worker thread silent failures when passing kwargs to the core pipeline.
- Corrected test fixture logic to properly validate multi-source merging and deterministic ordering.

## [0.3.3] - 2026-08-14

A non-functional clean-code audit pass across the whole codebase: naming,
documentation, logging, and formatting, with no intended behavior changes.
`ruff` and `black` (configured at a project-standard 100-char line length,
now pinned in `pyproject.toml`) were run across all of `src/` as an
objective check rather than relying on manual review alone; every change
below traces back to a real, tool- or hand-verified finding.

### Fixed
- **`risforge_gui/file_counter.py`**: `RecordCounter.run()` caught `OSError`
  but not `ValueError`, so a dropped/added file that fails to decode (see
  the `RisParsingError` handling added in 0.3.1) would raise uncaught on a
  `QThreadPool` worker thread -- its row would stay at "Counting..."
  forever with no visible error. Now also catches `ValueError`. Found
  during this audit, not previously reported; added a regression test that
  fails against the old code and passes against the fix.

### Changed (non-functional)
- Extracted a repeated magic number (`timeout=10`, five call sites) in
  `enrichment.py` into `REQUEST_TIMEOUT_SECONDS`.
- Renamed a handful of overly terse identifiers for clarity: `enrichment.py`
  (`c` &rarr; `concept`), `risforge_gui/theme.py` (`_build_stylesheet`'s `p`
  &rarr; `palette`, 40 call sites).
- `risforge_gui/app.py`: replaced a `print(..., file=sys.stderr)` with
  `logger.error(...)`; verified byte-identical stderr output via Python's
  default "last resort" log handler.
- `risforge_gui/worker.py`: replaced a nested ternary with an if/elif/else
  chain for the log-level mapping (readability only; verified an identical
  result for every possible log level).
- Removed two dead imports (`risforge_gui/worker.py`'s `typing.Any`,
  `risforge_gui/main_window.py`'s `PySide6.QtCore.Qt`), found via `ruff`.
- Added rationale-focused docstrings to the methods where the "why" wasn't
  already obvious from the name and signature (Qt model role-dispatch,
  drag/drop handlers, threaded worker entry points, stateful progress/log
  update methods) -- deliberately not added to ~30 trivial one-line
  property-style getters, to avoid restating the obvious.
- Reformatted `cleaning.py`, `cli.py`, `enrichment.py`, `merging.py`, and
  several GUI widget files to a consistent 100-character line width (the
  codebase's established but previously unenforced convention); no line's
  *content* changed, only wrapping.
- `risforge_gui/models.py`: kept `QModelIndex()` as a Qt-idiomatic default
  argument (this is the standard pattern from Qt's own Model/View
  documentation, not the mutable-default-argument bug a generic linter
  flags it as) and documented why, rather than "fixing" it away.

### Notes
- Evaluated three boolean-expression candidates for De Morgan's-law
  simplification (`cleaning.py`, `enrichment.py`, `main_window.py`) and
  left all three unchanged: each was already in its clearest form, and one
  (`main_window.py`'s overwrite-confirmation check) short-circuits a
  function with a real side effect (a modal dialog), where reordering the
  operands -- even via an equivalent-truth-table transform -- would risk
  changing when that dialog fires.

## [0.3.1] - 2026-08-12

### Fixed
- **Crash during enrichment**: `RisEnricher.enrich_file()` could raise
  `KeyError` (e.g. `KeyError: 'language'`) and abort the entire run when a
  RIS file contained a stray blank or otherwise non-tag-pattern line
  positioned early in a record. Root cause: a bug in `rispy` 0.10.0, where
  its parser tracks "the last tag seen" as state that persists *across
  record boundaries* within a single `rispy.load()` call — a malformed line
  at the start of one record could make it try to extend a field from the
  *previous* record onto the new (and therefore missing that key) record.
  Reproduces identically on every OS; it was not actually Windows-specific,
  though it was first reported there. `enrich_file()` now parses via
  `risforge.cleaning.parse_ris_records()` (already immune, since each
  record block gets an independent parser instance) instead of calling
  `rispy.load()` directly on the whole file. Malformed blocks are now
  tolerated and logged — exactly like `clean_ris_file()` already does —
  instead of aborting the run, and counted in a new `stats["skipped_malformed"]`.
- **UTF-8 BOM in RIS files** (common from Windows text editors) previously
  caused the first record's `TY` tag to go unrecognized, silently returning
  zero records with no error. Files are now read with `utf-8-sig`, which
  transparently strips a BOM if present and is a no-op otherwise.
- **Non-UTF-8 files** previously raised a raw `UnicodeDecodeError`. They now
  raise `RisParsingError` (a new use of an already-defined-but-previously-unused
  exception class) with a clear, actionable message naming the file. It's
  also a `ValueError` subclass, so every existing exception handler in the
  CLI, pipeline, and GUI worker already catches it correctly with no changes
  needed at those call sites.

### Changed (GUI)
- The results screen now shows a "Skipped (unreadable records)" row,
  visible only when that count is nonzero, so malformed input is visible to
  the user without cluttering the common case.

## [0.3.0] - 2026-08-11

### Added
- **Desktop GUI** (`risforge_gui`) — an optional PySide6 application for the
  full merge/clean/enrich workflow, installed via `pip install
  "risforge[gui]"` and launched with `risforge-gui`. It's a thin interface
  layer: every operation calls the same public `risforge` API the CLI uses
  (`risforge()`, `merge_ris_files()`, `clean_ris_file()`, `RisEnricher`) —
  no cleaning, merging, deduplication, or enrichment logic is duplicated in
  the GUI. Runs on Windows, macOS, and Linux.
  - Drag-and-drop `.ris` file input with asynchronous, non-blocking record
    counting.
  - Automatic workflow selection (merge+clean+enrich for multiple files,
    clean+enrich for one), plus standalone Merge/Clean/Enrich modes.
  - Threaded execution (`QThread`) with real-time per-stage progress,
    determinate enrichment progress (records processed/total), and an
    expandable activity log — the GUI never freezes during a run.
  - Human-readable error dialogs with expandable technical details; no raw
    tracebacks shown by default.
  - Non-destructive by default: original inputs are never modified, outputs
    always go to a new folder, and existing output files require an explicit
    overwrite confirmation.
  - Light/dark/system theming, centralized in one stylesheet module.

### Changed (core package, additive/backward-compatible)
- `RisEnricher.enrich_file()` gained an optional `progress_callback`
  parameter, invoked as `progress_callback(processed_count, total_count)`
  after each record. Defaults to `None` (unused) — no behavior change for
  existing callers. Added so the GUI (or any caller) can show real
  determinate enrichment progress without polling or reimplementing
  `enrich_file()`'s loop.
- `risforge()` gained optional `on_stage` and `enrichment_progress`
  parameters. `on_stage(stage, status)` fires around each phase
  (`"merge"`/`"clean"`/`"enrich"`, `"started"`/`"completed"`);
  `enrichment_progress` is forwarded to `RisEnricher.enrich_file()`. Both
  default to `None` — no behavior change for existing callers, including
  `run_pipeline()`, which does not expose these new parameters.

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

