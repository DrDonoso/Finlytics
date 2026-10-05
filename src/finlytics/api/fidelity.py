"""Fidelity ESPP import + read endpoints.

Routes
──────
  POST /api/investments/fidelity/import/preview   parse CSV, diff against DB (no write)
  POST /api/investments/fidelity/import/confirm   import lots + backfill prices
  GET  /api/investments/fidelity/kpis             aggregated portfolio KPIs
  GET  /api/investments/fidelity/evolution        value + contributions time series
  GET  /api/investments/fidelity/lots             per-lot detail with current valuation
  GET  /api/investments/fidelity/reminder         overdue-upload reminder (ESPP quarter-end)
"""
from __future__ import annotations

import calendar
import hashlib
import logging
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    FidelityEvolutionOut,
    FidelityImportResult,
    FidelityKpisOut,
    FidelityLotOut,
    FidelityLotsOut,
    FidelityPreviewLotOut,
    FidelityPreviewOut,
    FidelityReminderOut,
    ValuePoint,
)
from finlytics.api.uploads import read_upload
from finlytics.clock import today as local_today
from finlytics.db.models import (
    EsppLot,
    InvestmentConnection,
    InvestmentImportRun,
    PriceHistory,
    User,
)
from finlytics.investments.fidelity import (
    FidelityESPPProvider,
    LegacyFidelityLotsError,
    _compute_dedup_hash,
    require_usd_lots,
)
from finlytics.investments.fidelity_csv import (
    FidelityCsvError,
    FidelityCurrencyError,
    parse_usd_open_lots_csv,
)
from finlytics.investments.fidelity_valuation import cost_in_eur, total_cost_eur, value_fidelity
from finlytics.investments.market_data import (
    LatestPriceRow,
    backfill_price_history,
    get_current_fx_rate,
    get_latest_price,
    topup_recent_prices,
)
from finlytics.investments.service import _PROVIDERS

log = logging.getLogger(__name__)

router = APIRouter(prefix="/investments", tags=["fidelity"])

_PLUGIN_ID = "fidelity-espp"


# ── Connection helpers ────────────────────────────────────────────────────────

async def _get_or_create_fidelity_connection(
    user_id: int, db: AsyncSession
) -> InvestmentConnection:
    """Get or create the fidelity-espp connection for *user_id*.

    Must be called inside an active ``async with db.begin()`` block.
    """
    await db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    result = await db.execute(
        select(InvestmentConnection).where(
            InvestmentConnection.user_id == user_id,
            InvestmentConnection.plugin_id == _PLUGIN_ID,
        )
    )
    conn = result.scalar_one_or_none()
    if conn is None:
        conn = InvestmentConnection(
            user_id=user_id,
            plugin_id=_PLUGIN_ID,
            status="active",
            token_enc=None,
        )
        db.add(conn)
        await db.flush()
    return conn


async def _get_fidelity_connection(
    user_id: int, db: AsyncSession
) -> InvestmentConnection | None:
    """Return the fidelity-espp connection for *user_id*, or ``None`` (read-only)."""
    result = await db.execute(
        select(InvestmentConnection).where(
            InvestmentConnection.user_id == user_id,
            InvestmentConnection.plugin_id == _PLUGIN_ID,
        )
    )
    return result.scalar_one_or_none()


# ── Pure series helper (extracted for testability) ────────────────────────────

