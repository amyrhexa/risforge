"""Output configuration panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


def default_output_dir() -> Path:
    """Default output directory."""
    return Path.home() / "risforge-output"


class OutputConfigPanel(QGroupBox):
    """Output destination and intermediate-file options."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Output", parent)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.output_dir_edit = QLineEdit(str(default_output_dir()))
        self.output_dir_edit.setAccessibleName("Output directory")
        self.output_dir_edit.textChanged.connect(lambda _text: self.changed.emit())

        browse_dir = QPushButton("Browse...")
        browse_dir.clicked.connect(self._browse_output_dir)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self.output_dir_edit)
        dir_row.addWidget(browse_dir)

        dir_label = QLabel("Output folder")
        dir_label.setBuddy(self.output_dir_edit)
        form.addRow(dir_label, dir_row)

        self.final_name_edit = QLineEdit("enriched.ris")
        self.final_name_edit.setAccessibleName("Final RIS filename")

        final_label = QLabel("Final file name")
        final_label.setBuddy(self.final_name_edit)
        form.addRow(final_label, self.final_name_edit)

        layout.addLayout(form)

        self.keep_merged_check = QCheckBox("Keep the merged (pre-deduplication) file")
        layout.addWidget(self.keep_merged_check)

        self.keep_cleaned_check = QCheckBox("Keep the cleaned (deduplicated) file")
        self.keep_cleaned_check.setChecked(True)
        layout.addWidget(self.keep_cleaned_check)

        note = QLabel("Original input files are never modified.")
        note.setObjectName("HelperText")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _browse_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose an output folder",
            self.output_dir_edit.text(),
        )

        if folder:
            self.output_dir_edit.setText(folder)

    def output_dir(self) -> Path:
        text = self.output_dir_edit.text().strip()
        return Path(text) if text else default_output_dir()

    def final_ris_path(self) -> Path:
        name = self.final_name_edit.text().strip() or "enriched.ris"

        if not name.lower().endswith(".ris"):
            name += ".ris"

        return self.output_dir() / name

    def merged_path(self) -> Path:
        return self.output_dir() / "merged.ris"

    def cleaned_path(self) -> Path:
        return self.output_dir() / "clean.ris"

    def keep_merged(self) -> bool:
        return self.keep_merged_check.isChecked()

    def keep_cleaned(self) -> bool:
        return self.keep_cleaned_check.isChecked()
