"""Tests for /api/auth — setup, login, logout, me, status, and protected endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.auth import login_rate_limiter
from finlytics.api.deps import get_db
from finlytics.app import app
from finlytics.auth.security import create_token, hash_password
from finlytics.db.models import User


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.scalar = AsyncMock()
    begin_cm = AsyncMock()
    session.begin = MagicMock(return_value=begin_cm)
    return session


@pytest.fixture
async def auth_client(mock_session: MagicMock):
    """Test client with only get_db overridden — get_current_user runs for real
    so we can test the full auth flow (cookie validation, 401s)."""
    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_session
    app.dependency_overrides.pop(get_db, None)


def _fake_user(username: str = "drdonoso", password: str = "MyStr0ngP@ss!") -> MagicMock:
    user = MagicMock(spec=User)
    user.username = username
    user.password_hash = hash_password(password)
    return user


# ── GET /api/auth/status ──────────────────────────────────────────────────────

async def test_status_not_initialized(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=0)

    resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is False
    assert data["authenticated"] is False


async def test_status_initialized_not_authenticated(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=1)

    resp = await client.get("/api/auth/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is True
    assert data["authenticated"] is False


async def test_status_authenticated_with_valid_cookie(auth_client):
    client, session = auth_client
    token = create_token("drdonoso")
    user = _fake_user()
    # First scalar call: count (→ 1), second: user lookup (→ user)
    session.scalar = AsyncMock(side_effect=[1, user])

    resp = await client.get("/api/auth/status", cookies={"finlytics_session": token})

    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is True
    assert data["authenticated"] is True


async def test_status_not_authenticated_with_invalid_cookie(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=1)

    resp = await client.get(
        "/api/auth/status", cookies={"finlytics_session": "not-a-valid-jwt"}
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["initialized"] is True
    assert data["authenticated"] is False


# ── POST /api/auth/setup ──────────────────────────────────────────────────────

async def test_setup_creates_first_user(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=0)

    resp = await client.post(
        "/api/auth/setup",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "drdonoso"
    assert data["message"] == "User created successfully"
    assert "finlytics_session" in resp.cookies
    session.add.assert_called_once()
    assert session.commit.await_count == 1


async def test_setup_409_if_user_already_exists(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=1)

    resp = await client.post(
        "/api/auth/setup",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Setup already completed"


async def test_setup_422_password_too_short(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=0)

    resp = await client.post(
        "/api/auth/setup",
        json={"username": "drdonoso", "password": "short"},
    )

    assert resp.status_code == 422


async def test_setup_422_username_too_short(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=0)

    resp = await client.post(
        "/api/auth/setup",
        json={"username": "ab", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 422


async def test_setup_strips_username_whitespace(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=0)

    resp = await client.post(
        "/api/auth/setup",
        json={"username": "  drdonoso  ", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 201
    assert resp.json()["username"] == "drdonoso"


# ── POST /api/auth/login ──────────────────────────────────────────────────────

async def test_login_success_sets_cookie(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "drdonoso"
    assert data["message"] == "Login successful"
    assert "finlytics_session" in resp.cookies


async def test_login_401_wrong_password(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user(password="correct-password"))

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "wrong-password12"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_401_wrong_username(auth_client):
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    resp = await client.post(
        "/api/auth/login",
        json={"username": "nobody", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_nonexistent_user_runs_dummy_bcrypt_verify(auth_client):
    """Username not found must still call verify_password (dummy hash) — no timing short-circuit."""
    from unittest.mock import patch

    import finlytics.api.auth as _auth_mod

    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    with patch("finlytics.api.auth.verify_password") as mock_verify:
        mock_verify.return_value = False
        resp = await client.post(
            "/api/auth/login",
            json={"username": "nonexistent", "password": "SomeP@ssword1"},
        )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"
    # Dummy-verify path must have executed — no early return before bcrypt.
    mock_verify.assert_called_once_with("SomeP@ssword1", _auth_mod._DUMMY_HASH)


async def test_login_401_short_wrong_password_existing_user(auth_client):
    """A short (< 8 chars) wrong password for an existing user must return 401, NOT 422."""
    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "WRONG"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_401_nonexistent_user_short_password(auth_client):
    """A short password for a nonexistent user must return 401 (no info leak)."""
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    resp = await client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "abc"},
    )

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


async def test_login_generic_message_no_info_leak(auth_client):
    """Wrong username and wrong password return the exact same error message."""
    client, session = auth_client

    session.scalar = AsyncMock(return_value=None)
    resp_no_user = await client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": "somepassword"},
    )

    session.scalar = AsyncMock(return_value=_fake_user(password="correctpass"))
    resp_bad_pass = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "wrongpassword"},
    )

    assert (
        resp_no_user.json()["detail"]
        == resp_bad_pass.json()["detail"]
        == "Invalid credentials"
    )


# ── Remember-me flag on login ─────────────────────────────────────────────────

async def test_login_remember_true_sets_persistent_cookie(auth_client):
    """remember=True → persistent cookie (max-age present) with long-lived JWT."""
    from datetime import datetime, timezone

    from finlytics.auth.security import decode_token
    from finlytics.config import settings

    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!", "remember": True},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "finlytics_session=" in set_cookie
    assert "max-age=" in set_cookie

    token = resp.cookies.get("finlytics_session")
    assert token is not None
    payload = decode_token(token)
    assert payload is not None
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta_seconds = (exp - datetime.now(timezone.utc)).total_seconds()
    assert abs(delta_seconds - settings.auth_remember_expire_days * 24 * 3600) < 5


async def test_login_remember_true_max_age_matches_config(auth_client):
    """max-age on remember=True cookie must equal auth_remember_expire_days * 86400."""
    from finlytics.config import settings

    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!", "remember": True},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "").lower()
    expected = f"max-age={settings.auth_remember_expire_days * 24 * 3600}"
    assert expected in set_cookie


async def test_login_remember_false_sets_session_cookie(auth_client):
    """remember=False → session cookie (no max-age), JWT exp = auth_token_expire_days."""
    from datetime import datetime, timezone

    from finlytics.auth.security import decode_token
    from finlytics.config import settings

    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!", "remember": False},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "finlytics_session=" in set_cookie
    assert "max-age=" not in set_cookie

    token = resp.cookies.get("finlytics_session")
    assert token is not None
    payload = decode_token(token)
    assert payload is not None
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    delta_seconds = (exp - datetime.now(timezone.utc)).total_seconds()
    assert abs(delta_seconds - settings.auth_token_expire_days * 24 * 3600) < 5


async def test_login_no_remember_field_defaults_to_session_cookie(auth_client):
    """Omitting remember defaults to False: session cookie, no max-age."""
    client, session = auth_client
    session.scalar = AsyncMock(return_value=_fake_user())

    resp = await client.post(
        "/api/auth/login",
        json={"username": "drdonoso", "password": "MyStr0ngP@ss!"},
    )

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "").lower()
    assert "finlytics_session=" in set_cookie
    assert "max-age=" not in set_cookie


# ── POST /api/auth/logout ─────────────────────────────────────────────────────

async def test_logout_returns_200(auth_client):
    client, _ = auth_client
    resp = await client.post("/api/auth/logout")

    assert resp.status_code == 200
    assert resp.json() == {"message": "Logged out"}


async def test_logout_clears_cookie(auth_client):
    client, _ = auth_client
    resp = await client.post(
        "/api/auth/logout",
        cookies={"finlytics_session": "some-token"},
    )

    assert resp.status_code == 200
    # httpx reports the cleared cookie as an empty string or removes it
    assert resp.cookies.get("finlytics_session", "") == ""


async def test_logout_cookie_correct_flags(auth_client):
    """delete_cookie must pass httponly, samesite=lax, and path=/ — matching set_cookie."""
    client, _ = auth_client
    resp = await client.post("/api/auth/logout")

    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    cookie_lower = set_cookie.lower()
    assert "finlytics_session=" in set_cookie
    assert "httponly" in cookie_lower
    assert "samesite=lax" in cookie_lower
    assert "path=/" in cookie_lower


async def test_logout_idempotent_without_cookie(auth_client):
    """Logout works even when no cookie is present."""
    client, _ = auth_client
    resp = await client.post("/api/auth/logout")
    assert resp.status_code == 200


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

async def test_me_401_without_cookie(auth_client):
    client, session = auth_client
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_401_with_invalid_cookie(auth_client):
    client, session = auth_client
    resp = await client.get(
        "/api/auth/me", cookies={"finlytics_session": "not-a-valid-jwt"}
    )
    assert resp.status_code == 401


async def test_me_200_with_valid_cookie(auth_client):
    client, _session = auth_client
    token = create_token("drdonoso")

    # After fix: get_current_user opens its own session via async_session_factory,
    # not the get_db session. Patch the factory to return a mock auth session.
    auth_session = MagicMock()
    auth_session.scalar = AsyncMock(return_value=_fake_user())
    auth_session.__aenter__ = AsyncMock(return_value=auth_session)
    auth_session.__aexit__ = AsyncMock(return_value=False)

    with patch("finlytics.api.deps.async_session_factory", MagicMock(return_value=auth_session)):
        resp = await client.get("/api/auth/me", cookies={"finlytics_session": token})

    assert resp.status_code == 200
    assert resp.json() == {"username": "drdonoso"}


# ── Protected data endpoint behaviour ────────────────────────────────────────

async def test_data_endpoint_401_without_cookie(auth_client):
    """Any data endpoint returns 401 when no session cookie is present."""
    client, session = auth_client
    resp = await client.get("/api/accounts")
    assert resp.status_code == 401


async def test_data_endpoint_401_with_invalid_cookie(auth_client):
    client, session = auth_client
    resp = await client.get(
        "/api/accounts", cookies={"finlytics_session": "garbage"}
    )
    assert resp.status_code == 401


async def test_data_endpoint_200_with_valid_cookie(auth_client):
    """A data endpoint is reachable with a valid session cookie."""
    client, _session = auth_client
    token = create_token("drdonoso")

    auth_session = MagicMock()
    auth_session.scalar = AsyncMock(return_value=_fake_user())
    auth_session.__aenter__ = AsyncMock(return_value=auth_session)
    auth_session.__aexit__ = AsyncMock(return_value=False)

    with patch("finlytics.api.deps.async_session_factory", MagicMock(return_value=auth_session)):
        with patch("finlytics.db.queries.get_accounts", new_callable=AsyncMock) as mock_q:
            mock_q.return_value = []
            resp = await client.get(
                "/api/accounts", cookies={"finlytics_session": token}
            )

    assert resp.status_code == 200


# ── POST /api/auth/login — attempt rate limit ─────────────────────────────────
#
# The endpoint accepted unlimited attempts, so brute-forcing passwords was only
# limited by bandwidth. The counter is per-IP, not per-user: a per-user counter
# would let anyone lock out someone else's account.

async def test_login_429_after_too_many_failures(auth_client):
    """Once the attempt quota is exhausted, the endpoint returns 429 instead of 401."""
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)   # usuario inexistente → 401

    limit = login_rate_limiter.max_attempts
    for _ in range(limit):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "attacker", "password": "guess-attempt-1"},
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/api/auth/login",
        json={"username": "attacker", "password": "guess-attempt-2"},
    )

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    assert int(resp.headers["Retry-After"]) >= 1


async def test_login_429_does_not_leak_whether_the_user_exists(auth_client):
    """The 429 is returned before hitting the database.

    If the limit were checked after the query, response timing would still
    reveal whether the user exists despite the block.
    """
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    for _ in range(login_rate_limiter.max_attempts):
        await client.post(
            "/api/auth/login", json={"username": "attacker", "password": "whatever12"}
        )

    session.scalar.reset_mock()
    resp = await client.post(
        "/api/auth/login", json={"username": "drdonoso", "password": "MyStr0ngP@ss!"}
    )

    assert resp.status_code == 429
    session.scalar.assert_not_called()


async def test_successful_login_clears_the_counter(auth_client):
    """Failing then succeeding leaves no residual penalty."""
    client, session = auth_client

    # A few failures, still under the limit.
    session.scalar = AsyncMock(return_value=None)
    for _ in range(login_rate_limiter.max_attempts - 1):
        await client.post(
            "/api/auth/login", json={"username": "drdonoso", "password": "wrong-one-12"}
        )

    # Correct credentials.
    session.scalar = AsyncMock(return_value=_fake_user())
    ok = await client.post(
        "/api/auth/login", json={"username": "drdonoso", "password": "MyStr0ngP@ss!"}
    )
    assert ok.status_code == 200

    # Quota is fully restored: the next failure is 401, not 429.
    session.scalar = AsyncMock(return_value=None)
    after = await client.post(
        "/api/auth/login", json={"username": "drdonoso", "password": "wrong-two-12"}
    )
    assert after.status_code == 401


async def test_login_limit_can_be_disabled(auth_client, monkeypatch):
    """AUTH_LOGIN_MAX_ATTEMPTS=0 disables the limit entirely."""
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    monkeypatch.setattr(login_rate_limiter, "max_attempts", 0)

    for _ in range(25):
        resp = await client.post(
            "/api/auth/login", json={"username": "anyone", "password": "attempt-1234"}
        )
        assert resp.status_code == 401


async def test_forged_forwarded_header_does_not_bypass_the_limit(auth_client):
    """Varying X-Forwarded-For must not grant fresh attempts.

    This is why the IP is read from the connection: if the header were trusted,
    an attacker could change it on every request, never exhaust the quota, and
    render the limit worthless.
    """
    client, session = auth_client
    session.scalar = AsyncMock(return_value=None)

    for i in range(login_rate_limiter.max_attempts):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "attacker", "password": "guess-attempt"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/api/auth/login",
        json={"username": "attacker", "password": "guess-attempt"},
        headers={"X-Forwarded-For": "10.0.0.250"},
    )

    assert resp.status_code == 429
