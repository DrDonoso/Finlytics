from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db
from finlytics.api.schemas import DeleteMonthResult, StatementMonth, StatementOriginal
from finlytics.config import settings
from finlytics.db import queries
from finlytics.db.models import ImportRun

log = logging.getLogger(__name__)

router = APIRouter(prefix="/statements", tags=["statements"])


@router.get("/months", response_model=list[StatementMonth])
async def list_statement_months(
    account_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all (year, month) pairs that contain ≥1 transaction, sorted DESC.

    Pass ``?account_id=<id>`` to restrict to one account; omit for all accounts.
    """
    return await queries.get_statement_months(session, account_id=account_id)


@router.delete("/month", response_model=DeleteMonthResult)
async def delete_statement_month(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> DeleteMonthResult:
    """Delete all transactions for a given calendar month.

    Pass ``?account_id=<id>`` to restrict deletion to one account; omit to
    delete transactions for ALL accounts in that month.

    Hard-deletes every transaction whose ``transaction_date`` falls within
    [year-month-01 .. last day of month].  Junction rows in ``transaction_tags``
    are removed automatically via DB-level CASCADE.  Returns the count of deleted
    transactions so the frontend can confirm the operation.
    """
    deleted = await queries.delete_statement_month(
        session, year=year, month=month, account_id=account_id
    )
    return DeleteMonthResult(deleted=deleted)


@router.get("/originals", response_model=list[StatementOriginal])
async def list_statement_originals(
    year: int = Query(..., ge=1900, le=2100),
    month: int = Query(..., ge=1, le=12),
    account_id: int | None = Query(None),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List ImportRuns that have an original PDF on disk for the given month.

    Pass ``?account_id=<id>`` to restrict to one account; omit for all accounts.
    """
    return await queries.get_statement_originals(
        session, year=year, month=month, account_id=account_id
    )


@router.get("/original/{import_run_id}")
async def download_statement_original(
    import_run_id: int,
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    """Download the original uploaded PDF for a given ImportRun.

    Returns 404 when:
    - The ImportRun does not exist.
    - The run has no ``source_path`` (PDF was not captured).
    - The file is missing on disk.
    """
    from fastapi import HTTPException

    result = await session.execute(
        select(ImportRun).where(ImportRun.id == import_run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Import run not found")
    if run.source_path is None:
        raise HTTPException(status_code=404, detail="No original PDF for this import run")

    path = os.path.join(settings.upload_dir, run.source_path)
    if not os.path.isfile(path):
        log.warning("PDF file missing on disk: %s (import_run_id=%d)", path, import_run_id)
        raise HTTPException(status_code=404, detail="PDF file not found on disk")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=run.source_path,
    )
