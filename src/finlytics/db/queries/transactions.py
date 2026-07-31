"""Reading and modifying transactions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, nullslast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.db.models import Account, Category, Tag, Transaction, transaction_tags
from finlytics.db.queries.types import TransactionRow, UpdatedTransactionRow
from finlytics.db.queries._filters import DedupCollisionError, _apply_filters
from finlytics.db.repository import compute_dedup_hash, get_or_create_category, get_or_create_tag


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
) -> tuple[list[TransactionRow], int]:
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
            Transaction.is_system,
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
        exclude_system=False,
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

    items: list[TransactionRow] = [
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
            "is_system": bool(row["is_system"]),
        }
        for row in rows
    ]
    return items, total


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
) -> UpdatedTransactionRow | None:
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
