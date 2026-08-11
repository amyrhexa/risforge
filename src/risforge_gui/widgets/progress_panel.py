"""Progress screen: per-stage progress bars, running stats, expandable log."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from risforge_gui.widgets.log_panel import LogPanel

_STAGE_TITLES = {
    "merge": "Merge",
    "clean": "Deduplication",
    "enrich": "Enrichment",
}

_STAT_LABELS = {
    "input_files": "Input files",
    "merged_records": "Merged records",
    "unique_records": "Unique records",
    "enriched_records": "Enriched",
    "failed_enrichment": "Failed enrichment",
}


class ProgressPanel(QWidget):
    """Shown while a :class:`~risforge_gui.worker.PipelineWorker` is running."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProgressPage")
        layout = QVBoxLayout(self)

        title = QLabel("Processing")
        title.setObjectName("SectionHeading")
        layout.addWidget(title)

        self._bars: dict[str, QProgressBar] = {}
        bars_box = QGroupBox("Stages")
        bars_layout = QFormLayout(bars_box)
        for stage_key, stage_title in _STAGE_TITLES.items():
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(True)
            bar.setAccessibleName(f"{stage_title} progress")
            self._bars[stage_key] = bar
            bars_layout.addRow(QLabel(stage_title), bar)
        layout.addWidget(bars_box)

        stats_box = QGroupBox("Statistics")
        self._stats_layout = QFormLayout(stats_box)
        self._stat_value_labels: dict[str, QLabel] = {}
        for key, label_text in _STAT_LABELS.items():
            value_label = QLabel("\u2014")
            self._stat_value_labels[key] = value_label
            self._stats_layout.addRow(QLabel(label_text), value_label)
        layout.addWidget(stats_box)

        self.log_toggle = QToolButton()
        self.log_toggle.setText("Show activity log \u25be")
        self.log_toggle.setCheckable(True)
        self.log_toggle.setAccessibleName("Toggle activity log")
        self.log_toggle.toggled.connect(self._toggle_log)
        layout.addWidget(self.log_toggle)

        self.log_panel = LogPanel()
        self.log_panel.setVisible(False)
        self.log_panel.setMinimumHeight(160)
        layout.addWidget(self.log_panel, stretch=1)

        self.current_activity_label = QLabel("")
        self.current_activity_label.setObjectName("MutedLabel")
        layout.addWidget(self.current_activity_label)

    def _toggle_log(self, checked: bool) -> None:
        self.log_panel.setVisible(checked)
        self.log_toggle.setText("Hide activity log \u25b4" if checked else "Show activity log \u25be")

    # --- Public update API, called from MainWindow's signal-connected slots ---

    def reset(self, stages_in_use: list[str]) -> None:
        for stage_key, bar in self._bars.items():
            in_use = stage_key in stages_in_use
            bar.setVisible(in_use)
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFormat("Waiting..." if in_use else "Not applicable")
        for label in self._stat_value_labels.values():
            label.setText("\u2014")
        self.log_panel.clear()
        self.current_activity_label.setText("")

    def set_stage_status(self, stage: str, status: str) -> None:
        bar = self._bars.get(stage)
        if bar is None:
            return
        title = _STAGE_TITLES.get(stage, stage.title())
        if status == "started":
            # Merge/clean don't expose per-record progress, so show a
            # busy indicator rather than a fabricated percentage.
            bar.setRange(0, 0)
            bar.setFormat(f"{title} in progress...")
            self.current_activity_label.setText(f"{title} in progress...")
        elif status == "completed":
            bar.setRange(0, 100)
            bar.setValue(100)
            bar.setFormat(f"{title}: complete")
            self.current_activity_label.setText(f"{title} complete.")

    def set_enrichment_progress(self, processed: int, total: int) -> None:
        bar = self._bars.get("enrich")
        if bar is None or total <= 0:
            return
        bar.setRange(0, total)
        bar.setValue(processed)
        bar.setFormat(f"Enrichment: {processed:,}/{total:,} (%p%)")
        self.current_activity_label.setText(f"Enriching record {processed:,} of {total:,}...")

    def update_stats(self, stats: dict) -> None:
        for key, value in stats.items():
            label = self._stat_value_labels.get(key)
            if label is None or value is None:
                continue
            label.setText(f"{value:,}" if isinstance(value, int) else str(value))

    def append_log(self, level: str, message: str) -> None:
        self.log_panel.append_log(level, message)
