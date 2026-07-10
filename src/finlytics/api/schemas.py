"""Pydantic response schemas for the Finlytics REST API.

All amount fields are declared as ``float`` so FastAPI serialises them as JSON
numbers (not Decimal strings). Precision loss is acceptable in the API layer;
the DB stores full Numeric(14,2) precision.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from finlytics.contracts import ExtractedTransaction  # pydantic-only, no circular dep


# ── Tags ──────────────────────────────────────────────────────────────────────

class TagOut(BaseModel):
    id: int
    name: str
    color: str
    emoji: str | None = None
    tx_count: int = 0


class TagCreate(BaseModel):
    """Request body for POST /api/tags."""
    name: str
    color: str | None = None   # if None, server_default (#64748b) is used
    emoji: str | None = None   # optional emoji glyph (separate from name)


class TagUpdate(BaseModel):
    """Request body for PATCH /api/tags/{tag_id} — all fields optional.

    For ``emoji``: omitting the field leaves it unchanged; sending ``null``
    clears it; sending a non-empty string sets it.  The endpoint uses
    ``model_fields_set`` to distinguish "not provided" from "set to null".
    """
    name: str | None = None
    color: str | None = None
    emoji: str | None = None


# ── Accounts ──────────────────────────────────────────────────────────────────

def mask_account_number(number: str | None) -> str | None:
    """Mask an IBAN for display: country code (2 chars) + last 4 visible, middle masked.

    Examples:
      ``"ES7921000813610123456789"``  →  ``"ES******************6789"``
      ``None``                        →  ``None``
      Very short (≤6 chars)          →  returned as-is
    """
    if number is None:
        return None
    if len(number) <= 6:
        return number
    return number[:2] + "*" * (len(number) - 6) + number[-4:]


class AccountOut(BaseModel):
    id: int
    name: str
    type: str | None
    currency: str
    tx_count: int = 0
    account_number_masked: str | None = None


class AccountPatch(BaseModel):
    """Request body for PATCH /api/accounts/{account_id} — name only.

    Account number is immutable and may not be updated through this endpoint.
    """
    name: str


class DeleteAccountResult(BaseModel):
    """Response for DELETE /api/accounts/{account_id}."""
    deleted: int


# ── Categories ────────────────────────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    is_base: bool
    color: str
    name_es: str | None = None
    tx_count: int = 0


class CategoryCreate(BaseModel):
    """Request body for POST /api/categories."""
    name: str
    color: str | None = None


class CategoryUpdate(BaseModel):
    """Request body for PATCH /api/categories/{category_id} — color only for now."""
    color: str | None = None


# ── Transactions ──────────────────────────────────────────────────────────────

class TransactionOut(BaseModel):
    id: int
    transaction_date: date
    amount: float          # signed: negative=expense, positive=income
    currency: str
    description: str
    category: str
    account: str
    category_confidence: float | None
    balance_after: float | None
    tags: list[str] = []   # tag names; empty when no tags are attached
    merchant: str | None = None
    detail: str | None = None


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class TransactionUpdate(BaseModel):
    """Request body for PATCH /api/transactions/{id} — all fields optional."""
    description: str | None = None
    category: str | None = None    # category NAME; resolved via get_or_create_category
    amount: float | None = None    # signed: negative=expense, positive=income
    tags: list[str] | None = None  # when present, replaces the full tag set; [] clears all
    merchant: str | None = None    # "" clears to NULL; brand name sets it; None = no change


# ── Summary ───────────────────────────────────────────────────────────────────

class TopCategory(BaseModel):
    name: str
    amount: float          # expense magnitude (positive)


class OverviewOut(BaseModel):
    total_expense: float   # positive magnitude
    total_income: float
    net: float             # total_income - total_expense
    num_transactions: int
    top_category: TopCategory | None
    currency: str


class ByCategoryRow(BaseModel):
    category_id: int
    category: str
    amount: float          # expense magnitude (positive)
    count: int


class ByMonthRow(BaseModel):
    month: str             # "YYYY-MM"
    expense: float
    income: float
    net: float


class ByAccountRow(BaseModel):
    account: str
    expense: float
    income: float
    net: float
    currency: str


class CashflowCategoryRow(BaseModel):
    category: str
    amount: float          # always positive (magnitude)


class CashflowOut(BaseModel):
    """Response for GET /api/summary/cashflow (Sankey diagram source data)."""
    income: list[CashflowCategoryRow]   # positive transactions per category, desc
    expense: list[CashflowCategoryRow]  # expense magnitudes per category, desc
    total_income: float
    total_expense: float
    currency: str


# ── Statements ────────────────────────────────────────────────────────────────

class StatementMonth(BaseModel):
    """One calendar month that has ≥1 transaction."""
    year: int
    month: int
    count: int


class DeleteMonthResult(BaseModel):
    """Response for DELETE /api/statements/month."""
    deleted: int


# ── Backup ────────────────────────────────────────────────────────────────────

class BackupAccountIn(BaseModel):
    """Account entry inside a backup document."""
    name: str
    type: str
    currency: str


class BackupCategoryIn(BaseModel):
    """Category entry inside a backup document."""
    name: str
    is_base: bool
    color: str
    name_es: str | None = None


class BackupTagIn(BaseModel):
    """Tag entry inside a backup document."""
    name: str
    color: str
    emoji: str | None = None


class BackupTransactionIn(BaseModel):
    """Transaction entry inside a backup document."""
    transaction_date: date      # Pydantic parses "YYYY-MM-DD"
    amount: float               # signed: negative=expense, positive=income
    currency: str
    description: str
    merchant: str | None = None
    category: str | None = None   # canonical category name; null → uncategorised
    account: str                  # account name
    category_confidence: float | None = None
    balance_after: float | None = None
    tags: list[str] = []          # tag names


class BackupDocument(BaseModel):
    """Full backup payload — version 1 schema."""
    finlytics_backup_version: int
    exported_at: str
    accounts: list[BackupAccountIn] = []
    categories: list[BackupCategoryIn] = []
    tags: list[BackupTagIn] = []
    transactions: list[BackupTransactionIn] = []


class ImportSummary(BaseModel):
    """Response for POST /api/backup/import."""
    accounts_created: int
    accounts_existing: int
    categories_created: int
    categories_updated: int
    tags_created: int
    tags_updated: int
    transactions_inserted: int
    transactions_duplicates: int


# ── Imports ───────────────────────────────────────────────────────────────────

class ImportResult(BaseModel):
    import_run_id: int
    num_parsed: int
    num_inserted: int
    num_duplicates: int


class SuggestedTag(BaseModel):
    """AI-suggested color for a newly-proposed tag in an import preview."""
    name: str
    color: str  # hex #RRGGBB


class PreviewOut(BaseModel):
    """Response from POST /api/imports/preview — extracted transactions not yet persisted."""
    account_ref: str | None
    filename: str
    transactions: list[ExtractedTransaction]
    statement_year: int | None
    year_detected: bool
    suggested_tags: list[SuggestedTag] = []
    # IBAN detection fields (None when no IBAN found in the statement header)
    detected_account_masked: str | None = None  # masked IBAN for display
    detected_account_iban: str | None = None    # full IBAN (owner-approved over localhost)
    matched_account_id: int | None = None       # set when IBAN maps to an existing account
    matched_account_name: str | None = None     # name of the matched account


class ConfirmIn(BaseModel):
    """Request body for POST /api/imports/confirm — user-reviewed transaction list."""
    account_name: str | None = None  # required when account_number absent or new
    source_filename: str
    transactions: list[ExtractedTransaction]
    tag_colors: dict[str, str] | None = None
    account_number: str | None = None  # full IBAN; when provided, account resolved by number


class CheckDuplicatesItem(BaseModel):
    """Single transaction entry for POST /api/imports/check-duplicates."""
    transaction_date: date
    amount: Decimal  # signed; Decimal preserves exact string form for dedup_hash
    description: str
    detail: str | None = None


class CheckDuplicatesIn(BaseModel):
    """Request body for POST /api/imports/check-duplicates."""
    account_name: str
    transactions: list[CheckDuplicatesItem]


class CheckDuplicatesOut(BaseModel):
    """Response for POST /api/imports/check-duplicates.

    ``is_duplicate[i]`` is True when transaction[i] would be silently skipped
    by confirm (its dedup_hash already exists in the DB, OR it is a repeat of
    an earlier entry in this same request batch).
    """
    is_duplicate: list[bool]


# ── Rules ─────────────────────────────────────────────────────────────────────

class RulePreviewResult(BaseModel):
    """Response for POST /api/rules/preview."""
    count: int


class RuleApplyResult(BaseModel):
    """Response for POST /api/rules/apply and POST /api/rules/{id}/apply."""
    applied: int


class RuleIn(BaseModel):
    """Request body for POST /api/rules."""
    name: str
    priority: int = 100
    enabled: bool = True
    description_mode: Literal["contains", "starts_with", "exact", "regex"]
    description_value: str
    amount_sign: Literal["negative", "positive"] | None = None
    amount_min: float | None = None   # abs(tx.amount) >= amount_min when set; must be >= 0
    amount_max: float | None = None   # abs(tx.amount) <= amount_max when set; must be >= 0
    account_ref: str | None = None
    currency: str | None = None
    detail_mode: Literal["contains", "starts_with", "exact", "regex"] | None = None
    detail_value: str | None = None
    set_category: str | None = None
    set_merchant: str | None = None
    add_tags: list[str] = []
    skip_ai: bool = False


class RuleUpdate(BaseModel):
    """Request body for PATCH /api/rules/{id} — all fields optional."""
    name: str | None = None
    priority: int | None = None
    enabled: bool | None = None
    description_mode: Literal["contains", "starts_with", "exact", "regex"] | None = None
    description_value: str | None = None
    amount_sign: Literal["negative", "positive"] | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    account_ref: str | None = None
    currency: str | None = None
    detail_mode: Literal["contains", "starts_with", "exact", "regex"] | None = None
    detail_value: str | None = None
    set_category: str | None = None
    set_merchant: str | None = None
    add_tags: list[str] | None = None
    skip_ai: bool | None = None


class RuleOut(BaseModel):
    """Response schema for a rule."""
    id: int
    name: str
    priority: int
    enabled: bool
    description_mode: str
    description_value: str
    amount_sign: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    account_ref: str | None = None
    currency: str | None = None
    detail_mode: str | None = None
    detail_value: str | None = None
    set_category: str | None = None
    set_merchant: str | None = None
    add_tags: list[str] = []
    skip_ai: bool
    created_at: datetime
    updated_at: datetime
