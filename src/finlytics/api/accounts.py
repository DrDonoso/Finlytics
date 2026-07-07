from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import AccountOut
from finlytics.db import queries

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountOut]:
    return await queries.get_accounts(session)
