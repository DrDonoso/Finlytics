"""Shared data contracts between Finlytics subsystems.

``ExtractedTransaction`` lives here — not in the extraction layer — so that
the persistence layer (``finlytics.db.repository``) can import it without
pulling in openai, pdfplumber, or any other heavy extraction dependency.

Dependency graph (intentional):
    contracts.py  ←  extraction/schema.py   (re-exports for Banner's callers)
    contracts.py  ←  db/repository.py       (consumed by Shuri's persistence)

This module depends only on pydantic.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_serializer


class ExtractedTransaction(BaseModel):
    """Single parsed & categorized bank-statement transaction.

    This is the contract between Banner's extraction layer and Shuri's
    persistence layer.  Field names and types must stay in sync with the
    DB model in ``finlytics.db.models``.

    Signed-amount convention:
        negative → money out (expenses, fees, transfers out)
        positive → money in (income, refunds, transfers in)

    ``dedup_hash`` is intentionally absent — Shuri computes it from this data
    at persistence time.
    """

    transaction_date: date
    amount: Decimal = Field(
        description="Signed amount; negative = expense/out, positive = income/in"
    )
    currency: str = Field(default="EUR", description="ISO 4217 currency code")
    description: str = Field(
        description="Merchant name or raw description as it appears on the statement"
    )
    raw_line: Optional[str] = Field(
        default=None,
        description="Verbatim line(s) from the parsed statement, if available",
    )
    category: str = Field(
        description=(
            "Category name from the base taxonomy, or an LLM-proposed new one "
            "if nothing fits"
        )
    )
    category_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="LLM confidence score for the category assignment (0..1)",
    )
    account_ref: str = Field(
        description="Source account identifier — 'BBVA' or 'Indexa Capital'"
    )
    balance_after: Optional[Decimal] = Field(
        default=None,
        description="Running balance after this transaction, if present in the statement",
    )
    # Tags suggested by the LLM extractor (Banner will populate this list).
    # Shuri persists them as M:N links on import.  Default empty list ensures
    # backward compatibility: statements extracted before tags were introduced
    # (or extractors that don't emit tags) produce no tag rows.
    tags: list[str] = Field(
        default_factory=list,
        description="Free-form tag names to attach to this transaction (e.g. 'luz', 'agua')",
    )
    # Normalized brand/vendor name extracted by the LLM.  None when there is no
    # identifiable merchant (transfers, ATM, salary, taxes, etc.).
    # NOT translated — brand names are language-neutral (Amazon = Amazon in ES/EN).
    # NOT redacted — merchant names are needed for extraction accuracy.
    merchant: Optional[str] = Field(
        default=None,
        description=(
            "Normalized brand/vendor name in Title Case (e.g. 'Amazon', 'Mercadona'), "
            "or null when no merchant is identifiable"
        ),
    )
    # Set when a user-defined rule matched this transaction (apply_rules).
    # Used by the import preview to show a "🔗 Regla" badge.
    # Intentionally ignored by the persistence layer (Shuri).
    matched_rule_id: Optional[int] = Field(
        default=None,
        description="ID of the rule that matched this transaction, if any",
    )
    matched_rule_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the matched rule, if any",
    )

    # Ensure Decimal fields serialise as JSON numbers, not strings, so the API
    # contract ("amount: number") is honoured without lossy float arithmetic in
    # the persistence layer.
    @field_serializer("amount")
    def _ser_amount(self, v: Decimal) -> float:
        return float(v)

    @field_serializer("balance_after")
    def _ser_balance_after(self, v: Decimal | None) -> float | None:
        return float(v) if v is not None else None
