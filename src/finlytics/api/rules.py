"""Rules endpoints: GET (list), POST (create), PATCH (update), DELETE, preview, apply."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.api.deps import get_db
from finlytics.api.schemas import RuleApplyResult, RuleIn, RuleOut, RulePreviewResult, RuleUpdate
from finlytics.db import repository
from finlytics.db.models import Transaction
from finlytics.db.repository import get_or_create_category, get_or_create_tag
from finlytics.extraction.rules import (
    _compile_detail_regex,
    _compile_regex,
    _matches,
    _merge_tags,
)

router = APIRouter(prefix="/rules", tags=["rules"])


# ---------------------------------------------------------------------------
# Preview / apply helpers
# ---------------------------------------------------------------------------


class _RuleLike:
    """Duck-typed proxy over a ``RuleIn`` body satisfying ``RuleProtocol``.

    Only used for preview/apply; never persisted.  The ``id``, ``name``,
    ``priority``, and ``enabled`` fields are synthetic sentinel values.
    """

    def __init__(self, body: RuleIn) -> None:
        self.id = 0
        self.name = "<preview>"
        self.priority = 0
        self.enabled = True
        self.description_mode = body.description_mode
        self.description_value = body.description_value
        self.amount_sign = body.amount_sign
        self.amount_min = Decimal(str(body.amount_min)) if body.amount_min is not None else None
        self.amount_max = Decimal(str(body.amount_max)) if body.amount_max is not None else None
        self.account_ref = body.account_ref
        self.currency = body.currency
        self.detail_mode = body.detail_mode
        self.detail_value = body.detail_value
        self.set_category = body.set_category
        self.set_merchant = body.set_merchant
        self.add_tags = list(body.add_tags)
        self.skip_ai = body.skip_ai


class _StoredTxView:
    """Minimal adapter over a ``Transaction`` ORM row satisfying ``_matches()``."""

    __slots__ = ("description", "detail", "amount", "account_ref", "currency")

    def __init__(self, tx: Transaction) -> None:
        self.description: str = tx.description
        self.detail: str | None = tx.detail
        self.amount: Decimal = tx.amount
        self.account_ref: str = tx.account.name if tx.account else ""
        self.currency: str = tx.currency


async def _count_matching(session: AsyncSession, rule_like: Any) -> int:
    """Return the count of stored transactions that match *rule_like* conditions."""
    compiled_regex = _compile_regex(rule_like) if rule_like.description_mode == "regex" else None
    compiled_detail = (
        _compile_detail_regex(rule_like) if rule_like.detail_mode == "regex" else None
    )
    txs = (
        await session.execute(
            select(Transaction).options(selectinload(Transaction.account))
        )
    ).scalars().all()
    return sum(
        1 for tx in txs
        if _matches(_StoredTxView(tx), rule_like, compiled_regex, compiled_detail)
    )


async def _apply_to_transactions(session: AsyncSession, rule_like: Any) -> int:
    """Apply *rule_like* actions to all matching stored transactions.

    Runs inside a single ``session.begin()`` transaction.  Actions applied:
    - ``set_category`` → resolve/create category (same as import path), set ``category_id``.
    - ``set_merchant`` → update ``merchant`` column.
    - ``add_tags`` → MERGE with existing tags (case-insensitive dedup, order preserved).

    Returns the number of transactions that were matched (and had actions applied).
    """
    compiled_regex = _compile_regex(rule_like) if rule_like.description_mode == "regex" else None
    compiled_detail = (
        _compile_detail_regex(rule_like) if rule_like.detail_mode == "regex" else None
    )
    async with session.begin():
        txs = (
            await session.execute(
                select(Transaction).options(
                    selectinload(Transaction.account),
                    selectinload(Transaction.tags),
                )
            )
        ).scalars().all()

        category_cache: dict[str, Any] = {}
        applied = 0

        for tx in txs:
            if not _matches(_StoredTxView(tx), rule_like, compiled_regex, compiled_detail):
                continue

            if rule_like.set_category is not None:
                if rule_like.set_category not in category_cache:
                    category_cache[rule_like.set_category] = await get_or_create_category(
                        session, rule_like.set_category
                    )
                tx.category_id = category_cache[rule_like.set_category].id

            if rule_like.set_merchant is not None:
                tx.merchant = rule_like.set_merchant

            if rule_like.add_tags:
                existing_names = [t.name for t in tx.tags]
                merged_names = _merge_tags(existing_names, rule_like.add_tags)
                new_tags = []
                for name in merged_names:
                    new_tags.append(await get_or_create_tag(session, name))
                tx.tags = new_tags

            applied += 1

        await session.flush()
        return applied


def _rule_dict(rule: Any) -> dict[str, Any]:
    """Convert a Rule ORM object to a plain dict for response serialisation."""
    return {
        "id": rule.id,
        "name": rule.name,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "description_mode": rule.description_mode,
        "description_value": rule.description_value,
        "amount_sign": rule.amount_sign,
        "amount_min": float(rule.amount_min) if rule.amount_min is not None else None,
        "amount_max": float(rule.amount_max) if rule.amount_max is not None else None,
        "account_ref": rule.account_ref,
        "currency": rule.currency,
        "detail_mode": rule.detail_mode,
        "detail_value": rule.detail_value,
        "set_category": rule.set_category,
        "set_merchant": rule.set_merchant,
        "add_tags": rule.add_tags or [],
        "skip_ai": rule.skip_ai,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _validate_rule_fields(
    skip_ai: bool,
    description_mode: str,
    description_value: str,
    set_category: str | None,
    detail_mode: str | None = None,
    detail_value: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
) -> None:
    """Raise HTTP 422 when rule business constraints are violated.

    Rules:
    - skip_ai=True requires set_category to be non-null (line removed from LLM
      input entirely; must be fully categorised by the rule).
    - description_mode="regex" requires description_value to compile.
    - detail_mode and detail_value must BOTH be set or BOTH be null.
    - detail_mode="regex" requires detail_value to compile.
    - amount_min, amount_max must each be >= 0 when set.
    - When both are set, amount_min <= amount_max.
    """
    if skip_ai and not set_category:
        raise HTTPException(
            status_code=422,
            detail="set_category is required when skip_ai is true.",
        )
    if description_mode == "regex":
        try:
            re.compile(description_value)
        except re.error as exc:
            raise HTTPException(
                status_code=422,
                detail=f"description_value is not a valid regular expression: {exc}",
            )
    # detail_mode / detail_value: both set or both null
    if bool(detail_mode) != bool(detail_value):
        if detail_mode and not detail_value:
            raise HTTPException(
                status_code=422,
                detail="detail_value is required when detail_mode is set.",
            )
        else:
            raise HTTPException(
                status_code=422,
                detail="detail_mode is required when detail_value is set.",
            )
    if detail_mode == "regex" and detail_value:
        try:
            re.compile(detail_value)
        except re.error as exc:
            raise HTTPException(
                status_code=422,
                detail=f"detail_value is not a valid regular expression: {exc}",
            )
    # amount_min / amount_max: each must be >= 0; min <= max when both set
    if amount_min is not None and amount_min < 0:
        raise HTTPException(
            status_code=422,
            detail="amount_min must be >= 0.",
        )
    if amount_max is not None and amount_max < 0:
        raise HTTPException(
            status_code=422,
            detail="amount_max must be >= 0.",
        )
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(
            status_code=422,
            detail="amount_min must be <= amount_max.",
        )


@router.get("", response_model=list[RuleOut])
async def list_rules(
    session: AsyncSession = Depends(get_db),
) -> list[RuleOut]:
    """Return all rules ordered by (priority, id)."""
    rules = await repository.list_rules(session)
    return [_rule_dict(r) for r in rules]


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleIn,
    session: AsyncSession = Depends(get_db),
) -> RuleOut:
    """Create a new rule.

    * 201 — rule created.
    * 422 — skip_ai=true without set_category, or invalid regex pattern.
    """
    _validate_rule_fields(
        body.skip_ai,
        body.description_mode,
        body.description_value,
        body.set_category,
        body.detail_mode,
        body.detail_value,
        body.amount_min,
        body.amount_max,
    )
    async with session.begin():
        rule = await repository.create_rule(session, **body.model_dump())
    return _rule_dict(rule)


@router.post("/preview", response_model=RulePreviewResult)
async def preview_rule(
    body: RuleIn,
    session: AsyncSession = Depends(get_db),
) -> RulePreviewResult:
    """Count how many existing transactions match a rule's conditions.

    Body shape is identical to rule-create; action fields (set_category,
    set_merchant, add_tags) are accepted but ignored — only conditions are
    evaluated.  No data is modified.

    * 200 — ``{"count": <int>}``
    """
    count = await _count_matching(session, _RuleLike(body))
    return RulePreviewResult(count=count)


@router.post("/apply", response_model=RuleApplyResult)
async def apply_rule_to_transactions(
    body: RuleIn,
    session: AsyncSession = Depends(get_db),
) -> RuleApplyResult:
    """Apply a rule's conditions + actions to ALL current transactions.

    Body shape is identical to rule-create.  Every transaction that satisfies
    the rule's conditions has the rule's actions applied:

    - ``set_category`` — resolves or creates the category (same as import path).
    - ``set_merchant`` — overwrites the merchant column.
    - ``add_tags`` — merges new tags with existing ones (case-insensitive dedup).

    ``skip_ai`` has no effect here (it is an import-time concern only).

    * 200 — ``{"applied": <int>}`` — number of transactions that were matched
      and had actions applied.
    """
    applied = await _apply_to_transactions(session, _RuleLike(body))
    return RuleApplyResult(applied=applied)


@router.post("/{rule_id}/apply", response_model=RuleApplyResult)
async def apply_saved_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
) -> RuleApplyResult:
    """Apply a saved rule's conditions + actions to ALL current transactions.

    Equivalent to ``POST /api/rules/apply`` but reads conditions and actions
    from the persisted rule identified by *rule_id*.

    * 200 — ``{"applied": <int>}``
    * 404 — rule not found.
    """
    rule = await repository.get_rule(session, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found.")
    applied = await _apply_to_transactions(session, rule)
    return RuleApplyResult(applied=applied)


@router.patch("/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    session: AsyncSession = Depends(get_db),
) -> RuleOut:
    """Partially update a rule.

    * 200 — updated.
    * 404 — rule not found.
    * 422 — resulting state violates skip_ai/set_category constraint or invalid regex.

    Only supplied fields are modified; omitted fields keep their current values.
    """
    updates = body.model_dump(exclude_unset=True)
    async with session.begin():
        rule = await repository.get_rule(session, rule_id)
        if rule is None:
            raise HTTPException(status_code=404, detail="Rule not found.")
        effective_skip_ai = updates.get("skip_ai", rule.skip_ai)
        effective_mode = updates.get("description_mode", rule.description_mode)
        effective_value = updates.get("description_value", rule.description_value)
        effective_category = updates.get("set_category", rule.set_category)
        effective_detail_mode = updates.get("detail_mode", rule.detail_mode)
        effective_detail_value = updates.get("detail_value", rule.detail_value)
        effective_amount_min = updates.get("amount_min", rule.amount_min)
        effective_amount_max = updates.get("amount_max", rule.amount_max)
        _validate_rule_fields(
            effective_skip_ai, effective_mode, effective_value, effective_category,
            effective_detail_mode, effective_detail_value,
            effective_amount_min, effective_amount_max,
        )
        for field, value in updates.items():
            setattr(rule, field, value)
        rule.updated_at = datetime.now(timezone.utc)
        await session.flush()
    return _rule_dict(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: int,
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete a rule.

    * 204 — deleted.
    * 404 — rule not found.
    """
    async with session.begin():
        deleted = await repository.delete_rule(session, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found.")
