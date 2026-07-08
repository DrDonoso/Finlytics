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

Bold/detail markup (bold_markup=True, default on):
    BBVA statement PDFs encode transaction descriptions with distinct fonts:
      - Bold title (Helvetica-Bold, ~8pt) — the main concept, e.g. ADEUDOASUCARGO
      - Oblique detail (Helvetica-Oblique, ~7pt) — the sub-detail on the next visual
        line, e.g. GCREOCTOPUSENERGY

    When bold_markup=True the parser marks bold titles as **TITLE** and merges the
    immediately-following oblique detail onto the same logical line:
        **ADEUDOASUCARGO** GCREOCTOPUSENERGY

    This markup is consumed by the LLM extractor to populate
    ExtractedTransaction.description (bold concept) and .detail (oblique text).
    Set bold_markup=False to disable (useful in tests against non-BBVA fixtures).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Union

log = logging.getLogger(__name__)

Source = Union[Path, bytes]

# Matches lines that start with a date (DD/MM) — used to avoid consuming
# Courier-Oblique date/amount rows as bold-detail lines.
_DATE_ROW_RE = re.compile(r"^\d{2}/\d{2}")


def parse_statement(source: Source, *, file_type: str | None = None, bold_markup: bool = True) -> str:
    """Parse a bank-statement file and return extracted text.

    Args:
        source:      A Path to the file on disk, or raw file bytes.
        file_type:   Explicit file type override ('pdf', 'xlsx', 'csv').
                     If None, inferred from the file extension (requires a Path).
        bold_markup: When True (default) and the file is a PDF, annotate bold
                     titles and merge oblique detail lines (see module docstring).
                     Pass False to get plain text output (useful in tests that
                     use non-BBVA PDF fixtures without Helvetica-Bold fonts).

    Returns:
        Raw text content suitable for passing to the LLM extractor.

    Raises:
        ValueError: Unknown or unresolvable file type.
        NotImplementedError: File type is known but not yet implemented.
    """
    resolved_type = _resolve_type(source, file_type)
    log.debug("Parsing statement as %s", resolved_type)

    if resolved_type == "pdf":
        return _parse_pdf(source, bold_markup=bold_markup)
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


def _parse_pdf(source: Source, *, bold_markup: bool = True) -> str:
    """Extract text from a PDF using pdfplumber word positions.

    Strategy per page:
      Use extract_words() to reconstruct properly spaced text that includes
      ALL page content (headers AND transaction rows). The previous approach
      used extract_tables()-only when a page contained tables, which silently
      discarded header text (including the statement year). This version never
      loses header content.

      Words are grouped by y-coordinate into lines and joined with spaces,
      improving readability for PDFs that encode text without inter-word spaces.

      When bold_markup=True each page is post-processed by _merge_bold_detail
      to annotate bold-title + oblique-detail pairs.
    """
    import pdfplumber  # lazy import — only required when processing PDFs

    if isinstance(source, Path):
        ctx = pdfplumber.open(source)
    else:
        ctx = pdfplumber.open(io.BytesIO(source))

    pages: list[str] = []
    with ctx as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            page_text = _extract_page_text(page, bold_markup=bold_markup)
            if page_text:
                pages.append(f"[Page {page_num}]\n{page_text}")

    if not pages:
        log.warning("PDF produced no extractable text")
        return ""

    return "\n\n".join(pages)


# ---------------------------------------------------------------------------
# Bold / detail markup helpers (pure — unit-testable without a real PDF)
# ---------------------------------------------------------------------------


def _is_bold_font(fontname: str) -> bool:
    """Return True when *fontname* indicates a bold weight (e.g. 'Helvetica-Bold')."""
    return "Bold" in fontname


def _is_oblique_font(fontname: str) -> bool:
    """Return True when *fontname* indicates oblique/italic style (e.g. 'Helvetica-Oblique')."""
    return "Oblique" in fontname or "Italic" in fontname


def _dominant_font(words: list) -> str:
    """Return the most common fontname among a group of word dicts."""
    if not words:
        return ""
    fonts = [w.get("fontname", "") for w in words]
    return Counter(fonts).most_common(1)[0][0]


def _merge_bold_detail(lines_with_font: list[tuple[str, str]]) -> list[str]:
    """Merge bold-title + oblique-detail line pairs into single logical lines.

    For each bold-title line (dominant fontname contains 'Bold') optionally
    followed by an oblique-detail line (dominant fontname contains 'Oblique' or
    'Italic', AND the line does not look like a date/amount row), the pair is
    collapsed into a single logical line::

        **{bold_title}** {oblique_detail}

    A bold-title line with NO qualifying following line becomes::

        **{bold_title}**

    Non-bold lines (including Courier-Oblique date/amount rows) pass through
    unchanged.

    This is a PURE function — it does not open any file; inputs are plain
    Python strings. Unit-test it directly with synthetic (text, fontname) tuples.

    Args:
        lines_with_font: List of ``(text, dominant_fontname)`` tuples, one per
                         visual line in top-to-bottom order.

    Returns:
        List of output text lines with bold/detail pairs merged.
    """
    result: list[str] = []
    i = 0
    while i < len(lines_with_font):
        text, font = lines_with_font[i]
        if _is_bold_font(font):
            # Peek at the next line: consume it as detail when it is oblique
            # and does NOT look like a date/amount row (DD/MM prefix).
            if i + 1 < len(lines_with_font):
                next_text, next_font = lines_with_font[i + 1]
                if _is_oblique_font(next_font) and not _DATE_ROW_RE.match(next_text):
                    result.append(f"**{text}** {next_text}")
                    i += 2
                    continue
            result.append(f"**{text}**")
            i += 1
        else:
            result.append(text)
            i += 1
    return result


def _extract_page_text(page, *, bold_markup: bool = True) -> str:
    """Reconstruct page text from word positions with proper line spacing.

    Uses page.extract_words() which segments by character bounding-box gaps,
    then groups words sharing the same y-coordinate into lines and joins them
    with spaces. This preserves ALL content (headers, footers, table cells)
    without the tables-only discarding bug, and improves word spacing versus
    the raw extract_text() output for PDFs that encode text without spaces.

    When bold_markup=True, font information is requested (fontname, size) and
    _merge_bold_detail is applied to annotate bold-title + oblique-detail pairs.

    Falls back to page.extract_text() for scanned / image-based pages where
    no word objects are available.
    """
    words = page.extract_words(x_tolerance=3, y_tolerance=3, extra_attrs=["fontname", "size"])
    if not words:
        return page.extract_text() or ""

    # Group words by line: round 'top' to nearest 2 px so same-line words
    # (which may have slightly different y due to baseline differences) merge.
    lines: dict[int, list] = {}
    for word in words:
        y_key = round(float(word["top"]) / 2) * 2
        lines.setdefault(y_key, []).append(word)

    # Build (text, dominant_fontname) pairs for each visual line.
    raw_lines: list[tuple[str, str]] = []
    for y_key in sorted(lines):
        row = sorted(lines[y_key], key=lambda w: float(w["x0"]))
        text = " ".join(w["text"] for w in row)
        font = _dominant_font(row) if bold_markup else ""
        raw_lines.append((text, font))

    if bold_markup:
        text_lines = _merge_bold_detail(raw_lines)
    else:
        text_lines = [t for t, _ in raw_lines]

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
