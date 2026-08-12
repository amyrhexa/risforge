"""Runs a risforge operation on a background thread.

This is the single integration point between the GUI and the
``risforge`` core package. Every branch below calls a real,
already-public risforge function or method -- it does not
reimplement merging, cleaning, deduplication, or enrichment. Where the
core package didn't previously expose a way to observe progress
mid-operation (``RisEnricher.enrich_file``'s ``progress_callback`` and
``risforge()``'s ``on_stage``/``enrichment_progress`` parameters), that
was added directly to the core package as small, optional,
backward-compatible hooks -- not duplicated here.

Threading model: :class:`PipelineWorker` is a ``QThread``. Only its
``run()`` method executes on the worker thread; the instance itself is
created on (and its signals are received on) the GUI thread, so Qt's
queued cross-thread signal delivery applies automatically. No widget
is ever touched from inside ``run()`` -- only signals are emitted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from risforge import RisEnricher, clean_ris_file, merge_ris_files, risforge


class OperationMode(str, Enum):
    PIPELINE = "pipeline"
    MERGE = "merge"
    CLEAN = "clean"
    ENRICH = "enrich"


@dataclass
class PipelineConfig:
    """Everything a run needs, gathered from the GUI's config screens."""

    mode: OperationMode
    input_paths: list[Path]

    # Enrichment.
    email: str = ""
    cache_path: Path | None = None
    request_delay_seconds: float = 0.1
    fail_report_path: Path = field(default_factory=lambda: Path("failed_records.json"))

    # Output.
    merge_output_path: Path | None = None
    dedup_output_path: Path | None = None
    enriched_output_path: Path | None = None


class _LogBridge(logging.Handler):
    """Forwards risforge's own log records to a Qt signal.

    Reuses the log messages the core package already produces (see
    each module's ``logger.info``/``logger.warning`` calls) instead of
    inventing a parallel set of GUI-side status strings.
    """

    def __init__(self, log_signal: Signal) -> None:
        super().__init__(level=logging.INFO)
        self._log_signal = log_signal

    def emit(self, record: logging.LogRecord) -> None:
        level = "ERROR" if record.levelno >= logging.ERROR else (
            "WARNING" if record.levelno >= logging.WARNING else "INFO"
        )
        self._log_signal.emit(level, record.getMessage())


