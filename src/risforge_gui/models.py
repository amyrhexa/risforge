"""Table model for input RIS files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


@dataclass
class InputFileEntry:
    """One input-file row."""

    path: Path
    record_count: int | None = None
    status: str = "Counting..."
    error_message: str | None = None


class InputFilesModel(QAbstractTableModel):
    """Model for File | Records | Status."""

    COLUMNS = ("File", "Records", "Status")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[InputFileEntry] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._entries)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return display, tooltip, or alignment data."""
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

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 0:
                return str(entry.path)
            if column == 2 and entry.error_message:
                return entry.error_message

        if role == Qt.ItemDataRole.TextAlignmentRole and column == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def paths(self) -> list[Path]:
        return [entry.path for entry in self._entries]

    def is_present(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(entry.path.resolve() == resolved for entry in self._entries)

    def add_paths(self, paths: list[Path]) -> list[Path]:
        """Add files, skipping duplicates."""
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

    def total_known_records(self) -> int | None:
        """Sum record counts, or None while any file is pending."""
        if any(entry.record_count is None for entry in self._entries):
            return None

        return sum(entry.record_count or 0 for entry in self._entries)

    def _update_row(self, path: Path, **fields) -> None:
        resolved = path.resolve()

        for row, entry in enumerate(self._entries):
            if entry.path.resolve() != resolved:
                continue

            for key, value in fields.items():
                setattr(entry, key, value)

            top_left = self.index(row, 0)
            bottom_right = self.index(row, len(self.COLUMNS) - 1)
            self.dataChanged.emit(top_left, bottom_right)
            return
