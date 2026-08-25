"""risforge: merge, clean, deduplicate, and enrich RIS bibliographic files."""

from risforge.cleaning import clean_ris_file, process_ris_file
from risforge.enrichment import RisEnricher
from risforge.exceptions import RisForgeError, RisParsingError
from risforge.merging import MergeResult, merge_ris_files
from risforge.pipeline import PipelineResult, risforge, run_pipeline

__version__ = "0.4.0"

__all__ = [
    "MergeResult",
    "PipelineResult",
    "RisEnricher",
    "RisForgeError",
    "RisParsingError",
    "clean_ris_file",
    "merge_ris_files",
    "process_ris_file",
    "risforge",
    "run_pipeline",
]
