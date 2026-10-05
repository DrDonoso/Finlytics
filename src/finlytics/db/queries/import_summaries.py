"""Persistence and ledger facts for opt-in post-import summaries."""

from __future__ import annotations

import hashlib
from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import (
    Account,
    ImportRun,
    ImportSummaryJob,
    ImportSummarySettings,
    NotificationChannel,
    Transaction,
)
from finlytics.db.queries.summaries import (
    compare_amounts,
    compare_category_spending,
    get_by_category,
    get_overview,
)
from finlytics.db.queries.types import ImportSummaryFacts
from finlytics.mortgage.service import build_payment_context

MAX_ATTEMPTS = 3
LEASE_SECONDS = 180
ACTIVE_STATUSES = ("pending", "generating", "ready", "sending")


class SummaryConflictError(Exception):
    pass


class SummaryDataError(Exception):
    pass


def channel_version(channel: NotificationChannel) -> str:
    return hashlib.sha256(channel.config_enc.encode()).hexdigest()


async def get_summary_settings(
    db: AsyncSession, user_id: int, *, lock: bool = False
) -> ImportSummarySettings | None:
    stmt = select(ImportSummarySettings).where(ImportSummarySettings.user_id == user_id)
    return await db.scalar(stmt.with_for_update() if lock else stmt)


async def get_summary_channel(
    db: AsyncSession, user_id: int, channel_id: int | None
) -> NotificationChannel | None:
    return await db.scalar(select(NotificationChannel).where(
        NotificationChannel.id == channel_id,
        NotificationChannel.user_id == user_id,
        NotificationChannel.enabled.is_(True),
        NotificationChannel.channel == "telegram",
    ))


async def cancel_summaries(
    db: AsyncSession, user_id: int, *, channel_id: int | None = None, reason: str = "disabled"
) -> None:
    stmt = update(ImportSummaryJob).where(
        ImportSummaryJob.user_id == user_id,
        ImportSummaryJob.status.not_in(("sent", "cancelled", "uncertain")),
    )
    if channel_id is not None:
        stmt = stmt.where(ImportSummaryJob.channel_id == channel_id)
    await db.execute(stmt.values(
        status=case((ImportSummaryJob.status == "sending", "uncertain"), else_="cancelled"),
        error=reason, claim_token=None, lease_until=None, updated_at=datetime.now(UTC),
    ))


async def enqueue_import_summary(
    db: AsyncSession, *, user_id: int, import_run_id: int, account: Account,
    dates: list[date], num_inserted: int,
) -> int | None:
    if num_inserted == 0 or not dates:
        return None
    preference = await get_summary_settings(db, user_id, lock=True)
    if preference is None or not preference.enabled:
        return None
    channel = await get_summary_channel(db, user_id, preference.channel_id)
    job = ImportSummaryJob(
        user_id=user_id, import_run_id=import_run_id, account_id=account.id,
        account_name=account.name, channel_id=preference.channel_id,
        channel_version=channel_version(channel) if channel else "",
        from_date=min(dates), to_date=max(dates), language=preference.language,
        status="pending" if channel else "blocked",
        error=None if channel else "channel_unavailable",
    )
    db.add(job)
    await db.flush()
    return job.id


async def list_summary_jobs(
    db: AsyncSession, user_id: int, *, limit: int = 20
) -> list[ImportSummaryJob]:
    return list((await db.scalars(
        select(ImportSummaryJob).where(ImportSummaryJob.user_id == user_id)
        .order_by(ImportSummaryJob.id.desc()).limit(limit)
    )).all())


async def claim_summary(
    db: AsyncSession, *, now: datetime | None = None
) -> ImportSummaryJob | None:
    now = now or datetime.now(UTC)
    await db.execute(update(ImportSummaryJob).where(
        ImportSummaryJob.status == "sending", ImportSummaryJob.lease_until <= now,
    ).values(status="uncertain", error="delivery_uncertain", claim_token=None,
             lease_until=None, updated_at=now))
    await db.execute(update(ImportSummaryJob).where(
        ImportSummaryJob.status == "generating", ImportSummaryJob.lease_until <= now,
    ).values(
        status=case((ImportSummaryJob.generation_attempts < MAX_ATTEMPTS, "pending"),
                    else_="failed"),
        error="generation_interrupted", claim_token=None, lease_until=None,
        next_attempt_at=now, updated_at=now,
    ))
    await db.execute(update(ImportSummaryJob).where(
        ImportSummaryJob.status.in_((*ACTIVE_STATUSES, "blocked")),
        or_(ImportSummaryJob.account_id.is_(None), ImportSummaryJob.import_run_id.is_(None)),
    ).values(status="cancelled", error="source_removed", claim_token=None, lease_until=None,
             updated_at=now))
    job = await db.scalar(
        select(ImportSummaryJob)
        .where(ImportSummaryJob.status.in_(("pending", "ready")),
               ImportSummaryJob.next_attempt_at <= now)
        .order_by(ImportSummaryJob.next_attempt_at, ImportSummaryJob.id)
        .with_for_update(skip_locked=True).limit(1)
    )
    if job is None:
        return None
    job.status = "sending" if job.message_text is not None else "generating"
    job.claim_token = str(uuid4())
    job.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    job.updated_at = now
    await db.flush()
    return job


