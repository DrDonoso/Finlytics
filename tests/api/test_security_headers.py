"""Tests for the security-header and request-id middlewares.

Verifies:
  * Every response carries the security headers, the SPA shell included.
  * The interactive API docs keep their headers but skip the CSP, which would block them.
  * A header the route already set is preserved, never duplicated.
  * Streaming responses still stream through both middlewares.
  * The request id is generated, or echoed when the client's is well-formed.
  * The id is visible to handlers and to log records, and never leaks past the request.
  * The uvicorn log config tags every line with the request id.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from uvicorn.config import LOGGING_CONFIG

from finlytics.__main__ import _log_config
from finlytics.api.middleware import (
    SECURITY_HEADERS,
    RequestIdFilter,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    request_id_var,
)
from finlytics.app import app

_HEX_ID = re.compile(r"[0-9a-f]{32}")


def _client(asgi_app: ASGIApp) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=asgi_app), base_url="http://test")


async def _framed(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"X-Frame-Options": "SAMEORIGIN"})


async def _app_sets_request_id(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok", headers={"X-Request-ID": "from-the-app"})


async def _echo_request_id(_request: Request) -> PlainTextResponse:
    return PlainTextResponse(request_id_var.get())


async def _stream(_request: Request) -> StreamingResponse:
    async def chunks() -> AsyncIterator[str]:
        for chunk in ("a", "b", "c"):
            yield chunk

    return StreamingResponse(chunks(), media_type="text/plain")


_mini = Starlette(
    routes=[
        Route("/framed", _framed),
        Route("/app-id", _app_sets_request_id),
        Route("/echo-id", _echo_request_id),
        Route("/stream", _stream),
    ]
)


# ── Security headers ─────────────────────────────────────────────────────────


async def test_api_responses_carry_every_security_header() -> None:
    """A plain API response carries the full header set."""
    async with _client(app) as c:
        r = await c.get("/health")

    assert r.status_code == 200
    for name, value in SECURITY_HEADERS:
        assert r.headers.get_list(name) == [value]


async def test_spa_shell_carries_every_security_header(tmp_path: Path) -> None:
    """The HTML shell is the response the CSP actually protects."""
    (tmp_path / "index.html").write_text("<!doctype html><title>Finlytics</title>")

    with patch("finlytics.app._SPA_DIR", tmp_path):
        async with _client(app) as c:
            r = await c.get("/settings")

    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    for name, value in SECURITY_HEADERS:
        assert r.headers.get_list(name) == [value]


async def test_unhandled_errors_keep_security_headers_and_request_id() -> None:
    with patch("finlytics.app._SPA_DIR") as directory:
        directory.is_dir.side_effect = RuntimeError("private failure details")
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.get("/failed-page", headers={"X-Request-ID": "error-123"})

    assert response.status_code == 500
    assert "private failure details" not in response.text
    for name, value in SECURITY_HEADERS:
        assert response.headers.get_list(name) == [value]
    assert response.headers.get_list("x-request-id") == ["error-123"]


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
async def test_api_docs_skip_only_the_csp(path: str) -> None:
    """Swagger UI and ReDoc load their assets from a CDN, which the CSP would block."""
    async with _client(app) as c:
        r = await c.get(path)

    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


async def test_header_set_by_the_route_is_preserved() -> None:
    """The middleware fills gaps; it never overrides or duplicates a route's own header."""
    async with _client(SecurityHeadersMiddleware(_mini)) as c:
        r = await c.get("/framed")

    assert r.headers.get_list("x-frame-options") == ["SAMEORIGIN"]
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_streaming_response_passes_through_both_middlewares() -> None:
    """The assistant streams over SSE, so neither middleware may buffer the body."""
    async with _client(RequestIdMiddleware(SecurityHeadersMiddleware(_mini))) as c:
        r = await c.get("/stream")

    assert r.text == "abc"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert _HEX_ID.fullmatch(r.headers["x-request-id"])