def compute_evolution_series(
    lots: Sequence[EsppLot],
    price_map: dict[date, tuple[float, float]],
    min_date: date,
    max_date: date,
) -> tuple[list[ValuePoint], list[ValuePoint]]:
    """Compute value + contributions series from lots and a price map.

    Pure function — no I/O.  Exported so Barton can write the full test suite.

    Args:
        lots:       Iterable of objects with ``.purchase_date``, ``.shares``,
                    ``.cost_basis`` (all Decimal-compatible).
        price_map:  ``{date: (close_usd, fx_eur_usd)}`` — market days only;
                    weekend / holiday gaps are forward-filled internally.
        min_date:   Start of the date range (inclusive).
        max_date:   End of the date range (inclusive).

    Returns:
        ``(value_series, contributions_series)`` — each a list of
        ``ValuePoint(date="YYYY-MM-DD", value=float)``.

    Granularity (auto):
        - ≤ 2200 days (~6 years) → one point per actual MSFT trading day
          (dates present in ``price_map`` within [min_date, max_date])
        - > 2200 days → weekly from the first Monday ≥ min_date
          (with forward-fill for holiday Mondays)
    """
    total_days = (max_date - min_date).days
    use_weekly = total_days > 2200

    if use_weekly:
        # Build forward-filled price map so holiday Mondays get the last close
        all_days = [min_date + timedelta(days=i) for i in range(total_days + 1)]
        last_price: tuple[float, float] | None = None
        price_lookup: dict[date, tuple[float, float] | None] = {}
        for d in all_days:
            if d in price_map:
                last_price = price_map[d]
            price_lookup[d] = last_price

        d = min_date
        while d.weekday() != 0:             # advance to first Monday
            d += timedelta(days=1)
        series_dates: list[date] = []
        while d <= max_date:
            series_dates.append(d)
            d += timedelta(days=7)
    else:
        # Daily: one point per actual MSFT trading day in range
        series_dates = sorted(d for d in price_map if min_date <= d <= max_date)
        price_lookup = price_map  # type: ignore[assignment]

    lots_sorted = sorted(lots, key=lambda lot: lot.purchase_date)
    lot_idx = 0
    cum_shares = Decimal(0)
    cum_costs: dict[str, Decimal] = {}

    value_series: list[ValuePoint] = []
    contributions_series: list[ValuePoint] = []

    for sd in series_dates:
        # Advance step function: include lots whose purchase_date ≤ sd
        while lot_idx < len(lots_sorted) and lots_sorted[lot_idx].purchase_date <= sd:
            cum_shares += Decimal(str(lots_sorted[lot_idx].shares))
            lot = lots_sorted[lot_idx]
            cum_costs[lot.source_currency] = (
                cum_costs.get(lot.source_currency, Decimal(0)) + Decimal(str(lot.cost_basis))
            )
            lot_idx += 1

        price_pt = price_lookup.get(sd)
        if price_pt is not None and cum_shares > 0:
            close_usd, fx_eur_usd = price_pt
            value = float(cum_shares) * close_usd * fx_eur_usd
            value_series.append(ValuePoint(date=sd.isoformat(), value=round(value, 2)))

        fx = Decimal(str(price_pt[1])) if price_pt is not None else None
        cum_cost = total_cost_eur(cum_costs, fx)
        if cum_cost is not None and cum_cost > 0:
            contributions_series.append(
                ValuePoint(date=sd.isoformat(), value=round(float(cum_cost), 2))
            )

    return value_series, contributions_series


# ── ESPP purchase-reminder helpers ────────────────────────────────────────────

_ESPP_QUARTER_MONTHS = (3, 6, 9, 12)
_GRACE_DAYS = 5
_QUARTER_LABELS: dict[int, str] = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}


def _last_weekday_of_month(year: int, month: int) -> date:
    """Return the last Mon–Fri of *month*/*year* (Saturday → Friday, Sunday → Friday)."""
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    wd = d.weekday()  # Mon=0 … Sun=6
    if wd == 5:        # Saturday
        d -= timedelta(days=1)
    elif wd == 6:      # Sunday
        d -= timedelta(days=2)
    return d


def _expected_espp_dates(start_year: int = 2020, end_date: date | None = None) -> list[date]:
    """All expected ESPP purchase dates from *start_year* through *end_date* (inclusive).

    Dates are the last weekday of Mar / Jun / Sep / Dec each year.
    """
    if end_date is None:
        end_date = local_today()
    result: list[date] = []
    for year in range(start_year, end_date.year + 1):
        for month in _ESPP_QUARTER_MONTHS:
            d = _last_weekday_of_month(year, month)
            if d <= end_date:
                result.append(d)
    return result


