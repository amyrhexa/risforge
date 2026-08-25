from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from risforge_gui.widgets.input_panel import InputPanel


class TestAddFiles:
    def test_add_dropped_paths_adds_valid_ris_files(self, qtbot, two_ris_files) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)

        panel.add_dropped_paths(two_ris_files)

        assert panel.model.rowCount() == 2

    def test_record_counts_populate_asynchronously(self, qtbot, one_ris_file) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)

        panel.add_dropped_paths([one_ris_file])

        # sample.ris (bundled fixture) has 5 records.
        qtbot.waitUntil(lambda: panel.model.total_known_records() == 5, timeout=5000)

    def test_non_utf8_file_reports_an_error_instead_of_hanging(self, qtbot, tmp_path) -> None:
        """Regression test: RecordCounter.run() must catch ValueError too.

        parse_ris_records() raises RisParsingError (a ValueError
        subclass) for a file it can't decode as text. Before this fix,
        that would raise uncaught out of the QThreadPool worker, and
        the row would stay stuck at "Counting..." forever with no
        visible error -- catching only OSError missed it.
        """
        bad_path = tmp_path / "bad_encoding.ris"
        bad_path.write_bytes(b"TY  - JOUR\nTI  - Bad \xff\xfe byte sequence\nER  - \n")

        panel = InputPanel()
        qtbot.addWidget(panel)
        panel.add_dropped_paths([bad_path])

        row = panel.model.index(0, 2)
        qtbot.waitUntil(lambda: row.data() == "Error", timeout=5000)

    def test_files_changed_signal_fires_on_add(self, qtbot, one_ris_file) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)

        with qtbot.waitSignal(panel.files_changed, timeout=1000):
            panel.add_dropped_paths([one_ris_file])


class TestRejectInvalidFiles:
    def test_non_ris_files_are_rejected(self, qtbot, tmp_path, monkeypatch) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)

        # Avoid blocking on a real modal dialog during the test.
        warnings = []
        monkeypatch.setattr(
            "risforge_gui.widgets.input_panel.QMessageBox.warning",
            lambda *args, **kwargs: warnings.append(args) or QMessageBox.StandardButton.Ok,
        )

        bad_file = tmp_path / "notes.txt"
        bad_file.write_text("not a RIS file")

        panel.add_dropped_paths([bad_file])

        assert panel.model.rowCount() == 0
        assert len(warnings) == 1

    def test_mixed_valid_and_invalid_files(
        self, qtbot, tmp_path, one_ris_file, monkeypatch
    ) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)
        monkeypatch.setattr(
            "risforge_gui.widgets.input_panel.QMessageBox.warning", lambda *a, **k: None
        )


class TestRemoveAndClear:
    def test_remove_selected(self, qtbot, two_ris_files) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)
        panel.add_dropped_paths(two_ris_files)

        panel.table.selectRow(0)
        panel.remove_selected()

        assert panel.model.rowCount() == 1
        assert panel.model.paths() == [two_ris_files[1]]

    def test_clear_all(self, qtbot, two_ris_files) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)
        panel.add_dropped_paths(two_ris_files)

        panel.clear_all()

        assert panel.model.rowCount() == 0


class TestDuplicatePrevention:
    def test_adding_the_same_path_twice_is_a_no_op(self, qtbot, one_ris_file) -> None:
        panel = InputPanel()
        qtbot.addWidget(panel)

        panel.add_dropped_paths([one_ris_file])
        panel.add_dropped_paths([one_ris_file])

        assert panel.model.rowCount() == 1
