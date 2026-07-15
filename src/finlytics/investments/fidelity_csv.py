"""Fidelity 'View open lots' CSV parser — deterministic, no LLM.

Parses the manual export "View open lots.csv" produced by Fidelity
NetBenefits for ESPP / stock-plan accounts.  Pure function: bytes in →
dataclasses out.  No I/O, no DB, no network.
"""
from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_DATE_FMT = "%b-%d-%Y"   # e.g. Jun-30-2026
_TICKER = "MSFT"

# Footer pattern: "The values are displayed in EUR"
_CURRENCY_RE = re.compile(r"the values are displayed in\s+(\w+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NormalizedLot:
    """One open tax lot normalised from a 'View open lots' CSV row."""

    purchase_date: date
    shares: Decimal
    cost_basis: Decimal
    cost_basis_per_share: Decimal
    source_currency: str
    share_source: str        # "SP" = ESPP purchase | "DO" = dividend reinvest
    grant_date: date | None
    holding_period: str | None
    dedup_ordinal: int       # 0-based index within identical-key groups


@dataclass
class ParsedOpenLots:
    """Full result of parsing a Fidelity open-lots CSV export."""

    lots: list[NormalizedLot]
    source_currency: str
    ticker: str  # always "MSFT" for this connector


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _detect_currency(text: str) -> str:
    """Return ISO currency code from footer line; default 'USD'."""
    m = _CURRENCY_RE.search(text)
    return m.group(1).upper() if m else "USD"


def _parse_decimal(raw: str, eu_style: bool = False) -> Decimal:
    """Parse a locale-aware numeric string to Decimal.

    Auto-detects separator style when both dot and comma are present
    (rightmost = decimal separator).  *eu_style* is used only for the
    ambiguous single-comma case (e.g. '50,0000').
    """
    s = raw.strip().lstrip("\u20ac$\xa3").strip()
    if not s:
        raise ValueError(f"Empty numeric field: {raw!r}")

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        if s.rfind(".") > s.rfind(","):
            s = s.replace(",", "")                       # US: 1,234.56
        else:
            s = s.replace(".", "").replace(",", ".")     # EU: 1.234,56
    elif has_comma:
        if eu_style:
            s = s.replace(",", ".")                      # EU decimal: 50,0000
        else:
            s = s.replace(",", "")                       # US thousands: 1,234
    # elif has_dot only, or plain integer → already correct

    try:
        return Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"Cannot parse decimal from {raw!r}") from exc


def _parse_date(raw: str) -> date | None:
    """Parse Mon-DD-YYYY string; return None for '-' or blank."""
    s = raw.strip()
    if not s or s == "-":
        return None
    try:
        return datetime.strptime(s, _DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"Cannot parse date from {raw!r}") from exc


def _is_data_row(row: list[str]) -> bool:
    """True iff the row has enough non-empty cells to be a lot row."""
    if len([c for c in row if c.strip()]) < 11:
        return False
    first = row[0].strip()
    if not first:
        return False
    if first.lower().startswith("total"):
        return False
    if "values are displayed" in first.lower():
        return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_open_lots_csv(file_bytes: bytes) -> ParsedOpenLots:
    """Parse a Fidelity 'View open lots.csv' export.

    Structure handled:
    - Optional UTF-8 BOM.
    - Preamble / footer lines skipped automatically.
    - Trailing 'Total' aggregation row skipped.
    - Both US ('.') and EU (',') decimal styles; see :func:`_parse_decimal`.
    - Currency detected from footer text.
    - ``dedup_ordinal`` assigned 0, 1, 2 … within groups sharing identical
      ``(purchase_date, shares, cost_basis_per_share, share_source)``.
    """
    text = file_bytes.decode("utf-8-sig")  # strips BOM when present

    currency = _detect_currency(text)
    eu_style = currency == "EUR"

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    # Locate header row: first row whose first cell is 'Date acquired'
    header_idx = next(
        (
            i
            for i, r in enumerate(rows)
            if r and r[0].strip().lower() == "date acquired"
        ),
        None,
    )
    if header_idx is None:
        raise ValueError("Header row 'Date acquired' not found in CSV")

    ordinal_counter: dict[tuple, int] = defaultdict(int)
    lots: list[NormalizedLot] = []

    for row in rows[header_idx + 1 :]:
        if not _is_data_row(row):
            continue

        (
            date_acquired,
            quantity,
            cost_basis,
            cost_basis_per_share,
            _value,
            _gain_loss,
            _sale_avail,
            _transfer_avail,
            grant_date_raw,
            share_source,
            holding_period,
        ) = [c.strip() for c in row[:11]]

        purchase_date = _parse_date(date_acquired)
        if purchase_date is None:
            continue  # skip rows with unparseable dates

        shares = _parse_decimal(quantity, eu_style=eu_style)
        cb = _parse_decimal(cost_basis, eu_style=eu_style)
        cbps = _parse_decimal(cost_basis_per_share, eu_style=eu_style)
        grant_date = _parse_date(grant_date_raw)
        hp = holding_period if holding_period not in ("-", "") else None

        dedup_key = (purchase_date, shares, cbps, share_source)
        ordinal = ordinal_counter[dedup_key]
        ordinal_counter[dedup_key] += 1

        lots.append(
            NormalizedLot(
                purchase_date=purchase_date,
                shares=shares,
                cost_basis=cb,
                cost_basis_per_share=cbps,
                source_currency=currency,
                share_source=share_source,
                grant_date=grant_date,
                holding_period=hp,
                dedup_ordinal=ordinal,
            )
        )

    return ParsedOpenLots(lots=lots, source_currency=currency, ticker=_TICKER)
