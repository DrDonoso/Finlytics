"""Capa de consultas de la API de Finlytics.

Todas las funciones publicas reciben un ``AsyncSession`` y devuelven dicts de
Python, de modo que los routers quedan finos y la logica de agregacion se puede
probar por separado.

Convencion de signo (refleja Transaction.amount):
  amount < 0  -> gasto / salida de dinero
  amount > 0  -> ingreso / entrada / devolucion

Las agregaciones de gasto devuelven **magnitudes positivas**
(-amount WHERE amount < 0).

Organizacion
------------
Era un unico modulo de 1175 lineas con veinticinco funciones que mezclaban
cuentas, categorias, etiquetas, transacciones, agregaciones y extractos. Ahora
se reparte por dominios, pero este paquete vuelve a exportarlo todo: los routers
hacen ``from finlytics.db import queries`` y llaman a ``queries.get_accounts``,
y los tests parchean ``finlytics.db.queries.<funcion>``. Ambos patrones siguen
funcionando exactamente igual.
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
    # Categorias y etiquetas
    "create_tag",
    "delete_tag",
    "get_categories",
    "get_tags",
    "update_category",
    "update_tag",
    # Transacciones
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
    # Helpers internos: se reexportan porque hay tests que los usan directamente
    "_apply_filters",
    "_expense_expr",
    "_income_expr",
    "_split_leading_emoji",
]
