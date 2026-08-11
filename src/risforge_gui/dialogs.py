"""Error and confirmation dialogs.

Errors are always shown with a plain-language message first. Technical
detail (exception repr / traceback) is available but hidden behind
Qt's built-in "Show Details..." expander -- never shown by default.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error_dialog(
    parent: QWidget | None,
    title: str,
    message: str,
    details: str = "",
    affected_file: str = "",
) -> None:
    """Show a human-readable error, with technical details available on demand."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("risforge")
    box.setText(title)

    informative = message
    if affected_file:
        informative = f"File: {affected_file}\n\n{message}"
    box.setInformativeText(informative)

    if details:
        box.setDetailedText(details)

    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def confirm_overwrite(parent: QWidget | None, path: Path) -> bool:
    """Ask before overwriting an existing output file. Defaults to No (safe)."""
    result = QMessageBox.question(
        parent,
        "File already exists",
        f"A file already exists at:\n{path}\n\nOverwrite it?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return result == QMessageBox.StandardButton.Yes
