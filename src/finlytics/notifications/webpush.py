"""Web Push (RFC 8030): alerts sent to a browser through its push service.

Each message is encrypted for the browser that subscribed (RFC 8291, ``aes128gcm``) and signed
with the server's VAPID key (RFC 8292). That key is derived from ``AUTH_SECRET``, so it needs no
setting of its own; rotating the secret replaces it, and every device subscribes again the next
time Finlytics is opened there.

Only the push services of the major browsers are contacted (``PUSH_SERVICES``): a subscription is
an address its browser chose, and the server must never be made to send requests anywhere else.
Those addresses are never logged, only their push service.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

log = logging.getLogger(__name__)

PUSH_SERVICES = (
    "fcm.googleapis.com",  # Chrome, Edge on Android, Samsung Internet, Opera, Brave
    "push.apple.com",  # Safari, and the apps added to the Home Screen of an iPhone or iPad
    "push.services.mozilla.com",  # Firefox
    "notify.windows.com",  # Edge on Windows
)
MAX_ENDPOINT_LENGTH = 2048
# The order of the P-256 group.
P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
VAPID_INFO = b"Finlytics Web Push VAPID key (P-256)"
# Push services accept signed tokens valid for up to 24 hours.
VAPID_SECONDS = 12 * 3600
RECORD_SIZE = 4096
# Push services accept 4096 bytes: the 86-byte header, the message, its delimiter and the tag.
MAX_MESSAGE_BYTES = RECORD_SIZE - 86 - 1 - 16
TIMEOUT_SECONDS = 15.0

Urgency = Literal["very-low", "low", "normal", "high"]
# delivered: accepted by the push service · gone: the subscription no longer exists (forget it) ·
# retry: the push service or the network failed for now · rejected: refused (bad request, wrong
# key or token…), sending it again would change nothing.
Outcome = Literal["delivered", "gone", "retry", "rejected"]

# Tests replace it so that nothing reaches a real push service.
TRANSPORT: httpx.AsyncBaseTransport | None = None


def b64encode(data: bytes) -> str:
    """URL-safe base64 without padding, as browsers give and expect push keys."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64decode(text: str) -> bytes:
    """Decode URL-safe base64, with or without padding; ValueError if malformed."""
    if not text.isascii() or not text.strip("=").replace("-", "").replace("_", "").isalnum():
        raise ValueError("Expected URL-safe base64")
    data = text.rstrip("=")
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def browser_key(text: str) -> bytes:
    """The browser's public key (``p256dh``): an uncompressed point of P-256; ValueError if not."""
    data = b64decode(text)
    if len(data) != 65 or data[0] != 4:
        raise ValueError("Expected an uncompressed P-256 point")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), data)
    return data


def browser_auth(text: str) -> bytes:
    """The browser's authentication secret (``auth``): 16 bytes; ValueError if not."""
    data = b64decode(text)
    if len(data) != 16:
        raise ValueError("Expected 16 bytes")
    return data


def push_service(endpoint: str) -> str | None:
    """Host name of the subscription address when it is an HTTPS address of a known push
    service (``PUSH_SERVICES``), else None."""
    if len(endpoint) > MAX_ENDPOINT_LENGTH or not endpoint.isascii():
        return None
    try:
        parts = urlsplit(endpoint)
        port = parts.port
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if (
        parts.scheme != "https"
        or port not in {None, 443}
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or any(character.isspace() for character in endpoint)
    ):
        return None
    if any(host == service or host.endswith("." + service) for service in PUSH_SERVICES):
        return host
    return None


def vapid_key(secret: str) -> ec.EllipticCurvePrivateKey:
    """The server's VAPID key, derived from ``AUTH_SECRET``: 384 bits from HKDF reduced into the
    valid range of private keys (FIPS 186-5 A.2.1, "extra random bits")."""
    seed = HKDF(algorithm=hashes.SHA256(), length=48, salt=None, info=VAPID_INFO).derive(
        secret.encode()
    )
    return ec.derive_private_key(int.from_bytes(seed, "big") % (P256_ORDER - 1) + 1, ec.SECP256R1())


