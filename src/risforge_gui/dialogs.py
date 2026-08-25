"""Error and confirmation dialogs."""

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
    """Show a human-readable error with optional technical details."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle("risforge")
    box.setText(title)

    informative = message
    if affected_file:
        informative = f"File: {affected_file}\n{message}"

    box.setInformativeText(informative)

    if details:
        box.setDetailedText(details)

    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.exec()


def confirm_overwrite(parent: QWidget | None, path: Path) -> bool:
    """Ask before overwriting an existing file."""
    result = QMessageBox.question(
        parent,
        "File already exists",
        f"A file already exists at:\n{path}\n\nOverwrite it?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )

    return result == QMessageBox.StandardButton.Yes
