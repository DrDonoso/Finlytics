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

import asyncio
import base64
import contextlib
import hashlib
import logging
import os
import re
import tempfile
import unicodedata
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_db, get_llm_client
from finlytics.api.schemas import (
    CheckDuplicatesIn,
    CheckDuplicatesOut,
    ConfirmIn,
    ImportQuality,
    ImportResult,
    PreviewOut,
    SuggestedTag,
    mask_account_number,
)
from finlytics.api.uploads import (
    ensure_within_limit,
    max_base64_chars,
    read_upload,
    upload_too_large,
)
from finlytics.config import settings
from finlytics.contracts import ExtractedTransaction
from finlytics.db.models import Account, ImportRun, Tag, Transaction
from finlytics.db.repository import (
    compute_dedup_hash,
    create_opening_balance_tx,
    list_rules,
    upsert_transactions,
)
from finlytics.extraction.extractor import (
    detect_statement_year,
    extract_account_number,
    extract_transactions,
)
from finlytics.extraction.import_quality import compute_import_quality
from finlytics.extraction.llm_client import LLMClient
from finlytics.extraction.parser import UnsupportedFileTypeError, parse_statement
from finlytics.extraction.prematch import pre_match_rules
from finlytics.extraction.rules import apply_rules
from finlytics.extraction.tag_colors import suggest_tag_colors
from finlytics.log_safety import one_line

log = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


