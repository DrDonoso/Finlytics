"""Core authentication helpers: password hashing and JWT session tokens.

Note: passlib[bcrypt] 1.7.x is incompatible with bcrypt >= 4.0 (it uses
bcrypt.__about__.__version__ which was removed in bcrypt 4.0). We call the
bcrypt library directly — same algorithm, same cost factor, same security.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from finlytics.config import settings

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:  # a malformed hash, or a password over bcrypt's 72 bytes
        return False


def create_token(username: str, *, version: int, remember: bool = False) -> str:
    """Mint a session token for ``username``.

    ``version`` must be the user's current ``token_version``: bumping that column
    ends every session at once.  ``jti`` names this one token so that logout can
    revoke it alone, and ``rem`` records the remember-me choice, so a token
    re-issued later keeps the lifetime the user asked for.
    """
    days = settings.auth_remember_expire_days if remember else settings.auth_token_expire_days
    now = datetime.now(UTC)
    payload = {
        "sub": username,
        "ver": version,
        "jti": secrets.token_hex(16),
        "rem": remember,
        "iat": now,
        "exp": now + timedelta(days=days),
    }
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
