"""Asynchronous RIS record counting."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from risforge.cleaning import parse_ris_records


class _CounterSignals(QObject):
    finished = Signal(Path, int, int)
    failed = Signal(Path, str)


class RecordCounter(QRunnable):
    """Counts records in one RIS file on a background thread."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self.signals = _CounterSignals()

    def run(self) -> None:
        try:
            records, errors = parse_ris_records(self._path)
        except FileNotFoundError:
            self.signals.failed.emit(self._path, "File not found.")
        except (OSError, ValueError) as error:
            self.signals.failed.emit(self._path, f"Could not read file: {error}")
        else:
            self.signals.finished.emit(self._path, len(records), len(errors))
