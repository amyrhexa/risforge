"""Centralized theming for risforge_gui.

All colors live here, as two flat palettes (light/dark), rendered into
one Qt stylesheet template. No widget module should hardcode a color
-- if something needs a new color, it's added to both palettes here.

System-theme detection uses Qt's own color-scheme hint (available
since Qt 6.5) and falls back to light if that's unavailable, rather
than guessing at OS-specific mechanisms.
"""

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
    "success": "#1a7f37",
    "warning": "#8a5b00",
    "warning_bg": "#fff3d6",
    "danger": "#c22233",
    "danger_bg": "#fdecec",
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
    "success": "#3fb968",
    "warning": "#e0ac41",
    "warning_bg": "#3a2f14",
    "danger": "#f0616e",
    "danger_bg": "#3a1c20",
    "focus": "#5b8cf0",
}


def _build_stylesheet(p: dict[str, str]) -> str:
    """Render a palette dict into a Qt stylesheet.

    Kept as one template so the two palettes can never drift into
    inconsistent selectors -- only the color values differ.
    """
    return f"""
    QWidget {{
        background-color: {p['bg']};
        color: {p['text']};
        font-size: 13px;
    }}

    QMainWindow, #SetupPage, #ProgressPage, #ResultsPage {{
        background-color: {p['bg']};
    }}

    QGroupBox {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 6px;
        margin-top: 14px;
        padding: 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {p['text']};
    }}

    QLabel#HeaderTitle {{
        font-size: 22px;
        font-weight: 700;
    }}
    QLabel#HeaderSubtitle, QLabel#MutedLabel, QLabel#HelperText {{
        color: {p['text_muted']};
    }}
    QLabel#VersionLabel {{
        color: {p['text_muted']};
        font-size: 11px;
    }}
    QLabel#SectionHeading {{
        font-size: 14px;
        font-weight: 600;
    }}

    QPushButton {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 5px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        border-color: {p['accent']};
    }}
    QPushButton:pressed {{
        background-color: {p['surface_alt']};
    }}
    QPushButton:disabled {{
        color: {p['text_muted']};
    }}
    QPushButton#PrimaryButton {{
        background-color: {p['accent']};
        color: {p['accent_text']};
        border: none;
        font-weight: 600;
        padding: 8px 20px;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {p['accent_hover']};
    }}
    QPushButton#PrimaryButton:disabled {{
        background-color: {p['border']};
        color: {p['text_muted']};
    }}

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {p['accent']};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {p['focus']};
    }}
    QLineEdit:read-only {{
        color: {p['text_muted']};
    }}

    QTableView {{
        background-color: {p['surface']};
        alternate-background-color: {p['surface_alt']};
        gridline-color: {p['border']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        selection-background-color: {p['accent']};
        selection-color: {p['accent_text']};
    }}
    QHeaderView::section {{
        background-color: {p['surface_alt']};
        color: {p['text']};
        border: none;
        border-bottom: 1px solid {p['border']};
        padding: 4px 6px;
        font-weight: 600;
    }}

    QProgressBar {{
        background-color: {p['surface_alt']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        text-align: center;
        height: 18px;
    }}
    QProgressBar::chunk {{
        background-color: {p['accent']};
        border-radius: 3px;
    }}

    QPlainTextEdit#LogPanel {{
        background-color: {p['surface']};
        border: 1px solid {p['border']};
        border-radius: 4px;
        font-family: "Menlo", "Consolas", monospace;
        font-size: 12px;
    }}

    QToolButton {{
        border: none;
        color: {p['text_muted']};
    }}
    QToolButton:hover {{
        color: {p['text']};
    }}

    QScrollArea {{
        border: none;
    }}

    /* Visible keyboard focus outline everywhere, for accessibility */
    *:focus {{
        outline: none;
    }}
    QPushButton:focus, QComboBox:focus, QCheckBox:focus {{
        border: 2px solid {p['focus']};
    }}
    """


def resolve_system_theme() -> Theme:
    """Best-effort detection of the OS light/dark preference.

    Uses Qt's own color-scheme hint (Qt >= 6.5). Falls back to light
    mode if the platform doesn't report one, rather than guessing at
    OS-specific APIs.
    """
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return Theme.DARK
    except Exception:  # noqa: BLE001 -- best-effort detection only.
        pass
    return Theme.LIGHT


def apply_theme(app: QApplication, theme: Theme) -> None:
    """Apply a theme (or resolve+apply the system theme) to the whole app."""
    resolved = resolve_system_theme() if theme is Theme.SYSTEM else theme
    palette = DARK_PALETTE if resolved is Theme.DARK else LIGHT_PALETTE
    app.setStyleSheet(_build_stylesheet(palette))
