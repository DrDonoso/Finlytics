"""Unit tests for _merge_bold_detail — pure helper, no PDF required.

Tests cover:
- Bold title followed by oblique detail → merged as **T** D
- Bold title with no following oblique detail → **T**
- Non-bold lines pass through unchanged
- Date/amount rows (DD/MM prefix) are NOT consumed as detail
- Multiple bold+detail pairs on the same page
- Captures apply to any bold concept, not only ADEUDO
- A detail-like oblique line that is NOT preceded by a bold title passes through
- Empty input returns empty list
"""

from __future__ import annotations

import pytest

from finlytics.extraction.parser import (
    _is_bold_font,
    _is_oblique_font,
    _merge_bold_detail,
)


# ---------------------------------------------------------------------------
# Font classification helpers
# ---------------------------------------------------------------------------


def test_is_bold_font_helvetica_bold():
    assert _is_bold_font("Helvetica-Bold") is True


def test_is_bold_font_plain_not_bold():
    assert _is_bold_font("Helvetica") is False


def test_is_oblique_font_helvetica_oblique():
    assert _is_oblique_font("Helvetica-Oblique") is True


def test_is_oblique_font_italic():
    assert _is_oblique_font("Times-Italic") is True


def test_is_oblique_font_courier_oblique():
    """Courier-Oblique is oblique — detection is font-name based; the
    date-row guard in _merge_bold_detail prevents it from being consumed."""
    assert _is_oblique_font("Courier-Oblique") is True


def test_is_oblique_font_plain():
    assert _is_oblique_font("Helvetica") is False


# ---------------------------------------------------------------------------
# _merge_bold_detail core cases
# ---------------------------------------------------------------------------


def test_bold_followed_by_oblique_merges():
    lines = [
        ("ADEUDOASUCARGO", "Helvetica-Bold"),
        ("GCREOCTOPUSENERGY", "Helvetica-Oblique"),
    ]
    result = _merge_bold_detail(lines)
    assert result == ["**ADEUDOASUCARGO** GCREOCTOPUSENERGY"]


def test_bold_with_no_following_line():
    lines = [("ADEUDOASUCARGO", "Helvetica-Bold")]
    result = _merge_bold_detail(lines)
    assert result == ["**ADEUDOASUCARGO**"]


def test_bold_followed_by_another_bold_no_merge():
    """Two consecutive bold titles — second one should not be consumed as detail."""
    lines = [
        ("TITLE_A", "Helvetica-Bold"),
        ("TITLE_B", "Helvetica-Bold"),
    ]
    result = _merge_bold_detail(lines)
    assert result == ["**TITLE_A**", "**TITLE_B**"]


def test_non_bold_line_passes_through():
    lines = [("Some plain text", "Helvetica")]
    result = _merge_bold_detail(lines)
    assert result == ["Some plain text"]


def test_date_amount_row_not_consumed_as_detail():
    """A line beginning with DD/MM must NOT be consumed as detail even if oblique."""
    lines = [
        ("ADEUDOASUCARGO", "Helvetica-Bold"),
        ("01/06/2026 -120,00 880,00", "Courier-Oblique"),
    ]
    result = _merge_bold_detail(lines)
    # The date row is NOT consumed; bold title stands alone, row passes through
    assert result == ["**ADEUDOASUCARGO**", "01/06/2026 -120,00 880,00"]


def test_oblique_line_without_preceding_bold_passes_through():
    """An oblique line that does NOT follow a bold title is emitted as-is."""
    lines = [
        ("Some plain line", "Helvetica"),
        ("Oblique detail orphan", "Helvetica-Oblique"),
    ]
    result = _merge_bold_detail(lines)
    assert result == ["Some plain line", "Oblique detail orphan"]


def test_multiple_bold_detail_pairs():
    """Several pairs on one page are each merged independently."""
    lines = [
        ("HEADER LINE", "Helvetica"),
        ("ADEUDOASUCARGO", "Helvetica-Bold"),
        ("GCREOCTOPUSENERGY", "Helvetica-Oblique"),
        ("01/06/2026 -120,00 880,00", "Courier-Oblique"),
        ("COMPRAENCOMERCIO", "Helvetica-Bold"),
        ("SUPERMERCADO SA", "Helvetica-Oblique"),
        ("02/06/2026 -45,30 834,70", "Courier-Oblique"),
    ]
    result = _merge_bold_detail(lines)
    assert result == [
        "HEADER LINE",
        "**ADEUDOASUCARGO** GCREOCTOPUSENERGY",
        "01/06/2026 -120,00 880,00",
        "**COMPRAENCOMERCIO** SUPERMERCADO SA",
        "02/06/2026 -45,30 834,70",
    ]


def test_non_adeudo_title_is_also_merged():
    """Bold/detail markup is NOT limited to ADEUDO — any bold title qualifies."""
    lines = [
        ("TRANSFERENCIA", "Helvetica-Bold"),
        ("DESTINO BANCO ORIGEN", "Helvetica-Oblique"),
    ]
    result = _merge_bold_detail(lines)
    assert result == ["**TRANSFERENCIA** DESTINO BANCO ORIGEN"]


def test_empty_input_returns_empty():
    assert _merge_bold_detail([]) == []


def test_single_non_bold_line():
    lines = [("plain", "Courier")]
    assert _merge_bold_detail(lines) == ["plain"]


def test_bold_followed_by_plain_no_merge():
    """A bold title followed by a plain (non-oblique) line is NOT merged."""
    lines = [
        ("BOLD TITLE", "Helvetica-Bold"),
        ("plain follow", "Helvetica"),
    ]
    result = _merge_bold_detail(lines)
    assert result == ["**BOLD TITLE**", "plain follow"]
