"""Finlytics API query layer.

Every public function takes an ``AsyncSession`` and returns plain Python dicts,
which keeps the routers thin and makes the aggregation logic testable on its
own.

Sign convention (mirrors Transaction.amount):
  amount < 0  -> expense / money out
  amount > 0  -> income / money in / refund

Expense aggregations return **positive magnitudes**
(-amount WHERE amount < 0).

Layout
------
This used to be a single 1175-line module with twenty-five functions mixing
accounts, categories, tags, transactions, aggregations and statements. It is now
split by domain, but this package re-exports everything: routers do
``from finlytics.db import queries`` and call ``queries.get_accounts``, and tests
patch ``finlytics.db.queries.<function>``. Both patterns keep working unchanged.
"""

from finlytics.db.queries._filters import (
    DedupCollisionError,
    _apply_filters,
    _expense_expr,
    _income_expr,
    _split_leading_emoji,
)
from finlytics.db.queries.accounts import (
    delete_account,
    get_account_by_id,
    get_accounts,
)
from finlytics.db.queries.catalog import (
    TagNameConflictError,
    create_tag,
    delete_tag,
    get_categories,
    get_tags,
    update_category,
    update_tag,
)
from finlytics.db.queries.statements import (
    delete_statement_month,
    get_statement_months,
    get_statement_originals,
)
from finlytics.db.queries.summaries import (
    get_by_account,
    get_by_category,
    get_by_day,
    get_by_merchant,
    get_by_month,
    get_cashflow,
    get_overview,
)
from finlytics.db.queries.transactions import (
    get_transactions,
    update_transaction,
)

__all__ = [
    # Excepciones
    "DedupCollisionError",
    "TagNameConflictError",
    # Cuentas
    "delete_account",
    "get_account_by_id",
    "get_accounts",
    # Categories and tags
    "create_tag",
    "delete_tag",
    "get_categories",
    "get_tags",
    "update_category",
    "update_tag",
    # Transactions
    "get_transactions",
    "update_transaction",
    # Resumenes
    "get_by_account",
    "get_by_category",
    "get_by_day",
    "get_by_merchant",
    "get_by_month",
    "get_cashflow",
    "get_overview",
    # Extractos
    "delete_statement_month",
    "get_statement_months",
    "get_statement_originals",
    # Internal helpers: re-exported because some tests use them directly
    "_apply_filters",
    "_expense_expr",
    "_income_expr",
    "_split_leading_emoji",
]
