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
        "account_ref": rule.account_ref,
        "currency": rule.currency,
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
) -> None:
    """Raise HTTP 422 when rule business constraints are violated.

    Rules:
    - skip_ai=True requires set_category to be non-null (line removed from LLM
      input entirely; must be fully categorised by the rule).
    - description_mode="regex" requires description_value to compile.
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
        _validate_rule_fields(
            effective_skip_ai, effective_mode, effective_value, effective_category
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
