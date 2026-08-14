"""Timestamped, level-colored activity log."""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit

_MAX_LINES = 2000

_LEVEL_COLORS = {
    "INFO": None,  # inherit default text color
    "WARNING": "#c98a1a",
    "ERROR": "#d13a3a",
}


class LogPanel(QPlainTextEdit):
    """Read-only, append-only activity log. Never shows raw tracebacks."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LogPanel")
        self.setReadOnly(True)
        self.setMaximumBlockCount(_MAX_LINES)
        self.setAccessibleName("Activity log")

    def append_log(self, level: str, message: str) -> None:
        """Append one timestamped, level-colored line.

        Renders as HTML (not plain text) so WARNING/ERROR lines can be
        colored -- ``message`` is escaped first since it may contain
        arbitrary file paths or error text from risforge itself.
        ``setMaximumBlockCount`` above caps memory use on a very long
        or noisy run by silently dropping the oldest lines.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_message = html.escape(message)
        color = _LEVEL_COLORS.get(level.upper())
        line = f"{timestamp}  {safe_message}"
        if color:
            line = f'<span style="color:{color}">{line}</span>'
        self.appendHtml(line)
