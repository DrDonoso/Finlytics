from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import AccountCreate, AccountOut, AccountPatch, DeleteAccountResult, mask_account_number
from finlytics.db import queries
from finlytics.db.models import Account
from finlytics.db.repository import create_opening_balance_tx

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountOut, status_code=201)
async def create_account(
    body: AccountCreate,
    session: AsyncSession = Depends(get_db),
) -> AccountOut:
    """Create a new account, optionally with a synthetic opening-balance transaction.

    Returns 409 Conflict when the name or a non-null account_number already exists.
    Returns 422 when opening_balance is provided without opening_date.

    ⚠️ KPI skew: a non-zero opening_balance is stored as a regular Transaction
    (description="Saldo inicial").  Summary/KPI queries sum all Transaction.amount
    values, so a positive opening_balance will appear as "income" in that month.
    This is deliberate in the current slice — see follow-up proposal in
    decisions/inbox/shuri-post-accounts-contract.md for the is_system exclusion path.
    """
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name must not be empty.")

    async with session.begin():
        # ── Uniqueness guards ──────────────────────────────────────────────────
        existing_name = (
            await session.execute(select(Account).where(Account.name == name))
        ).scalar_one_or_none()
        if existing_name is not None:
            raise HTTPException(status_code=409, detail="An account with this name already exists.")

        if body.account_number is not None:
            existing_iban = (
                await session.execute(
                    select(Account).where(Account.account_number == body.account_number)
                )
            ).scalar_one_or_none()
            if existing_iban is not None:
                raise HTTPException(
                    status_code=409,
                    detail="An account with this account number already exists.",
                )

        # ── Create account ─────────────────────────────────────────────────────
        account = Account(
            name=name,
            type=body.type,
            currency=body.currency,
            account_number=body.account_number,
        )
        session.add(account)
        await session.flush()  # materialise account.id

        # ── Synthetic opening-balance transaction ──────────────────────────────
        if body.opening_balance is not None and body.opening_balance != 0:
            await create_opening_balance_tx(
                session,
                account_id=account.id,
                account_name=name,
                account_currency=body.currency,
                opening_balance=body.opening_balance,
                opening_date=body.opening_date,  # type: ignore[arg-type]
            )

    # Read back the freshly created row (includes tx_count from the JOIN query).
    row = await queries.get_account_by_id(session, account.id)
    if row is None:
        raise HTTPException(status_code=500, detail="Account creation failed unexpectedly.")
    return {**row, "account_number_masked": mask_account_number(row.get("account_number"))}


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

