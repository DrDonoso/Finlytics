"""Stand-ins for the push notification tests: a browser that subscribes (its keys, and reading
the messages it receives as it would) and a push service that records what is sent to it."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from finlytics.notifications.webpush import b64encode, hkdf, public_bytes


@dataclass
class Browser:
    endpoint: str = "https://web.push.apple.com/QGuQyavXutnMH-device-1"
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    secret: bytes = field(default_factory=lambda: os.urandom(16))

    def subscription(self, **changes: Any) -> dict[str, Any]:
        """The body of ``PUT /api/push/subscription`` for this browser."""
        return {
            "endpoint": self.endpoint,
            "keys": {"p256dh": b64encode(public_bytes(self.key)), "auth": b64encode(self.secret)},
            "locale": "es",
            **changes,
        }

    def read(self, body: bytes) -> Any:
        """Decrypt a push message as the browser does (RFC 8291), checking its framing."""
        salt, record_size, key_length = body[:16], int.from_bytes(body[16:20]), body[20]
        sender = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), body[21 : 21 + key_length]
        )
        key_info = b"WebPush: info\x00" + public_bytes(self.key) + body[21 : 21 + key_length]
        keying = hkdf(self.secret, self.key.exchange(ec.ECDH(), sender), key_info, 32)
        content_key = hkdf(salt, keying, b"Content-Encoding: aes128gcm\x00", 16)
        nonce = hkdf(salt, keying, b"Content-Encoding: nonce\x00", 12)
        record = AESGCM(content_key).decrypt(nonce, body[21 + key_length :], None)
        assert record_size == 4096 and record.endswith(b"\x02")
        return json.loads(record[:-1])


class PushService:
    """Stands in for every push service (``httpx.MockTransport``): records the requests and
    answers ``status``, or fails to connect while it is None."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status: int | None = 201

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status is None:
            raise httpx.ConnectError("unreachable", request=request)
        if self.status >= 400:
            return httpx.Response(self.status, json={"reason": "TestRefusal"})
        return httpx.Response(self.status)

    def messages(self, browser: Browser) -> list[Any]:
        """What ``browser`` received, decrypted, oldest first."""
        return [
            browser.read(request.content)
            for request in self.requests
            if str(request.url) == browser.endpoint
        ]
