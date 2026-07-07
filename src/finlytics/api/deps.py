"""FastAPI dependency providers for Finlytics.

Provides:
  get_db            → AsyncSession (yields; suitable for Depends)
  get_llm_client    → LLMClient   (raises 503 if LLM env vars are missing)
  get_current_user  → User        (raises 401 if session cookie is missing/invalid)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.auth.security import decode_token
from finlytics.config import settings
from finlytics.db.models import User
from finlytics.db.session import async_session_factory
from finlytics.extraction.llm_client import LLMClient, is_llm_configured


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session for the lifetime of the request."""
    async with async_session_factory() as session:
        yield session


def get_llm_client() -> LLMClient:
    """Return an LLMClient configured from settings.

    Raises 503 if the three required OpenAI env vars are not set so the caller
    gets a clear error instead of a cryptic AuthenticationError later.
    """
    if not is_llm_configured(settings):
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM not configured — set OPENAI_API_KEY, OPENAI_BASE_URL "
                "and OPENAI_MODEL to enable AI extraction."
            ),
        )
    return LLMClient.from_settings(settings)


async def get_current_user(request: Request) -> User:
    """Validate the httpOnly session cookie and return the authenticated user.

    Raises HTTP 401 if the cookie is absent, expired, or carries an unknown
    username.  Attach this as a router-level dependency to protect endpoints.

    Uses its OWN short-lived session (not the get_db request session) so that
    the User SELECT does not trigger SQLAlchemy autobegin on the shared session.
    If get_current_user used the request session, any subsequent
    ``async with session.begin()`` inside a write endpoint would raise
    ``InvalidRequestError: A transaction is already begun on this Session``.

    The session factory has expire_on_commit=False so the returned User stays
    accessible after its auth session closes (no DetachedInstanceError).
    """
    token = request.cookies.get("finlytics_session")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    username = payload.get("sub")
    async with async_session_factory() as auth_db:
        user = await auth_db.scalar(select(User).where(User.username == username))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
