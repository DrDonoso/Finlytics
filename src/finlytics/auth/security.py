"""Core authentication helpers: password hashing and JWT session tokens.

Note: passlib[bcrypt] 1.7.x is incompatible with bcrypt >= 4.0 (it uses
bcrypt.__about__.__version__ which was removed in bcrypt 4.0). We call the
bcrypt library directly — same algorithm, same cost factor, same security.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from finlytics.config import settings

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_token(username: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.auth_token_expire_days)
    payload = {"sub": username, "exp": expire, "iat": now}
    return jwt.encode(payload, settings.auth_secret, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.auth_secret, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
