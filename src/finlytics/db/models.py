"""SQLAlchemy 2 ORM models for Finlytics.

Table summary
─────────────
accounts                    – one row per bank/broker (BBVA, Indexa Capital, …)
categories                  – taxonomy of spending categories; is_base=True → seed data
import_runs                 – one row per statement-file import; holds import stats
transactions                – core ledger; dedup_hash enforces idempotent ingestion
tags                        – free-form labels; M:N with transactions via transaction_tags
transaction_tags            – join table for Transaction ↔ Tag many-to-many
investment_connections      – encrypted provider connections (Indexa, Fidelity ESPP, …)
investment_import_runs      – audit trail per CSV import (Fidelity ESPP)
espp_lots                   – immutable tax-lot per ESPP purchase row
price_history               – daily EOD close cache for portfolio valuation
investment_portfolio_cache  – per-connection DB cache for live portfolio data (24h freshness)
assistant_conversations     – chat threads with the finance assistant (per user)
assistant_messages          – user/assistant turns inside a conversation
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared declarative base for all Finlytics models."""


class User(Base):
    """Single application user for authentication.

    Only one User row is ever created (enforced at the application layer in
    the /api/auth/setup endpoint).  The UNIQUE constraint on ``username``
    acts as a last-resort safety net.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r}>"


class Account(Base):
    """A bank or brokerage account (e.g. BBVA, Indexa Capital)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    # IBAN or other account identifier; unique when non-NULL (enforced by partial index).
    account_number: Mapped[str | None] = mapped_column(String(34), nullable=True, unique=True)
    # e.g. "bank", "broker", "savings"
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    import_runs: Mapped[list["ImportRun"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Account id={self.id} name={self.name!r}>"


class Category(Base):
    """Spending / income category.

    is_base=True  → part of the seed taxonomy (canonical; never deleted)
    is_base=False → LLM-proposed or user-created
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name_es: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_base: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default="#64748b"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category id={self.id} name={self.name!r} base={self.is_base}>"


class Tag(Base):
    """Free-form label that can be attached to any transaction (many-to-many).

    Names are stored normalised: stripped and lowercased for dedup consistency
    (e.g. "Luz", " LUZ " → "luz").  This is enforced at the persistence layer
    in ``repository.get_or_create_tag``.

    ``color`` is a 7-character CSS hex string (e.g. "#3b82f6").  New tags get
    the default slate-grey palette entry unless an explicit colour is supplied.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    color: Mapped[str] = mapped_column(
        String(7), nullable=False, server_default="#64748b"
    )
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tag id={self.id} name={self.name!r}>"


# ── Many-to-many: Transaction ↔ Tag ──────────────────────────────────────────
# Using a plain Table (not a mapped model) because there are no extra columns.
# FKs use ON DELETE CASCADE so deleting a transaction cleans up its tag links.
transaction_tags = Table(
    "transaction_tags",
    Base.metadata,
    Column(
        "transaction_id",
        BigInteger,
        ForeignKey("transactions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)
# Index on tag_id so filtering transactions by tag is fast.
Index("ix_transaction_tags_tag_id", transaction_tags.c.tag_id)


class ImportRun(Base):
    """Audit record for a single statement-file import.

    One ImportRun is created per upload; it links every imported Transaction
    back to its source file so imports are fully traceable.
    """

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # ISO month string, e.g. "2024-01"; optional when period cannot be determined
    period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    num_parsed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    num_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    num_duplicates: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Relative filename under settings.upload_dir; None when no PDF was captured.
    source_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="import_runs")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="import_run")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ImportRun id={self.id} file={self.source_filename!r} "
            f"inserted={self.num_inserted} dupes={self.num_duplicates}>"
        )


class Transaction(Base):
    """An individual financial transaction.

    ``dedup_hash`` is a SHA-256 of (account_ref, transaction_date, amount,
    description) and acts as the idempotency key — re-importing the same
    statement never creates duplicates.

    Shared contract with Banner (extractor):
      transaction_date, amount, currency, description, raw_line,
      category, category_confidence, account_ref, balance_after
    """

    __tablename__ = "transactions"
    __table_args__ = (
        # Supports aggregation queries: by account + period
        Index("ix_transactions_account_date", "account_id", "transaction_date"),
        # Supports aggregation queries: by category
        Index("ix_transactions_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("accounts.id"), nullable=False
    )
    import_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("import_runs.id"), nullable=False
    )

    # ── Core financial fields (the shared contract) ───────────────────────────
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    # SIGNED: negative = expense / money out; positive = income / refund
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="EUR")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # ── Merchant (normalized brand name from LLM extraction) ─────────────────
    # Nullable; NOT part of dedup_hash so edits never break idempotency.
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ── Detail (non-bold sub-line from statement, e.g. "GCREOCTOPUSENERGY") ──
    # Nullable; IS part of dedup_hash when non-empty so the same concept line
    # with different detail sub-texts produces distinct rows.
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Idempotency ───────────────────────────────────────────────────────────
    dedup_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )

    # ── System flag ───────────────────────────────────────────────────────────
    # True for synthetic rows created by Finlytics itself (e.g. opening-balance
    # "Saldo inicial" entries).  Excluded from all KPI / flow aggregations so
    # they never distort income or expense totals.
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    account: Mapped["Account"] = relationship(back_populates="transactions")
    import_run: Mapped["ImportRun"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    # Tags are loaded lazily by default; use selectinload() for bulk reads.
    # passive_deletes=True defers secondary-table cleanup to the DB-level CASCADE.
    tags: Mapped[list["Tag"]] = relationship(
        secondary=transaction_tags,
        lazy="select",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Transaction id={self.id} date={self.transaction_date} "
            f"amount={self.amount} desc={self.description[:30]!r}>"
        )


class InvestmentConnection(Base):
    """An encrypted connection to an external investment provider.

    One row per discovered provider account.  Multiple accounts from the
    same token share the same ``token_enc`` ciphertext.  Token is NEVER
    stored in plaintext (Romanoff §1).
    """

    __tablename__ = "investment_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plugin_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # active | error | disconnected
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="active"
    )
    # Masked account label: first3•••last2 (e.g. "PBK•••Z5")
    account_label_masked: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Fernet ciphertext of the provider API token — NEVER the plaintext.
    # NULL for statement-import providers (e.g. Fidelity ESPP) that have no API token.
    token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<InvestmentConnection id={self.id} plugin={self.plugin_id!r} "
            f"mask={self.account_label_masked!r} status={self.status!r}>"
        )


