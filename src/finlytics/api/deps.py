"""FastAPI dependency providers for Finlytics.

Provides:
  get_db              → AsyncSession   (yields; suitable for Depends)
  get_llm_client      → LLMClient      (raises 503 if LLM env vars are missing)
  get_current_session → CurrentSession (raises 401 if session cookie is missing/invalid)
  get_current_user    → User           (same check, returns just the user)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.auth.security import decode_token
from finlytics.config import settings
from finlytics.db.models import RevokedToken, User
from finlytics.db.session import async_session_factory
from finlytics.extraction.llm_client import LLMClient, is_llm_configured

SESSION_COOKIE = "finlytics_session"


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


@dataclass(frozen=True)
class CurrentSession:
    """The authenticated user plus what their token says about the session."""

    user: User
    remember: bool


async def load_session_user(db: AsyncSession, claims: dict) -> User | None:
    """Return the user a decoded token belongs to, or None if it is no longer valid.

    A signature check alone is not enough: the token must also carry the user's
    current ``token_version`` and must not have been revoked by a logout.  Tokens
    minted before sessions became revocable have neither claim and are refused.
    """
    username = claims.get("sub")
    version = claims.get("ver")
    jti = claims.get("jti")
    if not isinstance(username, str) or not isinstance(jti, str):
        return None
    if not isinstance(version, int) or isinstance(version, bool):
        return None
    revoked = select(RevokedToken.jti).where(RevokedToken.jti == jti).exists()
    return await db.scalar(
        select(User).where(
            User.username == username,
            User.token_version == version,
            ~revoked,
        )
    )


async def get_current_session(request: Request) -> CurrentSession:
    """Validate the httpOnly session cookie and describe the session it opens.

    Raises HTTP 401 if the cookie is absent, expired, revoked, minted under an
    older ``token_version``, or carries an unknown username.

    Uses its OWN short-lived session (not the get_db request session) so that
    the User SELECT does not trigger SQLAlchemy autobegin on the shared session.
    If this used the request session, any subsequent
    ``async with session.begin()`` inside a write endpoint would raise
    ``InvalidRequestError: A transaction is already begun on this Session``.

    The session factory has expire_on_commit=False so the returned User stays
    accessible after its auth session closes (no DetachedInstanceError).
    """
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    claims = decode_token(token)
    if claims is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    async with async_session_factory() as auth_db:
        user = await load_session_user(auth_db, claims)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return CurrentSession(user=user, remember=claims.get("rem") is True)


async def get_current_user(request: Request) -> User:
    """Return the authenticated user; see ``get_current_session`` for the checks.

    Attach this as a router-level dependency to protect endpoints.
    """
    return (await get_current_session(request)).user
