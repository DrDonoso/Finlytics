"""Rules endpoints: GET (list), POST (create), PATCH (update), DELETE."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import RuleIn, RuleOut, RuleUpdate
from finlytics.db import repository

router = APIRouter(prefix="/rules", tags=["rules"])


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