@pytest.mark.parametrize("middleware", [SecurityHeadersMiddleware, RequestIdMiddleware])
async def test_non_http_scopes_pass_through(middleware: type) -> None:
    """Lifespan events reach the app untouched."""
    seen: list[Scope] = []

    async def stub(scope: Scope, _receive: Receive, _send: Send) -> None:
        seen.append(scope)

    async def receive() -> Message:
        return {"type": "lifespan.startup"}

    async def send(_message: Message) -> None:
        return None

    scope: Scope = {"type": "lifespan"}
    await middleware(stub)(scope, receive, send)

    assert seen == [scope]


# ── Request id ───────────────────────────────────────────────────────────────


async def test_request_id_is_generated_when_absent() -> None:
    """Every response carries an id, even when the client sent none."""
    async with _client(app) as c:
        r = await c.get("/health")

    assert _HEX_ID.fullmatch(r.headers["x-request-id"])


async def test_well_formed_incoming_request_id_is_echoed() -> None:
    """A proxy's id is kept, so its logs and ours line up."""
    async with _client(app) as c:
        r = await c.get("/health", headers={"X-Request-ID": "proxy-abc.123_X"})

    assert r.headers["x-request-id"] == "proxy-abc.123_X"


@pytest.mark.parametrize("incoming", ["with space", "a" * 65, "semi;colon", ""])
async def test_malformed_incoming_request_id_is_replaced(incoming: str) -> None:
    """A client cannot inject arbitrary text into the log lines."""
    async with _client(app) as c:
        r = await c.get("/health", headers={"X-Request-ID": incoming})

    assert _HEX_ID.fullmatch(r.headers["x-request-id"])


async def test_request_id_set_by_the_app_is_replaced() -> None:
    """The response carries exactly one id: the one the log lines were tagged with."""
    async with _client(RequestIdMiddleware(_mini)) as c:
        r = await c.get("/app-id", headers={"X-Request-ID": "client-1"})

    assert r.headers.get_list("x-request-id") == ["client-1"]


async def test_handler_sees_the_request_id_and_it_does_not_leak() -> None:
    """The id is bound for the request and unbound afterwards."""
    async with _client(RequestIdMiddleware(_mini)) as c:
        r = await c.get("/echo-id", headers={"X-Request-ID": "trace-1"})

    assert r.text == "trace-1"
    assert request_id_var.get() == "-"


# ── Logging ──────────────────────────────────────────────────────────────────


def _record() -> logging.LogRecord:
    return logging.LogRecord("finlytics.test", logging.INFO, __file__, 1, "msg", None, None)


def test_filter_tags_records_outside_a_request_with_a_dash() -> None:
    """Startup and background-task lines still format."""
    record = _record()

    assert RequestIdFilter().filter(record)
    assert record.request_id == "-"


def test_filter_tags_records_with_the_current_request_id() -> None:
    """A line logged while a request is in flight carries its id."""
    token = request_id_var.set("abc")
    try:
        record = _record()
        RequestIdFilter().filter(record)
    finally:
        request_id_var.reset(token)

    assert record.request_id == "abc"


def test_log_config_adds_the_request_id_without_mutating_uvicorns() -> None:
    """Both handlers are filtered and the application's own loggers reach them."""
    config = _log_config()

    assert config["filters"]["request_id"]["()"] is RequestIdFilter
    for name in ("default", "access"):
        assert config["formatters"][name]["fmt"].startswith("%(asctime)s [%(request_id)s] ")
        assert config["handlers"][name]["filters"] == ["request_id"]
    assert config["loggers"][""] == {"handlers": ["default"], "level": "INFO"}

    assert "filters" not in LOGGING_CONFIG
    assert "request_id" not in LOGGING_CONFIG["formatters"]["default"]["fmt"]
    assert "" not in LOGGING_CONFIG["loggers"]


def test_log_config_formats_application_records() -> None:
    """Applied for real, an application warning is printed with its id slot.

    Runs in a subprocess: dictConfig replaces the process-wide logging setup,
    which would break pytest's log capture for every later test.
    """
    code = (
        "import logging, logging.config\n"
        "from finlytics.__main__ import _log_config\n"
        "logging.config.dictConfig(_log_config())\n"
        "logging.getLogger('finlytics.probe').warning('probe-message')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "[-] " in result.stderr
    assert "probe-message" in result.stderr
