"""Smoke tests for risforge_gui."""

from __future__ import annotations


def test_import_risforge_gui() -> None:
    import risforge_gui

    assert hasattr(risforge_gui, "__version__")


def test_import_app_module() -> None:
    from risforge_gui import app

    assert callable(app.main)
