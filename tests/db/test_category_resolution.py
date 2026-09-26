"""get_or_create_category must look a category up BEFORE paying for a translation.

Runs against a real in-memory SQLite database so the case-insensitive and
Spanish-label matching is exercised as SQL, not as mock plumbing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.db.models import Base, Category
from finlytics.db.repository import get_or_create_category


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add_all([
            Category(name="Groceries", name_es="Supermercado", is_base=True),
            Category(name="Clothing", name_es="Ropa", is_base=False),
        ])
        await s.flush()
        yield s
    await engine.dispose()


@pytest.fixture
def translate():
    with patch("finlytics.db.repository.translate_category_name", new_callable=AsyncMock) as m:
        yield m


async def _count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Category))


@pytest.mark.parametrize("name", ["Groceries", "groceries", "  Groceries ", "Supermercado", "supermercado"])
async def test_existing_category_resolves_without_translation(session, translate, name):
    cat = await get_or_create_category(session, name)

    assert cat.name == "Groceries"
    translate.assert_not_called()
    assert await _count(session) == 2


async def test_paraphrase_from_the_llm_cannot_fork_an_existing_category(session, translate):
    translate.return_value = {"name_en": "Grocery", "name_es": "Supermercado"}

    cat = await get_or_create_category(session, "Groceries")

    assert cat.name == "Groceries"
    assert await _count(session) == 2


async def test_new_name_is_translated_and_matched_on_its_canonical_form(session, translate):
    translate.return_value = {"name_en": "Clothing", "name_es": "Ropa"}

    cat = await get_or_create_category(session, "Vestimenta")

    translate.assert_awaited_once_with("Vestimenta")
    assert cat.name == "Clothing"
    assert await _count(session) == 2


async def test_genuinely_new_name_is_created_with_both_labels(session, translate):
    translate.return_value = {"name_en": "Pet Care", "name_es": "Mascotas"}

    cat = await get_or_create_category(session, "Mascotas")

    assert (cat.name, cat.name_es) == ("Pet Care", "Mascotas")
    assert await _count(session) == 3


async def test_untranslatable_new_name_is_stored_literally(session, translate):
    translate.return_value = None

    cat = await get_or_create_category(session, " Gimnasio ")

    assert (cat.name, cat.name_es) == ("Gimnasio", None)


async def test_exact_name_wins_over_a_spanish_label_collision(session, translate):
    session.add(Category(name="Lodging", name_es="Hotel"))
    await session.flush()
    session.add(Category(name="Hotel", name_es="Alojamiento"))
    await session.flush()

    cat = await get_or_create_category(session, "hotel")

    assert cat.name == "Hotel"
    translate.assert_not_called()
