from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ris_path() -> Path:
    """Path to the bundled sample .ris fixture with known duplicates."""
    return FIXTURES_DIR / "sample.ris"
