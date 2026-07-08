"""Prompt templates for the LLM extraction step.

Keeping prompts in version-controlled files (not inline strings) makes them
auditable, diffable, and easy to iterate on without touching business logic.
"""

from __future__ import annotations

from finlytics.extraction.taxonomy import CATEGORIZATION_GUIDANCE, categories_for_prompt

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_TEMPLATE = """
You are a financial data extraction assistant specialising in Spanish and EU bank statements.
Your task is to extract ALL transactions from the provided bank-statement text and return them
as structured JSON matching the given schema.

## Extraction rules
- Extract EVERY transaction visible in the text. Do not skip any.
- Dates must be in ISO 8601 format: YYYY-MM-DD.
- Amounts are SIGNED: negative = money OUT (expenses, fees, debits),
  positive = money IN (income, refunds, credits).
- Currency defaults to "EUR" unless explicitly stated otherwise in the statement.
- `raw_line`: copy the verbatim line(s) from the statement that this transaction came from.
- `account_ref`: MUST be set to "{account_ref}".
- ⚠ PII boundary: do NOT include account numbers, IBANs, or card numbers in the
  `description` field. Use the merchant name or a generic label instead.
- If the statement shows a running balance per transaction, populate `balance_after`.
- ⚠ READABILITY: `description` and `detail` must always be human-readable. Bank statements
  often encode concepts as ALL-CAPS-no-space tokens (e.g. "ADEUDOASUCARGO"). NEVER copy these
  raw tokens verbatim — infer proper word boundaries and use natural sentence/Title case.

{year_handling}

{bold_detail_handling}

{merchant_extraction}

{categorization_guidance}

{tag_suggestion}

## Output
Return ONLY valid JSON matching the schema. No markdown fences, no commentary.
""".strip()

# ---------------------------------------------------------------------------
# Year-handling instruction blocks
# ---------------------------------------------------------------------------

_YEAR_KNOWN_BLOCK = """
## Year handling
The statement year is {year}. Transaction lines may show only day/month (e.g. "15/06" or "15 jun").
- When a line has no explicit year, assign {year}.
- If a line contains a full date with an explicit year, use THAT explicit year.
- You MUST NOT invent or guess a year. Use only the year present on the line, or {year} as the fallback.
""".strip()

_YEAR_UNKNOWN_BLOCK = """
## Year handling
No statement year could be determined from the document metadata.
- Use a year ONLY when it is explicitly present on the transaction line or elsewhere in the statement text.
- You MUST NOT fabricate or invent a year. If no year can be found for a transaction, use the year from the nearest dated context in the statement.
""".strip()

# ---------------------------------------------------------------------------
# Merchant extraction instruction block
# ---------------------------------------------------------------------------

_MERCHANT_BLOCK = """
## Merchant extraction

For each transaction, extract the normalized brand or vendor name.

Rules:
- Use the **well-known brand name in Title Case**: e.g. "Amazon", "Mercadona", "Zara",
  "H&M", "Octopus Energy", "Netflix", "Renfe", "Uber", "Spotify", "Iberdrola".
- Do NOT include branch locations, city names, reference codes, or terminal IDs — brand only.
- Brand names are NOT translated — always use the official brand name
  (e.g. "Amazon" not "Amazón", "H&M" not "H y M").
- Return **null** when there is no identifiable merchant:
  - Transfers between accounts or to a person (TRANSFERENCIA, BIZUM to a person)
  - ATM withdrawals or cash transactions
  - Taxes or fees paid to government bodies
  - Salary / payroll / nómina entries
  - Any line where the merchant cannot be reliably determined from the description
- Do NOT invent merchants. If uncertain, return null.
""".strip()

# ---------------------------------------------------------------------------
# Tag-suggestion instruction block
# ---------------------------------------------------------------------------

