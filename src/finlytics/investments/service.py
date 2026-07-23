"""Investment service orchestrator.

Resolves active connections for a user, decrypts tokens, calls the
IndexaProvider, aggregates multi-account results, and maintains a
DB-backed 24-hour cache per connection.

Cache behaviour:
  FRESH  (fetched_at < 24h): return cached payload immediately.
  STALE  (fetched_at >= 24h): return stale payload immediately; schedule a
         FastAPI BackgroundTask to re-fetch and update the DB cache.
  MISSING (no cache row): fetch live, store in DB, return (first load is slower).
"""
from __future__ import annotations

import dataclasses
import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.schemas import (
    CashInvestedSplit,
    ConnectionOut,
    ContributionEventOut,
    DiscoveredAccountOut,
    DrawdownOut,
    InvestmentHoldingOut,
    InvestmentPortfolioOut,
    InvestmentReturns,
    MonthlyReturnRow,
    ValuePoint,
)
from finlytics.db.models import InvestmentConnection, InvestmentPortfolioCache
from finlytics.db.session import async_session_factory
from finlytics.investments.base import (
    InvestmentProvider,
    NormalizedCashInvested,
    NormalizedContributionEvent,
    NormalizedDrawdown,
    NormalizedHolding,
    NormalizedMonthlyReturnRow,
    NormalizedPerformance,
    NormalizedPortfolio,
    NormalizedReturns,
    NormalizedValuePoint,
)
from finlytics.investments.crypto import (
    EncryptionNotConfiguredError,
    decrypt_token,
    encrypt_token,
)
from finlytics.investments.indexa import IndexaAuthError, IndexaConnectionError, IndexaProvider
from finlytics.investments.fidelity import FidelityESPPProvider

log = logging.getLogger(__name__)

_CACHE_MAX_AGE = 86400.0  # seconds (24 hours)
# Bump this whenever the NormalizedPortfolio JSON shape changes (e.g. new top-level
# fields, renamed keys, changed nesting).  Any cached row that lacks this version
# or carries a different value is treated as a cache MISS → synchronous live refetch.
# Existing rows written by pre-contribution_events code have no _schema_version key,
# so they are automatically invalidated on first request after this deploy.
_PORTFOLIO_SCHEMA_VERSION = 2
_refresh_in_flight: set[int] = set()  # connection IDs with an active background refresh

# Registry keyed by plugin_id — add new providers here.
# live_api providers (token_enc != NULL) are aggregated in get_portfolio().
# statement_import providers (token_enc IS NULL) have their own endpoints.
_PROVIDERS: dict[str, InvestmentProvider] = {
    "indexa-capital": IndexaProvider(),
    "fidelity-espp": FidelityESPPProvider(),
}


def _get_provider(plugin_id: str) -> InvestmentProvider:
    """Resolve a provider by plugin_id; raises ValueError for unknown ids."""
    provider = _PROVIDERS.get(plugin_id)
    if provider is None:
        raise ValueError(f"Unknown investment plugin_id: {plugin_id!r}")
    return provider


class NoValidAccountsError(Exception):
    """Raised when account_numbers contains no accounts owned by the token."""


# ── Account masking ───────────────────────────────────────────────────────────


def _mask_account(account_number: str) -> str:
    """Preserve first 3 chars + ••• + last 2 chars (Romanoff §2)."""
    if len(account_number) <= 5:
        tail = account_number[-min(2, len(account_number)):]
        return "•••" + tail
    return account_number[:3] + "•••" + account_number[-2:]


# ── Cache helpers ─────────────────────────────────────────────────────────────


def clear_connection_cache(connection_id: int) -> None:
    """Evict a connection from the in-flight refresh guard.

    The DB cache row is cleaned up automatically by ON DELETE CASCADE when the
    parent InvestmentConnection is deleted — no explicit DB deletion needed here.
    """
    _refresh_in_flight.discard(connection_id)


