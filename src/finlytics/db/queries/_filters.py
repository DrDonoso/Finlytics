"""Expresiones y filtros que comparten el resto de consultas.

Convencion de signo (refleja Transaction.amount):
  amount < 0  -> gasto / salida de dinero
  amount > 0  -> ingreso / entrada / devolucion

Las agregaciones de gasto devuelven magnitudes positivas
(-amount WHERE amount < 0).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from sqlalchemy import case, func, select

from finlytics.db.models import Tag, Transaction, transaction_tags


# ── Emoji helper ──────────────────────────────────────────────────────────────

# Los cuantificadores son posesivos (`++`, `*+`) a proposito: ninguna de las tres
# partes cede terreno a la siguiente, asi que el motor no prueba divisiones
# alternativas. Esa busqueda de divisiones es el ReDoS polinomico que senala
# CodeQL. No se ha conseguido explotar en CPython (crecimiento lineal con
# entradas de hasta 8000 caracteres), pero el patron ambiguo sobra igualmente en
# algo que escribe el usuario.
#
# Ojo: esto cambia un caso limite, y lo cambia a mejor. Un nombre formado solo
# por emojis se partia para que el ultimo hiciera de nombre ("**" -> emoji "*",
# nombre "*"), lo que contradice el contrato de abajo: si quitar el prefijo deja
# el nombre vacio, hay que devolver el nombre intacto. El patron viejo ademas era
# incoherente consigo mismo, porque ese reparto dependia de si la cadena
# terminaba en espacio o no: sin espacio partia, con espacio no. Al no ceder, el
# patron simplemente no casa y el nombre se devuelve entero en ambos casos.
_EMOJI_LEAD_RE = re.compile(
    r"^([\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u27BF]++)\s*+(\S.*)$",
    re.UNICODE,
)


def _split_leading_emoji(raw: str) -> tuple[str | None, str]:
    """Return ``(emoji, clean_name)`` by splitting a leading emoji from *raw*.

    Returns ``(None, raw)`` when *raw* has no leading emoji prefix, or when
    stripping the emoji would leave an empty name.
    """
    m = _EMOJI_LEAD_RE.match(raw)
    if m:
        clean = m.group(2).strip()
        if clean:
            return m.group(1), clean
    return None, raw


class DedupCollisionError(Exception):
    """Raised by update_transaction when the recomputed dedup_hash conflicts with another row."""


# ── Private helpers ───────────────────────────────────────────────────────────

def _expense_expr():
    """SUM of -amount for rows where amount < 0 (positive magnitude)."""
    return func.coalesce(
        func.sum(case((Transaction.amount < 0, -Transaction.amount), else_=0)),
        0,
    )


def _income_expr():
    """SUM of amount for rows where amount > 0."""
    return func.coalesce(
        func.sum(case((Transaction.amount > 0, Transaction.amount), else_=0)),
        0,
    )


def _apply_filters(
    stmt,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    day: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    merchant: str | None = None,
    exclude_system: bool = True,
):
    """Append WHERE clauses for the common optional filters.

    ``tags`` accepts one or more normalised tag names (OR semantics): a
    transaction matches when it has AT LEAST ONE of the given tags.
    A single-element list is equivalent to the old single-tag filter.

    ``flow`` restricts to one sign direction:
      * ``"expense"`` → amount < 0 (money out)
      * ``"income"``  → amount > 0 (money in / refunds)

    ``description`` performs a case-insensitive substring match (ILIKE).
    LIKE wildcards in the search term are escaped so ``%`` and ``_`` are
    treated as literals.

    ``amount_min`` / ``amount_max`` filter on the absolute magnitude of the
    amount so they work uniformly for both expenses and incomes.

    ``merchant`` performs a case-insensitive substring match (ILIKE) on the
    merchant column.  Same wildcard-escaping as ``description``.

    ``day`` filters to an exact calendar date (exact match on
    ``transaction_date``).  Intended for cross-filter drill-down from a
    heatmap click; takes precedence over any overlapping ``from_date`` /
    ``to_date`` range when combined.

    ``exclude_system`` (default ``True``) drops rows where
    ``Transaction.is_system`` is true — i.e. synthetic entries such as
    opening-balance ("Saldo inicial") transactions.  Pass ``False`` only
    when the caller explicitly needs to expose system rows (e.g. a future
    admin audit endpoint).
    """
    if from_date is not None:
        stmt = stmt.where(Transaction.transaction_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(Transaction.transaction_date <= to_date)
    if day is not None:
        stmt = stmt.where(Transaction.transaction_date == day)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if tags:
        tags_norm = [t.strip().lower() for t in tags]
        stmt = stmt.where(
            Transaction.id.in_(
                select(transaction_tags.c.transaction_id)
                .distinct()
                .join(Tag, Tag.id == transaction_tags.c.tag_id)
                .where(Tag.name.in_(tags_norm))
            )
        )
    if flow == "expense":
        stmt = stmt.where(Transaction.amount < 0)
    elif flow == "income":
        stmt = stmt.where(Transaction.amount > 0)
    if description is not None:
        term = description.strip()
        if term:
            # Escape LIKE special chars so the user's literal % / _ / \ are not wildcards.
            term = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(Transaction.description.ilike(f"%{term}%", escape="\\"))
    if amount_min is not None:
        stmt = stmt.where(func.abs(Transaction.amount) >= amount_min)
    if amount_max is not None:
        stmt = stmt.where(func.abs(Transaction.amount) <= amount_max)
    if merchant is not None:
        term = merchant.strip()
        if term:
            term = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(Transaction.merchant.ilike(f"%{term}%", escape="\\"))
    if exclude_system:
        stmt = stmt.where(Transaction.is_system == False)  # noqa: E712
    return stmt
