"""Main application window."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from risforge_gui.dialogs import confirm_overwrite, show_error_dialog
from risforge_gui.widgets import (
    EnrichmentConfigPanel,
    InputPanel,
    OutputConfigPanel,
    ProgressPanel,
    ResultsPanel,
)
from risforge_gui.worker import OperationMode, PipelineConfig, PipelineWorker

logger = logging.getLogger(__name__)

_ENRICHING_MODES = (OperationMode.PIPELINE, OperationMode.ENRICH)


class MainWindow(QMainWindow):
    """Primary RisForge GUI window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("RisForge - RIS Deduplication & Enrichment")
        self.resize(900, 720)

        self.worker: PipelineWorker | None = None
        self._running = False

        self._current_mode = OperationMode.PIPELINE
        self._current_config: PipelineConfig | None = None
        self._current_final_path: Path | None = None
        self._current_fail_report: Path | None = None
        self._latest_stats: dict[str, object] = {}

        self.input_panel = InputPanel()
        self.config_panel = EnrichmentConfigPanel()
        self.output_panel = OutputConfigPanel()
        self.progress_panel = ProgressPanel()
        self.results_panel = ResultsPanel()

        self.setup_page = self._build_setup_page()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.progress_panel)
        self.stack.addWidget(self.results_panel)
        self.setCentralWidget(self.stack)

        self.input_panel.files_changed.connect(self._update_start_enabled)
        self.results_panel.start_new_project.connect(self._start_new_project)

        self._on_mode_changed()
        self._update_start_enabled()

    def _build_setup_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        title = QLabel("RisForge")
        title.setObjectName("HeaderTitle")

        subtitle = QLabel("Merge, clean, deduplicate, and enrich RIS bibliography exports.")
        subtitle.setObjectName("HeaderSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.input_panel)

        operation_row = QHBoxLayout()
        operation_label = QLabel("Operation")

        self.operation_combo = QComboBox()
        self.operation_combo.addItem("Full Pipeline", OperationMode.PIPELINE)
        self.operation_combo.addItem("Merge only", OperationMode.MERGE)
        self.operation_combo.addItem("Clean only", OperationMode.CLEAN)
        self.operation_combo.addItem("Enrich only", OperationMode.ENRICH)
        self.operation_combo.currentIndexChanged.connect(self._on_mode_changed)

        operation_row.addWidget(operation_label)
        operation_row.addWidget(self.operation_combo, stretch=1)
        layout.addLayout(operation_row)

        layout.addWidget(self.config_panel)
        layout.addWidget(self.output_panel)

        controls = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.clicked.connect(self._start)

        controls.addStretch(1)
        controls.addWidget(self.start_button)
        layout.addLayout(controls)
        layout.addStretch(1)

        return page

    @property
    def _mode(self) -> OperationMode:
        return self.operation_combo.currentData()

    def _on_mode_changed(self) -> None:
        mode = self._mode
        self.config_panel.setVisible(mode in _ENRICHING_MODES)
        self._update_start_enabled()

    def _update_start_enabled(self) -> None:
        has_files = self.input_panel.model.rowCount() > 0
        self.start_button.setEnabled(has_files and not self._running)

    def _start(self) -> None:
        if self._running:
            return

        paths = self.input_panel.model.paths()
        if not paths:
            return

        mode = self._mode

        email = ""
        if mode in _ENRICHING_MODES:
            email = self.config_panel.email()
            if "@" not in email:
                show_error_dialog(
                    self,
                    "Contact email required",
                    "Enter a valid contact email for Crossref/OpenAlex/Unpaywall "
                    "polite-pool access.",
                )
                return

        if mode in (OperationMode.CLEAN, OperationMode.ENRICH) and len(paths) != 1:
            show_error_dialog(
                self,
                "One input file required",
                "Standalone Clean and Enrich operate on exactly one RIS file. "
                "Use Full Pipeline or Merge for multiple files.",
            )
            return

        output_dir = self.output_panel.output_dir()

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            show_error_dialog(
                self,
                "Cannot create output folder",
                str(error),
                details=repr(error),
                affected_file=str(output_dir),
            )
            return

        final_path = self.output_panel.final_ris_path()
        fail_report_path = output_dir / self.config_panel.fail_report_name()

        config = PipelineConfig(
            mode=mode,
            input_paths=paths,
            email=email,
            cache_path=self.config_panel.cache_path(),
            request_delay_seconds=self.config_panel.request_delay_seconds(),
            fail_report_path=fail_report_path,
        )

        overwrite_paths = [final_path]

        if mode is OperationMode.MERGE:
            config.merge_output_path = final_path
        elif mode is OperationMode.CLEAN:
            config.dedup_output_path = final_path
        elif mode is OperationMode.ENRICH:
            config.enriched_output_path = final_path
            overwrite_paths.append(fail_report_path)
        else:
            config.enriched_output_path = final_path
            config.dedup_output_path = self.output_panel.cleaned_path()
            overwrite_paths.append(config.dedup_output_path)

            if len(paths) > 1:
                config.merge_output_path = self.output_panel.merged_path()
                overwrite_paths.append(config.merge_output_path)

            overwrite_paths.append(fail_report_path)

        if not self._confirm_overwrites(overwrite_paths):
            return

        self._current_mode = mode
        self._current_config = config
        self._current_final_path = final_path
        self._current_fail_report = fail_report_path if mode in _ENRICHING_MODES else None

        self._latest_stats = {"input_files": len(paths)}
        total_records = self.input_panel.model.total_known_records()

        if total_records is not None:
            self._latest_stats["input_records"] = total_records

        self.progress_panel.reset(self._stages_for(mode, len(paths)))
        self.progress_panel.update_stats(self._latest_stats)
        self.stack.setCurrentWidget(self.progress_panel)

        self._set_running(True)

        self.worker = PipelineWorker(config, self)
        self.worker.stage_changed.connect(self.progress_panel.set_stage_status)
        self.worker.enrichment_progress.connect(self.progress_panel.set_enrichment_progress)
        self.worker.log_message.connect(self.progress_panel.append_log)
        self.worker.stats_changed.connect(self._on_stats)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.error_occurred.connect(self._on_error)
        self.worker.finished.connect(self._on_thread_finished)
        self.worker.start()

    def _confirm_overwrites(self, paths: list[Path]) -> bool:
        seen: set[Path] = set()

        for path in paths:
            if path in seen:
                continue

            seen.add(path)

            if path.exists() and not confirm_overwrite(self, path):
                return False

        return True

    @staticmethod
    def _stages_for(mode: OperationMode, input_count: int) -> list[str]:
        if mode is OperationMode.MERGE:
            return ["merge"]

        if mode is OperationMode.CLEAN:
            return ["clean"]

        if mode is OperationMode.ENRICH:
            return ["enrich"]

        if input_count > 1:
            return ["merge", "clean", "enrich"]

        return ["clean", "enrich"]

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._update_start_enabled()

    def _on_stats(self, stats: dict) -> None:
        self._latest_stats.update(stats)
        self.progress_panel.update_stats(stats)

    def _on_finished(self, _result: object) -> None:
        self._cleanup_intermediate_files()

        summary = dict(self._latest_stats)

        self.results_panel.set_results(
            summary,
            self.output_panel.output_dir(),
            self._current_final_path,
            self._current_fail_report,
        )

        self.stack.setCurrentWidget(self.results_panel)

    def _on_error(self, title: str, message: str, details: str, affected_file: str) -> None:
        self.stack.setCurrentWidget(self.setup_page)
        show_error_dialog(self, title, message, details, affected_file)

    def _on_thread_finished(self) -> None:
        self.worker = None
        self._set_running(False)

    def _cleanup_intermediate_files(self) -> None:
        config = self._current_config

        if config is None or config.mode is not OperationMode.PIPELINE:
            return

        if not self.output_panel.keep_merged() and config.merge_output_path is not None:
            config.merge_output_path.unlink(missing_ok=True)

        if not self.output_panel.keep_cleaned() and config.dedup_output_path is not None:
            config.dedup_output_path.unlink(missing_ok=True)

    def _start_new_project(self) -> None:
        self.input_panel.clear_all()
        self.stack.setCurrentWidget(self.setup_page)
        self._update_start_enabled()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._running:
            QMessageBox.warning(
                self,
                "Processing",
                "RisForge is still processing. Wait for the run to finish before closing.",
            )
            event.ignore()
            return

        super().closeEvent(event)