def public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def hkdf(salt: bytes, secret: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(secret)


def encrypt(
    message: bytes,
    receiver_public: bytes,
    receiver_auth: bytes,
    *,
    sender: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """The ``aes128gcm`` body of a push message for one browser (RFC 8291): a header with the salt
    and a new ECDH key of the server's, then the message encrypted as a single record.
    ``sender``/``salt`` are random unless given (tests use the RFC's example)."""
    if len(message) > MAX_MESSAGE_BYTES:
        raise ValueError("Push message too large")
    sender = sender or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    receiver = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), receiver_public)
    shared = sender.exchange(ec.ECDH(), receiver)
    sender_public = public_bytes(sender)
    key_info = b"WebPush: info\x00" + receiver_public + sender_public
    keying = hkdf(receiver_auth, shared, key_info, 32)
    content_key = hkdf(salt, keying, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, keying, b"Content-Encoding: nonce\x00", 12)
    # 0x02: the delimiter of the last (and only) record, without padding.
    ciphertext = AESGCM(content_key).encrypt(nonce, message + b"\x02", None)
    header = salt + struct.pack("!IB", RECORD_SIZE, len(sender_public)) + sender_public
    return header + ciphertext


@dataclass(frozen=True)
class Subscription:
    """Where a browser receives push messages and the keys to encrypt them (as it gives them)."""

    endpoint: str
    p256dh: str
    auth: str


def outcome(status: int) -> Outcome:
    if 200 <= status < 300:
        return "delivered"
    if status in {404, 410}:
        return "gone"
    if status in {408, 429} or status >= 500:
        return "retry"
    return "rejected"


def refusal(response: httpx.Response) -> str:
    """The reason a push service gave for refusing a message (Apple and Mozilla answer
    ``{"reason": ...}`` or ``{"errno": ...}``), never the rest of its answer."""
    try:
        body = response.json()
    except ValueError:
        return "-"
    if isinstance(body, dict):
        for key in ("reason", "errno"):
            value = body.get(key)
            if isinstance(value, str | int) and len(str(value)) <= 64:
                return str(value)
    return "-"


class WebPush:
    """Sends push messages, signed with the VAPID key derived from ``secret``, through one HTTP
    client."""

    def __init__(self, secret: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.key = vapid_key(secret)
        # The applicationServerKey browsers subscribe with.
        self.public_key = b64encode(public_bytes(self.key))
        self.client = httpx.AsyncClient(
            transport=transport or TRANSPORT, timeout=TIMEOUT_SECONDS, follow_redirects=False
        )

    async def close(self) -> None:
        await self.client.aclose()

    def authorization(self, endpoint: str, subject: str, now: float | None = None) -> str:
        """``Authorization`` header for the push service of ``endpoint`` (RFC 8292). ``subject``
        tells the push service who sends: the origin the device uses Finlytics from."""
        parts = urlsplit(endpoint)
        claims = {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int(now if now is not None else time.time()) + VAPID_SECONDS,
            "sub": subject,
        }
        token = jwt.encode(claims, self.key, algorithm="ES256", headers={"typ": "JWT"})
        return f"vapid t={token}, k={self.public_key}"

    async def send(
        self,
        subscription: Subscription,
        message: dict[str, Any],
        *,
        subject: str,
        ttl: int,
        urgency: Urgency = "normal",
        topic: str | None = None,
    ) -> Outcome:
        """Send ``message`` (JSON) to one browser. ``ttl``: seconds the push service keeps it while
        the device is unreachable; ``topic``: a newer message with the same one replaces it there."""
        service = push_service(subscription.endpoint)
        if service is None:
            return "gone"
        try:
            body = encrypt(
                json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(),
                browser_key(subscription.p256dh),
                browser_auth(subscription.auth),
            )
        except ValueError:
            log.warning("Push message not sent to %s (invalid keys or message too long)", service)
            return "rejected"
        headers = {
            "Authorization": self.authorization(subscription.endpoint, subject),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(max(0, ttl)),
            "Urgency": urgency,
        }
        if topic:
            headers["Topic"] = topic
        try:
            response = await self.client.post(subscription.endpoint, content=body, headers=headers)
        except httpx.HTTPError as error:
            log.warning("Push message not sent to %s (%s)", service, type(error).__name__)
            return "retry"
        result = outcome(response.status_code)
        if result in {"retry", "rejected"}:
            log.warning(
                "Push message refused by %s (%s %s)", service, response.status_code, refusal(response)
            )
        return result
