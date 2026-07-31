"""Pydantic response schemas for the Finlytics REST API.

All amount fields are declared as ``float`` so FastAPI serialises them as JSON
numbers (not Decimal strings). Precision loss is acceptable in the API layer;
the DB stores full Numeric(14,2) precision.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import re

from pydantic import BaseModel, Field, field_validator, model_validator

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


class AccountCreate(BaseModel):
    """Request body for POST /api/accounts.

    ``opening_date`` is REQUIRED when ``opening_balance`` is provided (422 otherwise).
    An ``opening_balance`` of 0 is accepted but does NOT create a synthetic transaction.
    A non-zero ``opening_balance`` creates exactly one ImportRun + Transaction
    (description="Saldo inicial") so the account registers a valid starting point.

    ⚠️ KPI note: a positive opening_balance counts as "income" in summary/KPI queries
    because those aggregate all Transaction.amount values. This is intentional in the
    current slice; a follow-up proposal (is_system flag + KPI exclusion) exists in
    decisions/inbox/shuri-post-accounts-contract.md.
    """
    name: str
    type: str = "bank"
    currency: str = "EUR"
    account_number: str | None = None
    opening_balance: float | None = None
    opening_date: date | None = None

    @model_validator(mode="after")
    def _require_opening_date_with_balance(self) -> "AccountCreate":
        if self.opening_balance is not None and self.opening_date is None:
            raise ValueError("opening_date is required when opening_balance is provided")
        return self


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
    is_system: bool = False


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


class ByMerchantRow(BaseModel):
    merchant: str
    amount: float          # expense magnitude (positive)
    count: int


class ByMonthRow(BaseModel):
    month: str             # "YYYY-MM"
    expense: float
    income: float
    net: float


class ByDayRow(BaseModel):
    day: str               # "YYYY-MM-DD"
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


class TransactionMonthsOut(BaseModel):
    """Response for GET /api/summary/months — available months for the Home KPI picker."""
    months: list[str]   # ["YYYY-MM", ...] sorted ASC; frontend takes last as default
    latest: str | None  # months[-1] or None when no transactions exist


# ── Statements ────────────────────────────────────────────────────────────────

class StatementMonth(BaseModel):
    """One calendar month that has ≥1 transaction."""
    year: int
    month: int
    count: int


class StatementReminderOut(BaseModel):
    """Response from GET /statements/reminder."""
    year: int | None
    month: int | None
    missing_account_ids: list[int]


class DeleteMonthResult(BaseModel):
    """Response for DELETE /api/statements/month."""
    deleted: int


class StatementOriginal(BaseModel):
    """One ImportRun that has an associated PDF on disk."""
    import_run_id: int
    source_filename: str
    account_name: str
    imported_at: datetime


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


class BackupRuleIn(BaseModel):
    """Rule entry inside a backup document."""
    name: str
    priority: int = 100
    enabled: bool = True
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
    skip_ai: bool = False


class BackupInvestmentConnectionIn(BaseModel):
    """Investment connection entry inside a backup document.

    token_enc is the already-encrypted DB ciphertext and is never decrypted by
    backup export/import.
    """
    plugin_id: str
    status: str = "active"
    account_label_masked: str | None = None
    token_enc: str | None = None
    last_synced_at: datetime | None = None


class BackupEsppLotIn(BaseModel):
    """Fidelity ESPP lot entry inside a backup document."""
    connection_plugin_id: str = "fidelity-espp"
    ticker: str = "MSFT"
    purchase_date: date
    grant_date: date | None = None
    shares: float
    cost_basis: float
    cost_basis_per_share: float
    source_currency: str
    share_source: str
    holding_period: str | None = None
    dedup_hash: str


class BackupPriceHistoryIn(BaseModel):
    """Market price row entry inside a backup document."""
    ticker: str
    price_date: date
    close_usd: float
    fx_eur_usd: float
    close_eur: float


class BackupInvestmentsIn(BaseModel):
    """Investment section inside a backup document."""
    connections: list[BackupInvestmentConnectionIn] = []
    espp_lots: list[BackupEsppLotIn] = []
    price_history: list[BackupPriceHistoryIn] = []


class BackupDocument(BaseModel):
    """Backup payload — version-aware schema (v1 and v2)."""
    finlytics_backup_version: int
    exported_at: str
    accounts: list[BackupAccountIn] = []
    categories: list[BackupCategoryIn] = []
    tags: list[BackupTagIn] = []
    transactions: list[BackupTransactionIn] = []
    rules: list[BackupRuleIn] = []
    investments: BackupInvestmentsIn | None = None


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
    rules_created: int = 0
    rules_updated: int = 0
    investment_connections_created: int = 0
    investment_connections_updated: int = 0
    espp_lots_inserted: int = 0
    espp_lots_duplicates: int = 0
    price_history_inserted: int = 0
    price_history_duplicates: int = 0


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


class ImportQualitySummary(BaseModel):
    error_count: int
    warning_count: int
    info_count: int
    flagged_row_count: int


class ImportQualitySignal(BaseModel):
    code: str
    severity: str
    count: int


class ImportQualityRowFlag(BaseModel):
    row_index: int
    code: str
    severity: str
    fields: list[str]


class ImportQuality(BaseModel):
    summary: ImportQualitySummary
    signals: list[ImportQualitySignal]
    row_flags: list[ImportQualityRowFlag]


class PreviewOut(BaseModel):
    """Response from POST /api/imports/preview — extracted transactions not yet persisted."""
    account_ref: str | None
    filename: str
    transactions: list[ExtractedTransaction]
    statement_year: int | None
    year_detected: bool
    quality: ImportQuality
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
    source_pdf_base64: str | None = None  # raw base64 of the uploaded PDF (no data-URL prefix)
    # Opening balance for NEW accounts only. The server infers opening_date as
    # (earliest transaction_date − 1 day). Ignored when the account already exists.
    opening_balance: float | None = None


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


# ── Investments ───────────────────────────────────────────────────────────────

class InvestmentReturns(BaseModel):
    """Performance metrics from the provider's performance endpoint."""
    twr_annual: float | None = None    # time-weighted return, annualised
    twr_total: float | None = None     # cumulative TWR (time_return)
    twr_last_week: float | None = None
    twr_last_month: float | None = None
    twr_last_year: float | None = None
    money_return: float | None = None          # money-weighted total return
    money_return_annual: float | None = None   # annualised money-weighted return
    volatility: float | None = None            # portfolio volatility
    xirr: float | None = None                  # money-weighted annualised return (IRR)
    pl: float | None = None                    # absolute P&L (EUR)
    invested: float | None = None              # net capital invested
    # "Valor total" box numbers (mirror Indexa UI)
    aportaciones: float | None = None          # gross inflows
    retenciones: float | None = None           # tax outflows (negative)
    rentabilidad_eur: float | None = None      # P&L in EUR
    rentabilidad_pct: float | None = None      # money-weighted return %
    sharpe_ratio: float | None = None          # Sharpe ratio


