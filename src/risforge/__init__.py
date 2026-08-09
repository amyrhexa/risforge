"""risforge: clean, deduplicate, and enrich RIS bibliographic files.

Typical usage::

    from risforge import clean_ris_file, RisEnricher, run_pipeline

    # Clean + deduplicate only
    records, errors = clean_ris_file("raw.ris", "clean.ris")

    # Enrich only
    enricher = RisEnricher(email="you@example.com")
    stats = enricher.enrich_file("clean.ris", "enriched.ris")

    # Both, in one call
    result = run_pipeline(
        "raw.ris", "clean.ris", "enriched.ris", email="you@example.com"
    )

See the ``risforge`` console script (``risforge --help``) for the
equivalent command-line interface.
"""

from risforge.cleaning import clean_ris_file, process_ris_file
from risforge.enrichment import RisEnricher
from risforge.exceptions import RisForgeError, RisParsingError
from risforge.pipeline import PipelineResult, run_pipeline

__version__ = "0.1.0"

__all__ = [
    "clean_ris_file",
    "process_ris_file",
    "RisEnricher",
    "run_pipeline",
    "PipelineResult",
    "RisForgeError",
    "RisParsingError",
]