# ── Serialisation helpers ─────────────────────────────────────────────────────


def _serialize_portfolio(portfolio: NormalizedPortfolio) -> dict:
    """Convert NormalizedPortfolio to a JSON-safe dict for DB storage."""
    data = dataclasses.asdict(portfolio)
    data["_schema_version"] = _PORTFOLIO_SCHEMA_VERSION
    return data


def _deserialize_portfolio(data: dict) -> NormalizedPortfolio:
    """Reconstruct NormalizedPortfolio from a JSON-loaded dict (DB cache row).

    Private keys such as ``_schema_version`` are silently ignored: the function
    extracts only the specific fields it needs rather than splatting the whole
    dict into the dataclass constructor, so unknown keys never cause errors.
    """
    perf_data = data.get("performance")
    performance: NormalizedPerformance | None = None
    if perf_data is not None:
        returns_data = perf_data.get("returns") or {}
        drawdown_data = perf_data.get("drawdown")
        ci_data = perf_data.get("cash_invested")

        # JSON keys are always strings; months_pct/months_eur use int keys in code.
        monthly_returns = [
            NormalizedMonthlyReturnRow(
                year=r["year"],
                months_pct={int(k): v for k, v in (r.get("months_pct") or {}).items()},
                months_eur={int(k): v for k, v in (r.get("months_eur") or {}).items()},
                total_pct=r.get("total_pct"),
                total_eur=r.get("total_eur"),
                benchmark_pct=r.get("benchmark_pct"),
            )
            for r in (perf_data.get("monthly_returns") or [])
        ]

        performance = NormalizedPerformance(
            total_value=perf_data["total_value"],
            returns=NormalizedReturns(**returns_data),
            value_series=[
                NormalizedValuePoint(**vp)
                for vp in (perf_data.get("value_series") or [])
            ],
            contributions_series=[
                NormalizedValuePoint(**vp)
                for vp in (perf_data.get("contributions_series") or [])
            ],
            contribution_events=[
                NormalizedContributionEvent(**ev)
                for ev in (perf_data.get("contribution_events") or [])
            ],
            monthly_returns=monthly_returns,
            drawdown=NormalizedDrawdown(**drawdown_data) if drawdown_data else None,
            cash_invested=NormalizedCashInvested(**ci_data) if ci_data else None,
        )

    return NormalizedPortfolio(
        holdings=[NormalizedHolding(**h) for h in (data.get("holdings") or [])],
        total_value=data["total_value"],
        total_invested=data.get("total_invested"),
        total_gain_loss=data.get("total_gain_loss"),
        performance=performance,
    )


async def _get_db_cache(
    connection_id: int, db: AsyncSession
) -> tuple[NormalizedPortfolio, datetime] | None:
    """Return (portfolio, fetched_at) from DB cache, or None if not found."""
    row = (
        await db.execute(
            select(InvestmentPortfolioCache).where(
                InvestmentPortfolioCache.connection_id == connection_id
            )
        )
    ).scalar_one_or_none()

    if row is None:
        return None

    if row.payload.get("_schema_version") != _PORTFOLIO_SCHEMA_VERSION:
        # Version mismatch: cached payload was written by an older code shape.
        # Delete the stale row NOW and flush so the caller can INSERT a fresh one
        # for the same connection_id without hitting the unique constraint.
        await db.delete(row)
        await db.flush()
        return None

    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)

    return _deserialize_portfolio(row.payload), fetched_at


