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

# bcrypt only ever reads the first 72 bytes of a password. Before 5.0 the library
# truncated silently; since then it raises ValueError instead. New passwords are
# capped at the API, and truncating here keeps a longer password set under the
# old behaviour verifiable, exactly as it was hashed.
BCRYPT_MAX_PASSWORD_BYTES = 72


def password_exceeds_bcrypt_limit(password: str) -> bool:
    return len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES


def _bcrypt_input(password: str) -> bytes:
    return password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(plain_password), hashed_password.encode("utf-8"))
    except ValueError:  # a malformed hash
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
