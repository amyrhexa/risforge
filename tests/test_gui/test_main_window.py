from __future__ import annotations

from pathlib import Path

from risforge import PipelineResult
from risforge_gui.main_window import MainWindow
from risforge_gui.worker import OperationMode


class TestApplicationStartsAndLoads:
    def test_main_window_loads(self, qtbot) -> None:
        window = MainWindow()
        qtbot.addWidget(window)

        assert window.windowTitle() == "risforge"
        assert window.stack.count() == 3
        assert window.stack.currentWidget() is window.setup_page

    def test_header_shows_the_real_package_version(self, qtbot) -> None:
        import risforge as risforge_core

        window = MainWindow()
        qtbot.addWidget(window)

        # Not hardcoded in the GUI -- pulled from the installed core package.
        version_labels = [
            w
            for w in window.findChildren(object)
            if getattr(w, "objectName", lambda: "")() == "VersionLabel"
        ]
        assert len(version_labels) == 1
        assert risforge_core.__version__ in version_labels[0].text()


class TestFilesCanBeAddedAndRemoved:
    def test_add_files_updates_table(self, qtbot, two_ris_files) -> None:
        window = MainWindow()
        qtbot.addWidget(window)

        window.input_panel.add_dropped_paths(two_ris_files)

        assert window.input_panel.model.rowCount() == 2

    def test_remove_files_updates_table(self, qtbot, two_ris_files) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths(two_ris_files)

        window.input_panel.table.selectRow(0)
        window.input_panel.remove_selected()

        assert window.input_panel.model.rowCount() == 1


class TestModeAdaptsUI:
    def test_pipeline_mode_shows_enrichment_settings(self, qtbot) -> None:
        window = MainWindow()
        qtbot.addWidget(window)

        window.mode_combo.setCurrentIndex(0)  # Full Pipeline

        assert window.enrichment_panel.isVisibleTo(window.setup_page.widget())

    def test_merge_mode_hides_enrichment_settings(self, qtbot) -> None:
        window = MainWindow()
        qtbot.addWidget(window)

        merge_index = [i for i, (_l, m) in enumerate(_mode_items()) if m is OperationMode.MERGE][0]
        window.mode_combo.setCurrentIndex(merge_index)

        assert not window.enrichment_panel.isVisibleTo(window.setup_page.widget())


class TestConfigGeneration:
    def test_pipeline_config_for_single_file(self, qtbot, one_ris_file, tmp_path) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])
        window.enrichment_panel.email_edit.setText("me@example.com")
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))

        config = window._gather_config()

        assert config is not None
        assert config.mode is OperationMode.PIPELINE
        assert config.input_paths == [one_ris_file]
        assert config.email == "me@example.com"
        assert config.enriched_output_path == tmp_path / "out" / "enriched.ris"
        assert config.dedup_output_path == tmp_path / "out" / "clean.ris"

    def test_pipeline_config_for_multiple_files_includes_merge_path(
        self, qtbot, two_ris_files, tmp_path
    ) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths(two_ris_files)
        window.enrichment_panel.email_edit.setText("me@example.com")
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))

        config = window._gather_config()

        assert config is not None
        assert config.merge_output_path == tmp_path / "out" / "merged.ris"

    def test_missing_email_blocks_pipeline_start(self, qtbot, one_ris_file, tmp_path, monkeypatch) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))
        # email left blank

        warnings = []
        monkeypatch.setattr(
            "risforge_gui.main_window.QMessageBox.warning",
            lambda *a, **k: warnings.append(a),
        )

        config = window._gather_config()

        assert config is None
        assert len(warnings) == 1

    def test_no_input_files_blocks_start(self, qtbot, tmp_path, monkeypatch) -> None:
        window = MainWindow()
        qtbot.addWidget(window)

        warnings = []
        monkeypatch.setattr(
            "risforge_gui.main_window.QMessageBox.warning",
            lambda *a, **k: warnings.append(a),
        )

        config = window._gather_config()

        assert config is None
        assert len(warnings) == 1

    def test_clean_mode_requires_exactly_one_file(self, qtbot, two_ris_files, tmp_path, monkeypatch) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths(two_ris_files)
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))
        clean_index = [i for i, (_l, m) in enumerate(_mode_items()) if m is OperationMode.CLEAN][0]
        window.mode_combo.setCurrentIndex(clean_index)

        warnings = []
        monkeypatch.setattr(
            "risforge_gui.main_window.QMessageBox.warning",
            lambda *a, **k: warnings.append(a),
        )

        config = window._gather_config()

        assert config is None
        assert len(warnings) == 1

    def test_fail_report_relative_name_resolves_under_output_dir(
        self, qtbot, one_ris_file, tmp_path
    ) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])
        window.enrichment_panel.email_edit.setText("me@example.com")
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))
        window.enrichment_panel.fail_report_edit.setText("failed_records.json")

        config = window._gather_config()

        assert config is not None
        assert config.fail_report_path == tmp_path / "out" / "failed_records.json"


