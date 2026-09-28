"""Rules endpoints: GET (list), POST (create), PATCH (update), DELETE, preview, apply."""

from __future__ import annotations

import string
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NamedTuple

import regex
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import ColumnElement, ColumnExpressionArgument, Numeric, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.api.deps import get_db
from finlytics.api.schemas import RuleApplyResult, RuleIn, RuleOut, RulePreviewResult, RuleUpdate
from finlytics.db import repository
from finlytics.db.models import Account, Tag, Transaction
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


class _Candidate(NamedTuple):
    """A stored transaction as the matcher reads it, without loading the ORM row."""

    id: int
    description: str
    detail: str | None
    amount: Decimal
    account_ref: str
    currency: str


# The SQL pre-filter only has to be a superset of what ``_matches`` accepts.
# Postgres's lower() follows the database collation — a C-locale database
# leaves "É" alone, a Turkish one lowers "I" to a dotless "ı" — so it could
# drop a row str.lower() matches.  translate() folds ASCII the same way
# everywhere, plus the two non-ASCII letters Python lowers to ASCII.
_FOLD_FROM = string.ascii_uppercase + "\u0130\u212a"
_FOLD_TO = string.ascii_lowercase + "ik"
_LIKE_ESCAPE = "/"
_APPLY_CHUNK = 1000


def _folded(column: ColumnExpressionArgument[str]) -> ColumnElement[str]:
    return func.translate(column, _FOLD_FROM, _FOLD_TO)


def _like_pattern(value: str) -> str:
    """LIKE pattern over the folded column, loose enough never to miss a match.

    Only ASCII is compared literally.  Python lowers any other character to
    exactly one character the database left untouched, so it becomes ``_``.
    The combining dot ``"İ".lower()`` appends after its ``i`` becomes ``%``,
    because the database folds that letter to a bare ``i``.
    """
    parts: list[str] = []
    previous = ""
    for char in value.lower():
        if char in "%_" + _LIKE_ESCAPE:
            parts.append(_LIKE_ESCAPE + char)
        elif char.isascii():
            parts.append(char)
        elif char == "\u0307" and previous == "i":
            parts.append("%")
        else:
            parts.append("_")
        previous = char
    return "".join(parts)


def _text_condition(
    column: ColumnExpressionArgument[str], mode: str, value: str
) -> ColumnElement[bool] | None:
    """SQL counterpart of ``_value_matches``; None for modes only Python can evaluate."""
    pattern = _like_pattern(value)
    if mode == "contains":
        pattern = f"%{pattern}%"
    elif mode == "starts_with":
        pattern = f"{pattern}%"
    elif mode != "exact":
        return None
    return _folded(column).like(pattern, escape=_LIKE_ESCAPE)


async def _candidate_conditions(
    session: AsyncSession, rule_like: Any
) -> list[ColumnElement[bool]] | None:
    """WHERE clauses narrowing the transactions *rule_like* could match.

    Returns None when no transaction can match, because ``account_ref`` names
    no existing account.
    """
    conditions: list[ColumnElement[bool]] = []

    description = _text_condition(
        Transaction.description, rule_like.description_mode, rule_like.description_value
    )
    if description is not None:
        conditions.append(description)

    if rule_like.detail_mode and rule_like.detail_value:
        detail = _text_condition(
            func.coalesce(Transaction.detail, ""), rule_like.detail_mode, rule_like.detail_value
        )
        if detail is not None:
            conditions.append(detail)

    if rule_like.amount_sign == "negative":
        conditions.append(Transaction.amount < 0)
    elif rule_like.amount_sign == "positive":
        conditions.append(Transaction.amount > 0)

    magnitude = func.abs(Transaction.amount, type_=Numeric())
    if rule_like.amount_min is not None:
        conditions.append(magnitude >= rule_like.amount_min)
    if rule_like.amount_max is not None:
        conditions.append(magnitude <= rule_like.amount_max)

    if rule_like.currency is not None:
        currency = _text_condition(Transaction.currency, "exact", rule_like.currency)
        if currency is not None:
            conditions.append(currency)

    if rule_like.account_ref is not None:
        wanted = rule_like.account_ref.lower()
        accounts = (await session.execute(select(Account.id, Account.name))).all()
        account_ids = [account_id for account_id, name in accounts if name.lower() == wanted]
        if not account_ids:
            return None
        conditions.append(Transaction.account_id.in_(account_ids))

    return conditions


