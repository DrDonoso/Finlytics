"""LLM extraction pipeline — raw statement text → list[ExtractedTransaction].

Pipeline:
    1. Build system + user prompts (prompts.py)
    2. Call LLMClient.parse() with a Pydantic response schema → structured JSON guaranteed
    3. Coerce LLM-facing types (str dates, float amounts) → contract types (date, Decimal)
    4. Log any categories proposed outside the base taxonomy
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from finlytics.extraction.llm_client import LLMClient, LLMError
from finlytics.extraction.prompts import build_system_prompt, build_user_prompt
from finlytics.extraction.redaction import redact_pii
from finlytics.extraction.schema import ExtractedTransaction
from finlytics.extraction.taxonomy import BASE_CATEGORIES, BASE_CATEGORY_ES

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking constants
# ---------------------------------------------------------------------------

# Maximum completion tokens per LLM call — raised well above the legacy 4096
# default to give each chunk ample output headroom.
_EXTRACTION_MAX_TOKENS = 8192

# Maximum raw-text lines per LLM call.  A BBVA monthly statement has
# roughly 2–4 raw lines per transaction, so 50 lines ≈ 15–20 transactions
# per chunk — comfortably within the token budget above.
_CHUNK_LINES = 50


# ---------------------------------------------------------------------------
# Statement year detection
# ---------------------------------------------------------------------------

_MONTHS_ES = (
    r"enero|febrero|marzo|abril|mayo|junio|julio"
    r"|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
)

# Priority 1: labeled date keywords + full date (dd/mm/yyyy or yyyy-mm-dd)
_LABEL_DATE_RE = re.compile(
    r"(?:fecha\s+(?:de\s+)?(?:emisi[oó]n|extracto|corte|estado)"
    r"|per[ií]odo(?:\s+del?\s+extracto)?"
    r"|a\s+fecha\s+de)"
    r"\s*[:\-]?\s*"
    r"(?:(\d{4})[-/](\d{2})[-/](\d{2})"  # yyyy-mm-dd → group 1 = year
    r"|(\d{2})[-/](\d{2})[-/](\d{4}))",  # dd/mm/yyyy → group 6 = year
    re.IGNORECASE,
)

# Priority 1b: "desde/hasta DD/MM/YYYY" period range
_DESDE_RE = re.compile(
    r"(?:desde|hasta)\s*:?\s*"
    r"(?:(\d{4})[-/](\d{2})[-/](\d{2})"  # yyyy-mm-dd → group 1 = year
    r"|(\d{2})[-/](\d{2})[-/](\d{4}))",  # dd/mm/yyyy → group 6 = year
    re.IGNORECASE,
)

# Priority 1c: "Fecha..." glued to its label + colon + date.
# Handles PDFs that encode "Fecha de emisión: dd/mm/yyyy" as one unspaced token
# e.g. "Fechadeemisi\ufffdn: 01/07/2026".  [^\n]{0,25}? keeps the match on one line.
_GLUED_LABEL_DATE_RE = re.compile(
    r"\bfecha[^\n]{0,25}?:\s*"
    r"(?:(\d{4})[-/](\d{2})[-/](\d{2})"  # yyyy-mm-dd → group 1 = year
    r"|(\d{2})[-/](\d{2})[-/](\d{4}))",  # dd/mm/yyyy → group 6 = year
    re.IGNORECASE,
)

# Priority 2: Spanish month name + 4-digit year.
# \s* (zero or more spaces) instead of \s+ so "JUNIO2026" (glued) also matches.
_MONTH_YEAR_RE = re.compile(
    r"(?:(?:extracto|estado)\s+de\s+)?"
    r"(?:a\s+)?(?:\d{1,2}\s+de\s+)?"
    rf"(?:{_MONTHS_ES})"
    r"\s*(?:de\s*)?"
    r"(20\d{2})",
    re.IGNORECASE,
)

# Priority 3: any full date (header region scan)
_FULL_DATE_RE = re.compile(
    r"(?:(\d{4})[-/](\d{2})[-/](\d{2})"  # yyyy-mm-dd → group 1 = year
    r"|(\d{2})[-/](\d{2})[-/](\d{4}))",  # dd/mm/yyyy → group 6 = year
)

# Priority 4: bare 4-digit year (frequency fallback)
_BARE_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def detect_statement_year(text: str) -> int | None:
    """Detect the statement year from raw statement text.

    Uses Spanish/EU-focused heuristics in priority order:
    1.  Labeled date keywords (fecha de emisión, periodo, etc.) + full date
    1b. desde/hasta + full date (period range)
    1c. Any "Fecha..." glued label + colon + full date (handles PDFs that
        encode multi-word labels without spaces, e.g. "Fechadeemisi\ufffdn:")
    2.  Spanish month name (enero…diciembre) optionally followed by "de"/spaces
        then a 4-digit year — handles glued forms like "JUNIO2026" or
        "EXTRACTODEJUNIO2026", plus normal "junio de 2026".
    3.  Any full date (dd/mm/yyyy or yyyy-mm-dd) in the header region (~500 chars)
    4.  Fallback: most frequent 4-digit year (2000–2099) across the full text

    Returns the best single int year, or None if nothing plausible is found.
    """

    def _plausible(y: int) -> bool:
        return 2000 <= y <= 2099

    # 1. Labeled keyword + date
    m = _LABEL_DATE_RE.search(text)
    if m:
        yr = int(m.group(1) or m.group(6))
        if _plausible(yr):
            return yr

    # 1b. desde / hasta + date
    m = _DESDE_RE.search(text)
    if m:
        yr = int(m.group(1) or m.group(6))
        if _plausible(yr):
            return yr

    # 1c. Glued "Fecha..." label (e.g. "Fechadeemisi\ufffdn: 01/07/2026")
    m = _GLUED_LABEL_DATE_RE.search(text)
    if m:
        yr = int(m.group(1) or m.group(6))
        if _plausible(yr):
            return yr

    # 2. Spanish month name + year (handles glued "JUNIO2026" and spaced "junio de 2026")
    m = _MONTH_YEAR_RE.search(text)
    if m:
        yr = int(m.group(1))
        if _plausible(yr):
            return yr

    # 3. Full date in the header region (first ~500 chars)
    m = _FULL_DATE_RE.search(text[:500])
    if m:
        yr = int(m.group(1) or m.group(6))
        if _plausible(yr):
            return yr

    # 4. Most frequent bare year in the full text
    years = _BARE_YEAR_RE.findall(text)
    if years:
        yr = int(Counter(years).most_common(1)[0][0])
        if _plausible(yr):
            return yr

    return None


# ---------------------------------------------------------------------------
# LLM-facing Pydantic schema
# ---------------------------------------------------------------------------
# Types map 1:1 to JSON primitives so the structured-output JSON schema is
# unambiguous. We coerce to ExtractedTransaction after the LLM call.


class _RawTransaction(BaseModel):
    """LLM-facing transaction model; uses JSON-native types (str, float)."""

    transaction_date: str = Field(description="ISO 8601 date: YYYY-MM-DD")
    amount: float = Field(
        description="Signed float; negative = expense/out, positive = income/in"
    )
    currency: str = Field(default="EUR")
    description: str
    raw_line: Optional[str] = None
    category: str
    is_proposed_category: bool = Field(
        default=False,
        description="True when the category is not in the base taxonomy and was invented by the model",
    )
    category_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    balance_after: Optional[float] = None
    tags: list[str] = Field(
        default_factory=list,
        description="0–3 free-form tag names (lowercase Spanish) suggested by the extractor",
    )
    merchant: Optional[str] = Field(
        default=None,
        description=(
            "Normalized brand/vendor name in Title Case "
            "(e.g. 'Amazon', 'Mercadona', 'Octopus Energy'), "
            "or null when no merchant is identifiable"
        ),
    )
    detail: Optional[str] = Field(
        default=None,
        description=(
            "Non-bold sub-detail text that followed the bold concept in the statement "
            "(parsed from **CONCEPT** detail markup); null when absent"
        ),
    )

    @field_validator("transaction_date", mode="before")
    @classmethod
    def _validate_date_format(cls, v: str) -> str:
        date.fromisoformat(v)  # raises ValueError early if the model returns garbage
        return v


class _ExtractionResult(BaseModel):
    """Wrapper object so the top-level JSON is an object, not a bare array.
    (OpenAI structured outputs require a top-level JSON object.)
    """

    transactions: list[_RawTransaction] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_transactions(
    statement_text: str,
    account_ref: str,
    client: LLMClient,
    statement_year: int | None = None,
) -> list[ExtractedTransaction]:
    """Extract and categorize transactions from raw statement text.

    Args:
        statement_text: Raw text output from the parser (PDF/XLSX/CSV).
        account_ref:    Account identifier, e.g. "BBVA" or "Indexa Capital".
        client:         An LLMClient instance (injectable for tests).
        statement_year: Optional year of the statement. If None, auto-detected
                        from statement_text via detect_statement_year().

    Returns:
        A list of ExtractedTransaction objects matching the shared contract.

    Note:
        PII boundary (Romanoff): statement_text is redacted (IBANs, card/PAN,
        account numbers masked to last 4) before being sent to the LLM.
        Full-fidelity text is preserved in local DB persistence only.
    """
    if not statement_text.strip():
        log.warning("extract_transactions called with empty statement text — returning []")
        return []

    # Auto-detect year from original text (before PII redaction — redaction doesn't strip years)
    effective_year = (
        statement_year if statement_year is not None else detect_statement_year(statement_text)
    )

    # ── PII redaction at the LLM boundary ────────────────────────────────────
    # Mask IBANs, card/PAN numbers, and long account numbers BEFORE sending to
    # the third-party LLM. Local DB persistence retains full-fidelity data.
    redacted_text = redact_pii(statement_text)

    system_prompt = build_system_prompt(account_ref, statement_year=effective_year)
    chunks = _split_into_chunks(redacted_text)

    log.info(
        "Extracting transactions: account=%s, input_chars=%d, statement_year=%s, chunks=%d",
        account_ref,
        len(statement_text),
        effective_year,
        len(chunks),
    )

    all_raw: list[_RawTransaction] = []
    for idx, chunk_text in enumerate(chunks):
        raw_txns = await _extract_chunk_with_retry(
            client, system_prompt, chunk_text, idx, len(chunks)
        )
        all_raw.extend(raw_txns)

    transactions = [_coerce(raw, account_ref) for raw in all_raw]

    proposed = [t for t in transactions if t.category not in BASE_CATEGORIES]
    if proposed:
        log.warning(
            "LLM proposed %d non-taxonomy categories: %s",
            len(proposed),
            [t.category for t in proposed],
        )

    log.info("Extracted %d transactions for account=%s", len(transactions), account_ref)
    return transactions


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _split_into_chunks(text: str, chunk_size: int = _CHUNK_LINES) -> list[str]:
    """Split *text* into non-empty chunks of at most *chunk_size* lines each."""
    lines = text.splitlines()
    chunks: list[str] = []
    for i in range(0, len(lines), chunk_size):
        chunk = "\n".join(lines[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _is_truncation_error(exc: LLMError) -> bool:
    """Return True when *exc* represents an LLM output truncation (length limit)."""
    msg = str(exc).lower()
    return "length limit" in msg or "finish_reason" in msg


async def _extract_chunk_with_retry(
    client: LLMClient,
    system_prompt: str,
    chunk_text: str,
    chunk_index: int,
    total_chunks: int,
) -> list[_RawTransaction]:
    """Parse one text chunk, retrying once with a half-size split on truncation.

    If the retry halves also truncate, re-raises a clear LLMError that names
    the chunk so the caller (and Shuri's error mapping) can surface a useful
    message instead of a raw 502.
    """
    label = f"chunk {chunk_index + 1}/{total_chunks}"
    try:
        result: _ExtractionResult = await client.parse(
            system=system_prompt,
            user=build_user_prompt(chunk_text),
            response_format=_ExtractionResult,
            temperature=0.0,
            max_completion_tokens=_EXTRACTION_MAX_TOKENS,
        )
        return result.transactions
    except LLMError as exc:
        if not _is_truncation_error(exc):
            raise

    # Truncation: split in half and retry each sub-chunk once.
    lines = chunk_text.splitlines()
    mid = len(lines) // 2
    if mid == 0:
        raise LLMError(
            f"Statement {label} exceeded the LLM output token limit "
            f"({_EXTRACTION_MAX_TOKENS} tokens) and is too small to split further. "
            "The statement section may contain unusually long lines."
        )

    txns: list[_RawTransaction] = []
    for sub_text in ("\n".join(lines[:mid]), "\n".join(lines[mid:])):
        if not sub_text.strip():
            continue
        try:
            sub_result: _ExtractionResult = await client.parse(
                system=system_prompt,
                user=build_user_prompt(sub_text),
                response_format=_ExtractionResult,
                temperature=0.0,
                max_completion_tokens=_EXTRACTION_MAX_TOKENS,
            )
            txns.extend(sub_result.transactions)
        except LLMError as sub_exc:
            raise LLMError(
                f"Statement {label} exceeded the LLM output token limit "
                f"({_EXTRACTION_MAX_TOKENS} tokens) even after splitting. "
                "The statement section may be too dense or the model too slow."
            ) from sub_exc
    return txns


def _coerce(raw: _RawTransaction, account_ref: str) -> ExtractedTransaction:
    """Convert LLM-facing types to the shared contract types."""
    try:
        amount = Decimal(str(raw.amount))
    except InvalidOperation:
        log.error("Could not parse amount %r — defaulting to 0", raw.amount)
        amount = Decimal("0")

    balance_after: Decimal | None = None
    if raw.balance_after is not None:
        try:
            balance_after = Decimal(str(raw.balance_after))
        except InvalidOperation:
            log.warning(
                "Could not parse balance_after %r — setting to None", raw.balance_after
            )

    clean_tags = _drop_category_tags(
        _drop_merchant_tags(_normalize_tags(raw.tags), raw.merchant),
        raw.category,
    )

    return ExtractedTransaction(
        transaction_date=date.fromisoformat(raw.transaction_date),
        amount=amount,
        currency=raw.currency or "EUR",
        description=raw.description,
        raw_line=raw.raw_line,
        category=raw.category,
        category_confidence=raw.category_confidence,
        account_ref=account_ref,
        balance_after=balance_after,
        tags=clean_tags,
        merchant=raw.merchant,
        detail=raw.detail,
    )


_MAX_TAGS = 3


def _normalize_tags(tags: list[str]) -> list[str]:
    """Normalize LLM-suggested tags: strip, lowercase, dedupe, drop empties, cap at _MAX_TAGS."""
    seen: set[str] = set()
    result: list[str] = []
    for tag in tags:
        normalized = tag.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
        if len(result) == _MAX_TAGS:
            break
    return result


# Matches one or more leading emoji characters (common Unicode emoji blocks + variation selectors).
_LEADING_EMOJI_RE = re.compile(
    r"^[\U00002600-\U000027BF\U0001F000-\U0001FFFF\uFE00-\uFE0F\u200D]+"
)


def _tag_core(tag: str) -> str:
    """Return the comparable core of an already-normalized tag: strip any leading emoji."""
    return _LEADING_EMOJI_RE.sub("", tag).strip()


def _drop_merchant_tags(tags: list[str], merchant: str | None) -> list[str]:
    """Drop any tag whose core value (leading emoji stripped) equals the normalized merchant.

    Tags are already lowercased/stripped by _normalize_tags. The merchant is compared
    case-insensitively. Returns the input list unchanged when merchant is None.
    """
    if merchant is None:
        return tags
    merchant_norm = merchant.strip().lower()
    if not merchant_norm:
        return tags
    return [tag for tag in tags if _tag_core(tag) != merchant_norm]


# Pre-built set of forbidden tag values: all EN + ES base category names, lowercased.
# Rebuilt once at import time for O(1) membership checks.
_BASE_CATEGORY_NAMES_LOWER: frozenset[str] = frozenset(
    c.strip().lower() for c in BASE_CATEGORIES
) | frozenset(v.strip().lower() for v in BASE_CATEGORY_ES.values())


def _drop_category_tags(tags: list[str], category: str) -> list[str]:
    """Drop any tag that duplicates a category name (EN or ES) or the row's own category.

    Checks both the transaction's specific category (handles custom/proposed ones)
    and the full set of base category names in English and Spanish.
    Tags already normalized (lowercase + stripped) by _normalize_tags.
    """
    category_norm = category.strip().lower()
    result = []
    for tag in tags:
        core = _tag_core(tag)
        if core == category_norm:
            continue  # restates the row's own category
        if core in _BASE_CATEGORY_NAMES_LOWER:
            continue  # matches any base category name (EN or ES)
        result.append(tag)
    return result
