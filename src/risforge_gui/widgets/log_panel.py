"""Activity log panel."""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtWidgets import QPlainTextEdit

_MAX_LINES = 2000

_LEVEL_COLORS = {
    "INFO": None,
    "WARNING": "#c98a1a",
    "ERROR": "#d13a3a",
}


class LogPanel(QPlainTextEdit):
    """Read-only activity log."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("LogPanel")
        self.setReadOnly(True)
        self.setMaximumBlockCount(_MAX_LINES)
        self.setAccessibleName("Activity log")

    def append_log(self, level: str, message: str) -> None:
        """Append one timestamped log line."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_message = html.escape(message)
        color = _LEVEL_COLORS.get(level.upper())

        line = f"{timestamp}  {safe_message}"

        if color:
            line = f'<span style="color:{color}">{line}</span>'

        self.appendHtml(line)
