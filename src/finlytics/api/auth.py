"""Authentication endpoints for Finlytics.

Router prefix : /auth  (mounted at /api in app.py → /api/auth/*)
Public        : status, setup, login, logout
Protected     : me, logout-others, password  (require a valid session cookie)

Sessions are signed JWTs in an httpOnly cookie, and they are revocable: each
token names itself (``jti``) and the ``token_version`` it was minted under.
Logout revokes that one token; a password change or "sign out other devices"
bumps the version, which ends every session, and hands the caller a new cookie
so the device making the request stays signed in.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import (
    SESSION_COOKIE,
    CurrentSession,
    get_current_session,
    get_current_user,
    get_db,
    load_session_user,
)
from finlytics.auth.ratelimit import RateLimiter, client_ip
from finlytics.auth.security import create_token, decode_token, hash_password, verify_password
from finlytics.config import settings
from finlytics.db.models import RevokedToken, User

router = APIRouter(prefix="/auth", tags=["auth"])

# Precomputed at import time — used to equalise bcrypt timing when the username
# does not exist, preventing username-enumeration via response-time differences.
_DUMMY_HASH: str = hash_password("__timing_dummy_constant__")

# Throttles failed logins per client IP. Deliberately not per username: keying on
# the username would let anyone lock out the legitimate account just by guessing
# against it. See finlytics.auth.ratelimit for the full rationale.  Password
# changes share it: guessing the current password there is the same attack.
login_rate_limiter = RateLimiter(
    max_attempts=settings.auth_login_max_attempts,
    window_seconds=settings.auth_login_window_seconds,
)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class _AuthBase(BaseModel):
    """Shared username validation for login and setup request bodies."""
    username: str = Field(..., min_length=1, max_length=150)

    @field_validator("username")
    @classmethod
    def strip_username(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 3:
            raise ValueError("username must be at least 3 characters after stripping whitespace")
        return stripped


class LoginIn(_AuthBase):
    """Login request — password accepted as any non-empty string.

    Intentionally NO min_length on password: format validation must not leak
    the password policy.  Invalid credentials always produce a generic 401.
    """
    password: str = Field(..., min_length=1, max_length=128)
    remember: bool = Field(default=False)


class SetupIn(_AuthBase):
    """First-user setup request — enforces a minimum password length."""
    password: str = Field(..., min_length=8, max_length=128)


class PasswordChangeIn(BaseModel):
    """Password change — the current password is re-verified, like a login."""
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseModel):
    username: str
    message: str


class StatusResponse(BaseModel):
    initialized: bool
    authenticated: bool


# ── Session helpers ───────────────────────────────────────────────────────────

def _start_session(response: Response, user: User, *, remember: bool) -> None:
    """Mint a token under the user's current version and set it as the cookie.

    Without remember-me the cookie has no max-age, so the browser drops it on
    close; the token inside still expires after ``auth_token_expire_days``.
    """
    token = create_token(user.username, version=user.token_version, remember=remember)
    max_age = settings.auth_remember_expire_days * 24 * 3600 if remember else None
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=max_age,
        path="/",
    )


def _check_login_limit(ip: str) -> None:
    """Spend one attempt from ``ip``'s budget, or raise 429 when it is exhausted."""
    # max_attempts <= 0 disables throttling (AUTH_LOGIN_MAX_ATTEMPTS=0).
    if login_rate_limiter.max_attempts <= 0:
        return
    verdict = login_rate_limiter.check(ip)
    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(verdict.retry_after)},
        )


async def _revoke(db: AsyncSession, claims: dict) -> None:
    """Record the token described by ``claims`` as revoked."""
    jti = claims.get("jti")
    exp = claims.get("exp")
    if not isinstance(jti, str) or not isinstance(exp, (int, float)):
        return
    now = datetime.now(UTC)
    # Rows only matter until their token would have expired anyway; dropping the
    # stale ones here keeps the table as small as the number of live sessions.
    await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
    if await db.get(RevokedToken, jti) is None:
        db.add(RevokedToken(jti=jti, expires_at=datetime.fromtimestamp(exp, tz=UTC)))
    try:
        await db.commit()
    except IntegrityError:
        # Two logouts of the same token raced; the other one already revoked it.
        await db.rollback()


