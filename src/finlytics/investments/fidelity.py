"""Fidelity ESPP investment provider — statement-import flavour.

This provider does NOT use a live API token.  Instead it ingests
pre-parsed lot records produced by Banner's CSV parser
(src/finlytics/investments/fidelity_csv.py — written in parallel; NOT
imported here to avoid coupling during parallel development).

Wave 1 ships:
  - import_lots(): idempotent lot ingestion + import-run audit trail.

Wave 2 will add:
  - Preview/confirm HTTP endpoints.
  - Price-service integration (Stooq + yfinance backfill).
  - Evolution series endpoint.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import EsppLot, InvestmentImportRun
from finlytics.investments.base import (
    InvestmentProvider,
    NormalizedPerformance,
    NormalizedPortfolio,
    ValidationResult,
)

_DEFAULT_TICKER = "MSFT"


@runtime_checkable
class LotRecord(Protocol):
    """Structural interface for a parsed ESPP lot.

    Matches the fields that Banner's fidelity_csv.py parser emits so that
    this module compiles and tests independently of that file.
    """

    purchase_date: date
    shares: Decimal
    cost_basis: Decimal
    cost_basis_per_share: Decimal
    source_currency: str
    share_source: str           # 'SP' (stock purchase) | 'DO' (dividend)
    grant_date: date | None
    holding_period: str | None
    dedup_ordinal: int          # 0-based index within identical (date, qty, price, source) groups


def _compute_dedup_hash(
    ticker: str,
    purchase_date: date,
    shares: Decimal,
    cost_basis_per_share: Decimal,
    share_source: str,
    dedup_ordinal: int,
) -> str:
    """Deterministic SHA-256 dedup key for an ESPP lot.

    Format: sha256("{ticker}|{purchase_date}|{shares:.8f}|{cost_basis_per_share:.6f}
                    |{share_source}|{dedup_ordinal}")

    Precision matches column types: shares NUMERIC(18,8), cost_basis_per_share NUMERIC(18,6).
    dedup_ordinal resolves duplicate DO lots that share identical (date, qty, price).
    """
    payload = (
        f"{ticker}|{purchase_date}"
        f"|{shares:.8f}"
        f"|{cost_basis_per_share:.6f}"
        f"|{share_source}|{dedup_ordinal}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FidelityESPPProvider(InvestmentProvider):
    """Statement-import provider for Fidelity ESPP MSFT holdings.

    plugin_id = "fidelity-espp"
    provider_type = "statement_import"

    The three live-API abstract methods raise NotImplementedError; this provider
    is never called via the portfolio aggregation loop (service.py skips
    connections with token_enc IS NULL).
    """

    plugin_id = "fidelity-espp"
    provider_type = "statement_import"

    # ── ABC stubs — not used for statement_import providers ──────────────────

    async def validate_token(self, token: str) -> ValidationResult:  # type: ignore[override]
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; no token API."
        )

    async def get_portfolio(  # type: ignore[override]
        self, token: str, account_numbers: list[str]
    ) -> NormalizedPortfolio:
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; use import_lots()."
        )

    async def get_performance(  # type: ignore[override]
        self, token: str, account_number: str
    ) -> NormalizedPerformance:
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; use import_lots()."
        )

    # ── Core import method ───────────────────────────────────────────────────

    async def import_lots(
        self,
        connection_id: int,
        lots: list,
        source_currency: str,
        file_hash: str,
        db: AsyncSession,
        *,
        ticker: str = _DEFAULT_TICKER,
    ) -> tuple[int, int]:
        """Persist parsed lots idempotently and record an import run.

        Two-level idempotency:
        (1) File-level: if file_hash already exists in investment_import_runs
            for this connection, return the previous (inserted, skipped) counts
            without touching espp_lots.
        (2) Lot-level: INSERT INTO espp_lots ON CONFLICT (dedup_hash) DO NOTHING
            so re-uploading a partially-imported file is also safe.

        Args:
            connection_id: PK of the investment_connections row.
            lots: Iterable of LotRecord-compatible objects from Banner's parser.
            source_currency: File-level currency detected from CSV footer (e.g. 'EUR').
            file_hash: sha256 hex digest of the raw file bytes.
            db: Async SQLAlchemy session (caller owns the transaction context).
            ticker: Equity ticker; defaults to 'MSFT'.

        Returns:
            (lots_inserted, lots_skipped) counts.
        """
        async with db.begin():
            # File-level dedup check (inside transaction for consistency)
            existing_run = (
                await db.execute(
                    select(InvestmentImportRun).where(
                        InvestmentImportRun.connection_id == connection_id,
                        InvestmentImportRun.file_hash == file_hash,
                    )
                )
            ).scalar_one_or_none()

            if existing_run is not None:
                return existing_run.lots_inserted, existing_run.lots_skipped

            lots_inserted = 0
            lots_skipped = 0

            for lot in lots:
                dedup_hash = _compute_dedup_hash(
                    ticker=ticker,
                    purchase_date=lot.purchase_date,
                    shares=Decimal(str(lot.shares)),
                    cost_basis_per_share=Decimal(str(lot.cost_basis_per_share)),
                    share_source=lot.share_source,
                    dedup_ordinal=lot.dedup_ordinal,
                )

                stmt = (
                    pg_insert(EsppLot)
                    .values(
                        connection_id=connection_id,
                        ticker=ticker,
                        purchase_date=lot.purchase_date,
                        grant_date=getattr(lot, "grant_date", None),
                        shares=lot.shares,
                        cost_basis=lot.cost_basis,
                        cost_basis_per_share=lot.cost_basis_per_share,
                        source_currency=lot.source_currency,
                        share_source=lot.share_source,
                        holding_period=getattr(lot, "holding_period", None),
                        dedup_hash=dedup_hash,
                    )
                    .on_conflict_do_nothing(index_elements=["dedup_hash"])
                    .returning(EsppLot.id)
                )
                result = await db.execute(stmt)
                if result.scalar_one_or_none() is not None:
                    lots_inserted += 1
                else:
                    lots_skipped += 1

            # Record the import run audit trail
            run = InvestmentImportRun(
                connection_id=connection_id,
                file_hash=file_hash,
                source_currency=source_currency,
                lots_inserted=lots_inserted,
                lots_skipped=lots_skipped,
            )
            db.add(run)

        return lots_inserted, lots_skipped
