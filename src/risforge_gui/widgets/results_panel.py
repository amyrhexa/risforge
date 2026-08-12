"""Results screen: completion summary and post-run actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SUMMARY_LABELS = {
    "input_files": "Input files",
    "input_records": "Input records",
    "unique_records": "Unique records",
    "enriched_records": "Enriched records",
    "failed_enrichment": "Unresolved records",
    "skipped_malformed": "Skipped (unreadable records)",
}


class ResultsPanel(QWidget):
    """Shown after a run finishes successfully."""

    start_new_project = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ResultsPage")
        self._output_dir: Path | None = None
        self._final_ris_path: Path | None = None
        self._fail_report_path: Path | None = None

        layout = QVBoxLayout(self)

        title = QLabel("Processing complete")
        title.setObjectName("SectionHeading")
        layout.addWidget(title)

        summary_box = QGroupBox("Summary")
        self._summary_form = QFormLayout(summary_box)
        self._value_labels: dict[str, QLabel] = {}
        self._summary_rows: dict[str, int] = {}
        for row, (key, label_text) in enumerate(_SUMMARY_LABELS.items()):
            value_label = QLabel("\u2014")
            self._value_labels[key] = value_label
            self._summary_rows[key] = row
            self._summary_form.addRow(QLabel(label_text), value_label)
        layout.addWidget(summary_box)

        actions = QHBoxLayout()

        self.open_folder_button = QPushButton("Open Output Folder")
        self.open_folder_button.setAccessibleName("Open output folder")
        self.open_folder_button.clicked.connect(self._open_output_folder)

        self.open_file_button = QPushButton("Open Final RIS")
        self.open_file_button.setAccessibleName("Open final RIS file")
        self.open_file_button.clicked.connect(self._open_final_file)

        self.view_failures_button = QPushButton("View Failure Report")
        self.view_failures_button.setAccessibleName("View failure report")
        self.view_failures_button.clicked.connect(self._open_failure_report)
        self.view_failures_button.setEnabled(False)

        self.new_project_button = QPushButton("Start New Project")
        self.new_project_button.setObjectName("PrimaryButton")
        self.new_project_button.setAccessibleName("Start a new project")
        self.new_project_button.clicked.connect(self.start_new_project.emit)

        for button in (
            self.open_folder_button,
            self.open_file_button,
            self.view_failures_button,
            self.new_project_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)

    def set_results(
        self,
        summary: dict,
        output_dir: Path,
        final_ris_path: Path | None,
        fail_report_path: Path | None,
    ) -> None:
        for key, label in self._value_labels.items():
            value = summary.get(key)
            label.setText(f"{value:,}" if isinstance(value, int) else "\u2014")

        # Keep the summary uncluttered for the common case: only show
        # "Skipped (unreadable records)" when there's actually
        # something to report, rather than a permanent "0" row.
        skipped = summary.get("skipped_malformed")
        row = self._summary_rows.get("skipped_malformed")
        if row is not None:
            self._summary_form.setRowVisible(row, bool(skipped))

        self._output_dir = output_dir
        self._final_ris_path = final_ris_path if final_ris_path and final_ris_path.exists() else None
        self._fail_report_path = (
            fail_report_path if fail_report_path and fail_report_path.exists() else None
        )

        self.open_file_button.setEnabled(self._final_ris_path is not None)
        self.view_failures_button.setEnabled(self._fail_report_path is not None)

    def _open_output_folder(self) -> None:
        if self._output_dir and self._output_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._output_dir)))
        else:
            QMessageBox.information(self, "Not found", "The output folder could not be found.")

    def _open_final_file(self) -> None:
        if self._final_ris_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._final_ris_path)))

    def _open_failure_report(self) -> None:
        if self._fail_report_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._fail_report_path)))
