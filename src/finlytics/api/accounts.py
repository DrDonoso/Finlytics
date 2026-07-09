from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import AccountOut, AccountPatch, DeleteAccountResult, mask_account_number
from finlytics.db import queries
from finlytics.db.models import Account

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
async def list_accounts(session: AsyncSession = Depends(get_db)) -> list[AccountOut]:
    rows = await queries.get_accounts(session)
    return [
        {**r, "account_number_masked": mask_account_number(r.get("account_number"))}
        for r in rows
    ]


@router.patch("/{account_id}", response_model=AccountOut)
async def patch_account(
    account_id: int,
    body: AccountPatch = Body(...),
    session: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Update an account's name. Account number is immutable and cannot be changed here."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty.")

    async with session.begin():
        result = await session.execute(select(Account).where(Account.id == account_id))
        account = result.scalar_one_or_none()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found.")
        account.name = name
        await session.flush()

    updated = await queries.get_account_by_id(session, account_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {**updated, "account_number_masked": mask_account_number(updated.get("account_number"))}


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

