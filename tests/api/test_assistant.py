"""API tests for the finance assistant router.

The SSE endpoint is the interesting one: everything checkable up front must
still produce a real HTTP status, because once the stream opens a status code is
no longer available.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api import assistant as assistant_api
from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.assistant.service import AnswerDelta, Completed, Failed, ToolStarted


NOW = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)


def make_conversation(conv_id: int = 1, title: str = "Spending") -> MagicMock:
    conversation = MagicMock()
    conversation.id = conv_id
    conversation.title = title
    conversation.created_at = NOW
    conversation.updated_at = NOW
    return conversation


def make_message(msg_id: int, role: str, content: str, tool_calls=None) -> MagicMock:
    message = MagicMock()
    message.id = msg_id
    message.role = role
    message.content = content
    message.tool_calls = tool_calls
    message.created_at = NOW
    return message


def scalars_returning(items):
    """Build the ``execute()`` result shape used by the router."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


@pytest.fixture(autouse=True)
def _reset_limiter():
    assistant_api._message_limiter.clear()
    yield
    assistant_api._message_limiter.clear()


@pytest.fixture
def enabled():
    """Report the assistant as configured without needing real credentials."""
    with patch.object(assistant_api, "is_llm_configured", return_value=True):
        yield


@pytest.fixture
async def client(mock_session):
    async def _override_get_db():
        yield mock_session

    async def _override_get_current_user():
        return MagicMock(username="testuser", id=1)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


class TestStatus:
    async def test_enabled_when_llm_is_configured(self, client, enabled):
        resp = await client.get("/api/assistant/status")
        assert resp.status_code == 200
        assert resp.json() == {"enabled": True, "reason": None}

    async def test_disabled_when_llm_is_not_configured(self, client):
        with patch.object(assistant_api, "is_llm_configured", return_value=False):
            resp = await client.get("/api/assistant/status")
        body = resp.json()
        # The UI hides the launcher on this, which beats a chat whose first
        # message is a 503.
        assert body["enabled"] is False
        assert "OPENAI_API_KEY" in body["reason"]

    async def test_disabled_by_setting(self, client, enabled):
        with patch.object(assistant_api.settings, "assistant_enabled", False):
            resp = await client.get("/api/assistant/status")
        assert resp.json()["enabled"] is False


class TestSuggestions:
    async def test_returns_i18n_keys_not_prose(self, client):
        resp = await client.get("/api/assistant/suggestions")
        assert resp.status_code == 200
        suggestions = resp.json()["suggestions"]
        assert suggestions
        assert all(s.startswith("assistant.suggestion.") for s in suggestions)


class TestConversationCrud:
    async def test_list_returns_the_users_threads(self, client, mock_session):
        mock_session.execute.return_value = scalars_returning([make_conversation()])
        resp = await client.get("/api/assistant/conversations")
        assert resp.status_code == 200
        assert resp.json()[0]["title"] == "Spending"

    async def test_create_returns_201(self, client, mock_session, enabled):
        mock_session.scalar = AsyncMock(return_value=0)

        async def _refresh(obj):
            obj.id = 42
            obj.created_at = NOW
            obj.updated_at = NOW

        mock_session.refresh = AsyncMock(side_effect=_refresh)
        resp = await client.post("/api/assistant/conversations")
        assert resp.status_code == 201
        assert resp.json()["id"] == 42

    async def test_create_is_refused_when_the_llm_is_absent(self, client):
        with patch.object(assistant_api, "is_llm_configured", return_value=False):
            resp = await client.post("/api/assistant/conversations")
        assert resp.status_code == 503

    async def test_create_is_capped(self, client, mock_session, enabled):
        mock_session.scalar = AsyncMock(
            return_value=assistant_api.settings.assistant_max_conversations
        )
        resp = await client.post("/api/assistant/conversations")
        assert resp.status_code == 409

    async def test_get_returns_the_message_history(self, client, mock_session):
        conversation = make_conversation()
        messages = [
            make_message(1, "user", "How much?"),
            make_message(2, "assistant", "320,50 €.",
                         [{"name": "get_spending_summary", "arguments": "{}", "ok": True}]),
        ]
        mock_session.scalar = AsyncMock(return_value=conversation)
        mock_session.execute.return_value = scalars_returning(messages)

        resp = await client.get("/api/assistant/conversations/1")
        body = resp.json()
        assert resp.status_code == 200
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        assert body["messages"][1]["tool_calls"][0]["name"] == "get_spending_summary"

    async def test_another_users_thread_is_404_not_403(self, client, mock_session):
        # A 403 would confirm the id exists.
        mock_session.scalar = AsyncMock(return_value=None)
        resp = await client.get("/api/assistant/conversations/999")
        assert resp.status_code == 404

    async def test_delete_returns_204(self, client, mock_session):
        mock_session.scalar = AsyncMock(return_value=make_conversation())
        resp = await client.delete("/api/assistant/conversations/1")
        assert resp.status_code == 204

    async def test_delete_of_a_missing_thread_is_404(self, client, mock_session):
        mock_session.scalar = AsyncMock(return_value=None)
        resp = await client.delete("/api/assistant/conversations/999")
        assert resp.status_code == 404