_TAG_SUGGESTION_BLOCK = """
## Tag suggestion

For each transaction suggest **0–3** short, free-form tag names that describe the
specific *purpose or type* of the transaction with more granularity than the category alone.

Rules:
- Tags are OPTIONAL — use an empty list (`[]`) when nothing meaningful applies.
  It is perfectly fine (and common) for a transaction to have NO tags.
- Tags are **THEMATIC/semantic** labels describing the kind or purpose of the transaction,
  e.g. "agua", "luz", "gas", "internet", "teléfono", "mascotas",
  "préstamo", "cashback", "promoción", "viaje", "bebé", "comunidad".
- Tags are in **Spanish, lowercase, 1–2 words**.
- Tags COMPLEMENT the category — they are the fine detail, not a replacement.
  Example: category = "Utilities", tag = "luz" for an IBERDROLA electricity bill.
- ⚠ NEVER use a CATEGORY name (in English OR Spanish) as a tag, and do NOT restate
  the transaction's category. Tags must be ORTHOGONAL, more-specific drill-down labels.
  Examples: category "Utilities"/"Suministros" → tags "luz", "agua" (NOT "suministros");
  category "Housing"/"Vivienda" → tags "préstamo", "comunidad" (NOT "vivienda").
  Prefer ZERO tags over a redundant category tag.
- ⚠ NEVER use a merchant / store / brand / company name as a tag
  (bad: "amazon", "mercadona", "zara", "h&m", "netflix", "repsol", "lidl" — those
  belong ONLY in the `merchant` field). Do NOT duplicate the transaction's merchant as a tag.
- Preferred seed tags — reuse these when they apply:
  luz · agua · gas · internet · teléfono
- Do NOT include PII in tags (no account numbers, card numbers, or the account holder's name).
- Cap at 3 tags per transaction.
""".strip()

# ---------------------------------------------------------------------------
# Bold/detail markup instruction block
# ---------------------------------------------------------------------------

_BOLD_DETAIL_BLOCK = """
## Bold concept / detail markup

The statement parser may have annotated some transaction descriptions with bold/detail markup.
Bank statements often encode concept titles WITHOUT spaces and in ALL CAPS
(e.g. `**ADEUDOASUCARGO**`). Do NOT copy these raw tokens verbatim — always normalise
to readable Spanish text.

Format:  **BOLDCONCEPT** optional-non-bold-detail

Extraction rules:
- Strip the `**` markers.
- `description` = the bold concept, rewritten as human-readable Spanish with proper word
  spacing and natural sentence/Title case. The readable form MUST be STABLE for the same
  concept type so users can write rules against it — every occurrence of the same concept
  must produce the exact same readable description.
  Examples of normalisation:
    `**ADEUDOASUCARGO**`                → description "Adeudo a su cargo"
    `**PAGOCONTARJETAENSUPERMERCADOS**` → description "Pago con tarjeta en supermercados"
    `**CASHBACKPROMOCIONCOMERCIAL**`    → description "Cashback promoción comercial"
- `detail` = the non-bold text that follows the `**...**` marker, likewise normalised to
  readable text (infer word boundaries; use natural brand/name casing).
  Set `detail` to null when there is no non-bold text after the marker.
  Examples of normalisation:
    `**ADEUDOASUCARGO** GCREOCTOPUSENERGY`            → detail "Octopus Energy"
    `**ADEUDOASUCARGO** PASSATGEFERROCARRILSCATALANS40-42` → detail "Passatge Ferrocarrils Catalans 40-42"
- If a line has NO `**` markers, set `description` to the full line text (normalised, not
  verbatim) and `detail` to null.
- ⚠ Do NOT include the `**` characters in `description` or `detail`.
- ⚠ NEVER emit ALL-CAPS-no-space strings in `description` or `detail` — always the
  readable, properly spaced form.
""".strip()

# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------

_USER_TEMPLATE = """
Extract all transactions from the following bank statement text.

--- STATEMENT START ---
{statement_text}
--- STATEMENT END ---
""".strip()


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------


def build_system_prompt(account_ref: str, statement_year: int | None = None) -> str:
    """Render the system prompt for a given account source."""
    guidance = CATEGORIZATION_GUIDANCE.format(categories=categories_for_prompt())
    year_block = (
        _YEAR_KNOWN_BLOCK.format(year=statement_year)
        if statement_year is not None
        else _YEAR_UNKNOWN_BLOCK
    )
    return _SYSTEM_TEMPLATE.format(
        account_ref=account_ref,
        categorization_guidance=guidance,
        year_handling=year_block,
        bold_detail_handling=_BOLD_DETAIL_BLOCK,
        merchant_extraction=_MERCHANT_BLOCK,
        tag_suggestion=_TAG_SUGGESTION_BLOCK,
    )


def build_user_prompt(statement_text: str) -> str:
    """Render the user prompt for the given raw statement text."""
    return _USER_TEMPLATE.format(statement_text=statement_text)
