"""GUI tests for MainWindow."""

from __future__ import annotations

from risforge_gui.main_window import MainWindow


def test_window_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "RisForge - RIS Deduplication & Enrichment"


def test_initial_start_disabled(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert not window.start_button.isEnabled()