class ValuePoint(BaseModel):
    """One (date, value) data-point in a portfolio value or contributions series."""
    date: str    # "YYYY-MM-DD" ISO format
    value: float


class ContributionEventOut(BaseModel):
    """A single contribution or withdrawal event derived from net_amounts deltas."""
    date: str        # YYYY-MM-DD
    amount: float    # positive = contribution, negative = withdrawal (rounded to cents)
    cumulative: float  # running net invested after this event
    type: str        # "contribution" | "withdrawal"


class DrawdownOut(BaseModel):
    """Max drawdown info from the provider."""
    max_drawdown: float       # fraction, negative (e.g. -0.1005)
    max_drawdown_eur: float   # EUR amount, negative (e.g. -1356.93)
    start_date: str           # YYYY-MM-DD
    end_date: str             # YYYY-MM-DD


class MonthlyReturnRow(BaseModel):
    """One calendar year row in the monthly returns matrix."""
    year: int
    months_pct: dict[int, float | None]   # {month: TWR return, or None if absent}
    months_eur: dict[int, float | None]   # {month: EUR P&L, or None if absent}
    total_pct: float | None = None        # compounded annual TWR return
    total_eur: float | None = None        # sum of monthly EUR P&L
    benchmark_pct: float | None = None    # compounded annual benchmark return


