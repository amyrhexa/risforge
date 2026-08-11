"""Asynchronous record counting for the input files table.

Counting records requires actually parsing the file, so it's done off
the GUI thread via QThreadPool. The parsing itself is not
reimplemented here -- it's the exact same
``risforge.cleaning.parse_ris_records`` used by cleaning and merging,
so a file's reported record count always matches what merge/clean
will actually do with it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from risforge.cleaning import parse_ris_records


class _CounterSignals(QObject):
    finished = Signal(Path, int, int)  # path, record_count, malformed_block_count
    failed = Signal(Path, str)  # path, human-readable error message


class RecordCounter(QRunnable):
    """Counts records in one RIS file on a background thread pool."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        self.signals = _CounterSignals()

    def run(self) -> None:  # noqa: D102 -- QRunnable interface
        try:
            records, errors = parse_ris_records(self._path)
        except FileNotFoundError:
            self.signals.failed.emit(self._path, "File not found.")
        except OSError as error:
            self.signals.failed.emit(self._path, f"Could not read file: {error}")
        else:
            self.signals.finished.emit(self._path, len(records), len(errors))
