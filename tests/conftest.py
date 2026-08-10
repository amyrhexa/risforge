from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MULTI_SOURCE_DIR = FIXTURES_DIR / "multi_source"


@pytest.fixture
def sample_ris_path() -> Path:
    """Path to the bundled sample .ris fixture with known duplicates."""
    return FIXTURES_DIR / "sample.ris"


@pytest.fixture
def multi_source_paths() -> list[Path]:
    """Three source files (scopus/pubmed/wos-style) sharing one duplicate paper.

    Each contains one paper that also appears in the other two (same
    DOI, slightly different metadata/casing), one paper unique to that
    file, and (scopus only) one intentionally malformed block.
    """
    return [
        MULTI_SOURCE_DIR / "scopus.ris",
        MULTI_SOURCE_DIR / "pubmed.ris",
        MULTI_SOURCE_DIR / "wos.ris",
    ]