class TestStartToResultsFlow:
    def test_successful_pipeline_run_updates_results_view(
        self, qtbot, one_ris_file, tmp_path, monkeypatch
    ) -> None:
        def fake_risforge(
            input_paths,
            dedup_path,
            enriched_path,
            email,
            merge_path,
            fail_report_path,
            on_stage,
            enrichment_progress,
        ):
            on_stage("clean", "started")
            on_stage("clean", "completed")
            on_stage("enrich", "started")
            enrichment_progress(1, 1)
            on_stage("enrich", "completed")
            Path(dedup_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")
            Path(enriched_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")
            return PipelineResult(
                cleaned_record_count=1,
                cleaning_errors=[],
                enrichment_stats={"processed": 1, "enriched": 1, "failed": 0},
                input_file_count=1,
                merged_record_count=None,
                merge_path=None,
                dedup_path=Path(dedup_path),
                enriched_path=Path(enriched_path),
            )

        monkeypatch.setattr("risforge_gui.worker.risforge", fake_risforge)

        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])
        qtbot.waitUntil(lambda: window.input_panel.model.total_known_records() == 5, timeout=5000)
        window.enrichment_panel.email_edit.setText("me@example.com")
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))

        window._on_start_clicked()
        assert window.stack.currentWidget() is window.progress_panel

        qtbot.waitUntil(lambda: window.stack.currentWidget() is window.results_panel, timeout=5000)
        window.worker.wait()

        assert window.results_panel._value_labels["unique_records"].text() == "1"
        assert window.results_panel._value_labels["enriched_records"].text() == "1"

    def test_error_during_run_shows_dialog_and_returns_to_setup(
        self, qtbot, one_ris_file, tmp_path, monkeypatch
    ) -> None:
        def fake_risforge(*args, **kwargs):
            raise FileNotFoundError("Input file 'missing.ris' not found.")

        monkeypatch.setattr("risforge_gui.worker.risforge", fake_risforge)

        shown_errors = []
        monkeypatch.setattr(
            "risforge_gui.main_window.show_error_dialog",
            lambda *args, **kwargs: shown_errors.append(args),
        )

        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])
        window.enrichment_panel.email_edit.setText("me@example.com")
        window.output_panel.output_dir_edit.setText(str(tmp_path / "out"))

        window._on_start_clicked()

        qtbot.waitUntil(lambda: len(shown_errors) == 1, timeout=5000)
        window.worker.wait()

        assert window.stack.currentWidget() is window.setup_page


class TestStartNewProject:
    def test_clears_input_files_and_returns_to_setup(self, qtbot, one_ris_file) -> None:
        window = MainWindow()
        qtbot.addWidget(window)
        window.input_panel.add_dropped_paths([one_ris_file])

        window._on_start_new_project()

        assert window.input_panel.model.rowCount() == 0
        assert window.stack.currentWidget() is window.setup_page


def _mode_items():
    from risforge_gui.main_window import _MODE_ITEMS

    return _MODE_ITEMS
