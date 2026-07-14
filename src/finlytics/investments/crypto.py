"""Connector token encryption helpers.

Uses symmetric Fernet (AES-128-CBC + HMAC-SHA256).  Key is read from the
app-wide FINLYTICS_ENCRYPTION_KEY env var.

Fail-closed by design: any encrypt/decrypt operation raises
EncryptionNotConfiguredError when the key is absent or malformed.
Plaintext tokens NEVER touch a log line or API response.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class EncryptionNotConfiguredError(Exception):
    """Raised when FINLYTICS_ENCRYPTION_KEY is absent, empty, or invalid."""


def _get_fernet() -> Fernet:
    # Deferred import avoids a circular dependency at module load time.
    from finlytics.config import settings  # noqa: PLC0415

    key = settings.finlytics_encryption_key
    if not key:
        raise EncryptionNotConfiguredError(
            "FINLYTICS_ENCRYPTION_KEY is not configured — "
            "cannot encrypt or decrypt connector tokens."
        )
    try:
        raw = key.encode() if isinstance(key, str) else key
        return Fernet(raw)
    except Exception as exc:
        raise EncryptionNotConfiguredError(
            "FINLYTICS_ENCRYPTION_KEY is invalid — "
            "cannot encrypt or decrypt connector tokens."
        ) from exc


def encrypt_token(plaintext: str) -> str:
    """Encrypt *plaintext* with Fernet.  Raises EncryptionNotConfiguredError on key issues."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext back to plaintext.

    Raises EncryptionNotConfiguredError if the key is absent, invalid,
    or if decryption fails (e.g. key was rotated without re-encrypting).
    """
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionNotConfiguredError(
            "Token decryption failed — the encryption key may have changed. "
            "Re-connect via the wizard."
        ) from exc