class CashInvestedSplit(BaseModel):
    """Breakdown of the latest portfolio snapshot (from Indexa portfolios[0], newest-first)."""
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float


class InvestmentPluginOut(BaseModel):
    """Response schema for a single investment plugin descriptor."""
    id: str
    name: str
    description: str
    icon: str
    status: str             # coming_soon | available | connected | error
    auth_type: str          # api_key | oauth | token | none
    supported_features: list[str]
    import_route: str | None = None  # frontend route for in-app CSV import; None when not supported


class InvestmentHoldingOut(BaseModel):
    """Normalised holding returned by any investment plugin."""
    plugin_id: str
    name: str
    ticker: str | None = None
    asset_class: str        # equity | fixed_income | mixed | crypto | cash | other
    units: float | None = None
    current_value: float
    cost_basis: float | None = None
    currency: str
    gain_loss: float | None = None
    gain_loss_pct: float | None = None
    last_updated: str       # ISO datetime string


class InvestmentPortfolioOut(BaseModel):
    """Aggregated portfolio summary across all connected plugins."""
    total_value: float
    total_invested: float | None = None
    total_gain_loss: float | None = None
    total_gain_loss_pct: float | None = None
    currency: str
    holdings: list[InvestmentHoldingOut]
    plugins_connected: int
    last_updated: str | None = None
    # Phase 2 — full visualisation fields
    returns: InvestmentReturns | None = None
    value_series: list[ValuePoint] = []
    contributions_series: list[ValuePoint] = []
    contribution_events: list[ContributionEventOut] = []
    monthly_returns: list[MonthlyReturnRow] | None = None
    drawdown: DrawdownOut | None = None
    cash_invested: CashInvestedSplit | None = None
    # Cache freshness metadata — additive/optional; frontend may use for a stale indicator
    cached_at: str | None = None      # ISO datetime of the oldest cache fetch across connections
    cache_stale: bool = False          # True when stale data returned + async refresh scheduled


class ValidateTokenRequest(BaseModel):
    """Request body for POST /api/investments/connections/validate."""
    token: str


class DiscoveredAccountOut(BaseModel):
    """One account discovered during token validation.

    Returned transiently to the wizard — raw ``account_number`` is only used
    by the next connect step and is NEVER stored (Romanoff §2).
    """
    account_number: str          # raw (sent back to client for the connect call)
    account_number_masked: str   # PBK•••Z5 — for display in the wizard
    type: str
    status: str


class ValidateTokenResponse(BaseModel):
    """Response for POST /api/investments/connections/validate."""
    accounts: list[DiscoveredAccountOut]


class ConnectCreate(BaseModel):
    """Request body for POST /api/investments/connections."""
    token: str
    account_numbers: list[str]   # subset from validate step; server re-validates ownership


class ConnectionOut(BaseModel):
    """Connection record returned to the frontend.

    Token is NEVER included — only metadata and the masked account label.
    """
    id: int
    plugin_id: str
    status: str                         # active | error | disconnected
    account_label_masked: str | None = None
    created_at: datetime
    last_synced_at: datetime | None = None


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


# ── Fidelity ESPP ─────────────────────────────────────────────────────────────

class FidelityPreviewLotOut(BaseModel):
    """One lot in the preview diff."""
    purchase_date: str           # YYYY-MM-DD
    shares: float
    cost_basis_per_share_eur: float
    cost_basis_total_eur: float
    share_source: str            # SP | DO
    grant_date: str | None = None
    source_currency: str