class TestSendMessageGuards:
    async def test_503_when_the_llm_is_absent(self, client):
        with patch.object(assistant_api, "is_llm_configured", return_value=False):
            resp = await client.post(
                "/api/assistant/conversations/1/messages", json={"content": "hi"}
            )
        assert resp.status_code == 503

    async def test_empty_message_is_rejected(self, client, enabled):
        resp = await client.post(
            "/api/assistant/conversations/1/messages", json={"content": "   "}
        )
        assert resp.status_code == 422

    async def test_oversized_message_is_rejected(self, client, enabled):
        resp = await client.post(
            "/api/assistant/conversations/1/messages",
            json={"content": "x" * (assistant_api.settings.assistant_max_message_chars + 1)},
        )
        assert resp.status_code == 413

    async def test_rate_limit_returns_429_with_retry_after(self, client, mock_session, enabled):
        mock_session.scalar = AsyncMock(return_value=None)  # 404s after the limiter
        with patch.object(assistant_api.settings, "assistant_rate_limit_messages", 2):
            limiter = assistant_api.RateLimiter(max_attempts=1, window_seconds=60)
            with patch.object(assistant_api, "_message_limiter", limiter):
                first = await client.post(
                    "/api/assistant/conversations/1/messages", json={"content": "hi"}
                )
                second = await client.post(
                    "/api/assistant/conversations/1/messages", json={"content": "hi"}
                )

        assert first.status_code == 404  # quota consumed, then the thread lookup failed
        assert second.status_code == 429
        assert second.headers["Retry-After"]

    async def test_unknown_thread_is_404(self, client, mock_session, enabled):
        mock_session.scalar = AsyncMock(return_value=None)
        resp = await client.post(
            "/api/assistant/conversations/999/messages", json={"content": "hi"}
        )
        assert resp.status_code == 404


class TestSendMessageStream:
    @pytest.fixture
    def ready(self, client, mock_session, enabled):
        """A client whose conversation lookup and history read both succeed.

        ``from_settings`` is stubbed because the real one builds an AsyncOpenAI,
        which refuses to construct without credentials — the router only reaches
        it behind ``is_llm_configured``, which these tests force true.
        """
        mock_session.scalar = AsyncMock(return_value=make_conversation(title=""))
        mock_session.execute.return_value = scalars_returning([])
        with patch.object(assistant_api.LLMClient, "from_settings", MagicMock()):
            yield client

    async def test_events_are_framed_as_sse(self, ready, mock_session):
        async def fake_turn(**kwargs):
            yield ToolStarted(name="get_spending_summary", label="Calculating totals")
            yield AnswerDelta("You spent ")
            yield AnswerDelta("320,50 €.")
            yield Completed(answer="You spent 320,50 €.", tool_calls=[])

        async def _refresh(obj):
            obj.id = 7

        mock_session.refresh = AsyncMock(side_effect=_refresh)

        with patch.object(assistant_api, "run_turn", fake_turn), patch.object(
            assistant_api, "async_session_factory",
            MagicMock(return_value=_session_cm(mock_session)),
        ):
            resp = await ready.post(
                "/api/assistant/conversations/1/messages", json={"content": "How much?"}
            )
            body = resp.text

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # nginx would otherwise buffer the whole stream into one lump.
        assert resp.headers["x-accel-buffering"] == "no"
        assert "event: tool" in body
        assert '"label": "Calculating totals"' in body
        assert 'event: token' in body
        assert '"text": "You spent "' in body
        assert "event: done" in body
        assert '"message_id": 7' in body

    async def test_failure_arrives_as_an_error_event(self, ready, mock_session):
        async def fake_turn(**kwargs):
            yield Failed("upstream is down")

        with patch.object(assistant_api, "run_turn", fake_turn), patch.object(
            assistant_api, "async_session_factory",
            MagicMock(return_value=_session_cm(mock_session)),
        ):
            resp = await ready.post(
                "/api/assistant/conversations/1/messages", json={"content": "How much?"}
            )

        # The response already started, so this cannot be an HTTP status.
        assert resp.status_code == 200
        assert "event: error" in resp.text
        assert "upstream is down" in resp.text

    async def test_an_unexpected_crash_does_not_leak_its_message(
        self, ready, mock_session, caplog
    ):
        async def fake_turn(**kwargs):
            raise RuntimeError("password=hunter2 host=db:5432")
            yield  # pragma: no cover — makes this an async generator

        with patch.object(assistant_api, "run_turn", fake_turn), patch.object(
            assistant_api, "async_session_factory",
            MagicMock(return_value=_session_cm(mock_session)),
        ):
            resp = await ready.post(
                "/api/assistant/conversations/1/messages", json={"content": "How much?"}
            )

        # This frame is rendered verbatim in the browser; an exception's text can
        # carry connection strings, file paths and SQL.
        assert "event: error" in resp.text
        assert "hunter2" not in resp.text
        assert "db:5432" not in resp.text
        assert "hunter2" in caplog.text

    async def test_the_question_is_stored_before_streaming(self, ready, mock_session):
        async def fake_turn(**kwargs):
            yield Failed("boom")

        with patch.object(assistant_api, "run_turn", fake_turn), patch.object(
            assistant_api, "async_session_factory",
            MagicMock(return_value=_session_cm(mock_session)),
        ):
            await ready.post(
                "/api/assistant/conversations/1/messages", json={"content": "How much?"}
            )

        # A model that dies halfway must not leave the user with an empty thread.
        stored = [c.args[0] for c in mock_session.add.call_args_list]
        assert any(getattr(m, "role", None) == "user" for m in stored)