async def _matching_candidates(session: AsyncSession, rule_like: Any) -> list[_Candidate]:
    """Stored transactions matching *rule_like*, filtered in SQL and confirmed by ``_matches``.

    The database discards what it can prove cannot match; every survivor is
    re-evaluated by the same matcher the import path uses, which is also the
    only place regular expressions run.
    """
    compiled_regex = _compile_regex(rule_like) if rule_like.description_mode == "regex" else None
    compiled_detail = (
        _compile_detail_regex(rule_like) if rule_like.detail_mode == "regex" else None
    )
    conditions = await _candidate_conditions(session, rule_like)
    if conditions is None:
        return []
    rows = await session.execute(
        select(
            Transaction.id,
            Transaction.description,
            Transaction.detail,
            Transaction.amount,
            Account.name,
            Transaction.currency,
        )
        .join(Transaction.account)
        .where(*conditions)
    )
    candidates = (_Candidate._make(row) for row in rows)
    return [
        candidate
        for candidate in candidates
        if _matches(candidate, rule_like, compiled_regex, compiled_detail)
    ]


async def _count_matching(session: AsyncSession, rule_like: Any) -> int:
    """Return the count of stored transactions that match *rule_like* conditions."""
    return len(await _matching_candidates(session, rule_like))


async def _apply_to_transactions(session: AsyncSession, rule_like: Any) -> int:
    """Apply *rule_like* actions to all matching stored transactions.

    Runs inside the caller's transaction.  Actions applied:
    - ``set_category`` → resolve/create category (same as import path), set ``category_id``.
    - ``set_merchant`` → update ``merchant`` column.
    - ``add_tags`` → MERGE with existing tags (case-insensitive dedup, order preserved).

    Only the matched rows are loaded as ORM objects.  Returns the number of
    transactions that were matched (and had actions applied).
    """
    ids = [candidate.id for candidate in await _matching_candidates(session, rule_like)]
    if not ids:
        return 0

    category_id = None
    if rule_like.set_category is not None:
        category_id = (await get_or_create_category(session, rule_like.set_category)).id
    tag_cache: dict[str, Tag] = {}

    for start in range(0, len(ids), _APPLY_CHUNK):
        txs = (
            await session.execute(
                select(Transaction)
                .where(Transaction.id.in_(ids[start : start + _APPLY_CHUNK]))
                .options(selectinload(Transaction.tags))
            )
        ).scalars().all()

        for tx in txs:
            if category_id is not None:
                tx.category_id = category_id

            if rule_like.set_merchant is not None:
                tx.merchant = rule_like.set_merchant

            if rule_like.add_tags:
                new_tags = []
                for name in _merge_tags([t.name for t in tx.tags], rule_like.add_tags):
                    if name not in tag_cache:
                        tag_cache[name] = await get_or_create_tag(session, name)
                    new_tags.append(tag_cache[name])
                tx.tags = new_tags

    await session.flush()
    return len(ids)


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
            regex.compile(description_value)
        except regex.error as exc:
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
            regex.compile(detail_value)
        except regex.error as exc:
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
) -> list[dict[str, Any]]:
    """Return all rules ordered by (priority, id)."""
    rules = await repository.list_rules(session)
    return [_rule_dict(r) for r in rules]


@router.post("", response_model=RuleOut, status_code=201)
async def create_rule(
    body: RuleIn,
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
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
    async with session.begin():
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
    async with session.begin():
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
) -> dict[str, Any]:
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
        rule.updated_at = datetime.now(UTC)
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
