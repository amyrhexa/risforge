"""Centralized GUI theming."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


LIGHT_PALETTE: dict[str, str] = {
    "bg": "#f4f5f7",
    "surface": "#ffffff",
    "surface_alt": "#eef0f3",
    "border": "#d6dae0",
    "text": "#1c2228",
    "text_muted": "#5b6472",
    "accent": "#2f5fd6",
    "accent_hover": "#2650b8",
    "accent_text": "#ffffff",
    "focus": "#2f5fd6",
}

DARK_PALETTE: dict[str, str] = {
    "bg": "#1b1e23",
    "surface": "#242830",
    "surface_alt": "#2c313a",
    "border": "#3b414c",
    "text": "#e8eaed",
    "text_muted": "#9aa3b0",
    "accent": "#5b8cf0",
    "accent_hover": "#79a1f4",
    "accent_text": "#0c1220",
    "focus": "#5b8cf0",
}


def _build_stylesheet(palette: dict[str, str]) -> str:
    """Render one palette into a Qt stylesheet."""
    return f"""
QWidget {{
    background-color: {palette["bg"]};
    color: {palette["text"]};
    font-size: 13px;
}}

QGroupBox {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: 6px;
    margin-top: 14px;
    padding: 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {palette["text"]};
}}

QLabel#HeaderTitle {{
    font-size: 22px;
    font-weight: 700;
}}

QLabel#HeaderSubtitle,
QLabel#HelperText,
QLabel#MutedLabel {{
    color: {palette["text_muted"]};
}}

QPushButton {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: 5px;
    padding: 6px 14px;
}}

QPushButton:hover {{
    border-color: {palette["accent"]};
}}

QPushButton:pressed {{
    background-color: {palette["surface_alt"]};
}}

QPushButton:disabled {{
    color: {palette["text_muted"]};
}}

QPushButton#PrimaryButton {{
    background-color: {palette["accent"]};
    color: {palette["accent_text"]};
    border: none;
    font-weight: 600;
    padding: 8px 20px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {palette["accent_hover"]};
}}

QLineEdit,
QSpinBox,
QDoubleSpinBox,
QComboBox {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: {palette["accent"]};
}}

QLineEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QComboBox:focus {{
    border: 1px solid {palette["focus"]};
}}

QTableView {{
    background-color: {palette["surface"]};
    alternate-background-color: {palette["surface_alt"]};
    gridline-color: {palette["border"]};
    border: 1px solid {palette["border"]};
    border-radius: 4px;
    selection-background-color: {palette["accent"]};
    selection-color: {palette["accent_text"]};
}}

QHeaderView::section {{
    background-color: {palette["surface_alt"]};
    color: {palette["text"]};
    border: none;
    border-bottom: 1px solid {palette["border"]};
    padding: 4px 6px;
    font-weight: 600;
}}

QProgressBar {{
    background-color: {palette["surface_alt"]};
    border: 1px solid {palette["border"]};
    border-radius: 4px;
    text-align: center;
    height: 18px;
}}

QProgressBar::chunk {{
    background-color: {palette["accent"]};
    border-radius: 3px;
}}

QPlainTextEdit#LogPanel {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: 4px;
    font-family: "Menlo", "Consolas", monospace;
    font-size: 12px;
}}

QToolButton {{
    border: none;
    color: {palette["text_muted"]};
}}

QToolButton:hover {{
    color: {palette["text"]};
}}
"""


def resolve_system_theme() -> Theme:
    """Detect OS light/dark preference when possible."""
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return Theme.DARK
    except Exception:
        pass

    return Theme.LIGHT


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Apply a theme to the application."""
    resolved = resolve_system_theme() if theme is Theme.SYSTEM else theme
    palette = DARK_PALETTE if resolved is Theme.DARK else LIGHT_PALETTE
    app.setStyleSheet(_build_stylesheet(palette))