async def _load_user(db: AsyncSession, session: CurrentSession) -> User:
    """Re-read the session's user through ``db`` so changes to it can be committed."""
    user = await db.get(User, session.user.id)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=StatusResponse)
async def auth_status(
    request: Request, db: AsyncSession = Depends(get_db)
) -> StatusResponse:
    """Public — reports whether setup is complete and whether the caller is
    authenticated.  The frontend uses this on mount to decide which screen to
    show (setup / login / dashboard)."""
    user_count = await db.scalar(select(func.count(User.id)))
    initialized = (user_count or 0) > 0

    authenticated = False
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        claims = decode_token(token)
        if claims is not None:
            authenticated = await load_session_user(db, claims) is not None

    return StatusResponse(initialized=initialized, authenticated=authenticated)


@router.post("/setup", response_model=AuthResponse, status_code=201)
async def auth_setup(
    body: SetupIn, response: Response, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    """Public (self-disabling) — creates the first and only user.

    Returns 409 if a user already exists.  On success, auto-logs in by setting
    the session cookie so the user lands directly on the dashboard.
    """
    user_count = await db.scalar(select(func.count(User.id)))
    if (user_count or 0) > 0:
        raise HTTPException(status_code=409, detail="Setup already completed")

    user = User(
        username=body.username,
        password_hash=await asyncio.to_thread(hash_password, body.password),
        token_version=0,
    )
    db.add(user)
    await db.flush()
    await db.commit()

    _start_session(response, user, remember=False)
    return AuthResponse(username=user.username, message="User created successfully")


@router.post("/login", response_model=AuthResponse)
async def auth_login(
    body: LoginIn, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AuthResponse:
    """Public — verifies credentials and sets the session cookie.

    Returns a GENERIC 401 for both wrong username and wrong password to avoid
    leaking which field is incorrect, and 429 once the caller's IP has burned
    through its attempt budget.
    """
    ip = client_ip(request)
    _check_login_limit(ip)

    # bcrypt at cost 12 takes ~250 ms of CPU; running it inline would freeze
    # every other request for that long, so it goes to a worker thread.
    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None:
        # Always run bcrypt to equalise timing — prevents username enumeration.
        await asyncio.to_thread(verify_password, body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not await asyncio.to_thread(verify_password, body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Authenticated: clear the counter so a couple of typos followed by a correct
    # password leave no trace for the next session.
    login_rate_limiter.reset(ip)

    _start_session(response, user, remember=body.remember)
    return AuthResponse(username=user.username, message="Login successful")


@router.post("/logout")
async def auth_logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict:
    """Public (idempotent) — revokes the session token and clears the cookie.

    Deleting the cookie alone would leave a copied token valid until it expired,
    so a token that still verifies is recorded in ``revoked_tokens``.  Anything
    else — no cookie, a forged or expired one — just gets the cookie cleared.
    """
    token = request.cookies.get(SESSION_COOKIE)
    claims = decode_token(token) if token else None
    if claims is not None:
        await _revoke(db, claims)

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
    )
    return {"message": "Logged out"}


@router.post("/logout-others")
async def auth_logout_others(
    response: Response,
    session: CurrentSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Protected — ends every session except the one making the request."""
    user = await _load_user(db, session)
    user.token_version += 1
    await db.commit()

    _start_session(response, user, remember=session.remember)
    return {"message": "Other sessions signed out"}


@router.post("/password")
async def auth_change_password(
    body: PasswordChangeIn,
    request: Request,
    response: Response,
    session: CurrentSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Protected — replaces the password and ends every other session.

    A wrong current password is a 400, not a 401: the caller IS authenticated,
    and the frontend treats any 401 as "the session is gone" and signs out.
    """
    ip = client_ip(request)
    _check_login_limit(ip)

    user = await _load_user(db, session)
    if not await asyncio.to_thread(verify_password, body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = await asyncio.to_thread(hash_password, body.new_password)
    user.token_version += 1
    await db.commit()
    login_rate_limiter.reset(ip)

    _start_session(response, user, remember=session.remember)
    return {"message": "Password changed"}


@router.get("/me")
async def auth_me(current_user: User = Depends(get_current_user)) -> dict:
    """Protected — returns the authenticated user's username.  401 if not logged in."""
    return {"username": current_user.username}
