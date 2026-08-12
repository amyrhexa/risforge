"""risforge: clean, deduplicate, and enrich RIS bibliographic files.

Three distinct operations, composed by :func:`risforge`:

- **merge** -- combine multiple RIS files into one, records intact,
  duplicates untouched (:func:`merge_ris_files`).
- **clean** -- deduplicate and merge duplicate-cluster metadata
  (:func:`clean_ris_file`).
- **enrich** -- fill in missing metadata from scholarly APIs
  (:class:`RisEnricher`).

Typical usage::

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
        input_paths=["scopus.ris", "pubmed.ris", "wos.ris"],
        dedup_path="clean.ris",
        enriched_path="enriched.ris",
        email="you@example.com",
    )

The individual stages remain directly usable on their own::

    from risforge import merge_ris_files, clean_ris_file, RisEnricher

    merge_ris_files(["scopus.ris", "pubmed.ris"], "merged.ris")
    records, errors = clean_ris_file("merged.ris", "clean.ris")
    RisEnricher(email="you@example.com").enrich_file("clean.ris", "enriched.ris")

``run_pipeline()`` (the pre-0.2.0 name, single-file only) is retained
for backward compatibility -- see its docstring in
:mod:`risforge.pipeline`.

See the ``risforge`` console script (``risforge --help``) for the
equivalent command-line interface.
"""

from risforge.cleaning import clean_ris_file, process_ris_file
from risforge.enrichment import RisEnricher
from risforge.exceptions import RisForgeError, RisParsingError
from risforge.merging import MergeResult, merge_ris_files
from risforge.pipeline import PipelineResult, risforge, run_pipeline

__version__ = "0.3.2"

__all__ = [
    "clean_ris_file",
    "process_ris_file",
    "RisEnricher",
    "merge_ris_files",
    "MergeResult",
    "risforge",
    "run_pipeline",
    "PipelineResult",
    "RisForgeError",
    "RisParsingError",
]
