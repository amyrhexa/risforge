# Usage details

This supplements the README with the specifics of how merging,
deduplication, and enrichment each decide what to do.

## Merging algorithm (`risforge.merging`)

`merge_ris_files()` has exactly one job: combine records from multiple
`.ris` files into one file, in input order. It is intentionally
"dumb" relative to cleaning:

1. Each input file is parsed independently with the same
   block-by-block, error-tolerant parser cleaning uses
   (`risforge.cleaning.parse_ris_records()`) — a malformed record in
   one file doesn't affect any other record in that file, or any
   other input file.
2. Every successfully parsed record from every file is appended, in
   the order the files were given, to one output list.
3. That list is written out as-is. No two records are ever compared
   to each other, no DOIs are normalized for matching, and no records
   are combined or dropped.

If `scopus.ris` has 5,000 records and `pubmed.ris` has 4,000, the
merged output has 9,000 records — including however many describe the
same papers. That's by design: merging answers "what's the union of
everything I was given", not "what's unique". Deduplication is a
separate, deliberate step that comes after.

## Deduplication algorithm (`risforge.cleaning`)

1. The input file is split into individual record blocks and parsed
   one at a time, so a single malformed block doesn't abort the whole
   file — it's recorded as an error and skipped.
2. Every record gets a normalized DOI (`normalize_doi`) and a
   normalized `title|first_author` composite key
   (`normalize_title` + `extract_first_author`).
3. Records are grouped into duplicate clusters with a union-find
   structure:
   - Pass 1 unions any two records with the same normalized DOI.
   - Pass 2 unions any two records with the same normalized
     title+first-author key — but only if doing so wouldn't merge two
     records that have *different*, explicit DOIs. This keeps the
     fuzzy fallback heuristic from ever overriding an explicit DOI
     mismatch.
4. Each cluster is merged into one record: the most complete record
   (by populated field count) is the base, and every other record in
   the cluster fills in whatever fields the base is missing, or adds
   list items (authors, keywords, etc.) the base doesn't already have.

No record is ever dropped for having *too little* data — only for
being a confirmed duplicate of another record.

## Enrichment algorithm (`risforge.enrichment`)

For each record:

1. Try to find a DOI already on the record (`doi` field, or one
   embedded in a `urls` entry).
2. If none exists, try to resolve one from the title via a Crossref
   title search, accepting the top match only if it's at least 90%
   similar (`difflib.SequenceMatcher` ratio) to the record's title.
3. If a DOI is available (existing or resolved), query Crossref
   (core metadata), Semantic Scholar (abstract), OpenAlex (subject
   concepts + open-access URL), and Unpaywall (best open-access PDF
   link).
4. Fill in only the fields the record doesn't already have a value
   for. Existing data always wins.

Records with no resolvable DOI are left untouched and logged to the
failure report (`failed_records.json` by default).

## Pipeline orchestration (`risforge.pipeline`)

`risforge()` decides whether to run the merge step at all based purely
on how many input paths it's given:

- **One input** (a bare path, or a one-item sequence): merging is
  skipped entirely. The input goes straight to `clean_ris_file()`.
  No intermediate merged file is created anywhere.
- **Two or more inputs**: `merge_ris_files()` runs first, writing an
  intermediate file (`merged.ris` next to your `dedup_path` by
  default, or wherever `merge_path` / `--merge-output` points). That
  merged file is then what gets passed to `clean_ris_file()`.

Either way, cleaning and enrichment always run exactly as they would
standalone -- the pipeline doesn't change their behavior, it just
decides what file to hand `clean_ris_file()` as input.
