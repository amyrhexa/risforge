"""Main application window.

Owns the three-screen flow (setup -> progress -> results) and is the
only place that constructs a :class:`~risforge_gui.worker.PipelineWorker`
and calls into the ``risforge`` API (indirectly, via the worker).
Every widget update happens in slots connected to the worker's
signals -- nothing here touches a widget from a non-GUI thread.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import risforge as risforge_core
from risforge_gui.dialogs import confirm_overwrite, show_error_dialog
from risforge_gui.theme import Theme, apply_theme
from risforge_gui.widgets.config_panel import EnrichmentConfigPanel
from risforge_gui.widgets.input_panel import InputPanel
from risforge_gui.widgets.output_panel import OutputConfigPanel
from risforge_gui.widgets.progress_panel import ProgressPanel
from risforge_gui.widgets.results_panel import ResultsPanel
from risforge_gui.worker import OperationMode, PipelineConfig, PipelineWorker

_MODE_ITEMS = [
    ("Full Pipeline (recommended)", OperationMode.PIPELINE),
    ("Merge only", OperationMode.MERGE),
    ("Clean only", OperationMode.CLEAN),
    ("Enrich only", OperationMode.ENRICH),
]

_RESULT_LABEL_BY_MODE = {
    OperationMode.PIPELINE: "Final file name",
    OperationMode.MERGE: "Merged file name",
    OperationMode.CLEAN: "Cleaned file name",
    OperationMode.ENRICH: "Enriched file name",
}

_DEFAULT_NAME_BY_MODE = {
    OperationMode.PIPELINE: "enriched.ris",
    OperationMode.MERGE: "merged.ris",
    OperationMode.CLEAN: "clean.ris",
    OperationMode.ENRICH: "enriched.ris",
}


def _resolve_relative_to(text: str, base: Path) -> Path:
    """A bare filename is relative to the output folder, not the process cwd."""
    path = Path(text)
    return path if path.is_absolute() else base / path


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("risforge")
        self.worker: PipelineWorker | None = None
        self._last_config: PipelineConfig | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.addWidget(self._build_header())

        self.stack = QStackedWidget()
        root_layout.addWidget(self.stack, stretch=1)

        self.setup_page = self._build_setup_page()
        self.progress_panel = ProgressPanel()
        self.results_panel = ResultsPanel()

        self.stack.addWidget(self.setup_page)
        self.stack.addWidget(self.progress_panel)
        self.stack.addWidget(self.results_panel)

        self.results_panel.start_new_project.connect(self._on_start_new_project)

        self._on_mode_changed()  # apply initial visibility rules

    # --- Header -----------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)

        text_column = QVBoxLayout()
        title = QLabel("risforge")
        title.setObjectName("HeaderTitle")
        subtitle = QLabel("Clean, deduplicate, and enrich RIS bibliographic files.")
        subtitle.setObjectName("HeaderSubtitle")
        version = QLabel(f"Version {risforge_core.__version__}")
        version.setObjectName("VersionLabel")
        text_column.addWidget(title)
        text_column.addWidget(subtitle)
        text_column.addWidget(version)
        layout.addLayout(text_column)
        layout.addStretch(1)

        theme_label = QLabel("Theme")
        theme_label.setObjectName("MutedLabel")
        self.theme_combo = QComboBox()
        self.theme_combo.setAccessibleName("Theme selector")
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        theme_label.setBuddy(self.theme_combo)
        layout.addWidget(theme_label)
        layout.addWidget(self.theme_combo)

        return header

    def _on_theme_changed(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        theme = {"System": Theme.SYSTEM, "Light": Theme.LIGHT, "Dark": Theme.DARK}[text]
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, theme)

    # --- Setup page ---------------------------------------------------------------

    def _build_setup_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("SetupPage")
        scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)

        self.input_panel = InputPanel()
        self.input_panel.files_changed.connect(self._on_mode_changed)
        layout.addWidget(self.input_panel)

        mode_box = QGroupBox("Operation")
        mode_layout = QHBoxLayout(mode_box)
        mode_label = QLabel("What should risforge do?")
        self.mode_combo = QComboBox()
        self.mode_combo.setAccessibleName("Operation mode")
        for label, _mode in _MODE_ITEMS:
            self.mode_combo.addItem(label)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_label.setBuddy(self.mode_combo)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.mode_combo, stretch=1)
        layout.addWidget(mode_box)

        self.mode_hint_label = QLabel("")
        self.mode_hint_label.setObjectName("HelperText")
        self.mode_hint_label.setWordWrap(True)
        layout.addWidget(self.mode_hint_label)

        self.enrichment_panel = EnrichmentConfigPanel()
        layout.addWidget(self.enrichment_panel)

        self.output_panel = OutputConfigPanel()
        layout.addWidget(self.output_panel)

        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("PrimaryButton")
        self.start_button.setAccessibleName("Start processing")
        self.start_button.clicked.connect(self._on_start_clicked)
        start_row = QHBoxLayout()
        start_row.addStretch(1)
        start_row.addWidget(self.start_button)
        layout.addLayout(start_row)
        layout.addStretch(1)

        scroll.setWidget(content)
        return scroll

    def _current_mode(self) -> OperationMode:
        return _MODE_ITEMS[self.mode_combo.currentIndex()][1]

    def _on_mode_changed(self) -> None:
        mode = self._current_mode()
        input_count = len(self.input_panel.model.paths())

        needs_enrichment_settings = mode in (OperationMode.PIPELINE, OperationMode.ENRICH)
        self.enrichment_panel.setVisible(needs_enrichment_settings)
        self.output_panel.keep_merged_check.setVisible(mode is OperationMode.PIPELINE)
        self.output_panel.keep_cleaned_check.setVisible(mode is OperationMode.PIPELINE)
        self.output_panel.final_name_edit.setPlaceholderText(_DEFAULT_NAME_BY_MODE[mode])

        hints = {
            OperationMode.PIPELINE: (
                "Merges multiple files automatically, then deduplicates and enriches. "
                "A single input file skips the merge step."
                if input_count > 1
                else "Deduplicates and enriches your input file."
            ),
            OperationMode.MERGE: "Combines every input file's records into one file. Does not deduplicate or enrich.",
            OperationMode.CLEAN: "Deduplicates a single RIS file. Requires exactly one input file.",
            OperationMode.ENRICH: "Fills in missing metadata for a single, already-clean RIS file. Requires exactly one input file.",
        }
        self.mode_hint_label.setText(hints[mode])

    # --- Start / validation ---------------------------------------------------------

    def _on_start_clicked(self) -> None:
        config = self._gather_config()
        if config is None:
            return
        self._last_config = config

        stages = self._stages_for_mode(config.mode, len(config.input_paths))
        self.progress_panel.reset(stages)
        self.stack.setCurrentWidget(self.progress_panel)

        self.worker = PipelineWorker(config)
        self.worker.stage_changed.connect(self.progress_panel.set_stage_status)
        self.worker.enrichment_progress.connect(self.progress_panel.set_enrichment_progress)
        self.worker.log_message.connect(self.progress_panel.append_log)
        self.worker.stats_changed.connect(self.progress_panel.update_stats)
        self.worker.error_occurred.connect(self._on_worker_error)
        self.worker.finished_ok.connect(self._on_worker_finished)
        self.worker.start()

    def _stages_for_mode(self, mode: OperationMode, input_count: int) -> list[str]:
        if mode is OperationMode.PIPELINE:
            return (["merge"] if input_count > 1 else []) + ["clean", "enrich"]
        return [mode.value]

    def _gather_config(self) -> PipelineConfig | None:
        mode = self._current_mode()
        input_paths = self.input_panel.model.paths()

        if not input_paths:
            QMessageBox.warning(self, "No input files", "Add at least one .ris file before starting.")
            return None

        if mode is OperationMode.CLEAN and len(input_paths) != 1:
            QMessageBox.warning(
                self,
                "Too many input files",
                "\"Clean only\" works on exactly one file. Either remove the extra files, "
                "or use \"Merge only\" first to combine them into one.",
            )
            return None

        if mode is OperationMode.ENRICH and len(input_paths) != 1:
            QMessageBox.warning(
                self,
                "Too many input files",
                "\"Enrich only\" works on exactly one file. Remove the extra files first.",
            )
            return None

        needs_email = mode in (OperationMode.PIPELINE, OperationMode.ENRICH)
        email = self.enrichment_panel.email()
        if needs_email and "@" not in email:
            QMessageBox.warning(
                self,
                "Contact email required",
                "Enrichment queries scholarly APIs that require a contact email address. "
                "Please enter one in Enrichment settings.",
            )
            return None

        output_dir = self.output_panel.output_dir()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            show_error_dialog(
                self,
                title="Could not create the output folder",
                message=f"{output_dir}\n\n{error}",
            )
            return None

        result_name = self.output_panel.final_name_edit.text().strip() or _DEFAULT_NAME_BY_MODE[mode]
        result_path = output_dir / result_name
        merge_path = output_dir / "merged.ris"
        dedup_path = output_dir / "clean.ris"
        fail_report_path = _resolve_relative_to(self.enrichment_panel.fail_report_name(), output_dir)

        outputs_to_check = {result_path}
        if mode is OperationMode.PIPELINE:
            if len(input_paths) > 1 and self.output_panel.keep_merged():
                outputs_to_check.add(merge_path)
            if self.output_panel.keep_cleaned():
                outputs_to_check.add(dedup_path)

        for path in sorted(outputs_to_check):
            if path.exists() and not confirm_overwrite(self, path):
                return None

        config = PipelineConfig(mode=mode, input_paths=input_paths)
        config.email = email
        config.cache_path = self.enrichment_panel.cache_path()
        config.request_delay_seconds = self.enrichment_panel.request_delay_seconds()
        config.fail_report_path = fail_report_path

        if mode is OperationMode.MERGE:
            config.merge_output_path = result_path
        elif mode is OperationMode.CLEAN:
            config.dedup_output_path = result_path
        elif mode is OperationMode.ENRICH:
            config.enriched_output_path = result_path
        else:  # PIPELINE
            config.merge_output_path = merge_path
            config.dedup_output_path = dedup_path
            config.enriched_output_path = result_path

        return config

    # --- Worker signal handlers --------------------------------------------------------

    def _on_worker_error(self, title: str, message: str, details: str, affected_file: str) -> None:
        show_error_dialog(self, title, message, details, affected_file)
        self.stack.setCurrentWidget(self.setup_page)

    def _on_worker_finished(self, result: object) -> None:
        config = self._last_config
        assert config is not None
        summary, final_path, fail_report_path = self._summarize(config, result)
        output_dir = final_path.parent if final_path else self.output_panel.output_dir()
        self.results_panel.set_results(summary, output_dir, final_path, fail_report_path)
        self.stack.setCurrentWidget(self.results_panel)

    def _summarize(
        self, config: PipelineConfig, result: object
    ) -> tuple[dict, Path | None, Path | None]:
        input_records = self.input_panel.model.total_known_records()

        if config.mode is OperationMode.MERGE:
            summary = {
                "input_files": result.input_file_count,  # type: ignore[attr-defined]
                "input_records": input_records,
            }
            return summary, config.merge_output_path, None

        if config.mode is OperationMode.CLEAN:
            records, _errors = result  # type: ignore[misc]
            summary = {"input_records": input_records, "unique_records": len(records)}
            return summary, config.dedup_output_path, None

        if config.mode is OperationMode.ENRICH:
            stats = result  # type: ignore[assignment]
            summary = {
                "input_records": stats.get("processed", 0),  # type: ignore[union-attr]
                "enriched_records": stats.get("enriched", 0),  # type: ignore[union-attr]
                "failed_enrichment": stats.get("failed", 0),  # type: ignore[union-attr]
            }
            return summary, config.enriched_output_path, config.fail_report_path

        # PIPELINE
        summary = {
            "input_files": result.input_file_count,  # type: ignore[attr-defined]
            "input_records": input_records,
            "unique_records": result.cleaned_record_count,  # type: ignore[attr-defined]
            "enriched_records": result.enrichment_stats.get("enriched", 0),  # type: ignore[attr-defined]
            "failed_enrichment": result.enrichment_stats.get("failed", 0),  # type: ignore[attr-defined]
        }
        return summary, config.enriched_output_path, config.fail_report_path

    # --- Reset --------------------------------------------------------------------------

    def _on_start_new_project(self) -> None:
        self.input_panel.clear_all()
        self.stack.setCurrentWidget(self.setup_page)
