"""GET /api/backup/export  — full-fidelity JSON snapshot of all user data.
POST /api/backup/import — idempotent restore from that snapshot.

Designed for owner-initiated migration (e.g. local → production).
The users table is intentionally excluded — auth is per-environment.

JSON schema v1
──────────────
{
  "finlytics_backup_version": 1,
  "exported_at": "<ISO-8601 UTC>",
  "accounts":     [ {"name","type","currency"} ],
  "categories":   [ {"name","is_base","color","name_es"} ],
  "tags":         [ {"name","color","emoji"} ],
  "transactions": [ {"transaction_date","amount","currency","description",
                      "merchant","category","account","category_confidence",
                      "balance_after","tags":[...]} ]
}

Restore semantics (all inside one DB transaction):
  Accounts   — get-or-create by name; existing rows left unchanged.
  Categories — UPSERT by canonical name: update color+name_es if exists.
               translate_category_name is BYPASSED — name_es comes from backup.
  Tags       — UPSERT by normalised name: update color+emoji if exists.
  Transactions — dedup via SHA-256 hash (ON CONFLICT DO NOTHING).
                 Tags linked via transaction_tags for newly-inserted rows only.
  ImportRun  — one synthetic run per restore (import_run_id is NOT nullable).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import BackupDocument, ImportSummary
from finlytics.db.models import (
    Account,
    Category,
    ImportRun,
    Tag,
    Transaction,
    transaction_tags,
)
from finlytics.db.repository import compute_dedup_hash, get_or_create_tag

log = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

_BACKUP_VERSION = 1


# ── Export ────────────────────────────────────────────────────────────────────


@router.get("/export")
async def export_backup(session: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Dump all accounts, categories, tags and transactions as a JSON backup.

    The users table is intentionally excluded — auth credentials are
    per-environment and must never be included in portable backups.
    """
    accounts_out = [
        {"name": a.name, "type": a.type, "currency": a.currency}
        for a in (
            await session.execute(select(Account).order_by(Account.name))
        ).scalars().all()
    ]

    categories_out = [
        {"name": c.name, "is_base": c.is_base, "color": c.color, "name_es": c.name_es}
        for c in (
            await session.execute(select(Category).order_by(Category.name))
        ).scalars().all()
    ]

    tags_out = [
        {"name": t.name, "color": t.color, "emoji": t.emoji}
        for t in (
            await session.execute(select(Tag).order_by(Tag.name))
        ).scalars().all()
    ]

    tx_rows = (
        await session.execute(
            select(
                Transaction.id,
                Transaction.transaction_date,
                Transaction.amount,
                Transaction.currency,
                Transaction.description,
                Transaction.merchant,
                Transaction.category_confidence,
                Transaction.balance_after,
                Category.name.label("category_name"),
                Account.name.label("account_name"),
            )
            .select_from(Transaction)
            .join(Account, Transaction.account_id == Account.id)
            .outerjoin(Category, Transaction.category_id == Category.id)
            .order_by(Transaction.transaction_date, Transaction.id)
        )
    ).mappings().all()

    # Batch-load tags — single query to avoid N+1.
    tx_ids = [row["id"] for row in tx_rows]
    tag_map: dict[int, list[str]] = {}
    if tx_ids:
        for tx_id, tname in (
            await session.execute(
                select(transaction_tags.c.transaction_id, Tag.name)
                .join(Tag, Tag.id == transaction_tags.c.tag_id)
                .where(transaction_tags.c.transaction_id.in_(tx_ids))
                .order_by(Tag.name)
            )
        ).all():
            tag_map.setdefault(tx_id, []).append(tname)

    transactions_out = [
        {
            "transaction_date": row["transaction_date"].isoformat(),
            "amount": float(row["amount"]),
            "currency": row["currency"],
            "description": row["description"],
            "merchant": row["merchant"],
            "category": row["category_name"],   # None when uncategorised
            "account": row["account_name"],
            "category_confidence": row["category_confidence"],
            "balance_after": (
                float(row["balance_after"]) if row["balance_after"] is not None else None
            ),
            "tags": tag_map.get(row["id"], []),
        }
        for row in tx_rows
    ]

    now_utc = datetime.now(timezone.utc)
    payload = {
        "finlytics_backup_version": _BACKUP_VERSION,
        "exported_at": now_utc.isoformat(),
        "accounts": accounts_out,
        "categories": categories_out,
        "tags": tags_out,
        "transactions": transactions_out,
    }
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": (
                f'attachment; filename="finlytics-backup-{now_utc.strftime("%Y-%m-%d")}.json"'
            )
        },
    )


# ── Import ────────────────────────────────────────────────────────────────────


