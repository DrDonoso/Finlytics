"""Formas de los datos que devuelve la capa de consultas.

Las funciones devolvían ``dict[str, Any]``, lo que anulaba la comprobación de
tipos justo en la frontera entre la base de datos y la API: si una consulta
dejaba de devolver una clave, o la devolvía con otro nombre, nada lo detectaba
hasta que Pydantic fallaba en tiempo de ejecución al serializar la respuesta.

Se usan ``TypedDict`` y no dataclasses a propósito: los valores siguen siendo
diccionarios en tiempo de ejecución, así que este cambio no altera el
comportamiento ni obliga a reescribir los tests, que devuelven diccionarios en
sus dobles.

Convención de signo (refleja Transaction.amount):
  amount < 0  -> gasto / salida de dinero
  amount > 0  -> ingreso / entrada / devolución

Los importes de gasto en las agregaciones son **magnitudes positivas**.
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


# ── Catálogos ────────────────────────────────────────────────────────────────

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


# ── Transacciones ────────────────────────────────────────────────────────────

class TransactionRow(TypedDict):
    id: int
    transaction_date: str
    """ISO 8601. La lectura serializa la fecha; la escritura devuelve un date."""
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
    """A diferencia de la lectura, aquí va el objeto date sin serializar."""
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


# ── Agregaciones ─────────────────────────────────────────────────────────────

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
