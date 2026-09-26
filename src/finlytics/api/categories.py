from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import CategoryCreate, CategoryOut, CategoryUpdate
from finlytics.db import queries
from finlytics.db.queries.types import CategoryRow, CategoryUpdateRow
from finlytics.db.repository import get_or_create_category

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(session: AsyncSession = Depends(get_db)) -> list[CategoryRow]:
    return await queries.get_categories(session)


@router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    body: CategoryCreate,
    session: AsyncSession = Depends(get_db),
) -> CategoryRow:
    """Create-or-get a category by name (idempotent).

    * An existing category (English name or Spanish label) is returned as-is.
    * A new name goes through ``translate_category_name`` to normalise the
      canonical English name and populate ``name_es``.  Falls back to the
      literal name when translation is unavailable (test env / no OpenAI config).
    * 201 always, whether created or found.
    """
    async with session.begin():
        cat = await get_or_create_category(
            session,
            body.name,
            is_base=False,
            color=body.color,
        )
    return {
        "id": cat.id,
        "name": cat.name,
        "name_es": cat.name_es,
        "is_base": cat.is_base,
        "color": cat.color,
        "tx_count": 0,
    }


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    body: CategoryUpdate,
    session: AsyncSession = Depends(get_db),
) -> CategoryUpdateRow:
    """Recolour a category.

    * 200 — updated.
    * 404 — category not found.

    Only ``color`` is accepted; renaming base categories is out of scope.
    Custom categories created by the LLM or the user default to the neutral
    grey (#64748b) until explicitly changed here.
    """
    cat = await queries.update_category(session, category_id, color=body.color)
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found.")
    return cat