class InvestmentImportRun(Base):
    """Audit trail for a single Fidelity ESPP CSV import.

    file_hash (sha256 of raw file bytes) is UNIQUE — re-uploading the same
    file is detected here at the file level before touching espp_lots.
    """

    __tablename__ = "investment_import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("investment_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex digest of the raw file bytes — file-level idempotency key
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    lots_inserted: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    lots_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<InvestmentImportRun id={self.id} conn={self.connection_id} "
            f"inserted={self.lots_inserted} skipped={self.lots_skipped}>"
        )


class EsppLot(Base):
    """An immutable ESPP tax-lot record — one row per CSV purchase row.

    dedup_hash = sha256(ticker|purchase_date|shares:.8f|cost_basis_per_share:.6f
                        |share_source|dedup_ordinal)

    INSERT ON CONFLICT (dedup_hash) DO NOTHING makes re-imports idempotent.
    share_source: 'SP' = stock purchase, 'DO' = dividend reinvestment.
    source_currency: detected from CSV footer (typically 'EUR' for Fidelity EU).
    """

    __tablename__ = "espp_lots"
    __table_args__ = (
        Index("ix_espp_lots_connection_purchase", "connection_id", "purchase_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("investment_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="MSFT"
    )
    purchase_date: Mapped[date] = mapped_column(Date, nullable=False)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cost_basis_per_share: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False
    )
    # Currency of cost_basis values (from CSV footer, e.g. 'EUR')
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # 'SP' = stock purchase | 'DO' = dividend reinvestment
    share_source: Mapped[str] = mapped_column(String(2), nullable=False)
    holding_period: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dedup_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EsppLot id={self.id} ticker={self.ticker!r} "
            f"date={self.purchase_date} shares={self.shares}>"
        )


