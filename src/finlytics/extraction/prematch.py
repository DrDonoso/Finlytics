"""Pre-LLM rule matcher — Phase 2 of the rules engine.

``pre_match_rules`` runs **before** the LLM call.  It scans raw statement
text line-by-line, identifies lines that a user-defined rule already matches,
extracts the transaction date and signed amount deterministically, and returns:

* ``matched_txs``    — fully-built ``ExtractedTransaction`` objects that never
  reach the LLM.
* ``remaining_text`` — statement text with matched lines removed (the
  reduced input sent to ``extract_transactions()``), saving LLM tokens.

SAFETY NET
----------
If a line's description matches a rule but date/amount extraction fails
(e.g. the line is a header, footer, or summary row rather than a real
transaction row), the line is left in ``remaining_text`` unchanged and a
``WARNING`` is logged.  No partial or corrupt transaction is ever emitted.
The LLM then processes the line as normal.

This guarantee means pre-matching can never produce data loss — it only
achieves cost savings when lines are confidently parseable.

Per-bank line formats
---------------------
Both BBVA and Indexa Capital share the same column layout::

    DD/MM/YYYY   DESCRIPTION   AMOUNT   BALANCE/PORTFOLIO_VALUE

BBVA examples::

    02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID   -45,30   1.404,70
    15/05/2026   NOMINA EMPRESA TECH SL                2.850,00   4.083,40
    20/05/2026   COMPRA EN EXTERIOR AMAZON USA         -25,00 USD  4.090,24

Indexa Capital examples::

    05/05/2026   APORTACION PERIODICA AUTOMATICA      +500,00   12.950,00
    12/05/2026   COMISION DE GESTION INDEXA CAPITAL     -3,25   12.946,75
    28/05/2026   TRANSFERENCIA A ES49 0182 ...        -200,00   12.768,00

Both use European number format: period = thousands separator, comma = decimal
point.  BBVA may omit the ``+`` prefix on positive amounts (income appears as
unsigned); Indexa always uses an explicit ``+`` or ``-`` sign.

Boundary
--------
Pure, synchronous — no DB access, no network calls.  Re-uses
``_description_matches`` and ``_compile_regex`` from ``rules.py`` via the
same duck-typed ``RuleProtocol`` interface.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, NamedTuple, Optional

from finlytics.contracts import ExtractedTransaction
from finlytics.extraction.rules import (
    RuleProtocol,
    _BoundedPattern,
    _compile_regex,
    _description_matches,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal result type from bank-format extractors
# ---------------------------------------------------------------------------


class _LineData(NamedTuple):
    """Structured result from a successful single-line parse."""

    date: date
    amount: Decimal
    description: str
    balance_after: Optional[Decimal]


# ---------------------------------------------------------------------------
# Shared European number / date helpers (exported for tests)
# ---------------------------------------------------------------------------


def _parse_european_amount(s: str) -> Decimal:
    """Convert a European-format number string to ``Decimal``.

    European convention: period = thousands separator, comma = decimal point.

    Examples::

        _parse_european_amount("-45,30")       → Decimal("-45.30")
        _parse_european_amount("+500,00")      → Decimal("500.00")
        _parse_european_amount("2.850,00")     → Decimal("2850.00")
        _parse_european_amount("1.234.567,89") → Decimal("1234567.89")

    Raises ``decimal.InvalidOperation`` on malformed / empty input.
    """
    cleaned = s.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def _parse_european_date(s: str, year: int) -> date:
    """Parse a ``DD/MM/YYYY`` or ``DD/MM`` date string.

    When the year component is absent (``DD/MM`` only), the provided *year*
    is used.  Raises ``ValueError`` for unrecognised formats or out-of-range
    date values.
    """
    parts = s.strip().split("/")
    if len(parts) == 3:
        day, month, yr = int(parts[0]), int(parts[1]), int(parts[2])
    elif len(parts) == 2:
        day, month, yr = int(parts[0]), int(parts[1]), year
    else:
        raise ValueError(
            f"Cannot parse date from {s!r}: expected DD/MM or DD/MM/YYYY"
        )
    return date(yr, month, day)


# ---------------------------------------------------------------------------
# Shared transaction-line regex
# ---------------------------------------------------------------------------
#
# Captures:
#   group 1 — date string   (DD/MM/YYYY or DD/MM)
#   group 2 — description   (lazy: stops at first ≥2-space run before amount)
#   group 3 — amount string (optional leading +/- sign, European format)
#   group 4 — balance/portfolio value (optional second European number)
#
# Handles:
#   • No sign, negative (-), positive (+) amounts
#   • Optional 3-letter currency suffix after amount (e.g. "USD" for BBVA
#     foreign-currency lines)
#   • Optional balance/portfolio column (group 4 may be None)

_EURO_STMT_LINE_RE = re.compile(
    r"^"
    r"(\d{2}/\d{2}/\d{4}|\d{2}/\d{2})"            # group 1: date
    r"\s+"
    r"(.+?)"                                         # group 2: description (lazy)
    r"\s{2,}"                                        # ≥2-space column separator
    r"([-+]?\d{1,3}(?:\.\d{3})*,\d{2})"            # group 3: amount
    r"(?:\s*[A-Z]{3})?"                              # optional currency suffix
    r"(?:\s{2,}(\d{1,3}(?:\.\d{3})*,\d{2}))?"      # group 4: balance (optional)
    r"\s*$",
)


def _parse_line(line: str, statement_year: int) -> _LineData | None:
    """Match *line* against the shared European statement regex and parse fields.

    Returns ``None`` for non-matching lines (headers, blank lines, totals rows).
    All sub-parser exceptions are caught and converted to ``None``; callers
    rely on this contract.
    """
    m = _EURO_STMT_LINE_RE.match(line)
    if not m:
        return None
    try:
        tx_date = _parse_european_date(m.group(1), statement_year)
        amount = _parse_european_amount(m.group(3))
        description = m.group(2).strip()
        balance_after = _parse_european_amount(m.group(4)) if m.group(4) else None
    except (ValueError, InvalidOperation):
        return None
    return _LineData(tx_date, amount, description, balance_after)


# ---------------------------------------------------------------------------
# Per-bank extractor functions
# ---------------------------------------------------------------------------


def _extract_bbva(line: str, statement_year: int) -> _LineData | None:
    """Extract date, amount, description, and balance from a BBVA statement line.

    Returns ``None`` for non-transaction lines (headers, totals, blank lines).

    Format::

        DD/MM/YYYY   DESCRIPTION   AMOUNT   BALANCE

        02/05/2026   COMPRA EN MERCADONA C/MAYOR 1 MADRID   -45,30   1.404,70
        15/05/2026   NOMINA EMPRESA TECH SL                2.850,00   4.083,40
        20/05/2026   COMPRA EN EXTERIOR AMAZON USA         -25,00 USD  4.090,24

    BBVA omits the ``+`` prefix on positive amounts (income / refunds appear
    as plain unsigned numbers, e.g. ``2.850,00`` and ``29,99``).
    """
    return _parse_line(line, statement_year)


def _extract_indexa(line: str, statement_year: int) -> _LineData | None:
    """Extract date, amount, description, and portfolio value from an Indexa Capital line.

    Returns ``None`` for non-transaction lines.

    Format::

        DD/MM/YYYY   DESCRIPTION   +/-AMOUNT   PORTFOLIO_VALUE

        05/05/2026   APORTACION PERIODICA AUTOMATICA      +500,00   12.950,00
        12/05/2026   COMISION DE GESTION INDEXA CAPITAL     -3,25   12.946,75
        28/05/2026   TRANSFERENCIA A ES49 0182 ...        -200,00   12.768,00

    Indexa uses explicit ``+`` for positive movements (deposits, dividends,
    interest) and ``-`` for outflows (fees, transfers out).
    """
    return _parse_line(line, statement_year)


def _extract_generic(line: str, statement_year: int) -> _LineData | None:
    """Generic fallback extractor for unknown or future account types.

    Uses the same European date+amount layout as BBVA and Indexa Capital.
    Works for any statement where a ``DD/MM(/YYYY)`` date leads the line and
    amounts use European formatting.  Returns ``None`` when the line does not
    match — triggering the safety net so the line is preserved for the LLM.
    """
    return _parse_line(line, statement_year)


# Dispatch table: lowercased account_ref → extractor function.
_EXTRACTORS: dict = {
    "bbva": _extract_bbva,
    "indexa capital": _extract_indexa,
}


def _get_extractor(account_ref: str):
    """Return the per-bank extractor for *account_ref* (case-insensitive lookup)."""
    return _EXTRACTORS.get(account_ref.strip().lower(), _extract_generic)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pre_match_rules(
    statement_text: str,
    rules: Iterable[RuleProtocol],
    *,
    statement_year: int,
    account_ref: str,
    currency: str = "EUR",
) -> tuple[list[ExtractedTransaction], str]:
    """Deterministically extract matched transactions from raw statement text.

    Runs **before** the LLM call.  For each line in *statement_text*, enabled
    rules are evaluated in ``(priority, id)`` ascending order.  If a rule's
    description predicate matches AND the line's date/amount parse successfully
    AND all optional filters (``amount_sign``, ``account_ref``, ``currency``)
    pass, an ``ExtractedTransaction`` is built from the rule's actions and the
    parsed fields.  The line is **removed** from the returned
    ``remaining_text`` (which is sent to the LLM, reducing token cost).

    Args:
        statement_text:  Raw text produced by ``parse_statement()``.
        rules:           Iterable of objects satisfying ``RuleProtocol``.
        statement_year:  Four-digit year used when a line's date is ``DD/MM``
                         only.  Pass the result of ``detect_statement_year()``
                         when available.
        account_ref:     Source account identifier (e.g. ``"BBVA"`` or
                         ``"Indexa Capital"``).  Selects the bank-format
                         extractor and populates
                         ``ExtractedTransaction.account_ref``.
        currency:        ISO 4217 currency code (default ``"EUR"``).

    Returns:
        ``(matched_txs, remaining_text)`` where:

        - ``matched_txs`` — fully built ``ExtractedTransaction`` objects ready
          to merge with the LLM-extracted results (Shuri's responsibility in
          Wave 3).
        - ``remaining_text`` — statement text with matched lines removed.
          Pass to ``extract_transactions()`` to reduce LLM token cost.
          May be empty / whitespace-only if every transaction line matched.

    SAFETY NET
    ----------
    If a line matches a rule's description predicate but date/amount cannot be
    extracted (e.g. it is a header, a summary row, or an unexpected format),
    the line is left in ``remaining_text`` unchanged and a ``WARNING`` is
    logged.  No partial or corrupt transaction is ever emitted.

    Rules whose ``set_category`` is ``None`` are skipped for pre-matching
    because a complete ``ExtractedTransaction`` requires a category; partial
    rules (set_category=None) rely on the LLM for categorisation and their
    lines pass through unchanged.

    This function is **pure** and **synchronous** — no DB access, no network.
    """
    enabled_rules = sorted(
        (r for r in rules if r.enabled),
        key=lambda r: (r.priority, r.id),
    )

    # Pre-compile regex patterns once (mirrors apply_rules approach)
    compiled: dict[int, _BoundedPattern | None] = {
        r.id: _compile_regex(r)
        for r in enabled_rules
        if r.description_mode == "regex"
    }

    extractor = _get_extractor(account_ref)

    matched_txs: list[ExtractedTransaction] = []
    remaining_lines: list[str] = []

    for line in statement_text.splitlines():
        line_consumed = False

        for rule in enabled_rules:
            # Rules without set_category cannot produce a complete transaction;
            # skip them — their lines go to the LLM unchanged.
            if rule.set_category is None:
                continue

            regex_pat = compiled.get(rule.id)
            if not _description_matches(line, rule, regex_pat):
                continue

            # Description matched — attempt deterministic date/amount extraction.
            line_data = extractor(line, statement_year)
            if line_data is None:
                # SAFETY NET: description matched but line is not parseable as a
                # transaction row (header, summary line, unexpected format, etc.).
                # Leave in remaining_text; LLM processes it as normal.
                logger.warning(
                    "Rule %d (%r): description matched but date/amount extraction "
                    "failed — line kept for LLM. Line: %r",
                    rule.id,
                    rule.name,
                    line[:100],
                )
                break  # Stop evaluating rules for this line; safety net applies.

            # Apply amount_sign / account_ref / currency filters now that the
            # amount is known — mirrors the filter logic in apply_rules exactly.
            if rule.amount_sign == "negative" and line_data.amount >= 0:
                continue
            if rule.amount_sign == "positive" and line_data.amount <= 0:
                continue
            # Magnitude filters: abs(line_data.amount) vs optional bounds.
            if rule.amount_min is not None and abs(line_data.amount) < rule.amount_min:
                continue
            if rule.amount_max is not None and abs(line_data.amount) > rule.amount_max:
                continue
            if rule.account_ref is not None:
                if (account_ref or "").lower() != rule.account_ref.lower():
                    continue
            if rule.currency is not None:
                if currency.lower() != rule.currency.lower():
                    continue

            # All conditions passed — build the ExtractedTransaction.
            # set_merchant, if provided, doubles as the human-readable description.
            description = (
                rule.set_merchant
                if rule.set_merchant is not None
                else line_data.description
            )

            tx = ExtractedTransaction(
                transaction_date=line_data.date,
                amount=line_data.amount,
                currency=currency,
                description=description,
                raw_line=line,
                category=rule.set_category,
                category_confidence=1.0,
                account_ref=account_ref,
                balance_after=line_data.balance_after,
                merchant=rule.set_merchant,
                tags=list(rule.add_tags),
                matched_rule_id=rule.id,
                matched_rule_name=rule.name,
            )
            matched_txs.append(tx)
            line_consumed = True
            break  # First match wins; stop evaluating rules for this line.

        if not line_consumed:
            remaining_lines.append(line)

    remaining_text = "\n".join(remaining_lines)
    return matched_txs, remaining_text
