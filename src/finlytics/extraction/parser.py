"""Statement file parsers — PDF (implemented), xlsx/csv (stubs for later slices).

Design:
    parse_statement(source, file_type=...) → str

    The output is raw text / tab-separated rows that is passed verbatim to the
    LLM extractor. Each format has its own private helper; new formats can be
    added without touching the public dispatch logic.

Dispatch order:
    pdf   → pdfplumber (lazy import, only when processing PDFs)
    xlsx  → NotImplementedError (openpyxl-based; add when xlsx fixtures available)
    csv   → stdlib csv (minimal implementation; not yet validated against bank exports)
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path
from typing import Union

log = logging.getLogger(__name__)

Source = Union[Path, bytes]


def parse_statement(source: Source, *, file_type: str | None = None) -> str:
    """Parse a bank-statement file and return extracted text.

    Args:
        source:    A Path to the file on disk, or raw file bytes.
        file_type: Explicit file type override ('pdf', 'xlsx', 'csv').
                   If None, inferred from the file extension (requires a Path).

    Returns:
        Raw text content suitable for passing to the LLM extractor.

    Raises:
        ValueError: Unknown or unresolvable file type.
        NotImplementedError: File type is known but not yet implemented.
    """
    resolved_type = _resolve_type(source, file_type)
    log.debug("Parsing statement as %s", resolved_type)

    if resolved_type == "pdf":
        return _parse_pdf(source)
    if resolved_type == "xlsx":
        return _parse_xlsx(source)
    if resolved_type == "csv":
        return _parse_csv(source)

    raise ValueError(
        f"Unsupported file type: {resolved_type!r}. Supported types: pdf, xlsx, csv."
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_type(source: Source, override: str | None) -> str:
    if override:
        return override.lower().lstrip(".")
    if isinstance(source, Path):
        return source.suffix.lower().lstrip(".")
    raise ValueError(
        "Cannot infer file type from raw bytes — pass file_type explicitly."
    )


def _to_bytes(source: Source) -> bytes:
    if isinstance(source, Path):
        return source.read_bytes()
    return source


def _parse_pdf(source: Source) -> str:
    """Extract text from a PDF using pdfplumber word positions.

    Strategy per page:
      Use extract_words() to reconstruct properly spaced text that includes
      ALL page content (headers AND transaction rows). The previous approach
      used extract_tables()-only when a page contained tables, which silently
      discarded header text (including the statement year). This version never
      loses header content.

      Words are grouped by y-coordinate into lines and joined with spaces,
      improving readability for PDFs that encode text without inter-word spaces.
    """
    import pdfplumber  # lazy import — only required when processing PDFs

    if isinstance(source, Path):
        ctx = pdfplumber.open(source)
    else:
        ctx = pdfplumber.open(io.BytesIO(source))

    pages: list[str] = []
    with ctx as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = _extract_page_text(page)
            if page_text:
                pages.append(f"[Page {page_num}]\n{page_text}")

    if not pages:
        log.warning("PDF produced no extractable text")
        return ""

    return "\n\n".join(pages)


def _extract_page_text(page) -> str:
    """Reconstruct page text from word positions with proper line spacing.

    Uses page.extract_words() which segments by character bounding-box gaps,
    then groups words sharing the same y-coordinate into lines and joins them
    with spaces. This preserves ALL content (headers, footers, table cells)
    without the tables-only discarding bug, and improves word spacing versus
    the raw extract_text() output for PDFs that encode text without spaces.

    Falls back to page.extract_text() for scanned / image-based pages where
    no word objects are available.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    if not words:
        return page.extract_text() or ""

    # Group words by line: round 'top' to nearest 2 px so same-line words
    # (which may have slightly different y due to baseline differences) merge.
    lines: dict[int, list] = {}
    for word in words:
        y_key = round(float(word["top"]) / 2) * 2
        lines.setdefault(y_key, []).append(word)

    text_lines: list[str] = []
    for y_key in sorted(lines):
        row = sorted(lines[y_key], key=lambda w: float(w["x0"]))
        text_lines.append(" ".join(w["text"] for w in row))

    return "\n".join(text_lines)


def _parse_xlsx(source: Source) -> str:  # noqa: ARG001
    """STUB: Extract rows from an xlsx file using openpyxl.

    Not yet implemented — will be added in a future slice once real BBVA or
    Indexa Capital xlsx exports are available for accuracy testing.
    """
    raise NotImplementedError(
        "xlsx parsing is not yet implemented. "
        "Add openpyxl-based row extraction here once real xlsx fixtures are available."
    )


def _parse_csv(source: Source) -> str:
    """Extract rows from a CSV file.

    Minimal stdlib implementation — not yet validated against real bank CSV
    exports. Handles UTF-8 BOM (common in Excel-generated CSVs).
    """
    raw = _to_bytes(source)
    text = raw.decode("utf-8-sig", errors="replace")  # utf-8-sig strips BOM automatically
    reader = csv.reader(io.StringIO(text))
    rows = ["\t".join(row) for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        log.warning("CSV produced no rows")
        return ""
    return "\n".join(rows)
