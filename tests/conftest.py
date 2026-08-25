from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_ris_path() -> Path:
    """Path to the bundled sample .ris fixture with known duplicates."""
    return FIXTURES_DIR / "sample.ris"


@pytest.fixture
def multi_source_paths(tmp_path: Path) -> list[Path]:
    """Three source files (scopus/pubmed/wos-style) sharing one duplicate paper.
    Generated dynamically to ensure tests are hermetic and contain the specific
    records expected by the merging and pipeline test suites.
    """
    scopus = tmp_path / "scopus.ris"
    pubmed = tmp_path / "pubmed.ris"
    wos = tmp_path / "wos.ris"

    shared_doi = "10.1016/j.neuroimage.2022.99999"

    # Scopus: 2 valid records + 1 malformed block.
    # "Cortical thickness" is the 2nd valid record to satisfy ordering tests.
    scopus_content = f"""TY  - JOUR
AU  - Smith, John A.
TI  - Deep Learning for Diffusion MRI Tractography
DO  - {shared_doi}
ER  -

TY  - JOUR
AU  - Unique, Scopus
TI  - Cortical thickness changes in early Parkinson's disease
ER  -

TY  - JOUR
AU  - Broken, Record
TI  - Missing ER terminator entirely
"""

    # Pubmed: 2 valid records. Contains the abstract for the shared paper.
    pubmed_content = f"""TY  - JOUR
AU  - Doe, Jane
TI  - Machine learning applications in neuroimaging: a review
ER  -

TY  - JOUR
AU  - Smith, J.A.
TI  - Deep Learning for Diffusion MRI Tractography
DO  - {shared_doi}
AB  - Second copy of the same paper, carries an abstract the others lack.
ER  -
"""

    # Wos: 2 valid records. Contains the keywords for the shared paper.
    wos_content = f"""TY  - JOUR
AU  - Lee, Sam
TI  - Structural connectome differences in schizophrenia
ER  -

TY  - JOUR
AU  - Smith, JA
TI  - Deep Learning for Diffusion MRI Tractography
DO  - {shared_doi}
KW  - diffusion MRI
KW  - tractography
KW  - deep learning
ER  -
"""

    scopus.write_text(scopus_content)
    pubmed.write_text(pubmed_content)
    wos.write_text(wos_content)

    return [scopus, pubmed, wos]
