"""Table model for the list of input RIS files.

Deliberately does not parse or count records itself -- that's done
asynchronously by :mod:`risforge_gui.file_counter`, which calls
``risforge.cleaning.parse_ris_records`` and reports back into this
model. This module only tracks display state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass
class InputFileEntry:
    path: Path
    record_count: int | None = None  # None while counting is in progress.
    status: str = "Counting..."
    error_message: str | None = None


class InputFilesModel(QAbstractTableModel):
    """Backs the input-files QTableView: File | Records | Status."""

    COLUMNS = ("File", "Records", "Status")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[InputFileEntry] = []

    # --- Qt model interface -----------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        entry = self._entries[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return entry.path.name
            if column == 1:
                return "Counting..." if entry.record_count is None else f"{entry.record_count:,}"
            if column == 2:
                return entry.status
        elif role == Qt.ItemDataRole.ToolTipRole:
            if column == 0:
                return str(entry.path)
            if column == 2 and entry.error_message:
                return entry.error_message
        elif role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index: QModelIndex):  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    # --- Domain-specific API -----------------------------------------------

    def paths(self) -> list[Path]:
        return [entry.path for entry in self._entries]

    def is_present(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(entry.path.resolve() == resolved for entry in self._entries)

    def add_paths(self, paths: list[Path]) -> list[Path]:
        """Add new files, skipping any already present. Returns what was actually added."""
        added: list[Path] = []
        new_entries = []
        for path in paths:
            if self.is_present(path):
                continue
            new_entries.append(InputFileEntry(path=path))
            added.append(path)

        if new_entries:
            start = len(self._entries)
            self.beginInsertRows(QModelIndex(), start, start + len(new_entries) - 1)
            self._entries.extend(new_entries)
            self.endInsertRows()
        return added

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._entries):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._entries[row]
                self.endRemoveRows()

    def clear(self) -> None:
        if not self._entries:
            return
        self.beginResetModel()
        self._entries.clear()
        self.endResetModel()

    def set_record_count(self, path: Path, count: int) -> None:
        self._update_row(path, record_count=count, status="Ready", error_message=None)

    def set_error(self, path: Path, message: str) -> None:
        self._update_row(path, record_count=None, status="Error", error_message=message)

    def _update_row(self, path: Path, **fields) -> None:
        resolved = path.resolve()
        for row, entry in enumerate(self._entries):
            if entry.path.resolve() == resolved:
                for key, value in fields.items():
                    setattr(entry, key, value)
                top_left = self.index(row, 0)
                bottom_right = self.index(row, len(self.COLUMNS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
                return

    def total_known_records(self) -> int | None:
        """Sum of record counts for entries that finished counting, or None if any are still pending/errored."""
        if any(entry.record_count is None for entry in self._entries):
            return None
        return sum(entry.record_count or 0 for entry in self._entries)