# ── Slug helper ───────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Return a filesystem-safe slug from *name*.

    NFKD-normalizes, strips accents, replaces runs of non-alphanumeric
    characters with ``_``, strips leading/trailing ``_``.
    Falls back to ``"account"`` when the result would be empty.

    Examples:
      "Cuenta Nómina" → "Cuenta_Nomina"
      "  BBVA / ES "  → "BBVA_ES"
    """
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", ascii_only).strip("_")
    return slug or "account"


def _source_pdf_name(account_name: str | None, period: str, pdf: bytes) -> str:
    """Name a stored original after its content as well as its account and month.

    Account and month alone are not unique: a second statement for the same month
    overwrote the first, and the earlier import then served the wrong document.
    """
    digest = hashlib.sha256(pdf).hexdigest()[:12]
    return f"{_slugify(account_name or 'account')}_{period.replace('-', '')}_{digest}.pdf"


def _store_source_pdf(directory: str, filename: str, data: bytes) -> None:
    """Write ``data`` atomically, leaving an existing file of that name untouched.

    The name is content-addressed, so an existing file already holds these bytes.
    Writing to a temporary file and renaming it means a crash mid-write can never
    leave a truncated PDF behind under the final name.  If the surrounding
    transaction fails the file stays unreferenced, and a retry reuses it.
    """
    path = os.path.join(directory, filename)
    if os.path.exists(path):
        return
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".upload-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_path, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
        raise


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
        log.info("Auto-created account %r (type=bank)", one_line(account_name))
    return account


async def _persist_import_run(
    session: AsyncSession,
    account_id: int,
    source_filename: str,
    transactions: list[ExtractedTransaction],
    *,
    tag_colors: dict[str, str] | None = None,
    account_name: str | None = None,
    source_pdf: bytes | None = None,
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

    # Save the original PDF to disk when provided.
    if source_pdf is not None and period is not None:
        filename = _source_pdf_name(account_name, period, source_pdf)
        try:
            await asyncio.to_thread(
                _store_source_pdf, settings.upload_dir, filename, source_pdf
            )
            import_run.source_path = filename
        except OSError as exc:
            log.warning("PDF save failed (import continues without source_path): %s", exc)

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


async def _parse_file(file_bytes: bytes, ext: str, error_status: int = 400) -> str:
    """Parse raw file bytes → statement text, raising HTTPException on failure.

    pdfplumber is synchronous and CPU-bound (seconds on a long statement), so it
    runs in a worker thread instead of stalling the event loop for everyone.

    Only a message written for the user reaches the response. A parser failure can
    carry file paths or library internals, so it is logged and answered generically.
    """
    try:
        return await asyncio.to_thread(parse_statement, file_bytes, file_type=ext)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=error_status, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=error_status, detail=f"{ext} files are not supported yet."
        ) from exc
    except Exception as exc:
        log.exception("File parsing failed for a .%s upload", one_line(ext))
        raise HTTPException(
            status_code=error_status, detail="File parsing failed."
        ) from exc


def _decode_pdf_base64(b64: str | None) -> bytes | None:
    """Decode a raw base64 string to bytes; return None when *b64* is None or malformed.

    Held to the same cap as a direct upload (413): the preview already refuses a
    larger file, so only a client bypassing the UI can send one here.
    """
    if b64 is None:
        return None
    if len(b64) > max_base64_chars():
        raise upload_too_large()
    try:
        pdf = base64.b64decode(b64)
    except ValueError:
        log.warning("source_pdf_base64 is malformed — PDF will not be saved")
        return None
    ensure_within_limit(len(pdf))
    return pdf


# ── Preview endpoint ──────────────────────────────────────────────────────────

@router.post("/preview", response_model=PreviewOut)
async def preview_import(
    file: UploadFile = File(...),
    account_name: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client),
) -> PreviewOut:
    """Parse + LLM-extract a statement WITHOUT persisting. Returns transactions for user review."""
    file_bytes = await read_upload(file)
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

    statement_text = await _parse_file(file_bytes, ext, error_status=400)

    year = detect_statement_year(statement_text)

    # Detect IBAN from statement header; look up existing account if found.
    detected_iban = extract_account_number(statement_text)
    matched_account_id: int | None = None
    matched_account_name: str | None = None

    if detected_iban is not None:
        iban_result = await session.execute(
            select(Account).where(Account.account_number == detected_iban)
        )
        matched_account = iban_result.scalar_one_or_none()
        if matched_account is not None:
            matched_account_id = matched_account.id
            matched_account_name = matched_account.name
            account_name = matched_account.name  # use DB name as extraction ref

    # account_ref for rules/extraction — use known name or empty string (don't crash)
    effective_ref = account_name or ""

    rules = await list_rules(session, enabled_only=True)
    matched_txs, remaining_text = pre_match_rules(
        statement_text, rules,
        statement_year=year,
        account_ref=effective_ref,
    )

    try:
        if remaining_text.strip():
            extracted = await extract_transactions(
                remaining_text, effective_ref, llm_client, statement_year=year
            )
        else:
            extracted = []
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("LLM extraction failed")
        raise HTTPException(status_code=502, detail="LLM extraction failed.") from exc

    extracted = apply_rules(extracted, rules)
    all_txs = sorted(matched_txs + extracted, key=lambda t: t.transaction_date)

    # Collect distinct normalized tag names across all transactions.
    all_tag_names = list({name.strip().lower() for tx in all_txs for name in tx.tags})

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
        except Exception:  # noqa: BLE001 — suggested colours are cosmetic
            log.warning("preview_import: could not build suggested_tags, returning empty list")

    return PreviewOut(
        account_ref=account_name,
        filename=filename,
        transactions=all_txs,
        statement_year=year,
        year_detected=(year is not None),
        quality=ImportQuality.model_validate(
            compute_import_quality(
                all_txs,
                statement_year=year,
                year_detected=(year is not None),
            )
        ),
        suggested_tags=suggested_tags,
        detected_account_masked=mask_account_number(detected_iban),
        detected_account_iban=detected_iban,
        matched_account_id=matched_account_id,
        matched_account_name=matched_account_name,
    )


# ── Confirm endpoint ──────────────────────────────────────────────────────────

@router.post("/confirm", response_model=ImportResult)
async def confirm_import(
    body: ConfirmIn = Body(...),
    session: AsyncSession = Depends(get_db),
) -> ImportResult:
    """Persist the user-reviewed (and optionally edited) transaction list from a preview.

    Account resolution order:
    1. If ``account_number`` (IBAN) is provided:
       - Found in DB → use existing account (name is ignored; IBAN is immutable key).
       - Not found   → create new Account(name=account_name, account_number=account_number).
    2. If ``account_number`` is None → get-or-create by ``account_name`` (legacy path).

    Every transaction is stored under the resolved account, and its
    ``dedup_hash`` is keyed on that account's id — never on the ``account_ref``
    the client sent — so a re-import is recognised whatever name either copy
    of the statement carried.

    Opening balance (new accounts only):
    When ``opening_balance`` is provided and the account was just created by this
    confirm call, a synthetic "Saldo inicial" transaction is inserted with
    ``opening_date = min(transaction_date) − 1 day``, identical to the logic in
    ``POST /api/accounts``.  If the account already existed the field is silently
    ignored — the UI must only send it for new accounts.
    """
    source_pdf = _decode_pdf_base64(body.source_pdf_base64)

    async with session.begin():
        was_created = False

        if body.account_number is not None:
            iban_result = await session.execute(
                select(Account).where(Account.account_number == body.account_number)
            )
            account = iban_result.scalar_one_or_none()
            if account is None:
                if not body.account_name:
                    raise HTTPException(
                        status_code=422,
                        detail="account_name is required when account_number is new.",
                    )
                account = Account(
                    name=body.account_name,
                    account_number=body.account_number,
                    type="bank",
                    currency="EUR",
                )
                session.add(account)
                await session.flush()
                was_created = True
                log.info(
                    "Auto-created account %r with IBAN %r",
                    one_line(body.account_name), one_line(body.account_number),
                )
        else:
            if not body.account_name:
                raise HTTPException(
                    status_code=422,
                    detail="Provide account_name or account_number.",
                )
            # Pre-check: detect whether _resolve_account will create a new account.
            pre_check = await session.execute(
                select(Account.id).where(Account.name == body.account_name)
            )
            was_created = pre_check.scalar_one_or_none() is None
            account = await _resolve_account(session, None, body.account_name)

        result = await _persist_import_run(
            session, account.id, body.source_filename, body.transactions,
            tag_colors=body.tag_colors,
            account_name=account.name,
            source_pdf=source_pdf,
        )

        # Synthetic opening-balance transaction for accounts created by this import.
        # Ignored when account already existed (was_created=False) or when there are
        # no transactions to infer the opening date from.
        if (
            was_created
            and body.opening_balance is not None
            and body.opening_balance != 0
            and body.transactions
        ):
            opening_date = (
                min(tx.transaction_date for tx in body.transactions)
                - timedelta(days=1)
            )
            await create_opening_balance_tx(
                session,
                account_id=account.id,
                account_currency=account.currency,
                opening_balance=body.opening_balance,
                opening_date=opening_date,
            )

    return result


# ── Check-duplicates endpoint ─────────────────────────────────────────────────

@router.post("/check-duplicates", response_model=CheckDuplicatesOut)
async def check_duplicates(
    body: CheckDuplicatesIn = Body(...),
    session: AsyncSession = Depends(get_db),
) -> CheckDuplicatesOut:
    """Flag which preview transactions would be skipped by confirm.

    For each input transaction, computes ``compute_dedup_hash`` using the
    same normalization as ``upsert_transactions``, then queries
    ``transactions.dedup_hash`` in one round-trip.

    ``account_name`` is resolved exactly as ``/confirm`` resolves it; a name
    with no account yet is a new account, which cannot hold duplicates.

    Also flags intra-batch repeats (second+ occurrence of the same hash)
    so the frontend can surface all duplicates in one pass.
    """
    if not body.transactions:
        return CheckDuplicatesOut(is_duplicate=[])

    account_id = (
        await session.execute(select(Account.id).where(Account.name == body.account_name))
    ).scalar_one_or_none()

    hashes = [
        compute_dedup_hash(
            account_id=account_id if account_id is not None else 0,
            transaction_date=item.transaction_date,
            amount=item.amount,
            description=item.description,
            detail=item.detail,
        )
        for item in body.transactions
    ]

    existing: set[str] = set()
    if account_id is not None:
        result = await session.execute(
            select(Transaction.dedup_hash).where(Transaction.dedup_hash.in_(hashes))
        )
        existing = set(result.scalars().all())

    is_duplicate: list[bool] = []
    seen: set[str] = set()
    for h in hashes:
        is_duplicate.append(h in existing or h in seen)
        seen.add(h)

    return CheckDuplicatesOut(is_duplicate=is_duplicate)


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

    file_bytes = await read_upload(file)
    filename = file.filename or "upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

    statement_text = await _parse_file(file_bytes, ext, error_status=422)
    year = detect_statement_year(statement_text)

    async with session.begin():
        account = await _resolve_account(session, account_id, account_name)

        rules = await list_rules(session, enabled_only=True)
        matched_txs, remaining_text = pre_match_rules(
            statement_text, rules,
            statement_year=year,
            account_ref=account.name,
        )

        try:
            if remaining_text.strip():
                extracted = await extract_transactions(
                    remaining_text, account.name, llm_client, statement_year=year
                )
            else:
                extracted = []
        except HTTPException:
            raise
        except Exception as exc:
            log.exception("LLM extraction failed")
            raise HTTPException(
                status_code=502, detail="LLM extraction failed."
            ) from exc

        extracted = apply_rules(extracted, rules)
        all_txs = sorted(matched_txs + extracted, key=lambda t: t.transaction_date)

        result = await _persist_import_run(
            session, account.id, filename, all_txs,
            account_name=account.name,
            source_pdf=file_bytes,
        )

    return result
