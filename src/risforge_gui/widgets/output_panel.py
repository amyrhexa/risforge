"""Output configuration: destination directory and file names.

All paths are built with pathlib.Path and a user-chosen directory
(via native file dialogs) -- nothing here assumes a Windows, Linux, or
macOS path layout.
"""

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
    QWidget,
)


def default_output_dir() -> Path:
    """A new, dedicated folder -- never an input file's own directory.

    Chosen so a first-time user never has to think about output
    placement, and so risforge never writes next to (let alone over)
    the files they dropped in.
    """
    return Path.home() / "risforge-output"


class OutputConfigPanel(QGroupBox):
    """ "Output" group box: destination directory, final filename, optional intermediates."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
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
        self.keep_merged_check.setAccessibleName("Keep intermediate merged file")
        layout.addWidget(self.keep_merged_check)

        self.keep_cleaned_check = QCheckBox("Keep the cleaned (deduplicated) file")
        self.keep_cleaned_check.setChecked(True)
        self.keep_cleaned_check.setAccessibleName("Keep intermediate cleaned file")
        layout.addWidget(self.keep_cleaned_check)

        note = QLabel(
            "Outputs are always written to new files here -- your original input files "
            "are never modified."
        )
        note.setObjectName("HelperText")
        note.setWordWrap(True)
        layout.addWidget(note)

    def _browse_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose an output folder", self.output_dir_edit.text()
        )
        if folder:
            self.output_dir_edit.setText(folder)

    # --- Resolved paths -------------------------------------------------------

    def output_dir(self) -> Path:
        text = self.output_dir_edit.text().strip()
        return Path(text) if text else default_output_dir()

    def final_ris_path(self) -> Path:
        name = self.final_name_edit.text().strip() or "enriched.ris"
        return self.output_dir() / name

    def merged_path(self) -> Path:
        return self.output_dir() / "merged.ris"

    def cleaned_path(self) -> Path:
        return self.output_dir() / "clean.ris"

    def keep_merged(self) -> bool:
        return self.keep_merged_check.isChecked()

    def keep_cleaned(self) -> bool:
        return self.keep_cleaned_check.isChecked()
