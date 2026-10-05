"""USD-only Fidelity imports with connection-scoped, cost-independent lot identities."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import EsppLot, InvestmentConnection, InvestmentImportRun
from finlytics.investments.base import (
    InvestmentProvider,
    NormalizedPerformance,
    NormalizedPortfolio,
    ValidationResult,
)
from finlytics.investments.fidelity_csv import FidelityCurrencyError

_DEFAULT_TICKER = "MSFT"


@runtime_checkable
class LotRecord(Protocol):
    """Structural interface for the CSV parser's lot records."""

    purchase_date: date
    shares: Decimal
    cost_basis: Decimal
    cost_basis_per_share: Decimal
    source_currency: str
    share_source: str           # 'SP' (stock purchase) | 'DO' (dividend)
    grant_date: date | None
    holding_period: str | None
    dedup_ordinal: int


def _compute_dedup_hash(
    connection_id: int,
    ticker: str,
    purchase_date: date,
    shares: Decimal,
    share_source: str,
    dedup_ordinal: int,
    grant_date: date | None = None,
) -> str:
    """Connection-scoped identity, independent of cost or display currency."""
    payload = (
        f"fidelity:v2|{connection_id}|{ticker}|{purchase_date}"
        f"|{shares:.8f}"
        f"|{share_source}|{grant_date or ''}|{dedup_ordinal}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LegacyFidelityLotsError(ValueError):
    code = "fidelity_legacy_lots"

    def __init__(self) -> None:
        super().__init__(
            "Back up your investments, then clear Fidelity data in Settings > Connectors "
            "before importing a complete USD export."
        )


async def require_usd_lots(db: AsyncSession, connection_id: int) -> None:
    legacy = await db.scalar(
        select(EsppLot.id)
        .where(EsppLot.connection_id == connection_id, EsppLot.source_currency != "USD")
        .limit(1)
    )
    if legacy is not None:
        raise LegacyFidelityLotsError()


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

    async def validate_token(self, token: str) -> ValidationResult:
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; no token API."
        )

    async def get_portfolio(
        self, token: str, account_numbers: list[str]
    ) -> NormalizedPortfolio:
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; use import_lots()."
        )

    async def get_performance(
        self, token: str, account_number: str
    ) -> NormalizedPerformance:
        raise NotImplementedError(
            "fidelity-espp is a statement_import provider; use import_lots()."
        )

    # ── Core import method ───────────────────────────────────────────────────

    async def import_lots(
        self,
        connection_id: int,
        lots: Sequence[LotRecord],
        source_currency: str,
        file_hash: str,
        db: AsyncSession,
        *,
        ticker: str = _DEFAULT_TICKER,
    ) -> tuple[int, int]:
        """Persist parsed lots idempotently and record an import run.

        Two-level idempotency:
        (1) File-level: if file_hash already exists in investment_import_runs
            for this connection, report no inserts and skip the file's lots.
        (2) Lot-level: INSERT INTO espp_lots ON CONFLICT (dedup_hash) DO NOTHING
            so re-uploading a partially-imported file is also safe.

        Args:
            connection_id: PK of the investment_connections row.
            lots: Parsed USD lot records.
            source_currency: Explicit file-level currency, which must be USD.
            file_hash: sha256 hex digest of the raw file bytes.
            db: Async SQLAlchemy session (caller owns the transaction context).
            ticker: Equity ticker; defaults to 'MSFT'.

        Returns:
            (lots_inserted, lots_skipped) counts.
        """
        if source_currency != "USD" or any(lot.source_currency != "USD" for lot in lots):
            raise FidelityCurrencyError("Only USD exports are supported.")
        async with db.begin():
            await db.scalar(
                select(InvestmentConnection.id)
                .where(InvestmentConnection.id == connection_id)
                .with_for_update()
            )
            await require_usd_lots(db, connection_id)
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
                return 0, len(lots)

            lots_inserted = 0
            lots_skipped = 0

            for lot in lots:
                dedup_hash = _compute_dedup_hash(
                    connection_id=connection_id,
                    ticker=ticker,
                    purchase_date=lot.purchase_date,
                    shares=Decimal(str(lot.shares)),
                    share_source=lot.share_source,
                    dedup_ordinal=lot.dedup_ordinal,
                    grant_date=lot.grant_date,
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
                        dedup_ordinal=lot.dedup_ordinal,
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
