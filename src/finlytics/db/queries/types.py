"""Shapes of the data the query layer returns.

These functions used to return ``dict[str, Any]``, which voided type checking
right at the boundary between the database and the API: if a query stopped
returning a key, or returned it under a different name, nothing caught it until
Pydantic failed at runtime while serialising the response.

``TypedDict`` is used rather than dataclasses on purpose: the values stay plain
dicts at runtime, so this does not change behaviour nor force a rewrite of the
tests, whose doubles return dicts.

Sign convention (mirrors Transaction.amount):
  amount < 0  -> expense / money out
  amount > 0  -> income / money in / refund

Expense amounts in the aggregations are **positive magnitudes**.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TypedDict

__all__ = [
    "AccountRow",
    "AccountSummaryRow",
    "CashflowItem",
    "CashflowSummary",
    "CategoryRow",
    "CategorySummaryRow",
    "DaySummaryRow",
    "MerchantSummaryRow",
    "MonthSummaryRow",
    "OverviewSummary",
    "StatementMonthRow",
    "StatementOriginalRow",
    "TagRow",
    "TopCategory",
    "TransactionRow",
    "UpdatedTransactionRow",
]


# ── Catalogues ───────────────────────────────────────────────────────────────

class AccountRow(TypedDict):
    id: int
    name: str
    type: str
    currency: str
    tx_count: int
    account_number: str | None


class CategoryRow(TypedDict):
    id: int
    name: str
    name_es: str | None
    is_base: bool
    color: str
    tx_count: int


class TagRow(TypedDict):
    id: int
    name: str
    color: str
    emoji: str | None


class TagWithCountRow(TagRow):
    tx_count: int


class CategoryUpdateRow(TypedDict):
    id: int
    name: str
    name_es: str | None
    is_base: bool
    color: str


# ── Transactions ─────────────────────────────────────────────────────────────

class TransactionRow(TypedDict):
    id: int
    transaction_date: str
    """ISO 8601. Reads serialise the date; writes return a date object."""
    amount: float
    currency: str
    description: str
    category: str
    account: str
    category_confidence: float | None
    balance_after: float | None
    tags: list[str]
    merchant: str | None
    detail: str | None
    is_system: bool


class UpdatedTransactionRow(TypedDict):
    id: int
    transaction_date: date
    """Unlike the read path, this carries the unserialised date object."""
    amount: float
    currency: str
    description: str
    category: str
    account: str
    category_confidence: float | None
    balance_after: float | None
    tags: list[str]
    merchant: str | None
    detail: str | None


# ── Aggregations ─────────────────────────────────────────────────────────────

class TopCategory(TypedDict):
    name: str
    amount: float


class OverviewSummary(TypedDict):
    total_expense: float
    total_income: float
    net: float
    num_transactions: int
    top_category: TopCategory | None
    currency: str


class CategorySummaryRow(TypedDict):
    category_id: int
    category: str
    amount: float
    count: int


class MerchantSummaryRow(TypedDict):
    merchant: str
    amount: float
    count: int


class MonthSummaryRow(TypedDict):
    month: str
    expense: float
    income: float
    net: float


class DaySummaryRow(TypedDict):
    day: str
    expense: float
    income: float
    net: float


class AccountSummaryRow(TypedDict):
    account: str
    expense: float
    income: float
    net: float
    currency: str


class CashflowItem(TypedDict):
    category: str
    amount: float


class CashflowSummary(TypedDict):
    income: list[CashflowItem]
    expense: list[CashflowItem]
    total_income: float
    total_expense: float
    currency: str


# ── Extractos ────────────────────────────────────────────────────────────────

class StatementMonthRow(TypedDict):
    year: int
    month: int
    count: int


class StatementOriginalRow(TypedDict):
    import_run_id: int
    source_filename: str
    account_name: str
    imported_at: datetime
