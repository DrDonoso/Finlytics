"""Durable post-import analysis. Network calls never run in the import transaction."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.assistant import settings as assistant_settings
from finlytics.assistant.limits import limiter_for
from finlytics.assistant.service import TurnUsage
from finlytics.config import settings
from finlytics.db.models import ImportSummaryAttempt, ImportSummaryJob, NotificationChannel
from finlytics.db.queries import import_summaries as queries
from finlytics.db.queries.types import ImportSummaryFacts
from finlytics.db.session import async_session_factory
from finlytics.extraction.llm_client import (
    LLMClient,
    LLMError,
    TextDelta,
    ToolCallsRequested,
    UsageReported,
    is_llm_configured,
)
from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token
from finlytics.notifications.import_summary_prompt import analysis_messages, render_import_summary
from finlytics.notifications.telegram import TelegramError, telegram_send_message

log = logging.getLogger(__name__)
GENERATION_TIMEOUT_SECONDS = 60
POLL_SECONDS = 30
_wake_event: asyncio.Event | None = None


@dataclass(frozen=True, repr=False)
class Destination:
    bot_token: str
    chat_id: str
    message_thread_id: int | None


def summary_destination(channel: NotificationChannel) -> Destination:
    if channel.channel != "telegram":
        raise TelegramError("Unsupported notification channel.")
    try:
        config = json.loads(decrypt_token(channel.config_enc))
    except (ValueError, TypeError):
        raise TelegramError("Invalid channel configuration.") from None
    if not isinstance(config, dict):
        raise TelegramError("Invalid channel configuration.")
    token, chat_id, thread = (
        config.get("bot_token"), config.get("chat_id"), config.get("message_thread_id")
    )
    if (
        not isinstance(token, str) or not token
        or not isinstance(chat_id, str) or not chat_id.lstrip("-").isdigit()
        or (thread is not None and (not isinstance(thread, int) or isinstance(thread, bool) or thread <= 0))
    ):
        raise TelegramError("Invalid channel configuration.")
    return Destination(token, chat_id, thread)


def wake_import_summaries() -> None:
    if _wake_event is not None:
        _wake_event.set()


def _retry_time(attempts: int, retry_after: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=max(30 * 2 ** (attempts - 1), retry_after))


async def _transition(job: ImportSummaryJob, status: str, error: str | None, **values: object) -> None:
    async with async_session_factory() as db, db.begin():
        await queries.update_claim(
            db, job, status=status, error=error, claim_token=None, lease_until=None, **values
        )
    if error is not None:
        log.warning("Import summary job_id=%d status=%s reason=%s", job.id, status, error)


async def _prepare_generation(
    db: AsyncSession, job: ImportSummaryJob
) -> tuple[ImportSummaryFacts, int] | None:
    channel = await queries.active_summary_channel(db, job)
    if channel is None:
        return None
    summary_destination(channel)
    if not is_llm_configured(settings):
        await queries.update_claim(db, job, status="blocked", error="ai_not_configured",
                                   claim_token=None, lease_until=None)
        return None
    facts = await queries.get_import_summary_facts(db, job)
    effective = assistant_settings.resolve_settings(
        await assistant_settings.get_settings_row(db, job.user_id)
    )
    if effective.monthly_token_budget is not None:
        from finlytics.clock import today

        spent = await assistant_settings.tokens_used_since(
            db, job.user_id, assistant_settings.month_start(today())
        )
        if spent >= effective.monthly_token_budget:
            await queries.update_claim(db, job, status="blocked", error="token_budget",
                                       claim_token=None, lease_until=None)
            return None
    verdict = limiter_for(effective.rate_limit_messages, effective.rate_limit_window_seconds).check(
        f"user:{job.user_id}"
    )
    if not verdict.allowed:
        await queries.update_claim(
            db, job, status="pending", error="rate_limited", claim_token=None, lease_until=None,
            next_attempt_at=datetime.now(UTC) + timedelta(seconds=verdict.retry_after),
        )
        return None
    if job.generation_attempts >= queries.MAX_ATTEMPTS:
        await queries.update_claim(db, job, status="failed", error="attempts_exhausted",
                                   claim_token=None, lease_until=None)
        return None
    if not await queries.update_claim(db, job, generation_attempts=job.generation_attempts + 1):
        return None
    attempt = ImportSummaryAttempt(job_id=job.id, user_id=job.user_id)
    db.add(attempt)
    await db.flush()
    return facts, attempt.id


async def _record_generation(
    job: ImportSummaryJob, attempt_id: int, usage: TurnUsage, message: str | None,
    error: str | None, retryable: bool,
) -> None:
    attempts = job.generation_attempts + 1
    status = "ready" if message is not None else (
        "pending" if retryable and attempts < queries.MAX_ATTEMPTS else "failed"
    )
    async with async_session_factory() as db, db.begin():
        attempt = await db.get(ImportSummaryAttempt, attempt_id)
        if attempt is not None:
            if usage.reported:
                attempt.prompt_tokens = usage.prompt_tokens
                attempt.completion_tokens = usage.completion_tokens
                attempt.total_tokens = usage.total_tokens
            attempt.answered = message is not None
        await queries.update_claim(
            db, job, status=status, message_text=message, error=error,
            claim_token=None, lease_until=None,
            next_attempt_at=datetime.now(UTC) if message is not None else _retry_time(attempts),
        )
    if error is not None:
        log.warning("Import summary generation job_id=%d reason=%s", job.id, error)


async def _generate(job: ImportSummaryJob) -> None:
    try:
        async with async_session_factory() as db, db.begin():
            prepared = await _prepare_generation(db, job)
    except queries.SummaryDataError as exc:
        await _transition(job, "failed", str(exc))
        return
    except EncryptionNotConfiguredError:
        await _transition(job, "blocked", "encryption_unavailable")
        return
    except TelegramError:
        await _transition(job, "blocked", "channel_unavailable")
        return
    if prepared is None:
        return
    facts, attempt_id = prepared
    usage = TurnUsage()
    message: str | None = None
    error: str | None = "generation_failed"
    retryable = False
    llm: LLMClient | None = None
    try:
        llm = LLMClient.from_settings(settings, max_retries=0)
        parts: list[str] = []
        length = 0
        async with asyncio.timeout(GENERATION_TIMEOUT_SECONDS):
            async for chunk in llm.stream_with_tools(
                analysis_messages(facts, job.language), tools=None, max_completion_tokens=1024,
            ):
                if isinstance(chunk, TextDelta):
                    if length < 8000:
                        parts.append(chunk.text[:8000 - length])
                        length += len(parts[-1])
                elif isinstance(chunk, UsageReported):
                    usage.prompt_tokens += chunk.prompt_tokens
                    usage.completion_tokens += chunk.completion_tokens
                    usage.total_tokens += chunk.total_tokens
                    usage.reported = True
                elif isinstance(chunk, ToolCallsRequested):
                    raise queries.SummaryDataError("unexpected_response")
        commentary = "".join(parts).strip()
        if not commentary:
            raise queries.SummaryDataError("empty_analysis")
        message = render_import_summary(facts, commentary, job.language)
        error = None
    except asyncio.CancelledError:
        error, retryable = "generation_interrupted", True
        raise
    except TimeoutError:
        error, retryable = "generation_timeout", True
    except LLMError as exc:
        error, retryable = "generation_failed", exc.retryable
    except queries.SummaryDataError as exc:
        error = str(exc)
    finally:
        with anyio.CancelScope(shield=True):
            await _record_generation(job, attempt_id, usage, message, error, retryable)
            if llm is not None:
                await llm.close()


async def _deliver(job: ImportSummaryJob) -> None:
    try:
        async with async_session_factory() as db, db.begin():
            channel = await queries.active_summary_channel(db, job)
            if channel is None:
                return
            destination = summary_destination(channel)
            if job.delivery_attempts >= queries.MAX_ATTEMPTS:
                await queries.update_claim(db, job, status="failed", error="attempts_exhausted",
                                           claim_token=None, lease_until=None)
                return
            if not await queries.update_claim(db, job, delivery_attempts=job.delivery_attempts + 1):
                return
    except EncryptionNotConfiguredError:
        await _transition(job, "blocked", "encryption_unavailable")
        return
    except TelegramError:
        await _transition(job, "blocked", "channel_unavailable")
        return

    status: str = "uncertain"
    error: str | None = "delivery_uncertain"
    next_attempt_at = datetime.now(UTC)
    try:
        if not job.message_text:
            raise TelegramError("Missing summary text.")
        async with asyncio.timeout(20):
            await telegram_send_message(
                destination.bot_token, destination.chat_id, job.message_text,
                message_thread_id=destination.message_thread_id,
            )
        status, error = "sent", None
    except asyncio.CancelledError:
        status, error = "uncertain", "delivery_uncertain"
        raise
    except TimeoutError:
        status, error = "uncertain", "delivery_uncertain"
    except TelegramError as exc:
        if exc.uncertain:
            status, error = "uncertain", "delivery_uncertain"
        else:
            attempts = job.delivery_attempts + 1
            status = "ready" if exc.retryable and attempts < queries.MAX_ATTEMPTS else "failed"
            error = "telegram_rejected"
            next_attempt_at = _retry_time(attempts, exc.retry_after)
    finally:
        with anyio.CancelScope(shield=True):
            await _transition(
                job, status, error, next_attempt_at=next_attempt_at,
                sent_at=datetime.now(UTC) if status == "sent" else None,
            )


async def process_next_summary() -> bool:
    async with async_session_factory() as db, db.begin():
        job = await queries.claim_summary(db)
    if job is None:
        return False
    if job.status == "generating":
        await _generate(job)
    else:
        await _deliver(job)
    return True


async def import_summary_loop() -> None:
    global _wake_event
    _wake_event = asyncio.Event()
    try:
        while True:
            _wake_event.clear()
            try:
                while await process_next_summary():
                    pass
            except Exception:
                log.exception("Import summary worker failed; pending jobs retained")
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
    finally:
        _wake_event = None
