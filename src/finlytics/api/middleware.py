"""HTTP middlewares: security headers and a per-request id.

Both are pure ASGI. ``BaseHTTPMiddleware`` pipes the response body through a
memory stream, which would hold back the assistant's server-sent events.
"""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Styles need 'unsafe-inline' because Recharts and React's `style` prop write
# style attributes. Scripts do not: the theme bootstrap is /theme-init.js, not an
# inline block, precisely so this policy needs no script exception.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "manifest-src 'self'; "
    "worker-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# No Strict-Transport-Security: the app is often reached over plain HTTP on a
# LAN, and HSTS belongs to whichever proxy terminates TLS.
SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("content-security-policy", CONTENT_SECURITY_POLICY),
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "strict-origin-when-cross-origin"),
    ("permissions-policy", "camera=(), microphone=(), geolocation=()"),
)

_ENCODED_HEADERS = tuple(
    (name.encode("latin-1"), value.encode("latin-1")) for name, value in SECURITY_HEADERS
)
_CSP_NAME = b"content-security-policy"
# Swagger UI and ReDoc load their bundles from a CDN and run an inline script,
# so the policy would leave them blank.
_CSP_EXEMPT_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})


class SecurityHeadersMiddleware:
    """Adds the security headers to every HTTP response that does not set its own."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        skip_csp = scope.get("path") in _CSP_EXEMPT_PATHS

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {name.lower() for name, _ in headers}
                for name, value in _ENCODED_HEADERS:
                    if name in present or (skip_csp and name == _CSP_NAME):
                        continue
                    headers.append((name, value))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

_REQUEST_ID_HEADER = b"x-request-id"
# The id is echoed into the logs and the response, so only a short token is
# accepted from the client: anything else could forge log lines.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == _REQUEST_ID_HEADER:
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.fullmatch(candidate) else None
    return None


class RequestIdMiddleware:
    """Tags each request with an id, exposed to logging and returned as X-Request-ID.

    A well-formed id sent by a reverse proxy is reused, so its logs and ours share it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        encoded = request_id.encode("latin-1")

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, encoded))
                message = {**message, "headers": headers}
            await send(message)

        token = request_id_var.set(request_id)
        await self.app(scope, receive, send_with_id)
        # Not in a `finally`: when an exception escapes, the server logs its
        # traceback after this frame unwinds, and that is the line most worth
        # tagging. Each request runs in its own task, so the value cannot leak.
        request_id_var.reset(token)


class RequestIdFilter(logging.Filter):
    """Gives every log record the ``request_id`` attribute the formatters print."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