class PipelineWorker(QThread):
    """Runs one risforge operation (per ``PipelineConfig.mode``) off the GUI thread."""

    stage_changed = Signal(str, str)  # stage, status ("started" | "completed")
    enrichment_progress = Signal(int, int)  # processed, total
    log_message = Signal(str, str)  # level, message
    stats_changed = Signal(dict)
    error_occurred = Signal(str, str, str, str)  # title, message, details, affected_file
    finished_ok = Signal(object)  # PipelineResult | MergeResult | dict | tuple

    def __init__(self, config: PipelineConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config

    def run(self) -> None:  # noqa: D102 -- QThread interface
        log_bridge = _LogBridge(self.log_message)
        risforge_logger = logging.getLogger("risforge")
        risforge_logger.addHandler(log_bridge)
        risforge_logger.setLevel(logging.INFO)
        try:
            self._run()
        except FileNotFoundError as error:
            self._report_error(
                title="A file could not be found",
                message=str(error),
                details=repr(error),
                affected_file=self._guess_affected_file(),
            )
        except ValueError as error:
            self._report_error(
                title="Invalid configuration",
                message=str(error),
                details=repr(error),
            )
        except (OSError, RuntimeError) as error:
            self._report_error(
                title="The operation failed",
                message=str(error),
                details=repr(error),
            )
        except Exception as error:  # noqa: BLE001
            # Deliberate, sole broad catch in the GUI: a QThread that
            # raises out of run() terminates silently with no signal
            # and no visible error at all -- worse than a generic
            # message. Every other branch above already handles the
            # exception types risforge's own API documents raising.
            import traceback

            self._report_error(
                title="An unexpected error occurred",
                message=f"{type(error).__name__}: {error}",
                details=traceback.format_exc(),
            )
        finally:
            risforge_logger.removeHandler(log_bridge)

    # --- Dispatch -----------------------------------------------------------

    def _run(self) -> None:
        config = self._config
        if config.mode is OperationMode.MERGE:
            self._run_merge(config)
        elif config.mode is OperationMode.CLEAN:
            self._run_clean(config)
        elif config.mode is OperationMode.ENRICH:
            self._run_enrich(config)
        else:
            self._run_pipeline(config)

    def _run_merge(self, config: PipelineConfig) -> None:
        assert config.merge_output_path is not None
        self.stage_changed.emit("merge", "started")
        result = merge_ris_files(config.input_paths, config.merge_output_path)
        self.stage_changed.emit("merge", "completed")
        self.stats_changed.emit(
            {"input_files": result.input_file_count, "merged_records": result.record_count}
        )
        self.finished_ok.emit(result)

    def _run_clean(self, config: PipelineConfig) -> None:
        assert config.dedup_output_path is not None
        self.stage_changed.emit("clean", "started")
        records, errors = clean_ris_file(config.input_paths[0], config.dedup_output_path)
        self.stage_changed.emit("clean", "completed")
        self.stats_changed.emit({"unique_records": len(records)})
        self.finished_ok.emit((records, errors))

    def _run_enrich(self, config: PipelineConfig) -> None:
        assert config.enriched_output_path is not None
        self.stage_changed.emit("enrich", "started")
        enricher = RisEnricher(
            email=config.email,
            cache_name=config.cache_path or ".api_cache",
        )
        stats = enricher.enrich_file(
            input_path=config.input_paths[0],
            output_path=config.enriched_output_path,
            fail_report_path=config.fail_report_path,
            request_delay_seconds=config.request_delay_seconds,
            progress_callback=self._on_enrichment_progress,
        )
        self.stage_changed.emit("enrich", "completed")
        self.stats_changed.emit(
            {
                "enriched_records": stats.get("enriched", 0),
                "failed_enrichment": stats.get("failed", 0),
                "skipped_malformed": stats.get("skipped_malformed", 0),
            }
        )
        self.finished_ok.emit(stats)

    def _run_pipeline(self, config: PipelineConfig) -> None:
        assert config.dedup_output_path is not None
        assert config.enriched_output_path is not None
        result = risforge(
            input_paths=config.input_paths,
            dedup_path=config.dedup_output_path,
            enriched_path=config.enriched_output_path,
            email=config.email,
            merge_path=config.merge_output_path,
            fail_report_path=config.fail_report_path,
            on_stage=self._on_stage,
            enrichment_progress=self._on_enrichment_progress,
        )
        self.stats_changed.emit(
            {
                "input_files": result.input_file_count,
                "merged_records": result.merged_record_count,
                "unique_records": result.cleaned_record_count,
                "enriched_records": result.enrichment_stats.get("enriched", 0),
                "failed_enrichment": result.enrichment_stats.get("failed", 0),
                "skipped_malformed": result.enrichment_stats.get("skipped_malformed", 0),
            }
        )
        self.finished_ok.emit(result)

    # --- Callbacks passed into the core API (invoked on this thread) -------

    def _on_stage(self, stage: str, status: str) -> None:
        self.stage_changed.emit(stage, status)

    def _on_enrichment_progress(self, processed: int, total: int) -> None:
        self.enrichment_progress.emit(processed, total)

    # --- Error reporting -----------------------------------------------------

    def _report_error(
        self, title: str, message: str, details: str = "", affected_file: str | None = None
    ) -> None:
        self.error_occurred.emit(title, message, details, affected_file or "")

    def _guess_affected_file(self) -> str | None:
        """Best-effort: name the first configured input file in a FileNotFoundError.

        risforge's own FileNotFoundError messages already include the
        specific missing path (see clean_ris_file/parse_ris_records),
        so this is only a fallback label for the error dialog's
        "affected file" field, not the source of truth.
        """
        if self._config.input_paths:
            return str(self._config.input_paths[0])
        return None
