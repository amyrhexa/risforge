"""Enrichment configuration: email, cache location, and an Advanced section."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def default_cache_path() -> Path:
    """Sensible cross-platform default: a hidden folder under the user's home directory.

    Uses pathlib throughout rather than any OS-specific path literal.
    """
    return Path.home() / ".risforge" / "api_cache"


class EnrichmentConfigPanel(QGroupBox):
    """"Enrichment settings" group box."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Enrichment settings", parent)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("you@example.com")
        self.email_edit.setAccessibleName("Contact email for metadata enrichment")
        self.email_edit.textChanged.connect(lambda _text: self.changed.emit())
        email_label = QLabel("Contact email")
        email_label.setBuddy(self.email_edit)
        form.addRow(email_label, self.email_edit)

        email_help = QLabel(
            "Used as the contact address for scholarly metadata API requests "
            "(Crossref, OpenAlex, Unpaywall). It's sent with each request as required "
            "by those services' usage policies -- it isn't stored or used anywhere else."
        )
        email_help.setObjectName("HelperText")
        email_help.setWordWrap(True)
        form.addRow(QLabel(""), email_help)

        self.cache_edit = QLineEdit(str(default_cache_path()))
        self.cache_edit.setAccessibleName("API response cache location")
        cache_browse = QPushButton("Browse...")
        cache_browse.clicked.connect(self._browse_cache)
        cache_row = QHBoxLayout()
        cache_row.addWidget(self.cache_edit)
        cache_row.addWidget(cache_browse)
        cache_label = QLabel("Response cache")
        cache_label.setBuddy(self.cache_edit)
        form.addRow(cache_label, cache_row)

        layout.addLayout(form)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Show advanced settings \u25be")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setAccessibleName("Toggle advanced enrichment settings")
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        layout.addWidget(self.advanced_toggle)

        self.advanced_box = QWidget()
        advanced_form = QFormLayout(self.advanced_box)

        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 5.0)
        self.delay_spin.setSingleStep(0.05)
        self.delay_spin.setValue(0.1)
        self.delay_spin.setSuffix(" s")
        self.delay_spin.setAccessibleName("Delay between enrichment requests")
        delay_label = QLabel("Request delay")
        delay_label.setBuddy(self.delay_spin)
        advanced_form.addRow(delay_label, self.delay_spin)

        self.fail_report_edit = QLineEdit("failed_records.json")
        self.fail_report_edit.setAccessibleName("Failure report filename")
        fail_browse = QPushButton("Browse...")
        fail_browse.clicked.connect(self._browse_fail_report)
        fail_row = QHBoxLayout()
        fail_row.addWidget(self.fail_report_edit)
        fail_row.addWidget(fail_browse)
        fail_label = QLabel("Failure report")
        fail_label.setBuddy(self.fail_report_edit)
        advanced_form.addRow(fail_label, fail_row)

        layout.addWidget(self.advanced_box)
        self.advanced_box.setVisible(False)

    def _toggle_advanced(self, checked: bool) -> None:
        self.advanced_box.setVisible(checked)
        self.advanced_toggle.setText(
            "Hide advanced settings \u25b4" if checked else "Show advanced settings \u25be"
        )

    def _browse_cache(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose a cache folder", str(Path(self.cache_edit.text()).parent)
        )
        if folder:
            self.cache_edit.setText(str(Path(folder) / "api_cache"))

    def _browse_fail_report(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(
            self, "Choose failure report location", self.fail_report_edit.text(), "JSON files (*.json)"
        )
        if path:
            self.fail_report_edit.setText(path)

    # --- Values ------------------------------------------------------------------

    def email(self) -> str:
        return self.email_edit.text().strip()

    def cache_path(self) -> Path:
        return Path(self.cache_edit.text().strip() or str(default_cache_path()))

    def request_delay_seconds(self) -> float:
        return self.delay_spin.value()

    def fail_report_name(self) -> str:
        return self.fail_report_edit.text().strip() or "failed_records.json"
