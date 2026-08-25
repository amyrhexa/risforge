"""Background worker executing risforge operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from risforge import RisEnricher, clean_ris_file, merge_ris_files, risforge


class OperationMode(str, Enum):
    PIPELINE = "pipeline"
    MERGE = "merge"
    CLEAN = "clean"
    ENRICH = "enrich"


@dataclass
class PipelineConfig:
    """Configuration for one GUI run."""

    mode: OperationMode
    input_paths: list[Path]

    email: str = ""
    cache_path: Path | None = None
    request_delay_seconds: float = 0.1
    fail_report_path: Path = field(default_factory=lambda: Path("failed_records.json"))

    merge_output_path: Path | None = None
    dedup_output_path: Path | None = None
    enriched_output_path: Path | None = None


class _LogBridge(logging.Handler):
    """Forwards risforge logs into Qt signals."""

    def __init__(self, log_signal: Signal) -> None:
        super().__init__(level=logging.INFO)
        self._log_signal = log_signal

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.ERROR:
            level = "ERROR"
        elif record.levelno >= logging.WARNING:
            level = "WARNING"
        else:
            level = "INFO"

        self._log_signal.emit(level, record.getMessage())


class PipelineWorker(QThread):
    """Runs one risforge operation off the GUI thread."""

    stage_changed = Signal(str, str)
    enrichment_progress = Signal(int, int)
    log_message = Signal(str, str)
    stats_changed = Signal(dict)
    error_occurred = Signal(str, str, str, str)
    finished_ok = Signal(object)

    def __init__(self, config: PipelineConfig, parent=None) -> None:
        super().__init__(parent)
        self._config = config

    def run(self) -> None:
        """Execute the operation and always emit a terminal signal."""
        log_bridge = _LogBridge(self.log_message)
        core_logger = logging.getLogger("risforge")

        core_logger.addHandler(log_bridge)
        old_level = core_logger.level
        core_logger.setLevel(logging.INFO)

        try:
            self._dispatch()
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
            import traceback

            self._report_error(
                title="An unexpected error occurred",
                message=f"{type(error).__name__}: {error}",
                details=traceback.format_exc(),
            )
        finally:
            core_logger.removeHandler(log_bridge)
            core_logger.setLevel(old_level)

    def _dispatch(self) -> None:
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
        output_path = self._required_path(config.merge_output_path, "Merge output path")

        self.stage_changed.emit("merge", "started")
        result = merge_ris_files(config.input_paths, output_path)
        self.stage_changed.emit("merge", "completed")

        self.stats_changed.emit(
            {
                "input_files": result.input_file_count,
                "merged_records": result.record_count,
            }
        )

        self.finished_ok.emit(result)

    def _run_clean(self, config: PipelineConfig) -> None:
        input_path = self._required_input(config)
        output_path = self._required_path(config.dedup_output_path, "Clean output path")

        self.stage_changed.emit("clean", "started")
        records, errors = clean_ris_file(input_path, output_path)
        self.stage_changed.emit("clean", "completed")

        self.stats_changed.emit({"unique_records": len(records)})
        self.finished_ok.emit((records, errors))

    def _run_enrich(self, config: PipelineConfig) -> None:
        input_path = self._required_input(config)
        output_path = self._required_path(config.enriched_output_path, "Enriched output path")

        if not config.email:
            raise ValueError("An email address is required for enrichment.")

        self.stage_changed.emit("enrich", "started")

        enricher = RisEnricher(
            email=config.email,
            cache_name=config.cache_path or ".api_cache",
        )

        stats = enricher.enrich_file(
            input_path=input_path,
            output_path=output_path,
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
        dedup_path = self._required_path(config.dedup_output_path, "Clean output path")
        enriched_path = self._required_path(config.enriched_output_path, "Enriched output path")

        if not config.email:
            raise ValueError("An email address is required for enrichment.")

        result = risforge(
            input_paths=config.input_paths,
            dedup_path=dedup_path,
            enriched_path=enriched_path,
            email=config.email,
            merge_path=config.merge_output_path,
            fail_report_path=config.fail_report_path,
            on_stage=self._on_stage,
            enrichment_progress=self._on_enrichment_progress,
            cache_name=config.cache_path or ".api_cache",
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

    def _on_stage(self, stage: str, status: str) -> None:
        self.stage_changed.emit(stage, status)

    def _on_enrichment_progress(self, processed: int, total: int) -> None:
        self.enrichment_progress.emit(processed, total)

    def _report_error(
        self,
        title: str,
        message: str,
        details: str = "",
        affected_file: str | None = None,
    ) -> None:
        self.error_occurred.emit(title, message, details, affected_file or "")

    def _guess_affected_file(self) -> str | None:
        if self._config.input_paths:
            return str(self._config.input_paths[0])
        return None

    @staticmethod
    def _required_input(config: PipelineConfig) -> Path:
        if not config.input_paths:
            raise ValueError("At least one input file is required.")
        return config.input_paths[0]

    @staticmethod
    def _required_path(path: Path | None, label: str) -> Path:
        if path is None:
            raise ValueError(f"{label} is required.")
        return path
