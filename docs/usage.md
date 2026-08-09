# Usage details

This supplements the README with the specifics of how deduplication
and enrichment decide what to do.

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
