"""POST /api/imports — statement upload → parse → LLM extract → persist.

Two-step flow (recommended — lets the user review before saving):
  1. POST /api/imports/preview  → parse + extract, NO persistence
  2. POST /api/imports/confirm  → persist the (possibly edited) transaction list

One-shot flow (kept for backwards compatibility):
  POST /api/imports  → parse + extract + persist in one request

External dependencies (parse_statement, extract_transactions, upsert_transactions,
LLMClient, _resolve_account, _persist_import_run) are all patchable for unit tests.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from finlytics.api.deps import get_db, get_llm_client
from finlytics.api.schemas import ConfirmIn, ImportResult, PreviewOut, SuggestedTag
from finlytics.contracts import ExtractedTransaction
from finlytics.db.models import Account, ImportRun, Tag
from finlytics.db.repository import upsert_transactions
from finlytics.extraction.extractor import detect_statement_year, extract_transactions
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.parser import parse_statement
from finlytics.extraction.tag_colors import suggest_tag_colors

log = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


# ── Shared helpers (patchable in tests) ──────────────────────────────────────

async def _resolve_account(
    session: AsyncSession,
    account_id: int | None,
    account_name: str | None,
) -> Account:
    """Return the Account matching id or name; auto-create by name if absent."""
    if account_id is not None:
        result = await session.execute(
            select(Account).where(Account.id == account_id)
        )
        account = result.scalar_one_or_none()
        if account is None:
            raise HTTPException(status_code=404, detail=f"Account {account_id} not found")
        return account

    assert account_name is not None  # guaranteed by caller
    result = await session.execute(
        select(Account).where(Account.name == account_name)
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = Account(name=account_name, type="bank", currency="EUR")
        session.add(account)
        await session.flush()
        log.info("Auto-created account %r (type=bank)", account_name)
    return account


async def _persist_import_run(
    session: AsyncSession,
    account_id: int,
    source_filename: str,
    transactions: list[ExtractedTransaction],
    *,
    tag_colors: dict[str, str] | None = None,
) -> ImportResult:
    """Create an ImportRun and upsert transactions. Must be called inside session.begin()."""
    period: str | None = (
        transactions[0].transaction_date.strftime("%Y-%m") if transactions else None
    )
    import_run = ImportRun(
        account_id=account_id,
        source_filename=source_filename,
        period=period,
        num_parsed=len(transactions),
    )
    session.add(import_run)
    await session.flush()  # materialise import_run.id

    num_inserted, num_duplicates = await upsert_transactions(
        session, import_run, transactions, tag_colors=tag_colors
    )
    import_run.num_inserted = num_inserted
    import_run.num_duplicates = num_duplicates

    log.info(
        "Import complete: run_id=%d parsed=%d inserted=%d dupes=%d",
        import_run.id, len(transactions), num_inserted, num_duplicates,
    )
    return ImportResult(
        import_run_id=import_run.id,
        num_parsed=len(transactions),
        num_inserted=num_inserted,
        num_duplicates=num_duplicates,
    )


def _parse_file(file_bytes: bytes, ext: str, error_status: int = 400) -> str:
    """Parse raw file bytes → statement text, raising HTTPException on failure."""
    try:
        return parse_statement(file_bytes, file_type=ext)
    except Exception as exc:
        raise HTTPException(
            status_code=error_status, detail=f"File parsing failed: {exc}"
        ) from exc


# ── Preview endpoint ──────────────────────────────────────────────────────────

@router.post("/preview", response_model=PreviewOut)
async def preview_import(
    file: UploadFile = File(...),
    account_name: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> PreviewOut:
    """Parse + LLM-extract a statement WITHOUT persisting. Returns transactions for user review."""
    file_bytes = await file.read()
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

    statement_text = _parse_file(file_bytes, ext, error_status=400)

    year = detect_statement_year(statement_text)

    try:
        extracted = await extract_transactions(
            statement_text, account_name or "", llm_client, statement_year=year
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("LLM extraction failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM extraction failed: {exc}") from exc

    # Collect distinct normalized tag names across all extracted transactions.
    all_tag_names = list({name.strip().lower() for tx in extracted for name in tx.tags})

    suggested_tags: list[SuggestedTag] = []
    if all_tag_names:
        try:
            db_result = await session.execute(select(Tag.name))
            existing_names = {row.lower() for row in db_result.scalars().all()}
            new_tag_names = [n for n in all_tag_names if n not in existing_names]
            if new_tag_names:
                color_map = await suggest_tag_colors(new_tag_names) or {}
                suggested_tags = [
                    SuggestedTag(name=n, color=c) for n, c in color_map.items()
                ]
        except Exception:
            log.warning("preview_import: could not build suggested_tags, returning empty list")

    return PreviewOut(
        account_ref=account_name,
        filename=filename,
        transactions=extracted,
        statement_year=year,
        year_detected=(year is not None),
        suggested_tags=suggested_tags,
    )


# ── Confirm endpoint ──────────────────────────────────────────────────────────

@router.post("/confirm", response_model=ImportResult)
async def confirm_import(
    body: ConfirmIn = Body(...),
    session: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Persist the user-reviewed (and optionally edited) transaction list from a preview."""
    async with session.begin():
        account = await _resolve_account(session, None, body.account_name)
        result = await _persist_import_run(
            session, account.id, body.source_filename, body.transactions,
            tag_colors=body.tag_colors,
        )
    return result


# ── One-shot endpoint (kept for backwards compatibility) ──────────────────────

@router.post("", response_model=ImportResult, status_code=201)
async def create_import(
    file: UploadFile = File(...),
    account_name: str | None = Form(None),
    account_id: int | None = Form(None),
    session: AsyncSession = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> ImportResult:
    """Upload a bank statement, extract transactions with the LLM and persist them."""
    if account_id is None and account_name is None:
        raise HTTPException(
            status_code=422,
            detail="Provide either account_id or account_name.",
        )

    file_bytes = await file.read()
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

    statement_text = _parse_file(file_bytes, ext, error_status=422)

    async with session.begin():
        account = await _resolve_account(session, account_id, account_name)

        try:
            extracted = await extract_transactions(
                statement_text, account.name, llm_client
            )
        except HTTPException:
            raise
        except Exception as exc:
            log.error("LLM extraction failed: %s", exc)
            raise HTTPException(
                status_code=502, detail=f"LLM extraction failed: {exc}"
            ) from exc

        result = await _persist_import_run(session, account.id, filename, extracted)

    return result