async def _bg_refresh_connection(
    connection_id: int,
    token_enc: str,
    account_label_masked: str | None,
    plugin_id: str,
) -> None:
    """Background task: re-fetch portfolio from the live API and update DB cache.

    Runs after the HTTP response is sent; creates its own DB session.
    """
    if connection_id in _refresh_in_flight:
        log.debug("Background refresh already in-flight for connection %d — skipping", connection_id)
        return
    _refresh_in_flight.add(connection_id)
    log.info("Background refresh started for connection %d", connection_id)
    try:
        try:
            token = decrypt_token(token_enc)
        except EncryptionNotConfiguredError:
            log.warning("Background refresh: encryption key missing for connection %d", connection_id)
            return

        try:
            validation = await _get_provider(plugin_id).validate_token(token)
        except (IndexaAuthError, IndexaConnectionError) as exc:
            log.warning("Background refresh: token validation failed for connection %d: %s", connection_id, exc)
            return

        acc_by_mask = {_mask_account(a.account_number): a for a in validation.accounts}
        acc = acc_by_mask.get(account_label_masked)
        if acc is None:
            log.warning("Background refresh: no account matches mask %r for connection %d", account_label_masked, connection_id)
            return

        try:
            portfolio = await _get_provider(plugin_id).get_portfolio(token, [acc.account_number])
        except (IndexaAuthError, IndexaConnectionError) as exc:
            log.warning("Background refresh: portfolio fetch failed for connection %d: %s", connection_id, exc)
            return

        now_dt = datetime.now(timezone.utc)
        payload = _serialize_portfolio(portfolio)

        async with async_session_factory() as bg_db:
            async with bg_db.begin():
                cache_row = (
                    await bg_db.execute(
                        select(InvestmentPortfolioCache).where(
                            InvestmentPortfolioCache.connection_id == connection_id
                        )
                    )
                ).scalar_one_or_none()

                if cache_row is None:
                    bg_db.add(InvestmentPortfolioCache(
                        connection_id=connection_id,
                        payload=payload,
                        fetched_at=now_dt,
                    ))
                else:
                    cache_row.payload = payload
                    cache_row.fetched_at = now_dt

                conn_row = (
                    await bg_db.execute(
                        select(InvestmentConnection).where(
                            InvestmentConnection.id == connection_id
                        )
                    )
                ).scalar_one_or_none()
                if conn_row is not None:
                    conn_row.last_synced_at = now_dt

        log.info("Background refresh completed for connection %d", connection_id)
    except Exception as exc:
        log.warning("Background refresh: unexpected error for connection %d: %s", connection_id, exc, exc_info=True)
    finally:
        _refresh_in_flight.discard(connection_id)


# ── Public service functions ──────────────────────────────────────────────────


async def validate_token_for_wizard(token: str) -> list[DiscoveredAccountOut]:
    """Validate *token* via Indexa /users/me; return discovered accounts.

    Stores NOTHING — no DB writes, no encryption.  Raises IndexaAuthError or
    IndexaConnectionError on failure (propagated to API layer for error responses).
    """
    validation = await _PROVIDERS["indexa-capital"].validate_token(token)
    return [
        DiscoveredAccountOut(
            account_number=acc.account_number,
            account_number_masked=_mask_account(acc.account_number),
            type=acc.account_type,
            status=acc.account_status,
        )
        for acc in validation.accounts
    ]


