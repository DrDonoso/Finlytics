"""Tests for the statement file parser."""

from pathlib import Path

import pytest

from finlytics.extraction.parser import _resolve_type, parse_statement


# ---------------------------------------------------------------------------
# _resolve_type
# ---------------------------------------------------------------------------


def test_resolve_type_from_pdf_path():
    assert _resolve_type(Path("statement.pdf"), None) == "pdf"


def test_resolve_type_from_xlsx_path():
    assert _resolve_type(Path("export.xlsx"), None) == "xlsx"


def test_resolve_type_override_takes_precedence():
    assert _resolve_type(Path("file.pdf"), "csv") == "csv"


def test_resolve_type_bytes_with_override():
    assert _resolve_type(b"raw bytes", "pdf") == "pdf"


def test_resolve_type_bytes_no_override_raises():
    with pytest.raises(ValueError, match="Cannot infer file type"):
        _resolve_type(b"raw bytes", None)


def test_resolve_type_strips_dot_from_override():
    assert _resolve_type(b"data", ".pdf") == "pdf"


# ---------------------------------------------------------------------------
# parse_statement dispatch
# ---------------------------------------------------------------------------


def test_unsupported_type_raises():
    with pytest.raises(ValueError, match="Unsupported file type"):
        parse_statement(b"data", file_type="docx")


def test_xlsx_not_implemented():
    with pytest.raises(NotImplementedError):
        parse_statement(b"data", file_type="xlsx")


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


def test_parse_csv_basic():
    csv_data = b"Date,Amount,Description\n2024-06-01,-42.50,MERCADONA\n"
    result = parse_statement(csv_data, file_type="csv")
    assert "MERCADONA" in result
    assert "Date" in result


def test_parse_csv_tab_separated_output():
    csv_data = b"Date,Amount\n2024-06-01,-10.00\n"
    result = parse_statement(csv_data, file_type="csv")
    assert "\t" in result


def test_parse_csv_utf8_bom():
    bom = b"\xef\xbb\xbf"
    csv_data = bom + b"Date,Amount\n2024-06-01,-10.00\n"
    result = parse_statement(csv_data, file_type="csv")
    assert "Date" in result
    assert not result.startswith("\ufeff")


def test_parse_csv_empty_returns_empty_string():
    result = parse_statement(b"\n\n   \n", file_type="csv")
    assert result == ""


def test_parse_csv_skips_blank_rows():
    csv_data = b"Date,Amount\n\n2024-06-01,-10.00\n\n"
    result = parse_statement(csv_data, file_type="csv")
    lines = result.strip().splitlines()
    assert len(lines) == 2  # header + 1 data row, blank rows dropped


# ---------------------------------------------------------------------------
# PDF parsing — header text must survive even when the page contains tables
# ---------------------------------------------------------------------------


def _build_pdf_with_header_and_table() -> bytes:
    """Build an in-memory PDF that has a heading paragraph above a table.

    When parsed with the old (tables-only) strategy the heading is lost;
    the new extract_words()-based parser must preserve it.
    """
    pytest.importorskip("reportlab", reason="reportlab required for PDF fixture")

    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm)
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("EXTRACTO JUNIO 2026", styles["Heading1"]),
        Table(
            [
                ["Fecha", "Concepto", "Importe"],
                ["01/06/2026", "MERCADONA", "-45.00"],
            ],
            colWidths=[4 * cm, 10 * cm, 4 * cm],
        ),
    ]
    doc.build(elements)
    return buf.getvalue()


def test_parse_pdf_header_survives_with_tables():
    """Header text (including year) must NOT be lost when a page also has tables.

    Regression guard for the bug where the tables-only branch discarded all
    non-table text, making detect_statement_year return None.
    """
    pdf_bytes = _build_pdf_with_header_and_table()
    result = parse_statement(pdf_bytes, file_type="pdf")
    assert "2026" in result, "Year from the heading must be present in parser output"
    assert "MERCADONA" in result, "Transaction row from the table must also be present"


def test_parse_pdf_no_duplicate_transactions():
    """Each transaction must appear exactly once — not duplicated by merging tables + text."""
    pdf_bytes = _build_pdf_with_header_and_table()
    result = parse_statement(pdf_bytes, file_type="pdf")
    assert result.count("MERCADONA") == 1, "Transaction text must not be emitted twice"
