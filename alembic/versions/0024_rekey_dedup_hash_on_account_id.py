"""Re-key transactions.dedup_hash on the account id.

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-27

The idempotency key hashed the account NAME. Renaming an account therefore
changed the key every stored row should have had, and re-importing a statement
afterwards inserted each transaction a second time. Two accounts whose names
differ only by case shared one dedup space, so the second silently skipped
legitimate rows. The amount was hashed in whatever spelling the caller held
(``-42.1``, ``-42.10``, ``3000.0``), so a key recomputed from the stored
``Numeric(14, 2)`` value did not match the one written at import time.

The key is now the account id with the amount quantized to cents, and every row
is re-hashed with that formula. Nothing is deleted: when several rows land on
the same key — a transaction force-imported past the duplicate check, or one
stored twice under two amount spellings — the oldest keeps it, the others get a
``legacy:<id>`` disambiguator, and the count is logged.

The re-hash runs in Python, so offline ``--sql`` mode is refused.
"""

import hashlib
import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

_BATCH = 2000
_CENT = Decimal("0.01")

_transactions = sa.table(
    "transactions",
    sa.column("id", sa.BigInteger),
    sa.column("account_id", sa.Integer),
    sa.column("transaction_date", sa.Date),
    sa.column("amount", sa.Numeric(14, 2)),
    sa.column("description", sa.Text),
    sa.column("detail", sa.String),
    sa.column("dedup_hash", sa.String),
)
_accounts = sa.table("accounts", sa.column("id", sa.Integer), sa.column("name", sa.String))


def account_id_key(row: Any, disambiguator: str | None = None) -> str:
    """Frozen copy of ``compute_dedup_hash`` as introduced by this revision."""
    cents = Decimal(str(row.amount)).quantize(_CENT, rounding=ROUND_HALF_UP)
    payload: dict[str, object] = {
        "account_id": row.account_id,
        "date": str(row.transaction_date),
        "amount": str(cents.copy_abs() if cents.is_zero() else cents),
        "description": row.description.strip().lower(),
    }
    if row.detail and row.detail.strip():
        payload["detail"] = row.detail.strip().lower()
    if disambiguator is not None:
        payload["disambiguator"] = disambiguator
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def account_name_key(row: Any, disambiguator: str | None = None) -> str:
    """The formula this revision replaces.

    The old key hashed the amount as the caller spelled it, which the stored
    column no longer records. The normalized form is what the import path
    produced, so most rows get their original key back; opening balances and
    restored backups used another spelling and may not.
    """
    amount = Decimal(str(row.amount)).normalize()
    payload: dict[str, object] = {
        "account": (row.account_name or "").strip().lower(),
        "date": str(row.transaction_date),
        "amount": "0" if amount.is_zero() else format(amount, "f"),
        "description": row.description.strip().lower(),
    }
    if disambiguator is not None:
        payload["disambiguator"] = disambiguator
    text = json.dumps(payload, sort_keys=True)
    if row.detail and row.detail.strip():
        text += "|" + row.detail.strip().lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rehash(conn: sa.Connection, key: Callable[..., str]) -> int:
    """Re-key every transaction with ``key``; return how many needed a disambiguator."""
    t, a = _transactions, _accounts
    query = (
        sa.select(
            t.c.id,
            t.c.account_id,
            t.c.transaction_date,
            t.c.amount,
            t.c.description,
            t.c.detail,
            a.c.name.label("account_name"),
        )
        .select_from(t.outerjoin(a, a.c.id == t.c.account_id))
        .order_by(t.c.id)
        .limit(_BATCH)
    )
    update = (
        t.update()
        .where(t.c.id == sa.bindparam("row_id"))
        .values(dedup_hash=sa.bindparam("new_hash"))
    )

    seen: set[str] = set()
    collisions = 0
    last_id = None
    while True:
        page = query if last_id is None else query.where(t.c.id > last_id)
        rows = conn.execute(page).all()
        if not rows:
            return collisions
        params = []
        for row in rows:
            new_hash = key(row)
            if new_hash in seen:
                new_hash = key(row, disambiguator=f"legacy:{row.id}")
                collisions += 1
            seen.add(new_hash)
            params.append({"row_id": row.id, "new_hash": new_hash})
        conn.execute(update, params)
        last_id = rows[-1].id


def _bind() -> sa.Connection:
    if op.get_context().as_sql:
        raise RuntimeError(
            "0024 re-hashes every transaction in Python and cannot run in offline "
            "--sql mode; run it against the database."
        )
    return op.get_bind()


def upgrade() -> None:
    collisions = rehash(_bind(), account_id_key)
    if collisions:
        log.warning(
            "0024: %d transaction(s) share a dedup key with an older row and were "
            "kept under a legacy key; they are likely duplicates worth reviewing.",
            collisions,
        )


def downgrade() -> None:
    rehash(_bind(), account_name_key)
