"""Rule preview and apply against a real database.

The pre-filter in ``api/rules.py`` is ``translate()`` and ``LIKE``, so only
PostgreSQL can show that it never discards a transaction the Python matcher
would accept.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from finlytics.api.rules import (
    _Candidate,
    _candidate_conditions,
    _matching_candidates,
    apply_rule_to_transactions,
    apply_saved_rule,
    preview_rule,
)
from finlytics.api.schemas import RuleIn
from finlytics.db.models import Account, Category, Rule, Tag, Transaction
from finlytics.extraction.rules import _compile_detail_regex, _compile_regex, _matches
from tests.pg.support import ingest, tx

Sessions = async_sessionmaker[AsyncSession]

KELVIN = "5 \u212aM RUN"
DOTTED_I = "\u0130STANBUL KEBAP"
COMBINING_DOT = "PAGO ki\u0307osk"


def rule(**fields: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "id": 0,
        "name": "test",
        "priority": 0,
        "enabled": True,
        "description_mode": "contains",
        "description_value": "",
        "amount_sign": None,
        "amount_min": None,
        "amount_max": None,
        "account_ref": None,
        "currency": None,
        "detail_mode": None,
        "detail_value": None,
        "set_category": None,
        "set_merchant": None,
        "add_tags": [],
        "skip_ai": False,
    }
    return SimpleNamespace(**(defaults | fields))


RULES = {
    "contains": rule(description_value="mercadona"),
    "exact": rule(description_mode="exact", description_value="MERCADONA"),
    "starts_with": rule(description_mode="starts_with", description_value="mercadona"),
    "empty value": rule(description_value=""),
    "accented": rule(description_value="Caf\u00e9"),
    "accented upper": rule(description_value="CAF\u00c9"),
    "percent": rule(description_value="50%"),
    "underscore": rule(description_value="50_"),
    "slash": rule(description_value="a/b"),
    "escape char": rule(description_value="/"),
    "ascii istanbul": rule(description_value="istanbul"),
    "dotted istanbul": rule(description_value="\u0130stanbul"),
    "leading combining dot": rule(description_value="\u0307stanbul"),
    "dotted exact": rule(description_mode="exact", description_value=DOTTED_I),
    "dotted prefix": rule(description_mode="starts_with", description_value="\u0130st"),
    "dotted kiosk": rule(description_value="K\u0130osk"),
    "kelvin": rule(description_value="km run"),
    "kelvin in value": rule(description_value="\u212aM"),
    "greek exact": rule(description_mode="exact", description_value="\u039f\u0394\u039f\u03a3"),
    "sharp s": rule(description_value="stra\u00dfe"),
    "sharp s spelled out": rule(description_value="strasse"),
    "regex": rule(description_mode="regex", description_value="^caf"),
    "invalid regex": rule(description_mode="regex", description_value="("),
    "unknown mode": rule(description_mode="fuzzy", description_value="mercadona"),
    "detail contains": rule(detail_mode="contains", detail_value="ref"),
    "detail prefix": rule(detail_mode="starts_with", detail_value="gcre"),
    "detail exact": rule(detail_mode="exact", detail_value="transfer"),
    "detail regex": rule(detail_mode="regex", detail_value="octopus(energy|gas)$"),
    "negative": rule(description_value="mercadona", amount_sign="negative"),
    "positive": rule(description_value="mercadona", amount_sign="positive"),
    "min": rule(amount_min=Decimal("45.30")),
    "max": rule(amount_max=Decimal("10")),
    "between": rule(amount_min=Decimal("12.40"), amount_max=Decimal("45.30")),
    "sub-cent bounds": rule(amount_min=Decimal("12.395"), amount_max=Decimal("45.305")),
    "bound beyond the column": rule(amount_max=Decimal("1E+20")),
    "currency": rule(currency="usd"),
    "currency mismatch": rule(description_value="amazon", currency="EUR"),
    "account": rule(account_ref="revolut"),
    "account and text": rule(description_value="caf\u00e9", account_ref="bbva"),
    "unknown account": rule(account_ref="nowhere"),
}


async def seed(sessions: Sessions, accounts: tuple[int, int]) -> None:
    bbva, revolut = accounts
    await ingest(
        sessions,
        bbva,
        [
            tx(),
            tx(description="MERCADONA SA", amount=Decimal("-12.00")),
            tx(
                description="COMPRA EN MERCADONA",
                amount=Decimal("-45.30"),
                detail="REF 0001",
                tags=["SUPER"],
            ),
            tx(description="DEVOLUCION MERCADONA", amount=Decimal("12.40")),
            tx(description="CAF\u00c9 CENTRAL", amount=Decimal("-3.20")),
            tx(description="caf\u00e9 de la esquina", amount=Decimal("-2.80")),
            tx(description="50% OFF OUTLET", amount=Decimal("-19.99")),
            tx(description="50_PERCENT", amount=Decimal("-5.00")),
            tx(description="A/B TEST", amount=Decimal("-1.00")),
            tx(description=DOTTED_I, amount=Decimal("-9.50")),
            tx(description="ISTANBUL AIRPORT", amount=Decimal("-30.00")),
            tx(description="K\u0130OSK", amount=Decimal("-1.50")),
            tx(description=COMBINING_DOT, amount=Decimal("-1.60")),
            tx(description=KELVIN, amount=Decimal("-15.00")),
            tx(description="\u039f\u0394\u039f\u03a3", amount=Decimal("-7.00")),
            tx(description="STRA\u00dfE 5", amount=Decimal("-8.00")),
            tx(description="NOMINA EMPRESA", amount=Decimal("2850.00"), detail="TRANSFER"),
            tx(description="OCTOPUS", amount=Decimal("-60.00"), detail="GCREOCTOPUSENERGY"),
            tx(description="OCTOPUS", amount=Decimal("-61.00"), detail="GCREOCTOPUSGAS"),
            tx(description="AMAZON US", amount=Decimal("-20.00"), currency="USD"),
        ],
    )
    await ingest(
        sessions,
        revolut,
        [
            tx(account_ref="Revolut"),
            tx(account_ref="Revolut", description="Caf\u00e9 Revolut", amount=Decimal("-4.00")),
        ],
    )


async def everything(session: AsyncSession) -> list[_Candidate]:
    rows = await session.execute(
        select(
            Transaction.id,
            Transaction.description,
            Transaction.detail,
            Transaction.amount,
            Account.name,
            Transaction.currency,
        ).join(Transaction.account)
    )
    return [_Candidate._make(row) for row in rows]


def matched_in_python(corpus: list[_Candidate], rule_like: Any) -> set[int]:
    compiled = _compile_regex(rule_like) if rule_like.description_mode == "regex" else None
    detail = _compile_detail_regex(rule_like) if rule_like.detail_mode == "regex" else None
    return {c.id for c in corpus if _matches(c, rule_like, compiled, detail)}


async def test_the_sql_prefilter_never_drops_a_match(sessions, accounts):
    await seed(sessions, accounts)

    async with sessions() as s:
        corpus = await everything(s)
        got = {label: {c.id for c in await _matching_candidates(s, r)} for label, r in RULES.items()}
        prefiltered = set(
            (
                await s.execute(
                    select(Transaction.id)
                    .join(Transaction.account)
                    .where(*await _candidate_conditions(s, RULES["contains"]))
                )
            ).scalars()
        )

    expected = {label: matched_in_python(corpus, r) for label, r in RULES.items()}
    assert got == expected

    ids = {(c.description, c.account_ref): c.id for c in corpus}
    assert expected["kelvin"] == {ids[KELVIN, "BBVA"]}
    assert expected["dotted istanbul"] == expected["leading combining dot"] == {ids[DOTTED_I, "BBVA"]}
    assert expected["dotted kiosk"] == {ids["K\u0130OSK", "BBVA"], ids[COMBINING_DOT, "BBVA"]}
    assert len(expected["accented"]) == 3
    assert len(expected["contains"]) == 5
    assert expected["empty value"] == {c.id for c in corpus}
    assert prefiltered == expected["contains"]


async def test_preview_counts_accented_matches(sessions, accounts):
    await seed(sessions, accounts)
    body = RuleIn(name="Cafe", description_mode="contains", description_value="CAF\u00c9")

    async with sessions() as s:
        assert (await preview_rule(body, s)).count == 3


async def test_apply_updates_only_the_matching_rows(sessions, accounts):
    await seed(sessions, accounts)
    async with sessions() as s, s.begin():
        s.add(Category(name="Supermarket", is_base=True))
    body = RuleIn(
        name="Mercadona",
        description_mode="contains",
        description_value="mercadona",
        amount_sign="negative",
        set_category="Supermarket",
        set_merchant="Mercadona",
        add_tags=["super", "Hogar"],
    )

    async with sessions() as s:
        result = await apply_rule_to_transactions(body, s)

    async with sessions() as s:
        rows = (
            await s.execute(
                select(Transaction).options(
                    selectinload(Transaction.tags), selectinload(Transaction.category)
                )
            )
        ).scalars().all()
        tags = sorted((await s.execute(select(Tag.name))).scalars())

    state = {
        r.description: (r.category.name, r.merchant, sorted(t.name for t in r.tags))
        for r in rows
        if "MERCADONA" in r.description
    }
    applied = ("Supermarket", "Mercadona", ["hogar", "super"])
    assert result.applied == 4
    assert state == {
        "MERCADONA": applied,
        "MERCADONA SA": applied,
        "COMPRA EN MERCADONA": applied,
        "DEVOLUCION MERCADONA": ("Groceries", None, []),
    }
    assert sum(r.merchant == "Mercadona" for r in rows) == 4
    assert tags == ["hogar", "super"]


async def test_a_saved_rule_is_read_and_applied_in_one_transaction(sessions, accounts):
    await seed(sessions, accounts)
    async with sessions() as s, s.begin():
        s.add(Category(name="Utilities", is_base=True))
        saved = Rule(
            name="Octopus",
            priority=10,
            description_mode="contains",
            description_value="octopus",
            detail_mode="regex",
            detail_value="energy|gas",
            set_category="Utilities",
            add_tags=[],
        )
        s.add(saved)

    async with sessions() as s:
        result = await apply_saved_rule(saved.id, s)

    async with sessions() as s:
        categories = (
            await s.execute(
                select(Category.name)
                .join(Transaction, Transaction.category_id == Category.id)
                .where(Transaction.description == "OCTOPUS")
            )
        ).scalars()
        assert sorted(categories) == ["Utilities", "Utilities"]
    assert result.applied == 2


async def test_applying_a_missing_rule_is_a_404(sessions, accounts):
    async with sessions() as s:
        with pytest.raises(HTTPException) as raised:
            await apply_saved_rule(987654, s)
        assert not s.in_transaction()
    assert raised.value.status_code == 404
