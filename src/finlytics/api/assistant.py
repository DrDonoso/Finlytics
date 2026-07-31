"""Finance assistant API — chat over the user's own financial data.

Routes
──────
  GET    /api/assistant/status                      — is the assistant usable?
  GET    /api/assistant/suggestions                 — starter prompts (i18n keys)
  GET    /api/assistant/conversations               — thread list, newest first
  POST   /api/assistant/conversations               — create a thread
  GET    /api/assistant/conversations/{id}          — thread with its messages
  DELETE /api/assistant/conversations/{id}          — delete a thread
  POST   /api/assistant/conversations/{id}/messages — ask a question (SSE stream)

All routes are auth-gated at the router-registration level in ``app.py``.
Conversations are scoped per user; a thread belonging to someone else answers
404, never 403 — a 403 would confirm that the id exists.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    AssistantConversationDetailOut,
    AssistantConversationOut,
    AssistantMessageIn,
    AssistantMessageOut,
    AssistantStatusOut,
    AssistantSuggestionsOut,
)
from finlytics.assistant import prompts
from finlytics.assistant.service import (
    AgentLimits,
    AnswerDelta,
    Completed,
    Failed,
    ToolStarted,
    run_turn,
)
from finlytics.auth.ratelimit import RateLimiter
from finlytics.clock import today as local_today
from finlytics.config import settings
from finlytics.db.models import AssistantConversation, AssistantMessage
from finlytics.db.session import async_session_factory
from finlytics.extraction.llm_client import LLMClient, is_llm_configured

log = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["assistant"])

# Keyed per user, not per IP: this guards a spending limit, and the person who
# runs up the OpenAI bill is the account, not the network they sit on.
_message_limiter = RateLimiter(
    max_attempts=settings.assistant_rate_limit_messages,
    window_seconds=settings.assistant_rate_limit_window_seconds,
)

# Longest a derived conversation title may be.
_TITLE_CHARS = 60


def _assistant_available() -> tuple[bool, str | None]:
    """Whether the assistant can run, and why not when it cannot."""
    if not settings.assistant_enabled:
        return False, "The assistant is disabled on this instance."
    if not is_llm_configured(settings):
        return False, (
            "LLM not configured — set OPENAI_API_KEY, OPENAI_BASE_URL and "
            "OPENAI_MODEL to enable the assistant."
        )
    return True, None


def _require_available() -> None:
    available, reason = _assistant_available()
    if not available:
        raise HTTPException(status_code=503, detail=reason)


def _derive_title(text: str) -> str:
    """First user message, trimmed, as the thread title.

    Deliberately not an LLM call: naming a thread is not worth doubling the cost
    of starting one.
    """
    flat = " ".join(text.split())
    if len(flat) <= _TITLE_CHARS:
        return flat
    return flat[: _TITLE_CHARS - 1].rstrip() + "…"


async def _get_owned_conversation(
    db: AsyncSession, conversation_id: int, user_id: int
) -> AssistantConversation:
    conversation = await db.scalar(
        select(AssistantConversation).where(
            AssistantConversation.id == conversation_id,
            AssistantConversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _to_out(conversation: AssistantConversation) -> AssistantConversationOut:
    return AssistantConversationOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _message_out(message: AssistantMessage) -> AssistantMessageOut:
    return AssistantMessageOut(
        id=message.id,
        role=message.role,  # type: ignore[arg-type]
        content=message.content,
        tool_calls=message.tool_calls,  # type: ignore[arg-type]
        created_at=message.created_at,
    )


# ── Metadata ──────────────────────────────────────────────────────────────────

@router.get("/status", response_model=AssistantStatusOut)
async def status() -> AssistantStatusOut:
    """Report whether the assistant is usable, without attempting a call."""
    available, reason = _assistant_available()
    return AssistantStatusOut(enabled=available, reason=reason)


@router.get("/suggestions", response_model=AssistantSuggestionsOut)
async def suggestions() -> AssistantSuggestionsOut:
    """Starter prompts for an empty thread, as i18n keys."""
    return AssistantSuggestionsOut(suggestions=prompts.SUGGESTIONS)


# ── Conversations ─────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=list[AssistantConversationOut])
async def list_conversations(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AssistantConversationOut]:
    """List the user's threads, most recently active first."""
    rows = (
        await db.execute(
            select(AssistantConversation)
            .where(AssistantConversation.user_id == user.id)
            .order_by(AssistantConversation.updated_at.desc())
        )
    ).scalars().all()
    return [_to_out(c) for c in rows]


@router.post("/conversations", response_model=AssistantConversationOut, status_code=201)
async def create_conversation(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantConversationOut:
    """Start an empty thread. The title is set from the first message sent to it."""
    _require_available()

    # The count and the insert share one transaction. Reading first and *then*
    # opening `db.begin()` would raise "a transaction is already begun": the
    # SELECT autobegins one, and SQLAlchemy refuses to nest.
    async with db.begin():
        count = await db.scalar(
            select(func.count())
            .select_from(AssistantConversation)
            .where(AssistantConversation.user_id == user.id)
        )
        if (count or 0) >= settings.assistant_max_conversations:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You have reached the limit of {settings.assistant_max_conversations} "
                    "conversations. Delete one to start another."
                ),
            )
        conversation = AssistantConversation(user_id=user.id, title="")
        db.add(conversation)

    await db.refresh(conversation)
    return _to_out(conversation)


