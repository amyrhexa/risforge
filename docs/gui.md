# risforge GUI

A desktop application for `risforge`, for researchers who'd rather not use the
command line. It's a thin interface over the same `risforge` Python API the
CLI uses -- no merging, cleaning, deduplication, or enrichment logic lives in
the GUI itself.

## Installing

The GUI is an optional extra, so a plain `pip install risforge` never pulls
in Qt:

```bash
pip install "risforge[gui]"
```

## Launching

```bash
risforge-gui
```

This installs as a proper desktop-app launcher (no console window pops up
alongside it on Windows).

## Supported platforms

Windows, macOS, and Linux, via [PySide6](https://doc.qt.io/qtforpython-6/)
(Qt 6). Anywhere `pip install "risforge[gui]"` succeeds, `risforge-gui` runs.

## Basic workflow

1. **Add files** -- drag `.ris` files into the window, or use *Add Files* /
   *Add Folder*. Each file's record count is counted in the background and
   filled in once ready.
2. **Choose an operation** -- *Full Pipeline* is selected by default and
   adapts automatically: one input file goes straight to
   deduplication + enrichment, multiple input files are merged first. You can
   also run *Merge only*, *Clean only*, or *Enrich only* as standalone steps.
3. **Enter a contact email** (Full Pipeline / Enrich only) -- see below for
   why this is needed.
4. **Choose an output folder** -- a new folder is suggested by default
   (`~/risforge-output`); your original input files are never modified or
   overwritten.
5. **Start**. Progress for each stage is shown as it runs; an expandable
   activity log shows the same messages `risforge`'s own logging produces.
6. **Review results** -- a summary of records in/out, and buttons to open the
   output folder, open the final file, or view the failure report.

## Where output files are created

Everything is written under the output folder you choose (default:
`~/risforge-output`), never next to or over your input files:

- `merged.ris` -- only for multi-file runs, and only if you keep it
- `clean.ris` -- the deduplicated file
- `enriched.ris` (or whatever name you choose) -- the final result
- `failed_records.json` -- only written if any records had no resolvable DOI

If any of these already exist, you're asked to confirm before they're
overwritten.

## How the enrichment email is used

It's sent as a contact address on requests to Crossref, OpenAlex, and
Unpaywall, exactly as required by those services' usage policies (their
"polite pool" access). It isn't stored anywhere by risforge, or used for
anything else.

## Troubleshooting

**`risforge-gui` prints "requires the GUI extras" and exits.**
PySide6 isn't installed. Run `pip install "risforge[gui]"`.

**The window looks broken or fonts are tiny on a high-DPI display.**
This is a Qt/OS display-scaling interaction, not a risforge setting. Most
platforms handle this automatically; if not, consult Qt's
[high-DPI documentation](https://doc.qt.io/qt-6/highdpi.html).

**Enrichment seems to hang.**
Each record makes a small number of API calls with a short delay between
records (configurable under *Show advanced settings*), so a large file can
legitimately take a while. Expand the activity log to confirm it's still
progressing -- the enrichment progress bar shows an exact record count, not
just a spinner.

**An error dialog appeared.**
The message at the top is meant to be understandable on its own. Click "Show
Details" for the full technical error if you need to report a bug.
