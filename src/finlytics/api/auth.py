"""Authentication endpoints for Finlytics.

Router prefix : /auth  (mounted at /api in app.py → /api/auth/*)
Public        : status, setup, login, logout
Protected     : me  (requires valid session cookie via get_current_user)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.auth.ratelimit import RateLimiter, client_ip
from finlytics.auth.security import create_token, decode_token, hash_password, verify_password
from finlytics.config import settings
from finlytics.db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "finlytics_session"
# Precomputed at import time — used to equalise bcrypt timing when the username
# does not exist, preventing username-enumeration via response-time differences.
_DUMMY_HASH: str = hash_password("__timing_dummy_constant__")

# Throttles failed logins per client IP. Deliberately not per username: keying on
# the username would let anyone lock out the legitimate account just by guessing
# against it. See finlytics.auth.ratelimit for the full rationale.
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


class AuthResponse(BaseModel):
    username: str
    message: str


class StatusResponse(BaseModel):
    initialized: bool
    authenticated: bool


# ── Cookie helper ─────────────────────────────────────────────────────────────

def _set_session_cookie(response: Response, token: str, max_age: int | None = None) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
        max_age=max_age,
        path="/",
    )


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
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        payload = decode_token(token)
        if payload is not None:
            username = payload.get("sub")
            user = await db.scalar(select(User).where(User.username == username))
            authenticated = user is not None

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
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.flush()
    await db.commit()

    _set_session_cookie(response, create_token(user.username))
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

    # max_attempts <= 0 disables throttling (AUTH_LOGIN_MAX_ATTEMPTS=0).
    if login_rate_limiter.max_attempts > 0:
        verdict = login_rate_limiter.check(ip)
        if not verdict.allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(verdict.retry_after)},
            )

    user = await db.scalar(select(User).where(User.username == body.username))
    if user is None:
        # Always run bcrypt to equalise timing — prevents username enumeration.
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Authenticated: clear the counter so a couple of typos followed by a correct
    # password leave no trace for the next session.
    login_rate_limiter.reset(ip)

    if body.remember:
        expire_days = settings.auth_remember_expire_days
        max_age = expire_days * 24 * 3600
    else:
        expire_days = settings.auth_token_expire_days
        max_age = None

    _set_session_cookie(response, create_token(user.username, expire_days), max_age)
    return AuthResponse(username=user.username, message="Login successful")


@router.post("/logout")
async def auth_logout(response: Response) -> dict:
    """Public (idempotent) — clears the session cookie regardless of its validity."""
    response.delete_cookie(
        key=_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.auth_cookie_secure,
    )
    return {"message": "Logged out"}


@router.get("/me")
async def auth_me(current_user: User = Depends(get_current_user)) -> dict:
    """Protected — returns the authenticated user's username.  401 if not logged in."""
    return {"username": current_user.username}