def _get_today() -> date:
    """Indirection for the app's local date; monkeypatched in tests for determinism."""
    return local_today()


def compute_espp_reminder(
    lots: Sequence[EsppLot],
    today: date | None = None,
    grace_days: int = _GRACE_DAYS,
) -> FidelityReminderOut:
    """Pure function — compute the ESPP upload-reminder state.

    Args:
        lots:       EsppLot rows with ``.purchase_date`` and ``.share_source``.
        today:      Override for deterministic testing; defaults to the app's
                    local date (see finlytics.clock).
        grace_days: Days after the expected purchase before marking overdue.

    Returns:
        FidelityReminderOut — overdue only when the grace window has closed AND
        no SP lot exists with purchase_date ≥ the expected quarter-end date.
    """
    if today is None:
        today = local_today()

    expected_dates = _expected_espp_dates(end_date=today)
    if not expected_dates:
        return FidelityReminderOut(overdue=False)

    most_recent = expected_dates[-1]
    quarter_month = most_recent.month
    period_label = f"{_QUARTER_LABELS[quarter_month]} {most_recent.year}"
    expected_date_str = most_recent.isoformat()

    sp_lots = [lot for lot in lots if lot.share_source == "SP"]
    last_lot_date = max((lot.purchase_date for lot in sp_lots), default=None)
    last_lot_date_str = last_lot_date.isoformat() if last_lot_date else None

    grace_deadline = most_recent + timedelta(days=grace_days)
    if today < grace_deadline:
        return FidelityReminderOut(
            overdue=False,
            expected_date=expected_date_str,
            period_label=period_label,
            last_lot_date=last_lot_date_str,
        )

    has_import = any(
        lot.share_source == "SP" and lot.purchase_date >= most_recent
        for lot in lots
    )
    return FidelityReminderOut(
        overdue=not has_import,
        expected_date=expected_date_str,
        period_label=period_label,
        last_lot_date=last_lot_date_str,
    )


# ── Import endpoints ──────────────────────────────────────────────────────────

