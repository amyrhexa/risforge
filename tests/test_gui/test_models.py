from __future__ import annotations

from risforge_gui.models import InputFilesModel


class TestInputFilesModel:
    def test_add_paths(self, two_ris_files) -> None:
        model = InputFilesModel()
        added = model.add_paths(two_ris_files)

        assert added == two_ris_files
        assert model.rowCount() == 2
        assert model.paths() == two_ris_files

    def test_skips_duplicate_paths(self, one_ris_file) -> None:
        model = InputFilesModel()
        model.add_paths([one_ris_file])
        added_again = model.add_paths([one_ris_file])

        assert added_again == []
        assert model.rowCount() == 1

    def test_remove_rows(self, two_ris_files) -> None:
        model = InputFilesModel()
        model.add_paths(two_ris_files)

        model.remove_rows([0])

        assert model.rowCount() == 1
        assert model.paths() == [two_ris_files[1]]

    def test_clear(self, two_ris_files) -> None:
        model = InputFilesModel()
        model.add_paths(two_ris_files)

        model.clear()

        assert model.rowCount() == 0

    def test_set_record_count_updates_status(self, one_ris_file) -> None:
        model = InputFilesModel()
        model.add_paths([one_ris_file])

        model.set_record_count(one_ris_file, 5)

        index = model.index(0, 1)
        assert model.data(index) == "5"
        status_index = model.index(0, 2)
        assert model.data(status_index) == "Ready"

    def test_set_error_updates_status(self, one_ris_file) -> None:
        model = InputFilesModel()
        model.add_paths([one_ris_file])

        model.set_error(one_ris_file, "boom")

        status_index = model.index(0, 2)
        assert model.data(status_index) == "Error"

    def test_total_known_records_none_while_pending(self, two_ris_files) -> None:
        model = InputFilesModel()
        model.add_paths(two_ris_files)

        assert model.total_known_records() is None

        model.set_record_count(two_ris_files[0], 3)
        assert model.total_known_records() is None  # second still pending

        model.set_record_count(two_ris_files[1], 4)
        assert model.total_known_records() == 7