class FidelityPreviewOut(BaseModel):
    """Response from POST /investments/fidelity/import/preview."""
    new_lots: list[FidelityPreviewLotOut]
    duplicate_count: int
    total_in_file: int
    source_currency: str
    file_already_imported: bool


class FidelityImportResult(BaseModel):
    """Response from POST /investments/fidelity/import/confirm."""
    inserted: int
    duplicates: int


class FidelityKpisOut(BaseModel):
    """Aggregated KPIs for the Fidelity ESPP portfolio."""
    total_shares: float
    invested_eur: float
    current_value_eur: float | None = None
    gain_loss_eur: float | None = None
    gain_loss_pct: float | None = None      # e.g. 12.5 for +12.5 %
    msft_price_usd: float | None = None
    usd_eur_rate: float | None = None       # fx_eur_usd = EUR per USD
    last_price_date: str | None = None      # YYYY-MM-DD
    price_stale: bool = True
    as_of_date: str                         # YYYY-MM-DD


class FidelityEvolutionOut(BaseModel):
    """Response from GET /investments/fidelity/evolution."""
    value_series: list[ValuePoint]
    contributions_series: list[ValuePoint]


class FidelityLotOut(BaseModel):
    """Single lot with current market valuation."""
    id: int
    purchase_date: str           # YYYY-MM-DD
    shares: float
    cost_basis_per_share_eur: float
    cost_basis_total_eur: float
    current_value_eur: float | None = None
    gain_loss_eur: float | None = None
    gain_loss_pct: float | None = None      # percentage
    share_source: str            # SP | DO
    grant_date: str | None = None


class FidelityLotsOut(BaseModel):
    """Response from GET /investments/fidelity/lots."""
    lots: list[FidelityLotOut]


class FidelityReminderOut(BaseModel):
    """Response from GET /investments/fidelity/reminder."""
    overdue: bool
    expected_date: str | None = None    # YYYY-MM-DD of the most recent expected ESPP purchase
    period_label: str | None = None     # e.g. "Q2 2026"
    last_lot_date: str | None = None    # YYYY-MM-DD of the latest SP lot in DB


# ── Investments Combined Overview ─────────────────────────────────────────────

class ProviderAllocationItem(BaseModel):
    """Provider slice in the by-provider allocation donut."""
    provider: str   # "indexa" | "fidelity"
    label: str      # display name — i18n applied on frontend
    value_eur: float
    pct: float      # percentage of total_value_eur (0–100)


class AssetClassAllocationItem(BaseModel):
    """Asset-class slice in the by-asset-class allocation donut."""
    asset_class: str    # "equity" | "fixed_income" | "cash" | "espp_stock" | "other"
    label: str          # display label — i18n applied on frontend
    value_eur: float
    pct: float          # percentage of total_value_eur (0–100)


class ProviderCardOut(BaseModel):
    """Summary card for one investment provider on the /investments overview page."""
    id: str                               # "indexa-capital" | "fidelity-espp"
    name: str
    icon: str
    value_eur: float | None = None        # null when current price unavailable
    gain_loss_eur: float | None = None    # null when current price unavailable
    gain_loss_pct: float | None = None    # percentage e.g. 19.4 for +19.4 %; null when unavailable
    route: str                            # frontend route: "/investments/{plugin_id}"


class CombinedOverviewOut(BaseModel):
    """Response for GET /api/investments/combined-overview.

    Aggregated investments overview across all connected providers
    (Indexa Capital + Fidelity ESPP).
    """
    total_value_eur: float
    total_invested_eur: float | None = None
    total_gain_loss_eur: float | None = None
    total_gain_loss_pct: float | None = None    # percentage e.g. 19.03 for +19.03 %
    by_provider: list[ProviderAllocationItem]
    by_asset_class: list[AssetClassAllocationItem]
    providers: list[ProviderCardOut]


