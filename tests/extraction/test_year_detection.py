"""Tests for detect_statement_year, year-aware build_system_prompt, and extract_transactions threading."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from finlytics.extraction.extractor import (
    _ExtractionResult,
    _RawTransaction,
    detect_statement_year,
    extract_transactions,
)
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.prompts import build_system_prompt


# ---------------------------------------------------------------------------
# Helpers (mirror test_extractor.py style)
# ---------------------------------------------------------------------------


def _make_client(transactions: list[_RawTransaction] | None = None) -> LLMClient:
    """Return an LLMClient whose .parse() returns a canned _ExtractionResult."""
    mock_inner = MagicMock()
    client = LLMClient(
        api_key="test-key",
        base_url="http://localhost",
        model="test-model",
        _client=mock_inner,
    )
    client.parse = AsyncMock(return_value=_ExtractionResult(transactions=transactions or []))
    return client


# ---------------------------------------------------------------------------
# detect_statement_year — parametric cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # Priority 0: period title "Extracto/Estado de <month> <year>"
        ("Extracto de julio de 2026\nSaldo 1000.00", 2026),
        # Priority 2: generic month+year (no extracto/estado prefix)
        ("Estado de cuenta junio de 2025", 2025),
        ("a 30 de junio de 2026\nMovimientos", 2026),
        ("julio 2026", 2026),
        # Priority 1: labeled keyword + dd/mm/yyyy
        ("Fecha de emisión: 01/07/2026\nMovimientos...", 2026),
        ("Fecha Extracto: 30/06/2025", 2025),
        # Priority 1: labeled keyword + yyyy-mm-dd
        ("Fecha Extracto 2026-07-01\nSaldo", 2026),
        # Priority 1: period range
        ("Periodo 01/06/2026 - 30/06/2026\nMovimientos", 2026),
        ("Período del extracto: 01/06/2025 - 30/06/2025", 2025),
        # Priority 0b: desde/hasta (period boundary, above issue-date label)
        ("desde 01/06/2026 hasta 30/06/2026", 2026),
        # Priority 4 fallback: bare year only (no full date, no month name)
        ("EXTRACTO DE CUENTA 2026\nMercadona 50.00", 2026),
        # No year at all → None
        ("MOVIMIENTOS DE CUENTA\nMercadona 50.00\nCarrefour 30.00", None),
        # --- Glued-text cases from real BBVA PDF (pdfplumber drops inter-word spaces) ---
        # Priority 0 (period title, glued): "EXTRACTODEJUNIO2026"
        ("EXTRACTODEJUNIO2026", 2026),
        # Priority 0 (period title in second line of glued header)
        ("EXTRACTOMENSUALDE CUENTASPERSONALES\nEXTRACTODEJUNIO2026", 2026),
        # Priority 1c (glued label + dd/mm/yyyy)
        ("Fechadeemisi\ufffdn: 01/07/2026", 2026),
        # Priority 1c (glued label, ASCII ó)
        ("Fechadeemisi\u00f3n: 01/07/2026", 2026),
        # Priority 0 wins: period title (June 2026) over glued issue-date label (July 2026)
        (
            "EXTRACTOMENSUALDE CUENTASPERSONALES\n"
            "EXTRACTODEJUNIO2026 Fechadeemisi\ufffdn: 01/07/2026",
            2026,
        ),
        # Alternate September spelling ("setiembre")
        ("setiembre 2024", 2024),
    ],
)
def test_detect_statement_year(text: str, expected: int | None) -> None:
    assert detect_statement_year(text) == expected


def test_detect_statement_year_empty_text_returns_none() -> None:
    assert detect_statement_year("") is None


def test_detect_statement_year_prefers_labeled_over_frequency() -> None:
    """Label keyword (priority 1) must win over a year that appears more often."""
    text = (
        "Fecha de emisión: 01/07/2026\n"
        "15/03/2025 Mercadona -30.00\n"
        "20/03/2025 Netflix -12.99\n"
        "25/03/2025 Carrefour -45.00\n"
    )
    # 2025 appears 3× in transaction lines; 2026 appears once via the label
    assert detect_statement_year(text) == 2026


def test_detect_statement_year_fallback_most_frequent() -> None:
    """Without any label or month name, the most frequent bare year wins."""
    text = (
        "EXTRACTO\n"
        "01/06/2023 Mercadona -30.00\n"
        "02/06/2023 Netflix -12.99\n"
        "03/06/2024 Carrefour -45.00\n"
    )
    # 2023 appears in the header-region first full date (priority 3),
    # so it wins via header scan even before the frequency fallback
    assert detect_statement_year(text) == 2023


def test_detect_statement_year_period_title_beats_issue_date() -> None:
    """Regression: BBVA December statement issued in January must return December's year.

    The BBVA header for a December 2025 statement looks like (glued tokens from
    pdfplumber, replacement char \ufffd for the ó in "emisión"):
        EXTRACTOMENSUALDE CUENTASPERSONALES
        EXTRACTODEDICIEMBRE2025 Fechadeemisi\ufffdn: 01/01/2026

    Before the fix _GLUED_LABEL_DATE_RE fired on the issue date first and returned
    2026.  The period title ("EXTRACTODEDICIEMBRE2025") must now win.
    """
    header = (
        "EXTRACTOMENSUALDE CUENTASPERSONALES\n"
        "EXTRACTODEDICIEMBRE2025 Fechadeemisi\ufffdn: 01/01/2026\n"
    )
    assert detect_statement_year(header) == 2025


# ---------------------------------------------------------------------------
# build_system_prompt — year-handling block content
# ---------------------------------------------------------------------------


def test_build_system_prompt_year_known_contains_year() -> None:
    prompt = build_system_prompt("BBVA", statement_year=2026)
    assert "2026" in prompt


def test_build_system_prompt_year_known_instructs_no_invention() -> None:
    prompt = build_system_prompt("BBVA", statement_year=2024)
    lower = prompt.lower()
    assert "year handling" in lower
    assert "2024" in prompt
    assert "must not" in lower


def test_build_system_prompt_year_unknown_warns_no_fabrication() -> None:
    prompt = build_system_prompt("BBVA", statement_year=None)
    lower = prompt.lower()
    assert "year handling" in lower
    assert "fabricat" in lower or "invent" in lower


def test_build_system_prompt_year_unknown_omits_year_assertion() -> None:
    prompt = build_system_prompt("BBVA", statement_year=None)
    assert "The statement year is" not in prompt


def test_build_system_prompt_backward_compatible_no_year_arg() -> None:
    """Old callers that pass only account_ref still get a valid prompt."""
    prompt = build_system_prompt("Indexa Capital")
    assert "Indexa Capital" in prompt
    assert "year handling" in prompt.lower()


# ---------------------------------------------------------------------------
# extract_transactions — statement_year threading
# ---------------------------------------------------------------------------


async def test_extract_passes_auto_detected_year_to_prompt() -> None:
    client = _make_client()
    text = "Extracto de julio de 2026\nMovimientos..."
    await extract_transactions(text, "BBVA", client)
    system_prompt = client.parse.call_args.kwargs["system"]
    assert "2026" in system_prompt


async def test_extract_explicit_year_used_directly() -> None:
    client = _make_client()
    # Text contains 2026, but we force 2024
    text = "Extracto de julio de 2026\nMovimientos..."
    await extract_transactions(text, "BBVA", client, statement_year=2024)
    system_prompt = client.parse.call_args.kwargs["system"]
    assert "2024" in system_prompt


async def test_extract_no_year_in_text_uses_unknown_block() -> None:
    client = _make_client()
    await extract_transactions("no dates here at all", "BBVA", client)
    system_prompt = client.parse.call_args.kwargs["system"]
    lower = system_prompt.lower()
    assert "fabricat" in lower or "invent" in lower


async def test_extract_default_year_none_still_returns_transactions() -> None:
    """End-to-end: no year provided, LLM mock still returns a transaction."""
    raw = _RawTransaction(
        transaction_date="2026-06-15",
        amount=-9.99,
        currency="EUR",
        description="NETFLIX",
        category="Subscriptions",
    )
    client = _make_client([raw])
    result = await extract_transactions("sin año en el texto", "BBVA", client)
    assert len(result) == 1
    assert result[0].description == "NETFLIX"
