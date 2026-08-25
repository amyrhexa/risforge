"""Input-files panel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
)

from risforge_gui.file_counter import RecordCounter
from risforge_gui.models import InputFilesModel


class InputPanel(QGroupBox):
    """Panel for adding, removing, and reviewing RIS input files."""

    files_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Input files", parent)
        self.setAcceptDrops(True)

        self.model = InputFilesModel(self)
        self.model.rowsInserted.connect(lambda *_: self.files_changed.emit())
        self.model.rowsRemoved.connect(lambda *_: self.files_changed.emit())
        self.model.modelReset.connect(self.files_changed.emit)

        self._thread_pool = QThreadPool.globalInstance()

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Add one or more .ris files. Drag and drop files here, or use the buttons below."
        )
        hint.setObjectName("HelperText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(140)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()

        self.add_files_button = QPushButton("Add Files...")
        self.add_files_button.clicked.connect(self.add_files_dialog)

        self.add_folder_button = QPushButton("Add Folder...")
        self.add_folder_button.clicked.connect(self.add_folder_dialog)

        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_selected)

        self.clear_button = QPushButton("Clear All")
        self.clear_button.clicked.connect(self.clear_all)

        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            button_row.addWidget(button)

        button_row.addStretch(1)
        layout.addLayout(button_row)

    def add_files_dialog(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(
            self,
            "Add RIS files",
            str(Path.home()),
            "RIS files (*.ris);;All files (*)",
        )

        self._add_paths([Path(path) for path in paths])

    def add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Add folder of RIS files",
            str(Path.home()),
        )

        if not folder:
            return

        found = sorted(
            path
            for path in Path(folder).iterdir()
            if path.is_file() and path.suffix.lower() == ".ris"
        )

        if not found:
            QMessageBox.information(
                self,
                "No RIS files found",
                f"No .ris files were found directly inside:\n{folder}",
            )
            return

        self._add_paths(found)

    def add_dropped_paths(self, paths: list[Path]) -> None:
        """Entry point for drag-and-drop."""
        ris_paths = [path for path in paths if path.suffix.lower() == ".ris"]
        rejected = [path for path in paths if path.suffix.lower() != ".ris"]

        if rejected:
            names = ", ".join(path.name for path in rejected)
            QMessageBox.warning(
                self,
                "Unsupported file type",
                f"Only .ris files are supported. These were not added:\n{names}",
            )

        if ris_paths:
            self._add_paths(ris_paths)

    def remove_selected(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        self.model.remove_rows(list(rows))

    def clear_all(self) -> None:
        self.model.clear()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]

        if paths:
            self.add_dropped_paths(paths)

        event.acceptProposedAction()

    def _add_paths(self, paths: list[Path]) -> None:
        added = self.model.add_paths(paths)

        for path in added:
            counter = RecordCounter(path)
            counter.signals.finished.connect(self._on_count_finished)
            counter.signals.failed.connect(self._on_count_failed)
            self._thread_pool.start(counter)

    def _on_count_finished(self, path: Path, record_count: int, malformed_count: int) -> None:
        self.model.set_record_count(path, record_count)

    def _on_count_failed(self, path: Path, message: str) -> None:
        self.model.set_error(path, message)