@router.post("/fidelity/import/preview", response_model=FidelityPreviewOut)
async def fidelity_import_preview(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityPreviewOut:
    """Parse a Fidelity 'View open lots' CSV and diff against existing lots.

    Does NOT persist anything.  Returns the list of new lots that would be
    inserted plus a duplicate count.
    """
    file_bytes = await read_upload(file)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        parsed = parse_usd_open_lots_csv(file_bytes)
    except FidelityCurrencyError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    except FidelityCsvError as exc:
        raise HTTPException(status_code=400, detail=f"CSV parsing failed: {exc}") from exc

    # Check if this exact file was previously imported for this user
    file_already_imported = (
        await db.execute(
            select(InvestmentImportRun.id)
            .join(
                InvestmentConnection,
                InvestmentImportRun.connection_id == InvestmentConnection.id,
            )
            .where(
                InvestmentConnection.user_id == user.id,
                InvestmentConnection.plugin_id == _PLUGIN_ID,
                InvestmentImportRun.file_hash == file_hash,
            )
        )
    ).scalar_one_or_none() is not None

    # Find which hashes already exist in the user's connection(s)
    user_conn_ids = list(
        (
            await db.execute(
                select(InvestmentConnection.id).where(
                    InvestmentConnection.user_id == user.id,
                    InvestmentConnection.plugin_id == _PLUGIN_ID,
                )
            )
        ).scalars().all()
    )

    known_indices: set[int] = set()
    for connection_id in user_conn_ids:
        try:
            await require_usd_lots(db, connection_id)
        except LegacyFidelityLotsError as exc:
            raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
        lot_hashes = [
            _compute_dedup_hash(
                connection_id=connection_id, ticker=parsed.ticker,
                purchase_date=lot.purchase_date, shares=lot.shares,
                share_source=lot.share_source, dedup_ordinal=lot.dedup_ordinal,
                grant_date=lot.grant_date,
            )
            for lot in parsed.lots
        ]
        existing_hashes = set(
            (
                await db.execute(
                    select(EsppLot.dedup_hash).where(
                        EsppLot.dedup_hash.in_(lot_hashes),
                        EsppLot.connection_id == connection_id,
                    )
                )
            ).scalars().all()
        )
        known_indices.update(i for i, h in enumerate(lot_hashes) if h in existing_hashes)

    new_lots: list[FidelityPreviewLotOut] = []
    duplicate_count = 0
    for i, lot in enumerate(parsed.lots):
        if i in known_indices:
            duplicate_count += 1
        else:
            new_lots.append(
                FidelityPreviewLotOut(
                    purchase_date=lot.purchase_date.isoformat(),
                    shares=float(lot.shares),
                    cost_basis_per_share_usd=float(lot.cost_basis_per_share),
                    cost_basis_total_usd=float(lot.cost_basis),
                    share_source=lot.share_source,
                    grant_date=lot.grant_date.isoformat() if lot.grant_date else None,
                    source_currency=lot.source_currency,
                )
            )

    return FidelityPreviewOut(
        new_lots=new_lots,
        duplicate_count=duplicate_count,
        total_in_file=len(parsed.lots),
        source_currency=parsed.source_currency,
        file_already_imported=file_already_imported,
    )


@router.post("/fidelity/import/confirm", response_model=FidelityImportResult)
async def fidelity_import_confirm(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityImportResult:
    """Import Fidelity ESPP lots idempotently and trigger historical price backfill."""
    file_bytes = await read_upload(file)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    try:
        parsed = parse_usd_open_lots_csv(file_bytes)
    except FidelityCurrencyError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc
    except FidelityCsvError as exc:
        raise HTTPException(status_code=400, detail=f"CSV parsing failed: {exc}") from exc

    # 1. Get or create the fidelity-espp connection (own transaction)
    async with db.begin():
        conn = await _get_or_create_fidelity_connection(user.id, db)
        connection_id = conn.id

    # 2. Import lots — FidelityESPPProvider.import_lots manages its own transaction
    provider: FidelityESPPProvider = _PROVIDERS[_PLUGIN_ID]  # type: ignore[assignment]
    try:
        inserted, skipped = await provider.import_lots(
            connection_id=connection_id,
            lots=parsed.lots,
            source_currency=parsed.source_currency,
            file_hash=file_hash,
            db=db,
            ticker=parsed.ticker,
        )
    except LegacyFidelityLotsError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc

    # 3. Backfill price history when new lots were added
    if inserted > 0 and parsed.lots:
        earliest_date = min(lot.purchase_date for lot in parsed.lots)
        try:
            await backfill_price_history(earliest_date, db)
        except Exception as exc:  # the lots are committed; prices can follow later
            log.warning("Price backfill failed (non-fatal): %s", exc, exc_info=True)

    return FidelityImportResult(inserted=inserted, duplicates=skipped)


# ── Read endpoints ─────────────────────────────────────────────────────────────

@router.get("/fidelity/kpis", response_model=FidelityKpisOut)
async def fidelity_kpis(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityKpisOut:
    """USD cost basis and gains translated to EUR at the same current FX rate."""
    # Price refresh first — must precede any other SQL (owns its transaction lifecycle)
    try:
        price: LatestPriceRow | None = await get_latest_price(db)
    except Exception as exc:  # render without a price rather than fail
        log.warning("get_latest_price failed (degraded): %s", exc, exc_info=True)
        price = None

    conn = await _get_fidelity_connection(user.id, db)
    if conn is None:
        return FidelityKpisOut(
            total_shares=0.0,
            invested_eur=0.0,
            current_value_eur=None,
            gain_loss_eur=None,
            gain_loss_pct=None,
            msft_price_usd=None,
            usd_eur_rate=None,
            last_price_date=None,
            price_stale=True,
            as_of_date=local_today().isoformat(),
        )

    lots = (
        await db.execute(select(EsppLot).where(EsppLot.connection_id == conn.id))
    ).scalars().all()

    valuation = value_fidelity(lots, price)

    return FidelityKpisOut(
        total_shares=float(valuation.total_shares),
        invested_eur=_rounded(valuation.invested_eur),
        cost_basis_usd=_rounded(valuation.cost_basis_usd),
        requires_usd_reimport=valuation.requires_usd_reimport,
        current_value_eur=_rounded(valuation.current_value_eur),
        gain_loss_eur=_rounded(valuation.gain_loss_eur),
        gain_loss_pct=_rounded(valuation.gain_loss_pct, 4),
        msft_price_usd=round(price.close_usd, 4) if price else None,
        usd_eur_rate=round(price.fx_eur_usd, 6) if price else None,
        last_price_date=price.price_date.isoformat() if price else None,
        price_stale=price.price_stale if price else True,
        as_of_date=local_today().isoformat(),
    )


def _rounded(value: Decimal | None, digits: int = 2) -> float | None:
    return round(float(value), digits) if value is not None else None


@router.get("/fidelity/evolution", response_model=FidelityEvolutionOut)
async def fidelity_evolution(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityEvolutionOut:
    """Value + contributions time series.

    Range: from the earliest lot purchase_date to today.
    Granularity: one point per actual MSFT trading day (daily market-day
    resolution).  Weekly only for extreme ranges > 6 years (~2200 days).

    EUR conversion uses a SINGLE latest EUR/USD rate applied to all historical
    dates (owner-approved Model-A).  The rate is fetched live from the Yahoo
    EURUSD=X snapshot; fallback: most recent stored fx_eur_usd.  This removes
    any dependency on per-day FX availability (Fridays, null bars are no longer
    dropped).
    """
    conn = await _get_fidelity_connection(user.id, db)
    if conn is None:
        return FidelityEvolutionOut(value_series=[], contributions_series=[])

    lots = (
        await db.execute(
            select(EsppLot)
            .where(EsppLot.connection_id == conn.id)
            .order_by(EsppLot.purchase_date)
        )
    ).scalars().all()

    if not lots:
        return FidelityEvolutionOut(value_series=[], contributions_series=[])

    min_date = min(lot.purchase_date for lot in lots)
    max_date = local_today()

    def _price_query():
        return (
            select(PriceHistory)
            .where(
                PriceHistory.ticker == "MSFT",
                PriceHistory.price_date >= min_date,
                PriceHistory.price_date <= max_date,
            )
            .order_by(PriceHistory.price_date)
        )

    # Commit the read autobegin transaction before calling topup_recent_prices,
    # which manages its own transaction lifecycle.
    await db.commit()
    try:
        await topup_recent_prices(db)
    except Exception as exc:  # serve the stored series
        log.warning("topup_recent_prices failed (non-fatal): %s", exc, exc_info=True)

    prices: Sequence[PriceHistory] = (await db.execute(_price_query())).scalars().all()

    # Backfill trigger:
    # (a) Empty: first import, populate from network.
    # (b) Friday gap: < 50 % of expected Fridays present → intersection bug recovery.
    #     Minimum sample of 30 rows avoids false-positives on tiny test fixtures.
    needs_backfill = not prices
    if not needs_backfill and len(prices) >= 30:
        expected_fridays = max(1, (max_date - min_date).days // 7)
        actual_fridays = sum(1 for p in prices if p.price_date.weekday() == 4)
        if actual_fridays < expected_fridays // 2:
            log.info(
                "fidelity_evolution: Friday gap detected (%d/%d) — triggering gap-recovery backfill",
                actual_fridays, expected_fridays,
            )
            needs_backfill = True

    if needs_backfill:
        await db.commit()
        try:
            await backfill_price_history(min_date, db)
        except Exception as exc:  # serve the stored series
            log.warning("Backfill failed (non-fatal): %s", exc, exc_info=True)
        prices = (await db.execute(_price_query())).scalars().all()

    # Single latest EUR/USD rate for all historical conversions (Model-A).
    # Try Yahoo live snapshot first; fall back to latest stored fx_eur_usd.
    latest_fx_eur_usd: float | None = None
    if prices:
        latest_fx_eur_usd = float(max(prices, key=lambda p: p.price_date).fx_eur_usd)
    try:
        live_fx = await get_current_fx_rate()
        if live_fx is not None:
            latest_fx_eur_usd = live_fx
    except Exception as exc:  # fall back to the stored FX
        log.warning("get_current_fx_rate failed (using stored FX): %s", exc, exc_info=True)

    price_map: dict[date, tuple[float, float]] = {
        p.price_date: (float(p.close_usd), latest_fx_eur_usd or float(p.fx_eur_usd))
        for p in prices
    }

    value_series, contributions_series = compute_evolution_series(
        lots, price_map, min_date, max_date
    )
    return FidelityEvolutionOut(
        value_series=value_series,
        contributions_series=contributions_series,
    )


@router.get("/fidelity/lots", response_model=FidelityLotsOut)
async def fidelity_lots(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityLotsOut:
    """Per-lot detail with current market valuation."""
    # Price refresh first — must precede any other SQL
    try:
        price: LatestPriceRow | None = await get_latest_price(db)
    except Exception as exc:  # render without a price rather than fail
        log.warning("get_latest_price failed (degraded): %s", exc, exc_info=True)
        price = None

    conn = await _get_fidelity_connection(user.id, db)
    if conn is None:
        return FidelityLotsOut(lots=[])

    lots = (
        await db.execute(
            select(EsppLot)
            .where(EsppLot.connection_id == conn.id)
            .order_by(EsppLot.purchase_date)
        )
    ).scalars().all()

    result: list[FidelityLotOut] = []
    for lot in lots:
        valuation = value_fidelity([lot], price)
        fx = Decimal(str(price.fx_eur_usd)) if price else None
        cost_per = cost_in_eur(lot.cost_basis_per_share, lot.source_currency, fx)

        result.append(
            FidelityLotOut(
                id=lot.id,
                purchase_date=lot.purchase_date.isoformat(),
                shares=float(lot.shares),
                cost_basis_per_share_eur=_rounded(cost_per, 6),
                cost_basis_total_eur=_rounded(valuation.invested_eur),
                current_value_eur=_rounded(valuation.current_value_eur),
                gain_loss_eur=_rounded(valuation.gain_loss_eur),
                gain_loss_pct=_rounded(valuation.gain_loss_pct, 4),
                share_source=lot.share_source,
                grant_date=lot.grant_date.isoformat() if lot.grant_date else None,
            )
        )

    return FidelityLotsOut(lots=result)


@router.get("/fidelity/reminder", response_model=FidelityReminderOut)
async def fidelity_reminder(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FidelityReminderOut:
    """ESPP upload-reminder: overdue when the quarter-end purchase hasn't been imported.

    - No fidelity connection → overdue=False (nothing to remind).
    - Within the 5-day grace window after the quarter-end → overdue=False.
    - Grace passed and no SP lot with purchase_date ≥ expected → overdue=True.
    - Always returns HTTP 200 (graceful).
    """
    conn = await _get_fidelity_connection(user.id, db)
    if conn is None:
        return FidelityReminderOut(overdue=False)

    lots = (
        await db.execute(
            select(EsppLot).where(
                EsppLot.connection_id == conn.id,
                EsppLot.share_source == "SP",
            )
        )
    ).scalars().all()

    return compute_espp_reminder(lots, today=_get_today())