class PriceHistory(Base):
    """Daily EOD close price for a ticker, with EUR/USD FX rate.

    Serves two purposes:
    (1) On-request price cache: fetch from Stooq / yfinance, store here.
    (2) Historical series: used by the evolution endpoint to compute
        value_eur(d) = shares_held(d) × close_usd(d) × fx_eur_usd(d).

    close_eur is a derived field computed at insert time:
        close_eur = close_usd × fx_eur_usd
    UNIQUE(ticker, price_date) → INSERT ON CONFLICT DO NOTHING for idempotent backfill.
    """

    __tablename__ = "price_history"
    __table_args__ = (
        UniqueConstraint("ticker", "price_date", name="uq_price_history_ticker_date"),
        Index("ix_price_history_ticker_date", "ticker", "price_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    price_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_eur_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # Derived: close_usd × fx_eur_usd — stored for query efficiency
    close_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PriceHistory ticker={self.ticker!r} date={self.price_date} "
            f"close_usd={self.close_usd} close_eur={self.close_eur}>"
        )


class InvestmentPortfolioCache(Base):
    """Per-connection DB cache for the live-fetched NormalizedPortfolio.

    One row per InvestmentConnection (connection_id UNIQUE).
    payload stores the JSON-serialised NormalizedPortfolio so the
    /portfolio endpoint can return immediately without hitting the
    Indexa API on every page load.

    Cache freshness: ~24 h (_CACHE_MAX_AGE in investments/service.py).
    Stale entries are served immediately while a FastAPI BackgroundTask
    re-fetches from Indexa and updates the row asynchronously.
    ON DELETE CASCADE cleans up the row when the parent connection is deleted.
    """

    __tablename__ = "investment_portfolio_cache"
    __table_args__ = (
        UniqueConstraint("connection_id", name="uq_portfolio_cache_connection_id"),
        Index("ix_portfolio_cache_connection_id", "connection_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("investment_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<InvestmentPortfolioCache connection_id={self.connection_id} "
            f"fetched_at={self.fetched_at}>"
        )


class Rule(Base):
    """User-defined rule for deterministic transaction categorisation.

    Rules are evaluated in ascending (priority, id) order — lower priority
    integer = matched first.  The first matching rule wins (no fall-through).

    Match criteria (all AND-ed with description_mode/value):
      amount_sign, account_ref, currency — each null = wildcard.

    Actions: set_category, set_merchant, add_tags override AI output.
    skip_ai = True removes the line from the LLM call entirely (Phase 2).
    Validation: skip_ai=True requires set_category to be non-null.
    """

    __tablename__ = "rules"
    __table_args__ = (
        Index("ix_rules_priority_id", "priority", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # ── Match criteria ────────────────────────────────────────────────────────
    # description_mode: contains | starts_with | exact | regex
    description_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    description_value: Mapped[str] = mapped_column(Text, nullable=False)
    amount_sign: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Magnitude filters (abs-value comparison, sign-agnostic). Each is independent;
    # either, both, or neither may be set.  Semantics: abs(tx.amount) >= amount_min
    # and abs(tx.amount) <= amount_max.  Both must be >= 0 when set.
    amount_min: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_max: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    account_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # detail_mode / detail_value mirror description_mode/value but match against
    # Transaction.detail (the non-bold sub-line).  Both null = no detail filter.
    detail_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detail_value: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Actions ───────────────────────────────────────────────────────────────
    set_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    set_merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # JSON array of tag name strings; empty list = no tags to add.
    add_tags: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'"))
    skip_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # ── Metadata ──────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Rule id={self.id} name={self.name!r} priority={self.priority}>"


# ── Notifications ─────────────────────────────────────────────────────────────

class Notification(Base):
    """A detected notification for a user.

    Rows are upserted by (user_id, dedup_key) — one row per standing condition.
    read_at / dismissed_at survive detector re-evaluations (never cleared on
    upsert). resolved_at is set when the condition is no longer detected; the
    row is kept so Telegram never re-sends a delivered notification.

    dedup_key examples:
      statement:missing:2026-06:acct-3   — one per (account × month)
      espp:overdue:2026-Q2               — one per ESPP quarter
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedup_key", name="uq_notifications_user_dedup"),
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_user_read", "user_id", "read_at"),
        Index("ix_notifications_user_status", "user_id", "dismissed_at", "resolved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "statement" | "espp" | …
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # "missing_statement" | "espp_overdue" | …
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # "info" | "warning"
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default="info")
    # stable identity key — never changes for the same condition instance
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # i18n key + args for the notification title (rendered on the frontend)
    title_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title_args: Mapped[dict] = mapped_column(JSON, nullable=False, server_default=text("'{}'"))
    # optional body text (i18n key + args)
    body_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    body_args: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # frontend route to navigate on click (e.g. "/finances?account_id=3")
    action_link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # state columns — null means unset; dismissed_at / read_at survive upserts
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # set by auto-resolve when the condition is no longer detected; row is kept
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification id={self.id} user={self.user_id} key={self.dedup_key!r}>"


class NotificationChannel(Base):
    """Encrypted notification delivery channel config (e.g. Telegram).

    config_enc stores a Fernet-encrypted JSON blob {bot_token, chat_id}.
    label is a human-readable masked display name (e.g. "Telegram · ••••1234").
    NEVER log or return config_enc; never return bot_token.
    """

    __tablename__ = "notification_channels"
    __table_args__ = (
        UniqueConstraint("user_id", "channel", name="uq_notification_channels_user_type"),
        Index("ix_notification_channels_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # "telegram" (extensible to future channels)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    # Fernet ciphertext of JSON {bot_token, chat_id} — NEVER the plaintext
    config_enc: Mapped[str] = mapped_column(Text, nullable=False)
    # Masked display label for the UI (e.g. "Telegram · ••••1234")
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotificationChannel id={self.id} user={self.user_id} channel={self.channel!r}>"


class NotificationDelivery(Base):
    """Delivery audit log for a single notification × channel send attempt.

    UNIQUE(notification_id, channel) is the idempotency guard that prevents
    double-sending: before sending, INSERT-or-skip on this constraint.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("notification_id", "channel", name="uq_notification_delivery"),
        Index("ix_notification_deliveries_notification_id", "notification_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    notification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False
    )
    # "telegram" (matches NotificationChannel.channel)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    # "sent" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<NotificationDelivery id={self.id} notif={self.notification_id} "
            f"channel={self.channel!r} status={self.status!r}>"
        )


# ── Finance assistant ─────────────────────────────────────────────────────────

class AssistantConversation(Base):
    """A chat thread between a user and the finance assistant.

    Scoped per user like notifications, even though the ledger itself is global
    (Transaction has no user_id): a conversation is personal context, not data.

    ``title`` is derived from the first user message, never generated by a
    second LLM call — that would double the cost of starting a thread.
    """

    __tablename__ = "assistant_conversations"
    __table_args__ = (
        Index("ix_assistant_conversations_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages: Mapped[list["AssistantMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AssistantMessage.id",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AssistantConversation id={self.id} user={self.user_id} title={self.title!r}>"


class AssistantMessage(Base):
    """One turn in an assistant conversation.

    Only ``user`` and ``assistant`` roles are stored. Tool round-trips are NOT
    persisted as rows and are never replayed into the model on a later turn:
    doing so would grow the token bill without bound and let the assistant
    answer a *new* question from a *previous* query's results. ``tool_calls``
    keeps a JSON audit trail of what was queried purely so the UI can show it.
    """

    __tablename__ = "assistant_messages"
    __table_args__ = (
        Index("ix_assistant_messages_conversation_id", "conversation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False
    )
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # [{"name": "get_spending_by_category", "arguments": {...}}, …] — audit only
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[AssistantConversation] = relationship(back_populates="messages")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AssistantMessage id={self.id} conv={self.conversation_id} role={self.role!r}>"
