"""PII redaction for statement text BEFORE it is sent to the third-party LLM.

Policy (Romanoff — Security/Privacy):
    - This module masks sensitive identifiers (IBANs, card/PAN numbers, long
      account numbers) in parsed statement text.
    - ONLY applied at the LLM boundary. Local persistence retains full fidelity.
    - Preserves last 4 digits/chars so the LLM can still match transactions.
    - Preserves amounts, dates, and merchant names (needed for extraction).
    - Pure-Python regex — no external dependencies.

Masking strategy:
    - Replace masked characters with '•' (U+2022) — unambiguous placeholder that
      won't appear in legitimate statement text and is visually distinct in logs.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# IBAN redaction
# ---------------------------------------------------------------------------
# IBANs: 2 uppercase letters + 2 check digits + 8-30 alphanumeric characters.
# Often written with spaces every 4 chars (e.g. "ES91 2100 0418 4502 0005 1332").
# We match both compact and spaced formats.

_IBAN_COMPACT = re.compile(
    r"\b([A-Z]{2}\d{2})([A-Z0-9]{8,30})\b"
)

_IBAN_SPACED = re.compile(
    r"\b([A-Z]{2}\d{2})"         # country + check digits
    r"((?:\s[A-Z0-9]{4}){2,8})"  # groups of 4 separated by spaces
    r"\b"
)


def _mask_iban_compact(m: re.Match) -> str:
    """Mask compact IBAN, keeping country+check and last 4."""
    prefix = m.group(1)  # e.g. "ES91"
    body = m.group(2)    # e.g. "2100041845020005133"
    if len(body) < 5:
        return m.group(0)  # too short to be a real IBAN body
    masked = "•" * (len(body) - 4) + body[-4:]
    return prefix + masked


def _mask_iban_spaced(m: re.Match) -> str:
    """Mask spaced IBAN, keeping country+check and last 4 digits."""
    prefix = m.group(1)  # "ES91"
    body = m.group(2)    # " 2100 0418 4502 0005 1332"
    digits_only = body.replace(" ", "")
    if len(digits_only) < 5:
        return m.group(0)
    masked = "•" * (len(digits_only) - 4) + digits_only[-4:]
    # Re-format in groups of 4 with spaces for readability
    groups = [masked[i:i+4] for i in range(0, len(masked), 4)]
    return prefix + " " + " ".join(groups)


# ---------------------------------------------------------------------------
# Card / PAN number redaction
# ---------------------------------------------------------------------------
# Card numbers: 13-19 digits, possibly spaced in groups of 4 (or 4-6-5, etc).
# We handle both compact and grouped formats.
# Important: must NOT match dates (8 digits like 20240601) or amounts.

# Compact: 13-19 consecutive digits not preceded/followed by alphanumeric
_PAN_COMPACT = re.compile(
    r"(?<![A-Z0-9])(\d{13,19})(?![0-9])"
)

# Spaced/dashed: groups of 4+ digits separated by spaces or dashes, total 13-19 digits
_PAN_SPACED = re.compile(
    r"(?<!\d)"
    r"(\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{1,7})"  # 4-4-4-1..7
    r"(?!\d)"
)

_PAN_SPACED_ALT = re.compile(
    r"(?<!\d)"
    r"(\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}(?:[\s\-]\d{1,3})?)"  # 4-4-4-4(-1..3)?
    r"(?!\d)"
)


def _mask_pan(digits: str, separator: str = "") -> str:
    """Mask all but last 4 digits of a PAN."""
    clean = re.sub(r"[\s\-]", "", digits)
    if len(clean) < 13:
        return digits  # not a PAN
    masked = "•" * (len(clean) - 4) + clean[-4:]
    if separator:
        # Re-format in groups of 4
        groups = [masked[i:i+4] for i in range(0, len(masked), 4)]
        return separator.join(groups)
    return masked


def _mask_pan_compact(m: re.Match) -> str:
    return _mask_pan(m.group(1))


def _mask_pan_spaced(m: re.Match) -> str:
    text = m.group(1)
    sep = " " if " " in text else "-"
    return _mask_pan(text, sep)


# ---------------------------------------------------------------------------
# Long account number redaction
# ---------------------------------------------------------------------------
# Account numbers: sequences of 10-12 digits (or 16-20 for some formats) that
# don't match IBAN or PAN patterns. Common in Spanish banking: CCC (10 digits),
# full account ref (20 digits without country prefix).
# We avoid matching amounts (which have decimal separators) and dates.

_ACCOUNT_NUMBER = re.compile(
    r"(?<![A-Z\d.,])"    # not preceded by letter, digit, or decimal separator
    r"(\d{10,12})"       # 10-12 consecutive digits
    r"(?![0-9.,])"       # not followed by digit or decimal separator
)


def _mask_account_number(m: re.Match) -> str:
    """Mask long account number, keeping last 4."""
    num = m.group(1)
    return "•" * (len(num) - 4) + num[-4:]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def redact_pii(text: str) -> str:
    """Redact PII (IBANs, card numbers, account numbers) from statement text.

    Designed to be called on parsed statement text BEFORE sending to the LLM.
    Preserves amounts, dates, and merchant/description text needed for extraction.

    Returns:
        The text with sensitive identifiers masked (last 4 chars preserved).
    """
    if not text:
        return text

    # Order matters: IBANs first (they contain digit sequences that could match
    # account numbers), then PANs, then account numbers.
    result = _IBAN_SPACED.sub(_mask_iban_spaced, text)
    result = _IBAN_COMPACT.sub(_mask_iban_compact, result)
    result = _PAN_SPACED_ALT.sub(_mask_pan_spaced, result)
    result = _PAN_SPACED.sub(_mask_pan_spaced, result)
    result = _PAN_COMPACT.sub(_mask_pan_compact, result)
    result = _ACCOUNT_NUMBER.sub(_mask_account_number, result)

    return result
