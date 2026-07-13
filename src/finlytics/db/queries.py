"""Async aggregation and query layer for the Finlytics API.

All public functions accept an ``AsyncSession`` and return plain Python dicts
so the API routers stay thin and the aggregation logic is independently
testable.

Sign convention (mirrors Transaction.amount):
  amount < 0  → expense / money out
  amount > 0  → income / money in / refund

Expense aggregations return **positive magnitudes** (−amount WHERE amount < 0).
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import case, delete, func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.db.models import Account, Category, ImportRun, Tag, Transaction, transaction_tags
from finlytics.db.repository import compute_dedup_hash, get_or_create_category, get_or_create_tag


# ── Emoji helper ──────────────────────────────────────────────────────────────

_EMOJI_LEAD_RE = re.compile(
    r"^([\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u27BF]+)\s*(.+)$",
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
    return stmt


# ── Account queries ───────────────────────────────────────────────────────────

async def get_accounts(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            Account.account_number,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Account)
        .outerjoin(Transaction, Transaction.account_id == Account.id)
        .group_by(Account.id, Account.name, Account.type, Account.currency, Account.account_number)
        .order_by(Account.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id, "name": r.name, "type": r.type, "currency": r.currency,
            "tx_count": r.tx_count, "account_number": r.account_number,
        }
        for r in rows
    ]


async def get_account_by_id(session: AsyncSession, account_id: int) -> dict[str, Any] | None:
    """Return a single account row with tx_count, or None if not found."""
    stmt = (
        select(
            Account.id,
            Account.name,
            Account.type,
            Account.currency,
            Account.account_number,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Account)
        .outerjoin(Transaction, Transaction.account_id == Account.id)
        .where(Account.id == account_id)
        .group_by(Account.id, Account.name, Account.type, Account.currency, Account.account_number)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    return {
        "id": row.id, "name": row.name, "type": row.type, "currency": row.currency,
        "tx_count": row.tx_count, "account_number": row.account_number,
    }


async def delete_account(session: AsyncSession, account_id: int) -> int | None:
    """Delete an account and all its transactions.

    Explicitly deletes transactions (which auto-cascades to transaction_tags
    via the DB-level ON DELETE CASCADE on transaction_tags.transaction_id),
    then import_runs, then the account — all in one transaction.

    Returns the number of transactions deleted, or ``None`` if the account
    does not exist.
    """
    async with session.begin():
        account = await session.get(Account, account_id)
        if account is None:
            return None
        tx_result = await session.execute(
            delete(Transaction).where(Transaction.account_id == account_id)
        )
        tx_count = tx_result.rowcount
        await session.execute(
            delete(ImportRun).where(ImportRun.account_id == account_id)
        )
        await session.delete(account)
    return tx_count


# ── Category queries ──────────────────────────────────────────────────────────

async def get_categories(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(
            Category.id,
            Category.name,
            Category.name_es,
            Category.is_base,
            Category.color,
            func.count(Transaction.id).label("tx_count"),
        )
        .select_from(Category)
        .outerjoin(Transaction, Transaction.category_id == Category.id)
        .group_by(Category.id, Category.name, Category.name_es, Category.is_base, Category.color)
        .order_by(Category.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "name_es": r.name_es,
            "is_base": r.is_base,
            "color": r.color,
            "tx_count": r.tx_count,
        }
        for r in rows
    ]


async def get_tags(session: AsyncSession) -> list[dict[str, Any]]:
    """Return all tags sorted alphabetically, each with a transaction count."""
    stmt = (
        select(
            Tag.id,
            Tag.name,
            Tag.color,
            Tag.emoji,
            func.count(transaction_tags.c.transaction_id).label("tx_count"),
        )
        .select_from(Tag)
        .outerjoin(transaction_tags, transaction_tags.c.tag_id == Tag.id)
        .group_by(Tag.id, Tag.name, Tag.color, Tag.emoji)
        .order_by(Tag.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"id": r.id, "name": r.name, "color": r.color, "emoji": r.emoji, "tx_count": r.tx_count}
        for r in rows
    ]


class TagNameConflictError(Exception):
    """Raised when creating or renaming a tag would duplicate an existing name."""


async def create_tag(
    session: AsyncSession,
    name: str,
    color: str | None = None,
    emoji: str | None = None,
) -> dict[str, Any]:
    """Create a new tag.  Raises ``TagNameConflictError`` if name already exists.

    Leading emoji is auto-split from *name* (e.g. "💡 luz" → name="luz",
    emoji="💡").  If an explicit *emoji* is supplied it takes precedence and
    only the name part is normalised.

    ``name`` is normalised (strip + lowercase after emoji split) before storage.
    ``color`` defaults to the server_default ("#64748b") when not supplied.
    """
    async with session.begin():
        derived_emoji, name_clean = _split_leading_emoji(name.strip())
        if emoji is None:
            emoji = derived_emoji
        name_norm = name_clean.strip().lower()

        existing = (
            await session.execute(select(Tag).where(Tag.name == name_norm))
        ).scalar_one_or_none()
        if existing is not None:
            raise TagNameConflictError(f"Tag '{name_norm}' already exists.")
        kwargs: dict[str, Any] = {"name": name_norm}
        if color is not None:
            kwargs["color"] = color
        if emoji is not None:
            kwargs["emoji"] = emoji
        tag = Tag(**kwargs)
        session.add(tag)
        await session.flush()
        return {"id": tag.id, "name": tag.name, "color": tag.color, "emoji": tag.emoji}


# Sentinel used internally by update_tag to distinguish "not provided" from "set to null".
_FIELD_UNSET = object()


async def update_tag(
    session: AsyncSession,
    tag_id: int,
    *,
    name: str | None = None,
    color: str | None = None,
    emoji: Any = _FIELD_UNSET,
) -> dict[str, Any] | None:
    """Rename and/or recolour/re-emoji a tag.

    Returns ``None`` if the tag does not exist.
    Raises ``TagNameConflictError`` if renaming to a name already held by a
    *different* tag.

    Leading emoji is auto-split from *name* when no explicit *emoji* is
    provided.  Example: rename to "💡 luz" with no emoji field → stored as
    name="luz", emoji="💡".

    ``emoji`` semantics (use ``model_fields_set`` in the endpoint):
    - not passed (default ``_FIELD_UNSET``) → derive from name if present; no
      change to emoji column when name has no leading emoji
    - passed as ``None`` → clear emoji (set to NULL)
    - passed as ``str``  → set emoji to that value
    """
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id))
        ).scalar_one_or_none()
        if tag is None:
            return None

        if name is not None:
            derived_emoji, name_clean = _split_leading_emoji(name.strip())
            name_norm = name_clean.strip().lower()
            # When no explicit emoji was provided, derive it from the name prefix.
            if emoji is _FIELD_UNSET and derived_emoji is not None:
                emoji = derived_emoji
            if name_norm != tag.name:
                conflict = (
                    await session.execute(
                        select(Tag).where(Tag.name == name_norm, Tag.id != tag_id)
                    )
                ).scalar_one_or_none()
                if conflict is not None:
                    raise TagNameConflictError(f"Tag '{name_norm}' already exists.")
                tag.name = name_norm

        if color is not None:
            tag.color = color

        if emoji is not _FIELD_UNSET:
            tag.emoji = emoji  # None → clears column; str → sets value

        await session.flush()
        return {"id": tag.id, "name": tag.name, "color": tag.color, "emoji": tag.emoji}


async def delete_tag(session: AsyncSession, tag_id: int) -> bool:
    """Delete a tag and its transaction_tags links (via CASCADE).

    Returns ``True`` if deleted, ``False`` if the tag does not exist.
    """
    async with session.begin():
        tag = (
            await session.execute(select(Tag).where(Tag.id == tag_id))
        ).scalar_one_or_none()
        if tag is None:
            return False
        await session.delete(tag)
        return True


async def update_category(
    session: AsyncSession,
    category_id: int,
    *,
    color: str | None = None,
) -> dict[str, Any] | None:
    """Update a category's color.

    Returns the updated category dict, or ``None`` if not found.
    Only ``color`` is writable for now (renaming base categories is out of scope).
    """
    async with session.begin():
        cat = (
            await session.execute(select(Category).where(Category.id == category_id))
        ).scalar_one_or_none()
        if cat is None:
            return None
        if color is not None:
            cat.color = color
        await session.flush()
        return {
            "id": cat.id,
            "name": cat.name,
            "name_es": cat.name_es,
            "is_base": cat.is_base,
            "color": cat.color,
        }


# ── Transaction queries ───────────────────────────────────────────────────────

# Allowlist mapping frontend sort keys to ORM columns.
_SORT_COLUMNS: dict[str, Any] = {
    "date": Transaction.transaction_date,
    "amount": Transaction.amount,
    "description": Transaction.description,
    "merchant": Transaction.merchant,
    "category": Category.name,
    "account": Account.name,
}


async def get_transactions(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    merchant: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "date",
    sort_dir: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    """Return ``(items, total)`` for the transactions list endpoint.

    ``sort_by`` must be one of the keys in ``_SORT_COLUMNS``; unknown values
    fall back to ``"date"``.  ``sort_dir`` must be ``"asc"`` or ``"desc"``;
    anything else falls back to ``"desc"``.

    A stable secondary sort on ``Transaction.id.desc()`` is always appended so
    pagination is deterministic even when the primary key ties.
    """
    # Coerce invalid inputs to safe defaults.
    if sort_by not in _SORT_COLUMNS:
        sort_by = "date"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"

    sort_col = _SORT_COLUMNS[sort_by]
    primary_order = nullslast(sort_col.asc() if sort_dir == "asc" else sort_col.desc())
    base = (
        select(
            Transaction.id,
            Transaction.transaction_date,
            Transaction.amount,
            Transaction.currency,
            Transaction.description,
            Transaction.category_confidence,
            Transaction.balance_after,
            Transaction.merchant,
            Transaction.detail,
            Category.name.label("category_name"),
            Account.name.label("account_name"),
        )
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .outerjoin(Category, Transaction.category_id == Category.id)
    )
    base = _apply_filters(
        base,
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
    )

    total: int = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        await session.execute(
            base
            .order_by(primary_order, Transaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).mappings().all()

    # Batch-load tags for the returned page (single query — no N+1).
    tx_ids = [row["id"] for row in rows]
    tag_map: dict[int, list[str]] = {}
    if tx_ids:
        tag_rows = (
            await session.execute(
                select(transaction_tags.c.transaction_id, Tag.name)
                .join(Tag, Tag.id == transaction_tags.c.tag_id)
                .where(transaction_tags.c.transaction_id.in_(tx_ids))
                .order_by(Tag.name)
            )
        ).all()
        for tx_id, tname in tag_rows:
            tag_map.setdefault(tx_id, []).append(tname)

    items = [
        {
            "id": row["id"],
            "transaction_date": row["transaction_date"].isoformat(),
            "amount": float(row["amount"]),
            "currency": row["currency"],
            "description": row["description"],
            "category": row["category_name"] or "Other",
            "account": row["account_name"],
            "category_confidence": row["category_confidence"],
            "balance_after": (
                float(row["balance_after"]) if row["balance_after"] is not None else None
            ),
            "tags": tag_map.get(row["id"], []),
            "merchant": row["merchant"],
            "detail": row["detail"],
        }
        for row in rows
    ]
    return items, total


# ── Aggregation queries ───────────────────────────────────────────────────────

async def get_overview(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    description: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    merchant: str | None = None,
    day: date | None = None,
) -> dict[str, Any]:
    stmt = _apply_filters(
        select(
            _expense_expr().label("total_expense"),
            _income_expr().label("total_income"),
            func.count(Transaction.id).label("num_transactions"),
        ).select_from(Transaction),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
        day=day,
    )
    row = (await session.execute(stmt)).one()
    total_expense = float(row.total_expense)
    total_income = float(row.total_income)

    # Top spending category within the same date/account/category/tag window
    top_stmt = _apply_filters(
        select(
            Category.name.label("name"),
            func.sum(-Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(Category.name)
        .order_by(func.sum(-Transaction.amount).desc())
        .limit(1),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        description=description,
        amount_min=amount_min,
        amount_max=amount_max,
        merchant=merchant,
        day=day,
    )
    top_row = (await session.execute(top_stmt)).one_or_none()

    # Currency: specific account's currency, or EUR as default
    currency = "EUR"
    if account_id is not None:
        acc_currency = (
            await session.execute(
                select(Account.currency).where(Account.id == account_id)
            )
        ).scalar_one_or_none()
        if acc_currency:
            currency = acc_currency

    return {
        "total_expense": total_expense,
        "total_income": total_income,
        "net": total_income - total_expense,
        "num_transactions": row.num_transactions,
        "top_category": (
            {"name": top_row.name, "amount": float(top_row.amount)}
            if top_row else None
        ),
        "currency": currency,
    }


async def get_by_category(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    merchant: str | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Expenses by category, sorted descending by magnitude."""
    stmt = _apply_filters(
        select(
            Category.id.label("category_id"),
            Category.name.label("category"),
            func.sum(-Transaction.amount).label("amount"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(Category.id, Category.name)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        tags=tags,
        flow=flow,
        merchant=merchant,
        day=day,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"category_id": r.category_id, "category": r.category, "amount": float(r.amount), "count": r.count}
        for r in rows
    ]


async def get_by_merchant(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    category_id: int | None = None,
    day: date | None = None,
) -> list[dict[str, Any]]:
    """Expenses by merchant, sorted descending by magnitude."""
    stmt = _apply_filters(
        select(
            Transaction.merchant.label("merchant"),
            func.sum(-Transaction.amount).label("amount"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .where(Transaction.amount < 0)
        .where(Transaction.merchant.is_not(None))
        .where(func.trim(Transaction.merchant) != "")
        .group_by(Transaction.merchant)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        tags=tags,
        flow=flow,
        category_id=category_id,
        day=day,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"merchant": r.merchant, "amount": float(r.amount), "count": r.count}
        for r in rows
    ]


async def get_by_month(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> list[dict[str, Any]]:
    """Expense / income / net grouped by calendar month (chronological)."""
    month_expr = func.to_char(Transaction.transaction_date, "YYYY-MM")
    stmt = _apply_filters(
        select(
            month_expr.label("month"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .group_by(month_expr)
        .order_by(month_expr),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "month": r.month,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
        }
        for r in rows
    ]


async def get_by_day(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
    merchant: str | None = None,
) -> list[dict[str, Any]]:
    """Expense / income / net grouped by calendar day (chronological)."""
    day_expr = func.to_char(Transaction.transaction_date, "YYYY-MM-DD")
    stmt = _apply_filters(
        select(
            day_expr.label("day"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .group_by(day_expr)
        .order_by(day_expr),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
        merchant=merchant,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "day": r.day,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
        }
        for r in rows
    ]


async def get_by_account(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> list[dict[str, Any]]:
    """Expense / income / net grouped by account."""
    stmt = _apply_filters(
        select(
            Account.name.label("account"),
            Account.currency.label("currency"),
            _expense_expr().label("expense"),
            _income_expr().label("income"),
        )
        .select_from(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .group_by(Account.name, Account.currency),
        from_date=from_date,
        to_date=to_date,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "account": r.account,
            "expense": float(r.expense),
            "income": float(r.income),
            "net": float(r.income) - float(r.expense),
            "currency": r.currency,
        }
        for r in rows
    ]


# ── Transaction mutation ──────────────────────────────────────────────────────

async def update_transaction(
    session: AsyncSession,
    transaction_id: int,
    *,
    description: str | None = None,
    amount: float | None = None,
    category_name: str | None = None,
    tags: list[str] | None = None,
    merchant: str | None = None,
) -> dict[str, Any] | None:
    """Apply a partial update to a transaction.

    Returns the updated transaction as a ``TransactionOut``-compatible dict,
    or ``None`` if the transaction does not exist.

    Raises ``DedupCollisionError`` when the recomputed dedup_hash would collide
    with a *different* existing transaction.

    The caller is responsible for managing the surrounding DB transaction; this
    function opens its own ``session.begin()`` scope.
    """
    async with session.begin():
        # ── 1. Load transaction (with tags for return value) ─────────────────
        tx = (
            await session.execute(
                select(Transaction)
                .where(Transaction.id == transaction_id)
                .options(selectinload(Transaction.tags))
            )
        ).scalar_one_or_none()

        if tx is None:
            return None

        # ── 2. Load account name (needed for dedup_hash computation) ─────────
        acc_name: str = (
            await session.execute(
                select(Account.name).where(Account.id == tx.account_id)
            )
        ).scalar_one()

        # ── 3. Resolve new field values (fall back to existing if not provided)
        new_description = description if description is not None else tx.description
        new_amount = Decimal(str(amount)) if amount is not None else tx.amount

        # ── 4. Dedup hash check (before any writes — fail fast) ───────────────
        new_hash = tx.dedup_hash
        if description is not None or amount is not None:
            candidate = compute_dedup_hash(
                account_ref=acc_name,
                transaction_date=tx.transaction_date,
                amount=new_amount,
                description=new_description,
                detail=tx.detail,
            )
            if candidate != tx.dedup_hash:
                collision_id = (
                    await session.execute(
                        select(Transaction.id).where(
                            Transaction.dedup_hash == candidate,
                            Transaction.id != transaction_id,
                        )
                    )
                ).scalar_one_or_none()
                if collision_id is not None:
                    raise DedupCollisionError(
                        f"Transaction id={collision_id} already has the same "
                        "account, date, amount, and description."
                    )
                new_hash = candidate

        # ── 5. Category resolution ────────────────────────────────────────────
        category_id = tx.category_id
        category_display: str | None = None
        if category_name is not None:
            cat = await get_or_create_category(session, category_name, is_base=False)
            category_id = cat.id
            category_display = cat.name
        elif tx.category_id is not None:
            category_display = (
                await session.execute(
                    select(Category.name).where(Category.id == tx.category_id)
                )
            ).scalar_one_or_none()

        # ── 6. Apply scalar updates ───────────────────────────────────────────
        tx.description = new_description
        tx.amount = new_amount
        tx.category_id = category_id
        tx.dedup_hash = new_hash

        # merchant: None = not provided (no change); "" = clear to NULL; str = set
        if merchant is not None:
            tx.merchant = None if merchant == "" else merchant

        # ── 7. Sync tags (replace full set when provided) ────────────────────
        if tags is not None:
            new_tags = [await get_or_create_tag(session, name) for name in tags]
            tx.tags = new_tags

        return {
            "id": tx.id,
            "transaction_date": tx.transaction_date,
            "amount": float(new_amount),
            "currency": tx.currency,
            "description": new_description,
            "category": category_display or "Other",
            "account": acc_name,
            "category_confidence": tx.category_confidence,
            "balance_after": (
                float(tx.balance_after) if tx.balance_after is not None else None
            ),
            "tags": [t.name for t in tx.tags],
            "merchant": tx.merchant,
            "detail": tx.detail,
        }


# ── Cashflow aggregation ──────────────────────────────────────────────────────

async def get_cashflow(
    session: AsyncSession,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    account_id: int | None = None,
    category_id: int | None = None,
    tags: list[str] | None = None,
    flow: Literal["expense", "income"] | None = None,
) -> dict[str, Any]:
    """Income and expense totals per category, for a Sankey diagram.

    * ``income``  — list of ``{category, amount}`` where amount > 0, sorted desc.
    * ``expense`` — list of ``{category, amount}`` (positive magnitudes), sorted desc.
    * Transactions with no category_id are bucketed under ``"Other"``.
    """
    category_expr = func.coalesce(Category.name, "Other")

    income_stmt = _apply_filters(
        select(
            category_expr.label("category"),
            func.sum(Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount > 0)
        .group_by(category_expr)
        .order_by(func.sum(Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )

    expense_stmt = _apply_filters(
        select(
            category_expr.label("category"),
            func.sum(-Transaction.amount).label("amount"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Transaction.category_id == Category.id)
        .where(Transaction.amount < 0)
        .group_by(category_expr)
        .order_by(func.sum(-Transaction.amount).desc()),
        from_date=from_date,
        to_date=to_date,
        account_id=account_id,
        category_id=category_id,
        tags=tags,
        flow=flow,
    )

    income_rows = (await session.execute(income_stmt)).all()
    expense_rows = (await session.execute(expense_stmt)).all()

    income = [{"category": r.category, "amount": float(r.amount)} for r in income_rows]
    expense = [{"category": r.category, "amount": float(r.amount)} for r in expense_rows]

    # Currency: specific account's currency, or EUR as default
    currency = "EUR"
    if account_id is not None:
        acc_currency = (
            await session.execute(
                select(Account.currency).where(Account.id == account_id)
            )
        ).scalar_one_or_none()
        if acc_currency:
            currency = acc_currency

    return {
        "income": income,
        "expense": expense,
        "total_income": sum(r["amount"] for r in income),
        "total_expense": sum(r["amount"] for r in expense),
        "currency": currency,
    }


# ── Statements (monthly view) ─────────────────────────────────────────────────

async def get_statement_months(
    session: AsyncSession,
    *,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return one entry per (year, month) that has ≥1 transaction, sorted DESC.

    When *account_id* is provided, restricts results to that account only.
    When omitted (``None``), all accounts are included (original behaviour).
    """
    year_col = func.extract("year", Transaction.transaction_date)
    month_col = func.extract("month", Transaction.transaction_date)
    stmt = (
        select(
            year_col.label("year"),
            month_col.label("month"),
            func.count(Transaction.id).label("count"),
        )
        .select_from(Transaction)
        .group_by(year_col, month_col)
        .order_by(year_col.desc(), month_col.desc())
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    rows = (await session.execute(stmt)).all()
    return [{"year": int(r.year), "month": int(r.month), "count": r.count} for r in rows]


async def delete_statement_month(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    account_id: int | None = None,
) -> int:
    """Hard-delete all transactions whose date falls within the given calendar month.

    When *account_id* is provided, only that account's transactions are deleted.
    When omitted (``None``), transactions for ALL accounts in the month are removed
    (original behaviour).

    The ``transaction_tags`` junction table is cleaned up automatically via the
    DB-level ``ON DELETE CASCADE`` on its ``transaction_id`` FK — no explicit
    junction delete is required.

    Returns the number of transactions deleted.
    """
    first_day = date(year, month, 1)
    last_day = date(year, month, monthrange(year, month)[1])
    stmt = delete(Transaction).where(
        Transaction.transaction_date >= first_day,
        Transaction.transaction_date <= last_day,
    )
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    async with session.begin():
        result = await session.execute(stmt)
        return result.rowcount


async def get_statement_originals(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    account_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return ImportRuns that have an original PDF on disk for the given month.

    Filters by ``period == "YYYY-MM"`` and ``source_path IS NOT NULL``.
    Optionally restricts to a single account when *account_id* is provided.
    Returns DISTINCT by source_path — when multiple runs share a filename
    (overwrite semantics) the one with the highest id (latest) is returned.
    """
    period = f"{year}-{month:02d}"
    # Use a subquery to pick the latest import_run_id per source_path.
    inner = (
        select(
            func.max(ImportRun.id).label("run_id"),
        )
        .where(ImportRun.period == period)
        .where(ImportRun.source_path.is_not(None))
        .group_by(ImportRun.source_path)
    )
    if account_id is not None:
        inner = inner.where(ImportRun.account_id == account_id)
    inner = inner.subquery()

    stmt = (
        select(
            ImportRun.id.label("import_run_id"),
            ImportRun.source_path.label("source_filename"),
            Account.name.label("account_name"),
            ImportRun.imported_at,
        )
        .select_from(ImportRun)
        .join(Account, ImportRun.account_id == Account.id)
        .join(inner, ImportRun.id == inner.c.run_id)
        .order_by(ImportRun.imported_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "import_run_id": r.import_run_id,
            "source_filename": r.source_filename,
            "account_name": r.account_name,
            "imported_at": r.imported_at,
        }
        for r in rows
    ]
