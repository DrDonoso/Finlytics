"""Session revocation: logout, "sign out other devices" and password change.

Runs against a real in-memory SQLite database, because what is under test is
whether a token that still verifies cryptographically is refused by the lookup
that follows — a mocked session would answer whatever the test told it to.

Each ``AsyncClient`` plays one device: its cookie jar holds that device's
session, exactly like a browser.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api.auth import login_rate_limiter
from finlytics.api.deps import get_db
from finlytics.app import app
from finlytics.auth.security import decode_token, hash_password
from finlytics.config import settings
from finlytics.db.models import Base, RevokedToken, User

USERNAME = "drdonoso"
PASSWORD = "MyStr0ngP@ss!"
NEW_PASSWORD = "An0ther-Str0ng-One"
COOKIE = "finlytics_session"


@pytest.fixture
async def factory(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _get_db():
        async with session_factory() as s:
            yield s

    # The guard opens its own session through the module-level factory.
    monkeypatch.setattr("finlytics.api.deps.async_session_factory", session_factory)
    # Cost 12 would add a quarter of a second to every login in this file.
    monkeypatch.setattr("finlytics.auth.security._BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(settings, "auth_cookie_secure", False)
    app.dependency_overrides[get_db] = _get_db

    async with session_factory() as s:
        s.add(User(username=USERNAME, password_hash=hash_password(PASSWORD)))
        await s.commit()

    yield session_factory

    app.dependency_overrides.pop(get_db, None)
    await engine.dispose()


@asynccontextmanager
async def _device():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _login(device: AsyncClient, *, password: str = PASSWORD, remember: bool = False) -> str:
    resp = await device.post(
        "/api/auth/login",
        json={"username": USERNAME, "password": password, "remember": remember},
    )
    assert resp.status_code == 200, resp.text
    return resp.cookies[COOKIE]


async def _is_signed_in(device: AsyncClient) -> bool:
    return (await device.get("/api/auth/me")).status_code == 200


async def _token_is_accepted(token: str) -> bool:
    async with _device() as stranger:
        stranger.cookies.set(COOKIE, token)
        return await _is_signed_in(stranger)


# ── Logout ────────────────────────────────────────────────────────────────────

async def test_logout_revokes_the_token_itself(factory):
    """A copy of the cookie taken before logout must stop working after it."""
    async with _device() as laptop:
        token = await _login(laptop)
        assert await _token_is_accepted(token)

        resp = await laptop.post("/api/auth/logout")

    assert resp.status_code == 200
    assert not await _token_is_accepted(token)


async def test_status_reports_a_revoked_session_as_signed_out(factory):
    async with _device() as laptop:
        token = await _login(laptop)
        await laptop.post("/api/auth/logout")

    async with _device() as stranger:
        stranger.cookies.set(COOKIE, token)
        status = (await stranger.get("/api/auth/status")).json()

    assert status == {"initialized": True, "authenticated": False}


async def test_logout_only_ends_its_own_session(factory):
    async with _device() as laptop, _device() as phone:
        await _login(laptop)
        await _login(phone)

        await laptop.post("/api/auth/logout")

        assert await _is_signed_in(phone)


async def test_logging_out_the_same_token_twice_is_harmless(factory):
    async with _device() as laptop:
        token = await _login(laptop)

    for _ in range(2):
        async with _device() as replay:
            replay.cookies.set(COOKIE, token)
            assert (await replay.post("/api/auth/logout")).status_code == 200

    async with factory() as s:
        rows = (await s.scalars(select(RevokedToken))).all()
    assert [r.jti for r in rows] == [decode_token(token)["jti"]]


async def test_logout_purges_revocations_whose_token_has_expired(factory):
    async with factory() as s:
        s.add(RevokedToken(jti="stale", expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
        await s.commit()

    async with _device() as laptop:
        token = await _login(laptop)
        await laptop.post("/api/auth/logout")

    async with factory() as s:
        jtis = set((await s.scalars(select(RevokedToken.jti))).all())
    assert jtis == {decode_token(token)["jti"]}


# ── Sign out other devices ────────────────────────────────────────────────────

async def test_logout_others_ends_every_other_session(factory):
    async with _device() as laptop, _device() as phone:
        await _login(laptop)
        await _login(phone)

        resp = await laptop.post("/api/auth/logout-others")

        assert resp.status_code == 200
        assert not await _is_signed_in(phone)
        assert await _is_signed_in(laptop)


async def test_logout_others_keeps_the_callers_remember_me(factory):
    async with _device() as laptop:
        await _login(laptop, remember=True)

        resp = await laptop.post("/api/auth/logout-others")

    assert f"max-age={settings.auth_remember_expire_days * 24 * 3600}" in resp.headers["set-cookie"].lower()
    claims = decode_token(resp.cookies[COOKIE])
    lifetime = claims["exp"] - claims["iat"]
    assert lifetime == settings.auth_remember_expire_days * 24 * 3600


async def test_session_endpoints_require_a_session(factory):
    async with _device() as stranger:
        assert (await stranger.post("/api/auth/logout-others")).status_code == 401
        resp = await stranger.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )
        assert resp.status_code == 401


# ── Password change ───────────────────────────────────────────────────────────

async def test_password_change_replaces_the_password(factory):
    async with _device() as laptop:
        await _login(laptop)

        resp = await laptop.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )

    assert resp.status_code == 200
    async with _device() as later:
        refused = await later.post(
            "/api/auth/login", json={"username": USERNAME, "password": PASSWORD}
        )
        assert refused.status_code == 401
        await _login(later, password=NEW_PASSWORD)


async def test_password_change_ends_other_sessions_but_not_the_callers(factory):
    async with _device() as laptop, _device() as phone:
        await _login(laptop)
        await _login(phone)

        await laptop.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )

        assert not await _is_signed_in(phone)
        assert await _is_signed_in(laptop)


async def test_wrong_current_password_is_a_400_and_changes_nothing(factory):
    """Not a 401: the caller is authenticated, and the SPA signs out on any 401."""
    async with _device() as laptop:
        await _login(laptop)

        resp = await laptop.post(
            "/api/auth/password",
            json={"current_password": "not-my-password", "new_password": NEW_PASSWORD},
        )

        assert resp.status_code == 400
        assert await _is_signed_in(laptop)

    async with _device() as later:
        await _login(later)


async def test_new_password_below_the_minimum_is_rejected(factory):
    async with _device() as laptop:
        await _login(laptop)

        resp = await laptop.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": "short"},
        )

    assert resp.status_code == 422


async def test_guessing_the_current_password_is_rate_limited(factory, monkeypatch):
    """Otherwise a stolen session could brute-force the password it lacks."""
    monkeypatch.setattr(login_rate_limiter, "max_attempts", 3)

    async with _device() as laptop:
        await _login(laptop)

        for _ in range(3):
            resp = await laptop.post(
                "/api/auth/password",
                json={"current_password": "a-wrong-guess", "new_password": NEW_PASSWORD},
            )
            assert resp.status_code == 400

        blocked = await laptop.post(
            "/api/auth/password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        )

    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1


# ── Tokens from before sessions were revocable ────────────────────────────────

async def test_a_token_without_session_claims_is_refused(factory):
    now = datetime.now(timezone.utc)
    legacy = jwt.encode(
        {"sub": USERNAME, "iat": now, "exp": now + timedelta(days=7)},
        settings.auth_secret,
        algorithm="HS256",
    )

    assert not await _token_is_accepted(legacy)
