"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import logging
import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that have ever appeared in the public .env.example / docs. Using any of
# them as the JWT signing key is equivalent to having no authentication at all.
_PLACEHOLDER_SECRETS = frozenset(
    {
        "your-random-secret-here",
        "your-secret-here",
        "changeme",
        "change-me",
        "changeme-use-a-strong-password",
        "secret",
        "password",
    }
)


class Settings(BaseSettings):
    """Finlytics runtime configuration.

    Variables are loaded (in priority order):
      1. Actual environment variables
      2. .env file in the working directory
      3. Field defaults

    DATABASE_URL can be supplied directly (docker-compose injects it); if absent
    it is assembled from the individual POSTGRES_* components so local dev works
    without a pre-built connection string.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Allow both DATABASE_URL and the component vars to coexist
        populate_by_name=True,
    )

    # ── PostgreSQL connection ─────────────────────────────────────────────────
    # Can be set as a single DATABASE_URL or via individual components.
    database_url: str = ""
    postgres_user: str = "finlytics"
    postgres_password: str = "changeme"
    postgres_db: str = "finlytics"
    postgres_host: str = "db"
    postgres_port: int = 5432

    @model_validator(mode="after")
    def _build_database_url(self) -> "Settings":
        """Assemble database_url from components when not supplied directly."""
        if not self.database_url:
            self.database_url = (
                f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
                f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
            )
        # Ensure we always use the async driver
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )
        return self

    # ── OpenAI ───────────────────────────────────────────────────────────────
    # Banner's extractor reads these EXACT attribute names — do not rename.
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None

    # ── App config ────────────────────────────────────────────────────────────
    timezone: str = "Europe/Madrid"
    port: int = 7777
    upload_dir: str = "/app/data/uploads"

    # ── Auth ──────────────────────────────────────────────────────────────────
    # Sign JWT session tokens. If unset, an ephemeral key is generated at startup
    # (sessions won't survive container restarts — set AUTH_SECRET in .env).
    auth_secret: str = ""
    auth_token_expire_days: int = 7
    auth_remember_expire_days: int = 30
    # Set False for localhost (http). Set True when behind an https reverse proxy.
    auth_cookie_secure: bool = False

    # ── Investments / connector encryption ───────────────────────────────────
    # App-wide Fernet key for encrypting all connector tokens at rest.
    # Scoped fail: app starts normally when absent; only encrypt/decrypt
    # operations fail (HTTP 503) if the key is missing or invalid.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    finlytics_encryption_key: str | None = None

    # ── Notifications background loop ─────────────────────────────────────────
    # Set NOTIFICATIONS_LOOP_ENABLED=false to suppress the loop (e.g. in
    # local dev or when running tests that don't need a live DB).
    notifications_loop_enabled: bool = True
    # Seconds between detector evaluation cycles.
    notifications_eval_interval_seconds: int = 300
    # Set TELEGRAM_SEND_ENABLED=false to suppress all Telegram sends globally
    # (useful for ops maintenance or test environments with real channels).
    telegram_send_enabled: bool = True

    @model_validator(mode="after")
    def _ensure_auth_secret(self) -> "Settings":
        """Reject public placeholders; auto-generate when AUTH_SECRET is unset.

        A placeholder copied verbatim from ``.env.example`` (a public file) would
        let anyone forge a session cookie, so it is a hard startup failure rather
        than a warning.
        """
        if self.auth_secret.strip().lower() in _PLACEHOLDER_SECRETS:
            raise ValueError(
                "AUTH_SECRET is set to a public placeholder value. Anyone could "
                "forge a session cookie with it. Generate your own with: "
                'python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if not self.auth_secret:
            self.auth_secret = secrets.token_urlsafe(32)
            logging.getLogger("finlytics.config").warning(
                "AUTH_SECRET not set — generated ephemeral key; "
                "sessions won't survive restarts."
            )
        return self


settings = Settings()
