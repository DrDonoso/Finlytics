"""SQLAlchemy 2 ORM models for Finlytics.

Table summary
─────────────
accounts          – one row per bank/broker (BBVA, Indexa Capital, …)
categories        – taxonomy of spending categories; is_base=True → seed data
import_runs       – one row per statement-file import; holds import stats
transactions      – core ledger; dedup_hash enforces idempotent ingestion
tags              – free-form labels; M:N with transactions via transaction_tags
transaction_tags  – join table for Transaction ↔ Tag many-to-many
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
