"""Seed script: inserts the canonical base category taxonomy.

Run once after migrations:
    python seed.py

Safe to run multiple times (idempotent: skips existing categories).
BASE_CATEGORIES is the single source of truth from finlytics.extraction.taxonomy.
Tags are user-created only; seed does not insert any tags.
"""

import asyncio

from sqlalchemy import select

from finlytics.db.models import Category
from finlytics.db.session import async_session_factory
from finlytics.extraction.taxonomy import BASE_CATEGORIES

# Distinct palette colors for the 20 base categories.
# Idempotent: only applied when the category's color is still the default grey.
BASE_CATEGORY_COLORS: dict[str, str] = {
    "Groceries":     "#22c55e",   # green-500
    "Dining":        "#ef4444",   # red-500
    "Transport":     "#3b82f6",   # blue-500
    "Fuel":          "#f97316",   # orange-500
    "Housing":       "#92400e",   # amber-800 (earth)
    "Utilities":     "#0d9488",   # teal-600
    "Health":        "#ec4899",   # pink-500
    "Insurance":     "#8b5cf6",   # violet-500
    "Shopping":      "#f43f5e",   # rose-500
    "Entertainment": "#eab308",   # yellow-500
    "Subscriptions": "#6366f1",   # indigo-500
    "Travel":        "#0ea5e9",   # sky-500
    "Education":     "#1d4ed8",   # blue-700
    "Income":        "#10b981",   # emerald-500
    "Transfers":     "#94a3b8",   # slate-400
    "Investments":   "#d97706",   # amber-600
    "Bank Fees":     "#dc2626",   # red-600
    "Taxes":         "#475569",   # slate-600
    "Cash/ATM":      "#84cc16",   # lime-400
    "Other":         "#a78bfa",   # violet-400
}

_DEFAULT_COLOR = "#64748b"


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
        f"Seed complete — "
        f"categories: {inserted_cats} inserted, {recolored_cats} recolored, "
        f"{skipped_cats} already had correct color"
    )


if __name__ == "__main__":
    asyncio.run(seed())