async def update_claim(
    db: AsyncSession, job: ImportSummaryJob, **values: object
) -> bool:
    result = await db.execute(update(ImportSummaryJob).where(
        ImportSummaryJob.id == job.id,
        ImportSummaryJob.claim_token == job.claim_token,
        ImportSummaryJob.status.in_(("generating", "sending")),
        ImportSummaryJob.lease_until > datetime.now(UTC),
    ).values(**values, updated_at=datetime.now(UTC)))
    return result.rowcount == 1


async def active_summary_channel(
    db: AsyncSession, job: ImportSummaryJob
) -> NotificationChannel | None:
    preference = await get_summary_settings(db, job.user_id)
    channel = await get_summary_channel(db, job.user_id, job.channel_id)
    source = await db.scalar(select(ImportRun.id).where(ImportRun.id == job.import_run_id))
    if (
        preference is None or not preference.enabled
        or preference.channel_id != job.channel_id or channel is None
        or channel_version(channel) != job.channel_version or source is None
    ):
        await update_claim(db, job, status="cancelled", error="configuration_changed",
                           claim_token=None, lease_until=None)
        return None
    owned = await db.scalar(select(ImportSummaryJob.id).where(
        ImportSummaryJob.id == job.id,
        ImportSummaryJob.claim_token == job.claim_token,
        ImportSummaryJob.status.in_(("generating", "sending")),
        ImportSummaryJob.lease_until > datetime.now(UTC),
    ))
    return channel if owned is not None else None


async def retry_summary(
    db: AsyncSession, user_id: int, job_id: int, *, acknowledge_uncertain: bool
) -> ImportSummaryJob | None:
    preference = await get_summary_settings(db, user_id, lock=True)
    job = await db.scalar(select(ImportSummaryJob).where(
        ImportSummaryJob.id == job_id, ImportSummaryJob.user_id == user_id,
    ).with_for_update())
    if job is None:
        return None
    if job.status in (*ACTIVE_STATUSES, "sent"):
        return job
    if job.status == "cancelled":
        raise SummaryConflictError("This summary was cancelled.")
    if job.status == "uncertain" and not acknowledge_uncertain:
        raise SummaryConflictError("Acknowledge that Telegram may already have received this message.")
    channel = await get_summary_channel(db, user_id, job.channel_id)
    if (
        preference is None or not preference.enabled or channel is None
        or preference.channel_id != job.channel_id
        or channel_version(channel) != job.channel_version
        or job.import_run_id is None or job.account_id is None
    ):
        raise SummaryConflictError("The original source or selected channel is no longer available.")
    job.status = "ready" if job.message_text is not None else "pending"
    job.generation_attempts = 0
    job.delivery_attempts = 0
    job.error = None
    job.claim_token = None
    job.lease_until = None
    job.next_attempt_at = datetime.now(UTC)
    job.updated_at = datetime.now(UTC)
    await db.flush()
    return job


def previous_summary_period(start: date, end: date) -> tuple[date, date]:
    if end < start:
        raise SummaryDataError("invalid_period")
    try:
        previous_end = start - timedelta(days=1)
        if start.day == 1 and end == date(start.year, start.month, monthrange(start.year, start.month)[1]):
            return previous_end.replace(day=1), previous_end
        return previous_end - (end - start), previous_end
    except OverflowError:
        raise SummaryDataError("invalid_period") from None


async def get_import_summary_facts(
    db: AsyncSession, job: ImportSummaryJob
) -> ImportSummaryFacts:
    account = await db.get(Account, job.account_id) if job.account_id is not None else None
    run = await db.get(ImportRun, job.import_run_id) if job.import_run_id is not None else None
    imported = await db.scalar(select(func.count()).select_from(Transaction).where(
        Transaction.import_run_id == job.import_run_id, Transaction.is_system.is_(False),
    ))
    if account is None or run is None or not imported:
        raise SummaryDataError("source_removed")
    previous_from, previous_to = previous_summary_period(job.from_date, job.to_date)
    currencies = set((await db.scalars(select(Transaction.currency).where(
        Transaction.account_id == account.id,
        Transaction.transaction_date >= previous_from,
        Transaction.transaction_date <= job.to_date,
        Transaction.is_system.is_(False),
    ).distinct())).all())
    if currencies - {account.currency}:
        raise SummaryDataError("mixed_currencies")
    current = await get_overview(
        db, account_id=account.id, from_date=job.from_date, to_date=job.to_date
    )
    if current["num_transactions"] == 0:
        raise SummaryDataError("source_removed")
    previous = await get_overview(
        db, account_id=account.id, from_date=previous_from, to_date=previous_to
    )
    categories = await get_by_category(
        db, account_id=account.id, from_date=job.from_date, to_date=job.to_date
    )
    previous_categories = await get_by_category(
        db, account_id=account.id, from_date=previous_from, to_date=previous_to
    )
    has_history = previous["num_transactions"] > 0
    return {
        "account": account.name,
        "from_date": job.from_date.isoformat(), "to_date": job.to_date.isoformat(),
        "previous_from": previous_from.isoformat(), "previous_to": previous_to.isoformat(),
        "inserted": run.num_inserted, "duplicates": run.num_duplicates,
        "current": current, "previous": previous if has_history else None,
        "spending_change": (
            compare_amounts(previous["total_expense"], current["total_expense"])
            if has_history else None
        ),
        "categories": categories[:6],
        "changes": compare_category_spending(previous_categories, categories)[:5] if has_history else [],
        "mortgage_payments": await build_payment_context(
            db, user_id=job.user_id, account_id=account.id,
            from_date=job.from_date, to_date=job.to_date, history_from=previous_from,
        ),
    }
