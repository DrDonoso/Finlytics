"""Expressions and filters shared by the rest of the queries.

Sign convention (mirrors Transaction.amount):
  amount < 0  -> expense / money out
  amount > 0  -> income / money in / refund

Expense aggregations return positive magnitudes
(-amount WHERE amount < 0).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Literal

from sqlalchemy import case, func, select

from finlytics.db.models import Tag, Transaction, transaction_tags


# ── Emoji helper ──────────────────────────────────────────────────────────────

# The quantifiers are possessive (`++`, `*+`) on purpose: none of the three
# parts gives ground to the next, so the engine never tries alternative splits.
# That search for splits is the polynomial ReDoS CodeQL flags. It could not be
# exploited on CPython (linear growth with inputs up to 8000 characters), but an
# ambiguous pattern is unnecessary in something the user writes anyway.
#
# Note this changes one edge case, and changes it for the better. A name made
# only of emojis used to be split so the last one acted as the name ("**" ->
# emoji "*", name "*"), contradicting the contract below: if stripping the prefix
# leaves an empty name, the name must be returned intact. The old pattern was
# also inconsistent with itself, because that split depended on whether the
# string ended in a space: without one it split, with one it did not. By not
# giving ground the pattern simply does not match and the name is returned whole
# in both cases.
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
