"""Database repository: idempotent ingestion and category helpers.

Key design decisions
────────────────────
* ``dedup_hash`` is computed from (account_ref, transaction_date, amount,
  description) using SHA-256.  Banner does NOT send this field; we compute it
  here at the persistence boundary to enforce idempotency.
* We use PostgreSQL's ``INSERT … ON CONFLICT DO NOTHING`` so re-importing the
  same statement in a single batch is safe even within the same call.
* Category resolution is cached per-call to avoid redundant DB round-trips and
  to prevent duplicate-insert races when several transactions share a category.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.contracts import ExtractedTransaction
from finlytics.db.models import Category, ImportRun, Rule, Tag, Transaction, transaction_tags
from finlytics.extraction.translate import translate_category_name


# ── Dedup hash ────────────────────────────────────────────────────────────────

def compute_dedup_hash(
    account_ref: str,
    transaction_date: date,
    amount: Decimal,
    description: str,
) -> str:
    """Return a deterministic SHA-256 hex digest for a transaction.

    The hash is stable across imports: the same real-world transaction always
    produces the same hash regardless of how many times the statement is
    re-uploaded.
    """
    payload = json.dumps(
        {
            "account": account_ref.strip().lower(),
            "date": str(transaction_date),
            "amount": str(amount),
            "description": description.strip().lower(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Category helpers ──────────────────────────────────────────────────────────

async def get_or_create_category(
    session: AsyncSession,
    name: str,
    *,
    is_base: bool = False,
    color: str | None = None,
) -> Category:
    """Return the Category with the given name, creating it if necessary.

    For NEW non-base categories, ``translate_category_name`` is called to
    produce a canonical English name (stored as ``name``) and a Spanish
    translation (stored as ``name_es``).  If translation is unavailable
    (unconfigured OpenAI / test env) the literal ``name`` is stored and
    ``name_es`` is left NULL — never raises.

    Dedup is on the canonical English name: a manual "Ropa" and an AI
    "Clothing" resolve to the SAME category once translation is applied.

    Base categories (``is_base=True``) are never translated.
    Existing categories are returned as-is (no re-translation).
    """
    if not is_base:
        result = await translate_category_name(name)
        if result:
            canonical = result["name_en"]
            name_es = result["name_es"]
        else:
            canonical = name
            name_es = None
    else:
        canonical = name
        name_es = None

    category = (
        await session.execute(select(Category).where(Category.name == canonical))
    ).scalar_one_or_none()

    if category is None:
        kwargs: dict = {"name": canonical, "is_base": is_base}
        if name_es is not None:
            kwargs["name_es"] = name_es
        if color is not None:
            kwargs["color"] = color
        category = Category(**kwargs)
        session.add(category)
        await session.flush()  # materialize id before use as FK

    return category


# ── Tag helpers ───────────────────────────────────────────────────────────────

async def get_or_create_tag(
    session: AsyncSession,
    name: str,
    *,
    color: str | None = None,
) -> Tag:
    """Return the Tag with the normalised name, creating it if necessary.

    Normalisation: strip whitespace + lowercase.  This is the single point
    where the "tags are lowercase" invariant is enforced for all callers.

    ``color`` is applied ONLY when creating a new tag.  Existing tags keep
    their stored color unchanged.
    """
    name = name.strip().lower()
    result = await session.execute(select(Tag).where(Tag.name == name))
    tag = result.scalar_one_or_none()
    if tag is None:
        tag = Tag(name=name)
        if color is not None:
            tag.color = color
        session.add(tag)
        await session.flush()  # materialise id before use
    return tag


async def sync_transaction_tags(
    session: AsyncSession,
    transaction_id: int,
    tag_names: list[str],
    *,
    tag_colors: dict[str, str] | None = None,
) -> None:
    """Sync a transaction's tags to EXACTLY the given list of names.

    * Creates any missing tags (via ``get_or_create_tag``), applying the
      supplied ``tag_colors`` color on creation (existing tags keep their color).
    * Replaces the full M:N set — existing tag links not in ``tag_names`` are
      removed; new ones are added.
    * An empty ``tag_names`` list clears all tags for the transaction.

    The caller is responsible for flushing/committing the session.
    """
    tx = (
        await session.execute(
            select(Transaction)
            .where(Transaction.id == transaction_id)
            .options(selectinload(Transaction.tags))
        )
    ).scalar_one()

    new_tags: list[Tag] = []
    for raw_name in tag_names:
        normalized = raw_name.strip().lower()
        color = (tag_colors or {}).get(normalized)
        new_tags.append(await get_or_create_tag(session, raw_name, color=color))

    tx.tags = new_tags
    await session.flush()


# ── Idempotent ingestion ──────────────────────────────────────────────────────

async def upsert_transactions(
    session: AsyncSession,
    import_run: ImportRun,
    transactions: list[ExtractedTransaction],
    tag_colors: dict[str, str] | None = None,
) -> tuple[int, int]:
    """Persist extracted transactions idempotently.

    Returns ``(num_inserted, num_duplicates)``.  Duplicates are detected via
    ``dedup_hash``; re-importing the same statement is safe.

    ``tag_colors`` maps normalized tag name → hex color; applied on tag
    creation only (existing tags keep their stored color).

    The caller is responsible for managing the session transaction
    (``session.begin()`` / commit / rollback).
    """
    num_inserted = 0
    num_duplicates = 0

    # Local cache: avoid repeated DB look-ups AND duplicate-insert races
    # when multiple transactions share the same category within one import.
    _category_cache: dict[str, Category] = {}

    async def _resolve_category(name: str) -> Category:
        if name not in _category_cache:
            _category_cache[name] = await get_or_create_category(
                session, name, is_base=False
            )
        return _category_cache[name]

    for tx in transactions:
        dedup_hash = compute_dedup_hash(
            account_ref=tx.account_ref,
            transaction_date=tx.transaction_date,
            amount=tx.amount,
            description=tx.description,
        )

        category = await _resolve_category(tx.category)

        stmt = (
            pg_insert(Transaction)
            .values(
                account_id=import_run.account_id,
                import_run_id=import_run.id,
                transaction_date=tx.transaction_date,
                amount=tx.amount,
                currency=tx.currency,
                description=tx.description,
                raw_line=tx.raw_line,
                category_id=category.id,
                category_confidence=tx.category_confidence,
                balance_after=tx.balance_after,
                merchant=tx.merchant,
                dedup_hash=dedup_hash,
            )
            .on_conflict_do_nothing(index_elements=["dedup_hash"])
            .returning(Transaction.id)
        )
        result = await session.execute(stmt)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is not None:
            num_inserted += 1
            if tx.tags:
                await sync_transaction_tags(
                    session, inserted_id, tx.tags, tag_colors=tag_colors
                )
        else:
            num_duplicates += 1

    return num_inserted, num_duplicates


# ── Rules CRUD ────────────────────────────────────────────────────────────────

async def list_rules(
    session: AsyncSession,
    *,
    enabled_only: bool = False,
) -> list[Rule]:
    """Return all rules ordered by (priority, id).

    Pass ``enabled_only=True`` to fetch only rules where enabled=True.
    The caller is responsible for the session transaction scope.
    """
    stmt = select(Rule)
    if enabled_only:
        stmt = stmt.where(Rule.enabled.is_(True))
    stmt = stmt.order_by(Rule.priority, Rule.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_rule(session: AsyncSession, rule_id: int) -> Rule | None:
    """Return the Rule with the given id, or None if not found."""
    result = await session.execute(select(Rule).where(Rule.id == rule_id))
    return result.scalar_one_or_none()


async def create_rule(session: AsyncSession, **kwargs) -> Rule:
    """Insert a new Rule and return it with its generated id.

    The caller is responsible for managing the session transaction
    (``session.begin()`` / commit / rollback).
    """
    rule = Rule(**kwargs)
    session.add(rule)
    await session.flush()  # materialise id + server defaults
    return rule


async def update_rule(session: AsyncSession, rule_id: int, **kwargs) -> Rule | None:
    """Apply partial updates to a Rule.

    Returns the updated Rule, or None if not found.
    The caller is responsible for managing the session transaction.
    Cross-field validation (skip_ai → set_category) is the caller's
    responsibility; this function applies values unconditionally.
    """
    rule = await get_rule(session, rule_id)
    if rule is None:
        return None
    for field, value in kwargs.items():
        setattr(rule, field, value)
    rule.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return rule


async def delete_rule(session: AsyncSession, rule_id: int) -> bool:
    """Delete a Rule by id.

    Returns True if deleted, False if not found.
    The caller is responsible for managing the session transaction.
    """
    rule = await get_rule(session, rule_id)
    if rule is None:
        return False
    await session.delete(rule)
    await session.flush()
    return True
