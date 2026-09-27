"""Seed script: inserts the canonical base category taxonomy.

Run once after migrations:
    python seed.py

Safe to run multiple times (idempotent: skips existing categories).
BASE_CATEGORIES is the single source of truth from finlytics.extraction.taxonomy.
Tags are user-created only; seed does not insert any tags.
"""

import asyncio
from datetime import datetime

from sqlalchemy import select

from finlytics.db.models import Category
from finlytics.db.session import async_session_factory
from finlytics.extraction.taxonomy import BASE_CATEGORIES

# Distinct palette colors for the 20 base categories, chosen to stay apart under
# normal vision and the common colour-vision deficiencies. Changing one needs a
# migration too (see 0025), since existing installs keep what was first seeded.
# Idempotent: only applied when the category's color is still the default grey.
BASE_CATEGORY_COLORS: dict[str, str] = {
    "Groceries":     "#70912f",
    "Dining":        "#b94644",
    "Transport":     "#4f86c6",
    "Fuel":          "#e65909",
    "Housing":       "#bd9670",
    "Utilities":     "#2bccb4",
    "Health":        "#e3a8b4",
    "Insurance":     "#6f69a3",
    "Shopping":      "#d77089",
    "Entertainment": "#cf7ffd",
    "Subscriptions": "#4963de",
    "Travel":        "#47a4b4",
    "Education":     "#c6c102",
    "Income":        "#26795f",
    "Transfers":     "#97bd95",
    "Investments":   "#049886",
    "Bank Fees":     "#9f696f",
    "Taxes":         "#896385",
    "Cash/ATM":      "#d1b876",
    "Other":         "#bdb0ef",
}

_DEFAULT_COLOR = "#64748b"


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def seed() -> None:
    inserted_cats = 0
    recolored_cats = 0

    async with async_session_factory() as session:
        async with session.begin():
            # ── Categories ────────────────────────────────────────────────────
            for name in BASE_CATEGORIES:
                palette_color = BASE_CATEGORY_COLORS.get(name, _DEFAULT_COLOR)
                result = await session.execute(
                    select(Category).where(Category.name == name)
                )
                existing = result.scalar_one_or_none()
                if existing is None:
                    session.add(Category(name=name, is_base=True, color=palette_color))
                    inserted_cats += 1
                elif existing.color == _DEFAULT_COLOR:
                    # Backfill: category was created with the migration default grey;
                    # assign its distinct palette color.  User-changed colors are preserved.
                    existing.color = palette_color
                    recolored_cats += 1

    skipped_cats = len(BASE_CATEGORIES) - inserted_cats - recolored_cats
    print(
        f"{_timestamp()} "
        f"Seed complete — "
        f"categories: {inserted_cats} inserted, {recolored_cats} recolored, "
        f"{skipped_cats} already had correct color"
    )


if __name__ == "__main__":
    asyncio.run(seed())
