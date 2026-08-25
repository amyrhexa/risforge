from __future__ import annotations

from pathlib import Path

from risforge import MergeResult, PipelineResult
from risforge_gui.worker import OperationMode, PipelineConfig, PipelineWorker


def _run_and_wait(qtbot, worker: PipelineWorker) -> None:
    """Start a worker and block until its OS thread has fully terminated.

    Waiting on QThread's own `finished` signal (rather than only our
    custom `finished_ok`/`error_occurred` signals) avoids a
    "QThread: Destroyed while thread is still running" abort: our
    custom signals are emitted from inside run(), slightly before the
    thread has actually finished tearing down.
    """
    with qtbot.waitSignal(worker.finished, timeout=5000):
        worker.start()
    worker.wait()


class TestMergeMode:
    def test_calls_merge_ris_files_and_emits_finished(
        self, qtbot, two_ris_files, tmp_path, monkeypatch
    ) -> None:
        calls = []

        def fake_merge(input_paths, output_path):
            calls.append((list(input_paths), Path(output_path)))
            Path(output_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")
            return MergeResult(
                input_file_count=len(input_paths), record_count=10, output_path=Path(output_path)
            )

        monkeypatch.setattr("risforge_gui.worker.merge_ris_files", fake_merge)

        config = PipelineConfig(
            mode=OperationMode.MERGE,
            input_paths=two_ris_files,
            merge_output_path=tmp_path / "merged.ris",
        )
        worker = PipelineWorker(config)
        results = []
        worker.finished_ok.connect(lambda r: results.append(r))

        _run_and_wait(qtbot, worker)

        assert len(results) == 1
        assert isinstance(results[0], MergeResult)
        assert results[0].record_count == 10
        assert calls[0][0] == two_ris_files


class TestCleanMode:
    def test_calls_clean_ris_file(self, qtbot, one_ris_file, tmp_path, monkeypatch) -> None:
        def fake_clean(input_path, output_path):
            Path(output_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")
            return ([{"title": "A"}, {"title": "B"}], [])

        monkeypatch.setattr("risforge_gui.worker.clean_ris_file", fake_clean)

        config = PipelineConfig(
            mode=OperationMode.CLEAN,
            input_paths=[one_ris_file],
            dedup_output_path=tmp_path / "clean.ris",
        )
        worker = PipelineWorker(config)
        results = []
        worker.finished_ok.connect(lambda r: results.append(r))

        _run_and_wait(qtbot, worker)

        records, errors = results[0]
        assert len(records) == 2
        assert errors == []


class TestEnrichMode:
    def test_calls_ris_enricher_with_progress_callback(
        self, qtbot, one_ris_file, tmp_path, monkeypatch
    ) -> None:
        class FakeEnricher:
            def __init__(self, email, cache_name):
                self.email = email
                self.cache_name = cache_name

            def enrich_file(
                self,
                input_path,
                output_path,
                fail_report_path,
                request_delay_seconds,
                progress_callback,
            ):
                Path(output_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")
                progress_callback(1, 2)
                progress_callback(2, 2)
                return {"processed": 2, "enriched": 2, "failed": 0}

        monkeypatch.setattr("risforge_gui.worker.RisEnricher", FakeEnricher)

        config = PipelineConfig(
            mode=OperationMode.ENRICH,
            input_paths=[one_ris_file],
            email="test@example.com",
            enriched_output_path=tmp_path / "enriched.ris",
        )
        worker = PipelineWorker(config)
        results = []
        progress_signal_calls = []
        worker.finished_ok.connect(lambda r: results.append(r))
        worker.enrichment_progress.connect(
            lambda done, total: progress_signal_calls.append((done, total))
        )

        _run_and_wait(qtbot, worker)

        assert results[0]["enriched"] == 2
        assert progress_signal_calls == [(1, 2), (2, 2)]


class TestPipelineMode:
    def test_calls_risforge_with_stage_and_progress_hooks(
        self, qtbot, two_ris_files, tmp_path, monkeypatch
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
            **kwargs,  # FIX: Accept cache_name and any other future kwargs
        ):
            on_stage("merge", "started")
            on_stage("merge", "completed")
            on_stage("clean", "started")
            on_stage("clean", "completed")
            on_stage("enrich", "started")
            enrichment_progress(1, 1)
            on_stage("enrich", "completed")

            Path(enriched_path).write_text("TY  - JOUR\nER  - \n", encoding="utf-8")

            return PipelineResult(
                cleaned_record_count=4,
                cleaning_errors=[],
                enrichment_stats={"processed": 4, "enriched": 3, "failed": 1},
                input_file_count=2,
                merged_record_count=6,
                merge_path=Path(merge_path) if merge_path else None,
                dedup_path=Path(dedup_path),
                enriched_path=Path(enriched_path),
            )

        monkeypatch.setattr("risforge_gui.worker.risforge", fake_risforge)

        config = PipelineConfig(
            mode=OperationMode.PIPELINE,
            input_paths=two_ris_files,
            email="test@example.com",
            merge_output_path=tmp_path / "merged.ris",
            dedup_output_path=tmp_path / "clean.ris",
            enriched_output_path=tmp_path / "enriched.ris",
        )

        worker = PipelineWorker(config)

        results = []
        stage_events = []

        worker.finished_ok.connect(lambda r: results.append(r))
        worker.stage_changed.connect(lambda stage, status: stage_events.append((stage, status)))

        _run_and_wait(qtbot, worker)

        assert results[0].cleaned_record_count == 4
        assert ("merge", "completed") in stage_events
        assert ("enrich", "completed") in stage_events


class TestErrorHandling:
    def test_file_not_found_reports_error_not_finished(self, qtbot, tmp_path, monkeypatch) -> None:
        def fake_merge(input_paths, output_path):
            raise FileNotFoundError(f"Input file '{input_paths[0]}' not found.")

        monkeypatch.setattr("risforge_gui.worker.merge_ris_files", fake_merge)

        config = PipelineConfig(
            mode=OperationMode.MERGE,
            input_paths=[tmp_path / "missing.ris"],
            merge_output_path=tmp_path / "merged.ris",
        )
        worker = PipelineWorker(config)
        finished_calls = []
        error_calls = []
        worker.finished_ok.connect(lambda r: finished_calls.append(r))
        worker.error_occurred.connect(lambda *args: error_calls.append(args))

        _run_and_wait(qtbot, worker)

        assert len(error_calls) == 1
        title, message, _details, _affected_file = error_calls[0]
        assert "not found" in title.lower() or "not found" in message.lower()
        assert finished_calls == []  # must not report success

    def test_unexpected_exception_is_caught_and_reported(
        self, qtbot, tmp_path, monkeypatch
    ) -> None:
        def fake_merge(input_paths, output_path):
            raise KeyError("secondary_title")  # simulates an unanticipated internal error

        monkeypatch.setattr("risforge_gui.worker.merge_ris_files", fake_merge)

        config = PipelineConfig(
            mode=OperationMode.MERGE,
            input_paths=[tmp_path / "a.ris"],
            merge_output_path=tmp_path / "merged.ris",
        )
        worker = PipelineWorker(config)
        error_calls = []
        worker.error_occurred.connect(lambda *args: error_calls.append(args))

        _run_and_wait(qtbot, worker)

        title, message, details, _affected_file = error_calls[0]
        assert "unexpected" in title.lower()
        # The raw KeyError never becomes the user-facing title...
        assert "KeyError" not in title
        # ...but is still available in the expandable technical details.
        assert "KeyError" in details
