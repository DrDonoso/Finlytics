"""Investment service orchestrator.

Resolves active connections for a user, decrypts tokens, calls the
IndexaProvider, aggregates multi-account results, and maintains a
5-minute in-memory TTL cache keyed by connection_id.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.schemas import (
    CashInvestedSplit,
    ConnectionOut,
    DiscoveredAccountOut,
    InvestmentHoldingOut,
    InvestmentPortfolioOut,
    InvestmentReturns,
    ValuePoint,
)
from finlytics.db.models import InvestmentConnection
from finlytics.investments.base import NormalizedPortfolio
from finlytics.investments.crypto import (
    EncryptionNotConfiguredError,
    decrypt_token,
    encrypt_token,
)
from finlytics.investments.indexa import IndexaAuthError, IndexaConnectionError, IndexaProvider

log = logging.getLogger(__name__)

_CACHE_TTL = 300.0  # seconds (5 minutes)
_portfolio_cache: dict[int, tuple[float, NormalizedPortfolio]] = {}

_provider = IndexaProvider()


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
    """Evict a single connection from the portfolio cache."""
    _portfolio_cache.pop(connection_id, None)


def _get_cached(connection_id: int) -> NormalizedPortfolio | None:
    entry = _portfolio_cache.get(connection_id)
    if entry and (time.monotonic() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _put_cache(connection_id: int, portfolio: NormalizedPortfolio) -> None:
    _portfolio_cache[connection_id] = (time.monotonic(), portfolio)


# ── Public service functions ──────────────────────────────────────────────────


async def validate_token_for_wizard(token: str) -> list[DiscoveredAccountOut]:
    """Validate *token* via Indexa /users/me; return discovered accounts.

    Stores NOTHING — no DB writes, no encryption.  Raises IndexaAuthError or
    IndexaConnectionError on failure (propagated to API layer for error responses).
    """
    validation = await _provider.validate_token(token)
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
    validation = await _provider.validate_token(token)

    # Server-side ownership filter — never trust client list blindly
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


async def get_portfolio(user_id: int, db: AsyncSession) -> InvestmentPortfolioOut:
    """Aggregate portfolio across all active connections.

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

    # Group by token_enc to call /users/me only once per unique token
    by_token: dict[str, list[InvestmentConnection]] = defaultdict(list)
    for conn in connections:
        by_token[conn.token_enc].append(conn)

    fetched: list[tuple[InvestmentConnection, NormalizedPortfolio]] = []
    status_errors: list[InvestmentConnection] = []
    synced_now: list[InvestmentConnection] = []

    for token_enc, group in by_token.items():
        try:
            token = decrypt_token(token_enc)
        except EncryptionNotConfiguredError:
            raise  # Let the API layer surface a 503

        # Separate cached from stale
        need_fetch: list[InvestmentConnection] = []
        for conn in group:
            hit = _get_cached(conn.id)
            if hit:
                fetched.append((conn, hit))
            else:
                need_fetch.append(conn)

        if not need_fetch:
            continue

        # Resolve account numbers from /users/me (once per unique token)
        try:
            validation = await _provider.validate_token(token)
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
                portfolio = await _provider.get_portfolio(token, [acc.account_number])
            except IndexaAuthError:
                status_errors.append(conn)
                continue
            except IndexaConnectionError as exc:
                log.warning("Indexa error for connection %d: %s", conn.id, exc)
                continue

            _put_cache(conn.id, portfolio)
            fetched.append((conn, portfolio))
            synced_now.append(conn)

    # Persist status / last_synced_at updates in one commit
    now_dt = datetime.now(timezone.utc)
    if status_errors or synced_now:
        for conn in status_errors:
            conn.status = "error"
        for conn in synced_now:
            conn.last_synced_at = now_dt
        await db.commit()

    return _aggregate(fetched, len(connections))


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
    has_returns = False
    first_perf_returns = None

    series_by_date: dict[str, float] = {}
    has_series = False

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
            if perf.returns.pl is not None:
                agg_pl += perf.returns.pl
                has_returns = True
            if perf.returns.invested is not None:
                agg_invested_ret += perf.returns.invested
            for vp in perf.value_series:
                series_by_date[vp.date] = series_by_date.get(vp.date, 0.0) + vp.value
                has_series = True
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
            xirr=first_perf_returns.xirr if single_account and first_perf_returns else None,
            pl=agg_pl,
            invested=agg_invested_ret or None,
        )

    value_series = (
        [ValuePoint(date=d, value=v) for d, v in sorted(series_by_date.items())]
        if has_series
        else []
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
        cash_invested=cash_invested,
    )
