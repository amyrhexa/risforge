from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

# Must be set before any PySide6.QtWidgets import creates a QApplication.
# Lets the whole GUI suite run without a real display server (CI, this sandbox, etc.).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

GUI_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def two_ris_files(tmp_path) -> list[Path]:
    """Two independent copies of the bundled sample fixture (distinct filesystem paths)."""
    source = GUI_FIXTURES_DIR / "sample.ris"
    first = tmp_path / "first.ris"
    second = tmp_path / "second.ris"
    shutil.copy(source, first)
    shutil.copy(source, second)
    return [first, second]


@pytest.fixture
def one_ris_file(tmp_path) -> Path:
    source = GUI_FIXTURES_DIR / "sample.ris"
    dest = tmp_path / "input.ris"
    shutil.copy(source, dest)
    return dest


@pytest.fixture
def multi_source_paths() -> list[Path]:
    base = GUI_FIXTURES_DIR / "multi_source"
    return [base / "scopus.ris", base / "pubmed.ris", base / "wos.ris"]


@pytest.fixture
def mocked_worker_apis(monkeypatch):
    """Replace risforge_gui.worker's RisEnricher with one wired to a mocked HTTP session.

    Reuses the exact mocked session/payloads from tests/test_enrichment.py
    and patches the name risforge_gui.worker looks up, so no GUI test
    ever makes a real network call. merge_ris_files/clean_ris_file
    never touch the network at all, so only enrich/pipeline paths need
    this.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_enrichment import (
        CROSSREF_PAYLOAD,
        OPENALEX_PAYLOAD,
        SEMANTIC_SCHOLAR_PAYLOAD,
        UNPAYWALL_PAYLOAD,
        _MockSession,
    )

    from risforge.enrichment import RisEnricher
    from risforge_gui import worker as worker_module

    session = _MockSession(
        {
            "api.crossref.org/works/10": CROSSREF_PAYLOAD,
            "api.openalex.org": OPENALEX_PAYLOAD,
            "api.semanticscholar.org": SEMANTIC_SCHOLAR_PAYLOAD,
            "api.unpaywall.org": UNPAYWALL_PAYLOAD,
        }
    )

    def _factory(email: str, **_kwargs) -> RisEnricher:
        return RisEnricher(email=email, session=session)

    monkeypatch.setattr(worker_module, "RisEnricher", _factory)
    return session


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """Prevent any modal QMessageBox from hanging a headless test run.

    An exec()'d QMessageBox waits for a click that can never come
    without a real display. Tests that need to verify a dialog *would*
    appear patch the specific function themselves instead.
    """
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
    )
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