# ── Notifications ─────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    """Response DTO for a single notification.

    title_key / title_args are i18n keys + args — rendered client-side in EN/ES.
    No PII, no tokens, no rendered strings from the backend.
    """

    id: int
    source: str            # "statement" | "espp" | …
    type: str              # "missing_statement" | "espp_overdue" | …
    severity: str          # "info" | "warning"
    title_key: str
    title_args: dict
    body_key: str | None = None
    body_args: dict | None = None
    action_link: str | None = None
    created_at: datetime
    read_at: datetime | None = None
    dismissed_at: datetime | None = None


class UnreadCountOut(BaseModel):
    """Response for GET /api/notifications/unread-count."""

    count: int


class ReadAllOut(BaseModel):
    """Response for POST /api/notifications/read-all."""

    updated: int


class NotificationChannelOut(BaseModel):
    """Safe channel record returned to the frontend.

    config_enc, bot_token, and chat_id are NEVER included.
    label is a masked display string (e.g. "Telegram · ••••6789").
    """

    id: int
    channel: str           # "telegram"
    label: str | None = None
    enabled: bool
    created_at: datetime


_CHAT_ID_RE = re.compile(r"^-?\d+$")


def _validate_chat_id(value: str) -> str:
    """Require a numeric Telegram chat ID (e.g. -1001234567890 or 123456789).

    @username handles and any non-numeric strings are rejected.
    """
    if not _CHAT_ID_RE.match(value):
        raise ValueError(
            "chat_id must be a numeric Telegram ID (e.g. 123456789 or -1001234567890). "
            "@username handles are not supported."
        )
    return value


def _validate_message_thread_id(value: int | None, chat_id: str | None) -> int | None:
    """Require a positive thread ID that targets a group chat.

    Forum topics only exist in supergroups, whose chat IDs are negative. A
    thread ID paired with a positive (private) chat ID is always a mistake and
    Telegram would reject the send at delivery time.
    """
    if value is None:
        return None
    if value <= 0:
        raise ValueError("message_thread_id must be a positive integer.")
    if chat_id is not None and not chat_id.startswith("-"):
        raise ValueError(
            "message_thread_id is only valid for group chats "
            "(a negative chat_id such as -1001234567890)."
        )
    return value


class TelegramChannelIn(BaseModel):
    """Request body for POST /api/notifications/channels."""

    bot_token: str
    chat_id: str                        # stored as string; must be a numeric Telegram ID
    message_thread_id: int | None = None  # optional forum topic inside a group

    @field_validator("chat_id")
    @classmethod
    def validate_chat_id(cls, v: str) -> str:
        return _validate_chat_id(v)

    @model_validator(mode="after")
    def validate_thread(self) -> "TelegramChannelIn":
        _validate_message_thread_id(self.message_thread_id, self.chat_id)
        return self


class TelegramTestIn(BaseModel):
    """Request body for POST /api/notifications/channels/telegram/test.

    If both bot_token and chat_id are provided, use them (wizard preview).
    If neither is provided, use the stored channel.
    """

    bot_token: str | None = None
    chat_id: str | None = None
    message_thread_id: int | None = None

    @field_validator("chat_id")
    @classmethod
    def validate_chat_id(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_chat_id(v)
        return v

    @model_validator(mode="after")
    def validate_thread(self) -> "TelegramTestIn":
        _validate_message_thread_id(self.message_thread_id, self.chat_id)
        return self


class TelegramTestOut(BaseModel):
    """Response for POST /api/notifications/channels/telegram/test."""

    ok: bool
    error: str | None = None


# ── Finance assistant ─────────────────────────────────────────────────────────

class AssistantStatusOut(BaseModel):
    """Response for GET /api/assistant/status.

    ``enabled`` is false when the OPENAI_* variables are unset or the feature is
    switched off.  The frontend hides the launcher on that basis, which is
    friendlier than a chat panel whose first message is a 503.
    """

    enabled: bool
    reason: str | None = None


class AssistantSuggestionsOut(BaseModel):
    """Starter prompts for an empty thread, as i18n keys (never prose)."""

    suggestions: list[str]


class AssistantToolCall(BaseModel):
    """Audit record of one tool the assistant ran while composing an answer."""

    name: str
    arguments: str
    ok: bool = True


class AssistantMessageOut(BaseModel):
    """One stored turn of a conversation."""

    id: int
    role: Literal["user", "assistant"]
    content: str
    tool_calls: list[AssistantToolCall] | None = None
    created_at: datetime


class AssistantConversationOut(BaseModel):
    """Conversation header, as listed in the thread picker."""

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AssistantConversationDetailOut(AssistantConversationOut):
    """Conversation header plus its full message list."""

    messages: list[AssistantMessageOut]


class AssistantMessageIn(BaseModel):
    """Request body for POST /api/assistant/conversations/{id}/messages."""

    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError("Message cannot be empty.")
        return text


class AssistantSettingsIn(BaseModel):
    """Request body for PUT /api/assistant/settings.

    Every field is optional and ``None`` means "clear the override and fall back
    to the environment default" — not "set to zero".
    """

    custom_instructions: str | None = None
    system_prompt: str | None = None
    rate_limit_messages: int | None = Field(default=None, ge=1, le=10_000)
    rate_limit_window_seconds: int | None = Field(default=None, ge=60, le=86_400)
    monthly_token_budget: int | None = Field(default=None, ge=1_000)

    @field_validator("custom_instructions")
    @classmethod
    def validate_instructions(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = v.strip()
        if not text:
            return None
        if len(text) > 2000:
            raise ValueError(
                "Custom instructions are limited to 2000 characters — they are "
                "resent to the model on every message."
            )
        return text

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: str | None) -> str | None:
        if v is None:
            return None
        text = v.strip()
        if not text:
            # Blank means "restore the default", not "send an empty prompt".
            return None
        if len(text) > 20_000:
            raise ValueError(
                "The system prompt is limited to 20000 characters — it is resent "
                "to the model on every message."
            )
        if "{context_block}" not in text:
            # Not a style rule: this placeholder is how the assistant learns
            # which accounts and categories exist. Without it the model has no
            # ids and starts guessing the ones it is told never to invent.
            raise ValueError(
                "The prompt must contain the {context_block} placeholder — it is "
                "where your accounts, categories and date range are injected. "
                "Without it the assistant cannot see what data you have."
            )
        return text


class AssistantSettingsOut(BaseModel):
    """Current settings, showing both what was stored and what is in force.

    The frontend needs both: a null override with a non-null effective value is
    "inherited from the environment", which reads very differently to the user
    than a value they chose themselves.
    """

    custom_instructions: str | None = None
    system_prompt: str | None = None
    rate_limit_messages: int | None = None
    rate_limit_window_seconds: int | None = None
    monthly_token_budget: int | None = None

    effective_rate_limit_messages: int
    effective_rate_limit_window_seconds: int
    max_custom_instructions_chars: int

    # The shipped prompt, so the editor can pre-fill it and offer a restore.
    default_system_prompt: str
    max_system_prompt_chars: int
    # Safety rules the saved prompt no longer contains. Advisory: the save is
    # allowed, but dropping one changes behaviour invisibly, because a
    # fabricated figure reads exactly like a calculated one.
    missing_safety_markers: list[str] = []


class AssistantUsagePeriod(BaseModel):
    """Token totals over one period."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    messages: int


class AssistantUsageDay(BaseModel):
    """One point of the daily usage series."""

    day: str
    tokens: int
    messages: int


class AssistantUsageOut(BaseModel):
    """Response for GET /api/assistant/usage."""

    this_month: AssistantUsagePeriod
    all_time: AssistantUsagePeriod
    by_day: list[AssistantUsageDay]
    monthly_token_budget: int | None = None
    budget_remaining: int | None = None
    # False when the provider never reports usage, so the UI can say "unknown"
    # instead of showing a confident zero.
    usage_available: bool = True

