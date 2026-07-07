"""Shared fixtures for quality / golden-set tests.

Loads the synthetic statement fixtures and their hand-labeled expected JSON
from tests/fixtures/statements/.  All fixtures are session-scoped because
the files do not change between tests.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "statements"


# ---------------------------------------------------------------------------
# Text fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def bbva_fixture_text() -> str:
    return (FIXTURE_DIR / "bbva_2026-05.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def bbva_expected() -> list[dict]:
    raw = (FIXTURE_DIR / "bbva_2026-05.expected.json").read_text(encoding="utf-8")
    return json.loads(raw)


@pytest.fixture(scope="session")
def indexa_fixture_text() -> str:
    return (FIXTURE_DIR / "indexa_2026-05.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def indexa_expected() -> list[dict]:
    raw = (FIXTURE_DIR / "indexa_2026-05.expected.json").read_text(encoding="utf-8")
    return json.loads(raw)


# ---------------------------------------------------------------------------
# PDF fixture (generated once per session using reportlab)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def bbva_pdf_bytes(bbva_fixture_text: str) -> bytes:
    """Return a PDF containing the BBVA synthetic statement text.

    Generated at test-time using reportlab (optional test dependency).
    The PDF is created in-memory — no file I/O required for this fixture.

    If reportlab is not installed the test using this fixture is auto-skipped.
    """
    reportlab = pytest.importorskip("reportlab", reason="reportlab not installed — skipping PDF fixture tests")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _, height = A4
    y = height - 50
    for line in bbva_fixture_text.splitlines():
        if y < 50:
            c.showPage()
            y = height - 50
        # Replace non-ASCII chars so the default Type1 font doesn't choke
        safe_line = line.encode("latin-1", errors="replace").decode("latin-1")
        c.drawString(50, y, safe_line)
        y -= 14
    c.save()
    return buf.getvalue()
