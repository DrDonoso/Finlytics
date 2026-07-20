"""GET /api/backup/export  — JSON snapshot of selected user data sections.
POST /api/backup/import — idempotent restore from that snapshot.

Designed for owner-initiated migration (e.g. local → production).
The users table is intentionally excluded — auth is per-environment.

JSON schema v2
──────────────
{
  "finlytics_backup_version": 2,
  "exported_at": "<ISO-8601 UTC>",
  "accounts":     [ {"name","type","currency"} ],
  "categories":   [ {"name","is_base","color","name_es"} ],
  "tags":         [ {"name","color","emoji"} ],
  "transactions": [ {"transaction_date","amount","currency","description",
                      "merchant","category","account","category_confidence",
                      "balance_after","tags":[...]} ],
  "rules":        [ ... ],
  "investments":  {
    "connections": [ {"plugin_id","status","account_label_masked","token_enc",
                      "last_synced_at"} ],
    "espp_lots": [...],
    "price_history": [...]
  }
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

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import BackupDocument, ImportSummary
from finlytics.db.models import (
    Account,
    Category,
    EsppLot,
    ImportRun,
    InvestmentConnection,
    PriceHistory,
    Rule,
    Tag,
    Transaction,
    User,
    transaction_tags,
)
from finlytics.db.repository import compute_dedup_hash, get_or_create_tag

log = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

_BACKUP_VERSION = 2
_SUPPORTED_IMPORT_VERSIONS = {1, 2}


# ── Export ────────────────────────────────────────────────────────────────────


@router.get("/export")
async def export_backup(
    accounts: bool | None = Query(default=None),
    categories: bool | None = Query(default=None),
    tags: bool | None = Query(default=None),
    transactions: bool | None = Query(default=None),
    rules: bool | None = Query(default=None),
    investments: bool | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Dump selected sections as a JSON backup.

    The users table is intentionally excluded — auth credentials are
    per-environment and must never be included in portable backups.
    """
    now_utc = datetime.now(timezone.utc)
    payload = {
        "finlytics_backup_version": _BACKUP_VERSION,
        "exported_at": now_utc.isoformat(),
    }

    requested = {
        "accounts": accounts,
        "categories": categories,
        "tags": tags,
        "transactions": transactions,
        "rules": rules,
        "investments": investments,
    }
    include_all = all(value is None for value in requested.values())
    include = {name: include_all or value is True for name, value in requested.items()}

    if include["accounts"]:
        payload["accounts"] = [
            {"name": a.name, "type": a.type, "currency": a.currency}
            for a in (
                await session.execute(select(Account).order_by(Account.name))
            ).scalars().all()
        ]

    if include["categories"]:
        payload["categories"] = [
            {"name": c.name, "is_base": c.is_base, "color": c.color, "name_es": c.name_es}
            for c in (
                await session.execute(select(Category).order_by(Category.name))
            ).scalars().all()
        ]

    if include["tags"]:
        payload["tags"] = [
            {"name": t.name, "color": t.color, "emoji": t.emoji}
            for t in (
                await session.execute(select(Tag).order_by(Tag.name))
            ).scalars().all()
        ]

    if include["transactions"]:
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

        payload["transactions"] = [
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

    if include["rules"]:
        payload["rules"] = [
            {
                "name": r.name,
                "priority": r.priority,
                "enabled": r.enabled,
                "description_mode": r.description_mode,
                "description_value": r.description_value,
                "amount_sign": r.amount_sign,
                "amount_min": float(r.amount_min) if r.amount_min is not None else None,
                "amount_max": float(r.amount_max) if r.amount_max is not None else None,
                "account_ref": r.account_ref,
                "currency": r.currency,
                "detail_mode": r.detail_mode,
                "detail_value": r.detail_value,
                "set_category": r.set_category,
                "set_merchant": r.set_merchant,
                "add_tags": r.add_tags,
                "skip_ai": r.skip_ai,
            }
            for r in (
                await session.execute(select(Rule).order_by(Rule.priority, Rule.id))
            ).scalars().all()
        ]

    if include["investments"]:
        connections = (
            await session.execute(
                select(InvestmentConnection)
                .where(InvestmentConnection.user_id == current_user.id)
                .order_by(InvestmentConnection.plugin_id)
            )
        ).scalars().all()
        connection_ids = [c.id for c in connections]
        plugin_by_connection_id = {c.id: c.plugin_id for c in connections}

        espp_lots_out: list[dict] = []
        if connection_ids:
            espp_lots_out = [
                {
                    "connection_plugin_id": plugin_by_connection_id[lot.connection_id],
                    "ticker": lot.ticker,
                    "purchase_date": lot.purchase_date.isoformat(),
                    "grant_date": lot.grant_date.isoformat() if lot.grant_date else None,
                    "shares": float(lot.shares),
                    "cost_basis": float(lot.cost_basis),
                    "cost_basis_per_share": float(lot.cost_basis_per_share),
                    "source_currency": lot.source_currency,
                    "share_source": lot.share_source,
                    "holding_period": lot.holding_period,
                    "dedup_hash": lot.dedup_hash,
                }
                for lot in (
                    await session.execute(
                        select(EsppLot)
                        .where(EsppLot.connection_id.in_(connection_ids))
                        .order_by(EsppLot.purchase_date, EsppLot.id)
                    )
                ).scalars().all()
            ]

        payload["investments"] = {
            "connections": [
                {
                    "plugin_id": c.plugin_id,
                    "status": c.status,
                    "account_label_masked": c.account_label_masked,
                    "token_enc": c.token_enc,
                    "last_synced_at": (
                        c.last_synced_at.isoformat() if c.last_synced_at else None
                    ),
                }
                for c in connections
            ],
            "espp_lots": espp_lots_out,
            "price_history": [
                {
                    "ticker": p.ticker,
                    "price_date": p.price_date.isoformat(),
                    "close_usd": float(p.close_usd),
                    "fx_eur_usd": float(p.fx_eur_usd),
                    "close_eur": float(p.close_eur),
                }
                for p in (
                    await session.execute(
                        select(PriceHistory).order_by(
                            PriceHistory.ticker, PriceHistory.price_date
                        )
                    )
                ).scalars().all()
            ],
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
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> ImportSummary:
    """Restore a backup idempotently.

    The entire restore runs inside one DB transaction so a failure rolls back
    all changes and leaves the database in its original state.
    """
    if body.finlytics_backup_version not in _SUPPORTED_IMPORT_VERSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported backup version {body.finlytics_backup_version}. "
                f"Supported versions: {sorted(_SUPPORTED_IMPORT_VERSIONS)}."
            ),
        )

    rules_created = 0
    rules_updated = 0
    investment_connections_created = 0
    investment_connections_updated = 0
    espp_lots_inserted = 0
    espp_lots_duplicates = 0
    price_history_inserted = 0
    price_history_duplicates = 0

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

        # ── Rules ────────────────────────────────────────────────────────────
        for rule_in in body.rules:
            row = (
                await session.execute(select(Rule).where(Rule.name == rule_in.name))
            ).scalar_one_or_none()
            values = {
                "priority": rule_in.priority,
                "enabled": rule_in.enabled,
                "description_mode": rule_in.description_mode,
                "description_value": rule_in.description_value,
                "amount_sign": rule_in.amount_sign,
                "amount_min": (
                    Decimal(str(rule_in.amount_min))
                    if rule_in.amount_min is not None
                    else None
                ),
                "amount_max": (
                    Decimal(str(rule_in.amount_max))
                    if rule_in.amount_max is not None
                    else None
                ),
                "account_ref": rule_in.account_ref,
                "currency": rule_in.currency,
                "detail_mode": rule_in.detail_mode,
                "detail_value": rule_in.detail_value,
                "set_category": rule_in.set_category,
                "set_merchant": rule_in.set_merchant,
                "add_tags": rule_in.add_tags,
                "skip_ai": rule_in.skip_ai,
            }
            if row is not None:
                for key, value in values.items():
                    setattr(row, key, value)
                row.updated_at = datetime.now(timezone.utc)
                await session.flush()
                rules_updated += 1
            else:
                session.add(Rule(name=rule_in.name, **values))
                await session.flush()
                rules_created += 1

        # ── Investments ──────────────────────────────────────────────────────
        investment_connection_id_map: dict[str, int] = {}
        investments_in = body.investments
        if investments_in is not None:
            for conn_in in investments_in.connections:
                row = (
                    await session.execute(
                        select(InvestmentConnection).where(
                            InvestmentConnection.user_id == current_user.id,
                            InvestmentConnection.plugin_id == conn_in.plugin_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is not None:
                    row.status = conn_in.status
                    row.account_label_masked = conn_in.account_label_masked
                    row.token_enc = conn_in.token_enc
                    row.last_synced_at = conn_in.last_synced_at
                    await session.flush()
                    investment_connections_updated += 1
                    investment_connection_id_map[conn_in.plugin_id] = row.id
                else:
                    new_conn = InvestmentConnection(
                        user_id=current_user.id,
                        plugin_id=conn_in.plugin_id,
                        status=conn_in.status,
                        account_label_masked=conn_in.account_label_masked,
                        token_enc=conn_in.token_enc,
                        last_synced_at=conn_in.last_synced_at,
                    )
                    session.add(new_conn)
                    await session.flush()
                    investment_connections_created += 1
                    investment_connection_id_map[conn_in.plugin_id] = new_conn.id

            async def _ensure_investment_connection(plugin_id: str) -> int:
                existing_id = investment_connection_id_map.get(plugin_id)
                if existing_id is not None:
                    return existing_id
                row = (
                    await session.execute(
                        select(InvestmentConnection).where(
                            InvestmentConnection.user_id == current_user.id,
                            InvestmentConnection.plugin_id == plugin_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is not None:
                    investment_connection_id_map[plugin_id] = row.id
                    return row.id
                new_conn = InvestmentConnection(
                    user_id=current_user.id,
                    plugin_id=plugin_id,
                    status="active",
                    token_enc=None,
                )
                session.add(new_conn)
                await session.flush()
                investment_connection_id_map[plugin_id] = new_conn.id
                return new_conn.id

            for lot_in in investments_in.espp_lots:
                connection_id = await _ensure_investment_connection(
                    lot_in.connection_plugin_id
                )
                insert_stmt = (
                    pg_insert(EsppLot)
                    .values(
                        connection_id=connection_id,
                        ticker=lot_in.ticker,
                        purchase_date=lot_in.purchase_date,
                        grant_date=lot_in.grant_date,
                        shares=Decimal(str(lot_in.shares)),
                        cost_basis=Decimal(str(lot_in.cost_basis)),
                        cost_basis_per_share=Decimal(str(lot_in.cost_basis_per_share)),
                        source_currency=lot_in.source_currency,
                        share_source=lot_in.share_source,
                        holding_period=lot_in.holding_period,
                        dedup_hash=lot_in.dedup_hash,
                    )
                    .on_conflict_do_nothing(index_elements=["dedup_hash"])
                    .returning(EsppLot.id)
                )
                result = await session.execute(insert_stmt)
                if result.scalar_one_or_none() is not None:
                    espp_lots_inserted += 1
                else:
                    espp_lots_duplicates += 1

            for price_in in investments_in.price_history:
                existing_price = (
                    await session.execute(
                        select(PriceHistory).where(
                            PriceHistory.ticker == price_in.ticker,
                            PriceHistory.price_date == price_in.price_date,
                        )
                    )
                ).scalar_one_or_none()
                if existing_price is not None:
                    existing_price.close_usd = Decimal(str(price_in.close_usd))
                    existing_price.fx_eur_usd = Decimal(str(price_in.fx_eur_usd))
                    existing_price.close_eur = Decimal(str(price_in.close_eur))
                    await session.flush()
                    price_history_duplicates += 1
                else:
                    session.add(
                        PriceHistory(
                            ticker=price_in.ticker,
                            price_date=price_in.price_date,
                            close_usd=Decimal(str(price_in.close_usd)),
                            fx_eur_usd=Decimal(str(price_in.fx_eur_usd)),
                            close_eur=Decimal(str(price_in.close_eur)),
                        )
                    )
                    await session.flush()
                    price_history_inserted += 1

    return ImportSummary(
        accounts_created=accounts_created,
        accounts_existing=accounts_existing,
        categories_created=categories_created,
        categories_updated=categories_updated,
        tags_created=tags_created,
        tags_updated=tags_updated,
        transactions_inserted=transactions_inserted,
        transactions_duplicates=transactions_duplicates,
        rules_created=rules_created,
        rules_updated=rules_updated,
        investment_connections_created=investment_connections_created,
        investment_connections_updated=investment_connections_updated,
        espp_lots_inserted=espp_lots_inserted,
        espp_lots_duplicates=espp_lots_duplicates,
        price_history_inserted=price_history_inserted,
        price_history_duplicates=price_history_duplicates,
    )