async def connect_plugin(
    user_id: int,
    plugin_id: str,
    token: str,
    account_numbers: list[str],
    db: AsyncSession,
) -> list[ConnectionOut]:
    """Re-validate *token*, persist rows only for *account_numbers* owned by the token.

    Server-side ownership check: any number in *account_numbers* not present in
    the token's actual accounts is silently dropped.  If the intersection is
    empty, raises NoValidAccountsError.

    Raises:
        IndexaAuthError: token rejected (401/403).
        IndexaConnectionError: network / timeout error.
        NoValidAccountsError: no account_numbers match the token's accounts.
        EncryptionNotConfiguredError: FINLYTICS_ENCRYPTION_KEY absent / invalid.
    """
    validation = await _get_provider(plugin_id).validate_token(token)
    owned = {acc.account_number: acc for acc in validation.accounts}
    requested = set(account_numbers)
    selected = [acc for num, acc in owned.items() if num in requested]

    if not selected:
        raise NoValidAccountsError(
            "None of the requested account_numbers belong to this token."
        )

    token_enc = encrypt_token(token)  # raises EncryptionNotConfiguredError if key missing

    out: list[ConnectionOut] = []

    async with db.begin():
        for acc in selected:
            masked = _mask_account(acc.account_number)

            existing = (
                await db.execute(
                    select(InvestmentConnection).where(
                        InvestmentConnection.user_id == user_id,
                        InvestmentConnection.plugin_id == plugin_id,
                        InvestmentConnection.account_label_masked == masked,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.token_enc = token_enc
                existing.status = "active"
                conn = existing
            else:
                conn = InvestmentConnection(
                    user_id=user_id,
                    plugin_id=plugin_id,
                    status="active",
                    account_label_masked=masked,
                    token_enc=token_enc,
                )
                db.add(conn)
                await db.flush()

            out.append(
                ConnectionOut(
                    id=conn.id,
                    plugin_id=conn.plugin_id,
                    status=conn.status,
                    account_label_masked=conn.account_label_masked,
                    created_at=conn.created_at,
                    last_synced_at=conn.last_synced_at,
                )
            )

    return out


async def list_connections(user_id: int, db: AsyncSession) -> list[ConnectionOut]:
    """Return all connections for *user_id* (masked labels only — token excluded)."""
    rows = (
        await db.execute(
            select(InvestmentConnection)
            .where(InvestmentConnection.user_id == user_id)
            .order_by(InvestmentConnection.created_at)
        )
    ).scalars().all()

    return [
        ConnectionOut(
            id=r.id,
            plugin_id=r.plugin_id,
            status=r.status,
            account_label_masked=r.account_label_masked,
            created_at=r.created_at,
            last_synced_at=r.last_synced_at,
        )
        for r in rows
    ]


async def delete_connection(
    connection_id: int, user_id: int, db: AsyncSession
) -> bool:
    """Hard-delete the connection row (and its ciphertext).  Returns False if not found."""
    async with db.begin():
        row = (
            await db.execute(
                select(InvestmentConnection).where(
                    InvestmentConnection.id == connection_id,
                    InvestmentConnection.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

        if row is None:
            return False
        await db.delete(row)

    clear_connection_cache(connection_id)
    return True


async def get_portfolio(
    user_id: int,
    db: AsyncSession,
    background_tasks: BackgroundTasks | None = None,
) -> InvestmentPortfolioOut:
    """Aggregate portfolio across all active connections.

    Cache behaviour:
      FRESH  (age < 24h): return cached payload, no live API call.
      STALE  (age >= 24h): return stale cached payload immediately; if
             background_tasks is provided, schedule an async refresh so the
             next open is fresh. cache_stale=True signals this to the caller.
      MISSING (no cache row): fetch live from Indexa, store in DB, return
             (this first load is unavoidably slower).

    Raises EncryptionNotConfiguredError if decryption is impossible (propagates
    to API layer which returns 503).  Per-connection Indexa errors are logged
    and silently skipped so a single bad connection doesn't kill the whole page.
    """
    connections = (
        await db.execute(
            select(InvestmentConnection).where(
                InvestmentConnection.user_id == user_id,
                InvestmentConnection.status == "active",
            )
        )
    ).scalars().all()

    if not connections:
        return InvestmentPortfolioOut(
            total_value=0.0,
            total_invested=None,
            total_gain_loss=None,
            total_gain_loss_pct=None,
            currency="EUR",
            holdings=[],
            plugins_connected=0,
            last_updated=None,
        )

    # Group by token_enc; skip statement_import providers (token_enc IS NULL).
    by_token: dict[str, list[InvestmentConnection]] = defaultdict(list)
    for conn in connections:
        if conn.token_enc is not None:
            by_token[conn.token_enc].append(conn)

    fetched: list[tuple[InvestmentConnection, NormalizedPortfolio]] = []
    status_errors: list[InvestmentConnection] = []
    synced_now: list[InvestmentConnection] = []
    stale_connections: list[InvestmentConnection] = []
    cache_rows_added = False
    any_cached = False
    any_stale = False
    oldest_cache_ts: datetime | None = None
    now_dt = datetime.now(timezone.utc)

    for token_enc, group in by_token.items():
        need_fetch: list[InvestmentConnection] = []

        for conn in group:
            cached = await _get_db_cache(conn.id, db)
            if cached is None:
                need_fetch.append(conn)
            else:
                portfolio, fetched_at = cached
                age_s = (now_dt - fetched_at).total_seconds()
                if age_s < _CACHE_MAX_AGE:
                    # Fresh: return immediately, no live call
                    fetched.append((conn, portfolio))
                    any_cached = True
                    if oldest_cache_ts is None or fetched_at < oldest_cache_ts:
                        oldest_cache_ts = fetched_at
                else:
                    # Stale: return cached payload now, refresh async
                    fetched.append((conn, portfolio))
                    stale_connections.append(conn)
                    any_cached = True
                    any_stale = True
                    if oldest_cache_ts is None or fetched_at < oldest_cache_ts:
                        oldest_cache_ts = fetched_at

        if not need_fetch:
            continue

        # Live fetch for connections with no cache row
        try:
            token = decrypt_token(token_enc)
        except EncryptionNotConfiguredError:
            raise  # Let the API layer surface a 503

        # Resolve account numbers from /users/me (once per unique token)
        try:
            validation = await _get_provider(group[0].plugin_id).validate_token(token)
        except IndexaAuthError:
            status_errors.extend(need_fetch)
            log.warning(
                "Indexa auth error during portfolio fetch; "
                "marking %d connection(s) as error (ids: %s)",
                len(need_fetch),
                [c.id for c in need_fetch],
            )
            continue
        except IndexaConnectionError as exc:
            log.warning("Indexa connection error during portfolio fetch: %s", exc)
            continue

        acc_by_mask = {
            _mask_account(a.account_number): a for a in validation.accounts
        }

        for conn in need_fetch:
            acc = acc_by_mask.get(conn.account_label_masked)
            if acc is None:
                log.warning(
                    "No Indexa account matches mask %r for connection %d — skipping",
                    conn.account_label_masked,
                    conn.id,
                )
                continue

            try:
                portfolio = await _get_provider(conn.plugin_id).get_portfolio(
                    token, [acc.account_number]
                )
            except IndexaAuthError:
                status_errors.append(conn)
                continue
            except IndexaConnectionError as exc:
                log.warning("Indexa error for connection %d: %s", conn.id, exc)
                continue

            # Cache miss → INSERT new row (no SELECT needed; _get_db_cache returned None)
            db.add(InvestmentPortfolioCache(
                connection_id=conn.id,
                payload=_serialize_portfolio(portfolio),
                fetched_at=now_dt,
            ))
            cache_rows_added = True
            fetched.append((conn, portfolio))
            synced_now.append(conn)

    # Persist: status updates + last_synced_at + new cache rows — one commit
    if status_errors or synced_now or cache_rows_added:
        for conn in status_errors:
            conn.status = "error"
        for conn in synced_now:
            conn.last_synced_at = now_dt
        await db.commit()

    # Schedule async refresh for stale connections (response already ready to send)
    if background_tasks is not None and stale_connections:
        for conn in stale_connections:
            if conn.id not in _refresh_in_flight and conn.token_enc:
                background_tasks.add_task(
                    _bg_refresh_connection,
                    conn.id,
                    conn.token_enc,
                    conn.account_label_masked,
                    conn.plugin_id,
                )

    result = _aggregate(fetched, len(connections))

    # Attach cache freshness metadata (additive/optional fields)
    if any_cached and oldest_cache_ts is not None:
        result.cached_at = oldest_cache_ts.isoformat()
        result.cache_stale = any_stale

    return result


# ── Aggregation ───────────────────────────────────────────────────────────────


def _aggregate(
    fetched: list[tuple[InvestmentConnection, NormalizedPortfolio]],
    total_connections: int,
) -> InvestmentPortfolioOut:
    if not fetched:
        return InvestmentPortfolioOut(
            total_value=0.0,
            total_invested=None,
            total_gain_loss=None,
            total_gain_loss_pct=None,
            currency="EUR",
            holdings=[],
            plugins_connected=total_connections,
            last_updated=None,
        )

    now_str = datetime.now(timezone.utc).isoformat()
    all_holdings: list[InvestmentHoldingOut] = []
    total_value = 0.0
    total_invested = 0.0
    total_gain_loss = 0.0
    has_invested = False

    agg_pl = 0.0
    agg_invested_ret = 0.0
    agg_money_return = 0.0
    agg_aportaciones: float | None = None
    agg_retenciones: float | None = None
    agg_rentabilidad_eur: float | None = None
    has_returns = False
    first_perf_returns = None
    first_perf = None

    series_by_date: dict[str, float] = {}
    contrib_by_date: dict[str, float] = {}
    events_by_date: dict[str, float] = {}
    has_series = False
    has_contrib = False
    has_events = False

    ci_cash = ci_instr_amt = ci_instr_cost = ci_total = 0.0
    has_ci = False

    single_account = len(fetched) == 1

    for idx, (conn, portfolio) in enumerate(fetched):
        for h in portfolio.holdings:
            all_holdings.append(
                InvestmentHoldingOut(
                    plugin_id=conn.plugin_id,
                    name=h.name,
                    ticker=h.ticker,
                    asset_class=h.asset_class,
                    units=h.units,
                    current_value=h.current_value,
                    cost_basis=h.cost_basis,
                    currency="EUR",
                    gain_loss=h.gain_loss,
                    gain_loss_pct=h.gain_loss_pct,
                    last_updated=now_str,
                )
            )

        total_value += portfolio.total_value
        if portfolio.total_invested is not None:
            total_invested += portfolio.total_invested
            has_invested = True
        if portfolio.total_gain_loss is not None:
            total_gain_loss += portfolio.total_gain_loss

        if portfolio.performance:
            perf = portfolio.performance
            if idx == 0:
                first_perf_returns = perf.returns
                first_perf = perf
            if perf.returns.pl is not None:
                agg_pl += perf.returns.pl
                has_returns = True
            if perf.returns.invested is not None:
                agg_invested_ret += perf.returns.invested
            if perf.returns.money_return is not None:
                agg_money_return += perf.returns.money_return
                has_returns = True
            # Summable box numbers
            if perf.returns.aportaciones is not None:
                agg_aportaciones = (agg_aportaciones or 0.0) + perf.returns.aportaciones
                has_returns = True
            if perf.returns.retenciones is not None:
                agg_retenciones = (agg_retenciones or 0.0) + perf.returns.retenciones
                has_returns = True
            if perf.returns.rentabilidad_eur is not None:
                agg_rentabilidad_eur = (agg_rentabilidad_eur or 0.0) + perf.returns.rentabilidad_eur
                has_returns = True
            for vp in perf.value_series:
                series_by_date[vp.date] = series_by_date.get(vp.date, 0.0) + vp.value
                has_series = True
            for vp in perf.contributions_series:
                contrib_by_date[vp.date] = contrib_by_date.get(vp.date, 0.0) + vp.value
                has_contrib = True
            for ev in perf.contribution_events:
                events_by_date[ev.date] = events_by_date.get(ev.date, 0.0) + ev.amount
                has_events = True
            if perf.cash_invested:
                ci = perf.cash_invested
                ci_cash += ci.cash_amount
                ci_instr_amt += ci.instruments_amount
                ci_instr_cost += ci.instruments_cost
                ci_total += ci.total_amount
                has_ci = True

    returns: InvestmentReturns | None = None
    if has_returns:
        returns = InvestmentReturns(
            twr_annual=first_perf_returns.twr_annual if single_account and first_perf_returns else None,
            twr_total=first_perf_returns.twr_total if single_account and first_perf_returns else None,
            twr_last_week=first_perf_returns.twr_last_week if single_account and first_perf_returns else None,
            twr_last_month=first_perf_returns.twr_last_month if single_account and first_perf_returns else None,
            twr_last_year=first_perf_returns.twr_last_year if single_account and first_perf_returns else None,
            volatility=first_perf_returns.volatility if single_account and first_perf_returns else None,
            money_return=agg_money_return or None,
            money_return_annual=first_perf_returns.money_return_annual if single_account and first_perf_returns else None,
            xirr=first_perf_returns.xirr if single_account and first_perf_returns else None,
            pl=agg_pl,
            invested=agg_invested_ret or None,
            aportaciones=agg_aportaciones,
            retenciones=agg_retenciones,
            rentabilidad_eur=agg_rentabilidad_eur,
            rentabilidad_pct=first_perf_returns.rentabilidad_pct if single_account and first_perf_returns else None,
            sharpe_ratio=first_perf_returns.sharpe_ratio if single_account and first_perf_returns else None,
        )

    value_series = (
        [ValuePoint(date=d, value=v) for d, v in sorted(series_by_date.items())]
        if has_series
        else []
    )

    contributions_series = (
        [ValuePoint(date=d, value=v) for d, v in sorted(contrib_by_date.items())]
        if has_contrib
        else []
    )

    # contribution_events: aggregate by date (sum deltas), recompute cumulative
    contribution_events_out: list[ContributionEventOut] = []
    if has_events:
        running = 0.0
        for d, amt in sorted(events_by_date.items()):
            amt_r = round(amt, 2)
            if amt_r == 0.0:
                continue
            running = round(running + amt_r, 2)
            contribution_events_out.append(ContributionEventOut(
                date=d,
                amount=amt_r,
                cumulative=running,
                type="contribution" if amt_r > 0 else "withdrawal",
            ))

    # Monthly returns + drawdown: single-account only (non-aggregatable)
    monthly_returns: list[MonthlyReturnRow] | None = None
    if single_account and first_perf and first_perf.monthly_returns:
        monthly_returns = [
            MonthlyReturnRow(
                year=r.year,
                months_pct=r.months_pct,
                months_eur=r.months_eur,
                total_pct=r.total_pct,
                total_eur=r.total_eur,
                benchmark_pct=r.benchmark_pct,
            )
            for r in first_perf.monthly_returns
        ]

    drawdown_out: DrawdownOut | None = None
    if single_account and first_perf and first_perf.drawdown:
        d = first_perf.drawdown
        drawdown_out = DrawdownOut(
            max_drawdown=d.max_drawdown,
            max_drawdown_eur=d.max_drawdown_eur,
            start_date=d.start_date,
            end_date=d.end_date,
        )

    cash_invested = (
        CashInvestedSplit(
            cash_amount=ci_cash,
            instruments_amount=ci_instr_amt,
            instruments_cost=ci_instr_cost,
            total_amount=ci_total,
        )
        if has_ci
        else None
    )

    invested_val = total_invested if has_invested else None
    gl_val = total_gain_loss if all_holdings else None
    gl_pct = (
        (total_gain_loss / total_invested)
        if (has_invested and total_invested and all_holdings)
        else None
    )

    return InvestmentPortfolioOut(
        total_value=total_value,
        total_invested=invested_val,
        total_gain_loss=gl_val,
        total_gain_loss_pct=gl_pct,
        currency="EUR",
        holdings=all_holdings,
        plugins_connected=total_connections,
        last_updated=now_str,
        returns=returns,
        value_series=value_series,
        contributions_series=contributions_series,
        contribution_events=contribution_events_out,
        monthly_returns=monthly_returns,
        drawdown=drawdown_out,
        cash_invested=cash_invested,
    )