@router.post("/import", response_model=ImportSummary)
async def import_backup(
    body: BackupDocument = Body(...),
    session: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """Restore a backup idempotently.

    The entire restore runs inside one DB transaction so a failure rolls back
    all changes and leaves the database in its original state.
    """
    if body.finlytics_backup_version != _BACKUP_VERSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported backup version {body.finlytics_backup_version}. "
                f"Only version {_BACKUP_VERSION} is accepted."
            ),
        )

    async with session.begin():
        # ── Accounts ─────────────────────────────────────────────────────────
        accounts_created = 0
        accounts_existing = 0
        account_id_map: dict[str, int] = {}  # name → id

        for acc in body.accounts:
            row = (
                await session.execute(select(Account).where(Account.name == acc.name))
            ).scalar_one_or_none()
            if row is not None:
                accounts_existing += 1
                account_id_map[acc.name] = row.id
            else:
                new_acc = Account(name=acc.name, type=acc.type, currency=acc.currency)
                session.add(new_acc)
                await session.flush()
                accounts_created += 1
                account_id_map[acc.name] = new_acc.id

        # ── Categories ───────────────────────────────────────────────────────
        # translate_category_name is intentionally bypassed — name_es comes
        # straight from the backup and is written directly to the row.
        categories_created = 0
        categories_updated = 0
        category_id_map: dict[str, int] = {}  # name → id

        for cat in body.categories:
            row = (
                await session.execute(select(Category).where(Category.name == cat.name))
            ).scalar_one_or_none()
            if row is not None:
                row.color = cat.color
                row.name_es = cat.name_es   # restore backup value (may be None)
                await session.flush()
                categories_updated += 1
                category_id_map[cat.name] = row.id
            else:
                new_cat = Category(
                    name=cat.name,
                    is_base=cat.is_base,
                    color=cat.color,
                    name_es=cat.name_es,
                )
                session.add(new_cat)
                await session.flush()
                categories_created += 1
                category_id_map[cat.name] = new_cat.id

        # ── Tags ─────────────────────────────────────────────────────────────
        tags_created = 0
        tags_updated = 0
        tag_id_map: dict[str, int] = {}  # normalised name → id

        for tag_in in body.tags:
            norm = tag_in.name.strip().lower()
            row = (
                await session.execute(select(Tag).where(Tag.name == norm))
            ).scalar_one_or_none()
            if row is not None:
                row.color = tag_in.color
                row.emoji = tag_in.emoji    # restore backup value (may be None)
                await session.flush()
                tags_updated += 1
                tag_id_map[norm] = row.id
            else:
                kwargs: dict = {"name": norm, "color": tag_in.color}
                if tag_in.emoji is not None:
                    kwargs["emoji"] = tag_in.emoji
                new_tag = Tag(**kwargs)
                session.add(new_tag)
                await session.flush()
                tags_created += 1
                tag_id_map[norm] = new_tag.id

        # ── Synthetic ImportRun ───────────────────────────────────────────────
        # import_run_id is NOT nullable on Transaction; create one synthetic run
        # anchored to the first account (audit purposes only).
        first_account_id = next(iter(account_id_map.values()), None)
        import_run: ImportRun | None = None
        if first_account_id is not None:
            import_run = ImportRun(
                account_id=first_account_id,
                source_filename="backup-restore",
                num_parsed=len(body.transactions),
            )
            session.add(import_run)
            await session.flush()   # materialise import_run.id

        # ── Transactions ─────────────────────────────────────────────────────
        transactions_inserted = 0
        transactions_duplicates = 0

        for tx in body.transactions:
            acc_id = account_id_map.get(tx.account)
            if acc_id is None:
                # Transaction references an account absent from the backup.
                # import_run is also None in this path, so skip cleanly.
                log.warning(
                    "Backup import: skipping transaction for unknown account %r",
                    tx.account,
                )
                continue

            # import_run is non-None here: acc_id ≠ None ⟹ account_id_map has
            # entries ⟹ first_account_id was set ⟹ import_run was created.
            cat_id = category_id_map.get(tx.category) if tx.category else None

            dedup_hash = compute_dedup_hash(
                account_ref=tx.account,
                transaction_date=tx.transaction_date,
                amount=Decimal(str(tx.amount)),
                description=tx.description,
                detail=None,  # BackupTransactionIn has no detail field
            )

            insert_stmt = (
                pg_insert(Transaction)
                .values(
                    account_id=acc_id,
                    import_run_id=import_run.id,  # type: ignore[union-attr]
                    transaction_date=tx.transaction_date,
                    amount=Decimal(str(tx.amount)),
                    currency=tx.currency,
                    description=tx.description,
                    merchant=tx.merchant,
                    category_id=cat_id,
                    category_confidence=tx.category_confidence,
                    balance_after=(
                        Decimal(str(tx.balance_after))
                        if tx.balance_after is not None
                        else None
                    ),
                    dedup_hash=dedup_hash,
                )
                .on_conflict_do_nothing(index_elements=["dedup_hash"])
                .returning(Transaction.id)
            )
            result = await session.execute(insert_stmt)
            inserted_id = result.scalar_one_or_none()

            if inserted_id is not None:
                transactions_inserted += 1
                # Link tags.  Tags already in tag_id_map (from body.tags) are
                # resolved by name.  Tags that appear only in a transaction's
                # list are get-or-created (no metadata, not counted in summary).
                for raw_name in tx.tags:
                    norm = raw_name.strip().lower()
                    if norm not in tag_id_map:
                        tag = await get_or_create_tag(session, norm)
                        tag_id_map[norm] = tag.id
                    await session.execute(
                        pg_insert(transaction_tags)
                        .values(transaction_id=inserted_id, tag_id=tag_id_map[norm])
                        .on_conflict_do_nothing()
                    )
            else:
                transactions_duplicates += 1

    return ImportSummary(
        accounts_created=accounts_created,
        accounts_existing=accounts_existing,
        categories_created=categories_created,
        categories_updated=categories_updated,
        tags_created=tags_created,
        tags_updated=tags_updated,
        transactions_inserted=transactions_inserted,
        transactions_duplicates=transactions_duplicates,
    )