@router.get(
    "/conversations/{conversation_id}", response_model=AssistantConversationDetailOut
)
async def get_conversation(
    conversation_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AssistantConversationDetailOut:
    """Return a thread with its full message history."""
    conversation = await _get_owned_conversation(db, conversation_id, user.id)
    rows = (
        await db.execute(
            select(AssistantMessage)
            .where(AssistantMessage.conversation_id == conversation.id)
            .order_by(AssistantMessage.id)
        )
    ).scalars().all()
    return AssistantConversationDetailOut(
        **_to_out(conversation).model_dump(),
        messages=[_message_out(m) for m in rows],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Delete a thread and its messages."""
    # Ownership check and delete in one transaction — see create_conversation
    # for why the read cannot happen before `db.begin()`.
    async with db.begin():
        await _get_owned_conversation(db, conversation_id, user.id)
        await db.execute(
            delete(AssistantConversation).where(
                AssistantConversation.id == conversation_id,
                AssistantConversation.user_id == user.id,
            )
        )
    return Response(status_code=204)


# ── Messaging (SSE) ───────────────────────────────────────────────────────────

def _sse(event: str, payload: dict) -> str:
    """Frame one Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    body: AssistantMessageIn,
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Ask a question and stream the answer back as Server-Sent Events.

    Event types:
      ``tool``   — a query is running; ``{name, label}`` for the activity chip
      ``token``  — a fragment of the answer; ``{text}``
      ``done``   — finished; ``{message_id, title}``
      ``error``  — the turn failed; ``{detail}``

    Errors after the first byte cannot become an HTTP status — the response has
    already started — so they arrive as an ``error`` event instead. Everything
    that can be checked up front (auth, ownership, rate limit, configuration) is
    checked before the stream opens, so those still return a real status code.
    """
    _require_available()

    if len(body.content) > settings.assistant_max_message_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Message is too long (max {settings.assistant_max_message_chars} "
                "characters)."
            ),
        )

    verdict = _message_limiter.check(f"user:{user.id}")
    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many assistant messages. Try again shortly.",
            headers={"Retry-After": str(verdict.retry_after)},
        )

    # Ownership check, history read and the question's insert share one
    # transaction: a SELECT autobegins one, so opening `db.begin()` afterwards
    # would raise "a transaction is already begun".
    async with db.begin():
        conversation = await _get_owned_conversation(db, conversation_id, user.id)

        # Replay window: older turns are dropped rather than summarised. A
        # summary would be another paid call, and the tools can always re-fetch
        # the facts.
        history_rows = (
            await db.execute(
                select(AssistantMessage)
                .where(AssistantMessage.conversation_id == conversation.id)
                .order_by(AssistantMessage.id.desc())
                .limit(settings.assistant_history_messages)
            )
        ).scalars().all()

        title = conversation.title or _derive_title(body.content)

        # Persist the question before streaming: if the model fails halfway, the
        # user should still see what they asked rather than an empty thread.
        db.add(
            AssistantMessage(
                conversation_id=conversation.id, role="user", content=body.content
            )
        )
        conversation.title = title
        conversation.updated_at = datetime.now(timezone.utc)

    history = [
        {"role": m.role, "content": m.content} for m in reversed(history_rows)
    ]
    history.append({"role": "user", "content": body.content})

    llm = LLMClient.from_settings(settings)
    limits = AgentLimits(
        max_tool_iterations=settings.assistant_max_tool_iterations,
        max_tool_result_rows=settings.assistant_max_tool_result_rows,
        projection_rates=settings.assistant_projection_rate_values,
    )
    today = local_today()
    conversation_id_value = conversation.id
    user_id = user.id

    async def event_stream():
        # The request-scoped session is closed by its dependency as soon as this
        # generator starts yielding, so the turn runs on its own session.
        async with async_session_factory() as stream_db:
            try:
                async for event in run_turn(
                    llm=llm,
                    session=stream_db,
                    user_id=user_id,
                    history=history,
                    today=today,
                    limits=limits,
                    background_tasks=background_tasks,
                ):
                    if isinstance(event, ToolStarted):
                        yield _sse("tool", {"name": event.name, "label": event.label})
                    elif isinstance(event, AnswerDelta):
                        yield _sse("token", {"text": event.text})
                    elif isinstance(event, Failed):
                        yield _sse("error", {"detail": event.message})
                        return
                    elif isinstance(event, Completed):
                        message = AssistantMessage(
                            conversation_id=conversation_id_value,
                            role="assistant",
                            content=event.answer,
                            tool_calls=event.tool_calls or None,
                        )
                        # `commit()` rather than `begin()`: run_turn has already
                        # run its context and tool queries on this session, so a
                        # transaction is autobegun and `begin()` would raise.
                        stream_db.add(message)
                        await stream_db.commit()
                        await stream_db.refresh(message)
                        yield _sse(
                            "done", {"message_id": message.id, "title": title}
                        )
            except Exception:  # noqa: BLE001 — the stream must close cleanly
                # The exception text is logged, never streamed: it can carry
                # connection strings, file paths and SQL, and this frame is
                # rendered verbatim in the user's browser.
                log.exception("Assistant stream failed")
                yield _sse(
                    "error",
                    {"detail": "The assistant failed. Check the server logs for details."},
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Without this, an nginx in front of the app buffers the whole
            # stream and the answer arrives in one lump at the end.
            "X-Accel-Buffering": "no",
        },
    )