class TestTitleDerivation:
    def test_short_question_becomes_the_title(self):
        assert assistant_api._derive_title("  How much did I spend?  ") == "How much did I spend?"

    def test_long_question_is_truncated(self):
        title = assistant_api._derive_title("x" * 200)
        assert len(title) <= assistant_api._TITLE_CHARS
        assert title.endswith("…")

    def test_whitespace_is_collapsed(self):
        assert assistant_api._derive_title("a\n\n  b") == "a b"


class TestTransactionDiscipline:
    """SQLAlchemy autobegins on the first SELECT, and refuses a nested begin().

    The shared ``mock_session`` fixture cannot catch this: its ``begin()`` is an
    AsyncMock that accepts any call order. So these tests swap in a double that
    enforces the real rule — a read-then-``begin()`` endpoint raised
    ``InvalidRequestError`` in production while every mocked test passed.
    """

    @pytest.fixture
    def strict_session(self):
        return StrictSession()

    @pytest.fixture
    async def strict_client(self, strict_session):
        async def _override_get_db():
            yield strict_session

        async def _override_get_current_user():
            return MagicMock(username="testuser", id=1)

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_get_current_user
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    async def test_create_does_not_nest_transactions(self, strict_client, strict_session, enabled):
        strict_session.scalar_result = 0
        resp = await strict_client.post("/api/assistant/conversations")
        assert resp.status_code == 201

    async def test_delete_does_not_nest_transactions(self, strict_client, strict_session):
        strict_session.scalar_result = make_conversation()
        resp = await strict_client.delete("/api/assistant/conversations/1")
        assert resp.status_code == 204

    async def test_send_message_does_not_nest_transactions(
        self, strict_client, strict_session, enabled
    ):
        strict_session.scalar_result = make_conversation(title="")

        async def fake_turn(**kwargs):
            yield Failed("stopped here — the transaction path is what is under test")

        with patch.object(assistant_api, "run_turn", fake_turn), \
             patch.object(assistant_api.LLMClient, "from_settings", MagicMock()), \
             patch.object(
                 assistant_api, "async_session_factory",
                 MagicMock(return_value=_session_cm(strict_session)),
             ):
            resp = await strict_client.post(
                "/api/assistant/conversations/1/messages", json={"content": "hi"}
            )

        assert resp.status_code == 200
        assert "event: error" in resp.text


class StrictSession:
    """Session double that reproduces SQLAlchemy's autobegin rule.

    Any ``execute``/``scalar`` starts a transaction, and ``begin()`` raises while
    one is open — which is precisely what a MagicMock will happily let you do,
    and why this bug reached production.

    Return values are set through ``scalar_result`` / ``execute_result`` rather
    than by reassigning the methods, so a test cannot accidentally disable the
    autobegin tracking the way replacing ``session.scalar`` with a bare AsyncMock
    would.
    """

    def __init__(self):
        self.in_transaction = False
        self.scalar_result = None
        self.execute_result = scalars_returning([])
        self.added: list = []

    def _autobegin(self) -> None:
        self.in_transaction = True

    async def execute(self, *_args, **_kwargs):
        self._autobegin()
        return self.execute_result

    async def scalar(self, *_args, **_kwargs):
        self._autobegin()
        return self.scalar_result

    def begin(self):
        if self.in_transaction:
            raise AssertionError(
                "A transaction is already begun on this Session — the endpoint "
                "read before opening begin(); SQLAlchemy raises InvalidRequestError here."
            )
        self.in_transaction = True
        return _StrictTransaction(self)

    async def commit(self):
        self.in_transaction = False

    async def rollback(self):
        self.in_transaction = False

    async def refresh(self, obj, *_args, **_kwargs):
        # Stand in for the server defaults a real refresh would populate.
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "created_at", None) is None:
            obj.created_at = NOW
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = NOW

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def close(self):
        pass


class _StrictTransaction:
    def __init__(self, session: StrictSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc):
        self._session.in_transaction = False
        return False


def _session_cm(session):
    """Wrap a mock session so ``async with async_session_factory()`` works."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm
