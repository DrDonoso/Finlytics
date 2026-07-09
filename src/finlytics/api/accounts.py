from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import AccountOut, DeleteAccountResult
from finlytics.db import queries

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountOut]:
    return await queries.get_accounts(session)


@router.delete("/{account_id}", response_model=DeleteAccountResult)
async def delete_account(
    account_id: int,
    session: AsyncSession = Depends(get_db),
) -> DeleteAccountResult:
    """Delete an account and all its transactions.

    * 200 — ``{deleted: N}`` where N = number of transactions removed.
    * 404 — account not found.
    """
    result = await queries.delete_account(session, account_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {"deleted": result}
