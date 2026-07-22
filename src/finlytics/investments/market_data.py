"""Market data service: Yahoo Chart API (primary) + Stooq/yfinance (fallback).

FX DIRECTION
────────────
Yahoo ``EURUSD=X`` ``regularMarketPrice`` quotes USD per 1 EUR (e.g. 1.0823).
We store ``fx_eur_usd`` as EUR-per-USD:

    fx_eur_usd = 1 / eurusd_quote      ← ~0.9239 when quote = 1.0823

    close_eur = close_usd × fx_eur_usd = close_usd / eurusd_quote

Example: MSFT $450, EURUSD = 1.08 → close_eur = 450 / 1.08 ≈ 416.67 EUR  ✓

Stooq ``eurusd`` / yfinance ``EURUSD=X`` quote the same direction (USD per EUR),
so the same inversion applies to the fallback path.
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import PriceHistory

log = logging.getLogger(__name__)

# ── Yahoo Chart API constants ─────────────────────────────────────────────────

_YAHOO_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)
_YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")

# ── Stooq fallback constant ───────────────────────────────────────────────────

_STOOQ_BASE = "https://stooq.com/q/d/l/"

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
_MSFT_TICKER = "MSFT"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class LatestPriceRow:
    """Snapshot of the most recently available MSFT price."""

    price_date: date
    close_usd: float
    fx_eur_usd: float   # EUR per USD  (= 1 / USD-per-EUR quote)
    close_eur: float
    price_stale: bool   # True when price_date < last business day


# ── Date helpers ──────────────────────────────────────────────────────────────

def _last_business_day(ref: date | None = None) -> date:
    """Return *ref* (default today) rolled back to the most recent Mon–Fri."""
    d = ref or date.today()
    while d.weekday() >= 5:          # 5 = Sat, 6 = Sun
        d -= timedelta(days=1)
    return d


def _to_unix(d: date) -> int:
    """Convert a date to a Unix timestamp (UTC midnight)."""
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


# ── Yahoo Chart API helpers ───────────────────────────────────────────────────

def _parse_yahoo_history(data: dict) -> list[dict]:
    """Parse Yahoo Chart JSON into sorted ``{date, close}`` dicts.

    Skips entries where ``close`` is null or non-positive.
    Dates are derived from Unix timestamps interpreted as UTC.
    """
    try:
        result = data["chart"]["result"][0]
        timestamps: list = result.get("timestamp") or []
        closes: list = result["indicators"]["quote"][0].get("close") or []
        rows: list[dict] = []
        for ts, close in zip(timestamps, closes):
            if close is None or close <= 0:
                continue
            rows.append({
                "date": datetime.fromtimestamp(ts, tz=timezone.utc).date(),
                "close": float(close),
            })
        rows.sort(key=lambda r: r["date"])
        return rows
    except (KeyError, IndexError, TypeError):
        return []


def _parse_yahoo_snapshot(data: dict) -> dict | None:
    """Parse Yahoo Chart meta into a ``{date, close}`` snapshot.

    Returns ``None`` if the response is malformed.
    """
    try:
        meta = data["chart"]["result"][0]["meta"]
        return {
            "date": datetime.fromtimestamp(
                meta["regularMarketTime"], tz=timezone.utc
            ).date(),
            "close": float(meta["regularMarketPrice"]),
        }
    except (KeyError, IndexError, TypeError):
        return None


async def _yahoo_get(symbol: str, params: dict | None = None) -> dict | None:
    """GET Yahoo Chart API for *symbol*.

    Tries ``query1.finance.yahoo.com`` first; on 429 or connection error
    retries on ``query2.finance.yahoo.com``.  Returns raw JSON dict or ``None``
    when both hosts fail.
    """
    headers = {"User-Agent": _YAHOO_UA}
    for host in _YAHOO_HOSTS:
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(
                    url, params=params or {}, headers=headers, follow_redirects=True
                )
                if resp.status_code == 429:
                    log.warning("Yahoo 429 on %s for %r — trying next host", host, symbol)
                    continue
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            log.warning("Yahoo request failed for %r on %s: %s", symbol, host, exc)
    return None


async def _fetch_yahoo_history(symbol: str, start: date | None = None) -> list[dict]:
    """Fetch EOD history from Yahoo Chart API.

    When *start* is given, requests ``period1`` → ``period2=tomorrow``.
    Using tomorrow as period2 (not today midnight) ensures today's in-progress
    bar is included — Yahoo interprets period2=today-midnight as "before today".
    Returns ``[]`` on failure.
    """
    params: dict = {"interval": "1d"}
    if start:
        params["period1"] = _to_unix(start)
        params["period2"] = _to_unix(date.today() + timedelta(days=1))
    data = await _yahoo_get(symbol, params=params)
    if data is None:
        return []
    return _parse_yahoo_history(data)


async def _fetch_yahoo_snapshot(symbol: str) -> dict | None:
    """Fetch the latest price snapshot from Yahoo Chart meta.

    Returns ``{date, close}`` or ``None`` on failure.
    """
    data = await _yahoo_get(symbol)
    if data is None:
        return None
    return _parse_yahoo_snapshot(data)


# ── Stooq + yfinance fallback helpers ────────────────────────────────────────

def _parse_stooq_csv(text: str) -> list[dict]:
    """Parse a Stooq plain-CSV response into ``{date, close}`` dicts.

    Stooq format: ``Date,Open,High,Low,Close,Volume``  (header always present).
    Rows with ``Close <= 0`` are skipped (incomplete trading-day data).
    Returns rows sorted ascending by date.
    """
    rows: list[dict] = []
    reader = csv.DictReader(io.StringIO(text.strip()))
    for row in reader:
        try:
            d = date.fromisoformat(row["Date"])
            close = float(row["Close"])
            if close > 0:
                rows.append({"date": d, "close": close})
        except (KeyError, ValueError):
            continue
    rows.sort(key=lambda r: r["date"])
    return rows


async def _fetch_stooq(symbol: str, start: date | None = None) -> list[dict]:
    """GET EOD history from Stooq for *symbol*. Returns ``[]`` on any failure."""
    params: dict[str, str] = {"s": symbol, "i": "d"}
    if start:
        params["d1"] = start.strftime("%Y%m%d")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_STOOQ_BASE, params=params, follow_redirects=True)
            resp.raise_for_status()
        text = resp.text
        if len(text) < 30 or "No data" in text:
            return []
        return _parse_stooq_csv(text)
    except Exception as exc:
        log.warning("Stooq fetch failed for %r: %s", symbol, exc)
        return []


def _fetch_yfinance_sync(symbol: str, start: date | None) -> list[dict]:
    """Synchronous yfinance download — called via ``run_in_executor``."""
    try:
        import yfinance as yf  # noqa: PLC0415 — late import to keep startup fast
        t = yf.Ticker(symbol)
        kw: dict = {"auto_adjust": True}
        if start:
            kw["start"] = start.isoformat()
        else:
            kw["period"] = "max"
        hist = t.history(**kw)
        if hist.empty:
            return []
        rows: list[dict] = []
        for idx, row in hist.iterrows():
            try:
                d = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
                close = float(row["Close"])
                if close > 0:
                    rows.append({"date": d, "close": close})
            except Exception:
                continue
        rows.sort(key=lambda r: r["date"])
        return rows
    except Exception as exc:
        log.warning("yfinance fetch failed for %r: %s", symbol, exc)
        return []


async def _fetch_yfinance(symbol: str, start: date | None = None) -> list[dict]:
    """Async wrapper for ``_fetch_yfinance_sync`` (thread-pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _fetch_yfinance_sync, symbol, start)


async def _fetch_with_fallback(
    yahoo_sym: str,
    stooq_sym: str,
    yf_sym: str,
    start: date | None = None,
) -> list[dict]:
    """Yahoo Chart (primary) → Stooq → yfinance fallback.  Returns ``[]`` when all fail."""
    rows = await _fetch_yahoo_history(yahoo_sym, start=start)
    if rows:
        return rows
    log.info("Yahoo empty for %r, trying Stooq %r", yahoo_sym, stooq_sym)
    rows = await _fetch_stooq(stooq_sym, start=start)
    if rows:
        return rows
    log.info("Stooq empty for %r, trying yfinance %r", stooq_sym, yf_sym)
    rows = await _fetch_yfinance(yf_sym, start=start)
    return rows


# ── Public API ────────────────────────────────────────────────────────────────

async def topup_recent_prices(db: AsyncSession) -> None:
    """Incremental top-up: fetch recent closes and UPSERT with ON CONFLICT DO UPDATE.

    Window: [max_stored_date − 90 days … tomorrow].  The 90-day lookback
    recovers any days previously dropped by the old ``msft ∩ fx`` intersection
    bug (every Friday was missing because Yahoo's ``EURUSD=X`` daily series
    never includes Fridays due to weekend FX rollover).

    Every MSFT trading day is stored independently of FX availability.  For
    days where the same-day EURUSD bar is absent (Fridays, occasional nulls),
    the most recently available FX rate is used as a fill-forward value.
    ``close_eur`` is stored for DB completeness; the read path
    (fidelity_evolution) re-converts with a single latest FX at query time.

    **Transaction contract**: must be called with a *fresh* AsyncSession (no
    open autobegin transaction).  Opens and closes its own ``db.begin()``
    blocks internally.  Network failures are logged and silently swallowed so
    callers always degrade gracefully.  Does nothing when price_history is
    completely empty — the full backfill (triggered at import-confirm time)
    handles first-time population.
    """
    # 1. Find the most recent stored date + FX in one query
    max_date: date | None = None
    latest_stored_fx: float | None = None
    async with db.begin():
        result = await db.execute(
            select(PriceHistory.price_date, PriceHistory.fx_eur_usd)
            .where(PriceHistory.ticker == _MSFT_TICKER)
            .order_by(PriceHistory.price_date.desc())
            .limit(1)
        )
        row = result.first()
        if row:
            max_date = row[0]
            latest_stored_fx = float(row[1])

    if max_date is None:
        return  # price_history empty — full backfill handles first-time population

    # 90-day lookback: recovers recent Fridays skipped by the old intersection bug
    lookback_start = max_date - timedelta(days=90)

    # 2. Fetch daily history (network, outside any tx)
    try:
        msft_rows, fx_rows = await asyncio.gather(
            _fetch_yahoo_history(_MSFT_TICKER, start=lookback_start),
            _fetch_yahoo_history("EURUSD=X", start=lookback_start),
        )
    except Exception as exc:
        log.warning("topup_recent_prices: fetch failed: %s", exc)
        return

    if not msft_rows:
        log.warning("topup_recent_prices: no MSFT data returned")
        return

    # Build FX lookup (EUR per USD) from fetched rows
    fx_map: dict[date, float] = {}
    for r in fx_rows:
        eurusd_quote = r["close"]  # USD per EUR (e.g. 1.0823)
        if eurusd_quote > 0:
            fx_map[r["date"]] = 1.0 / eurusd_quote  # EUR per USD

    # Latest FX: prefer freshest fetched value; fallback to stored DB value
    latest_fx_eur_usd: float | None = latest_stored_fx
    if fx_map:
        latest_fx_eur_usd = fx_map[max(fx_map.keys())]

    if latest_fx_eur_usd is None:
        # Stored row exists (max_date != None) so fx_eur_usd is always non-null; this
        # branch is theoretically unreachable but guarded for safety.
        log.warning("topup_recent_prices: no FX rate available, skipping")
        return

    # Store ALL MSFT trading days — Fridays use the most recent available FX
    values = []
    for r in msft_rows:
        d = r["date"]
        close_usd = r["close"]
        fx = fx_map.get(d, latest_fx_eur_usd)   # exact same-day FX or latest fallback
        close_eur = close_usd * fx
        values.append({
            "ticker":     _MSFT_TICKER,
            "price_date": d,
            "close_usd":  Decimal(str(round(close_usd, 6))),
            "fx_eur_usd": Decimal(str(round(fx, 6))),
            "close_eur":  Decimal(str(round(close_eur, 6))),
        })

    if not values:
        return

    # 3. UPSERT with ON CONFLICT DO UPDATE — overwrites intraday values with settled closes
    stmt = pg_insert(PriceHistory).values(values)
    async with db.begin():
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["ticker", "price_date"],
                set_={
                    "close_usd":  stmt.excluded.close_usd,
                    "fx_eur_usd": stmt.excluded.fx_eur_usd,
                    "close_eur":  stmt.excluded.close_eur,
                },
            )
        )

    log.info(
        "topup_recent_prices: upserted %d rows for MSFT (lookback from %s)",
        len(values), lookback_start,
    )


async def get_latest_price(db: AsyncSession) -> LatestPriceRow | None:
    """Return the latest MSFT daily close, running an incremental top-up first.

    Calls ``topup_recent_prices`` to correct the last stored day to its
    settled close and fill any missing recent days before reading.  Falls back
    to the most recent cached close when the network is unavailable.

    **Transaction contract**: must be called with a *fresh* AsyncSession (no
    prior SQL executed on it in this request).

    Returns ``None`` only when price_history is completely empty.
    """
    # 1. Incremental top-up — settles last day to official close, fills gaps
    try:
        await topup_recent_prices(db)
    except Exception as exc:
        log.warning("get_latest_price: topup failed (degraded): %s", exc)

    # 2. Return latest close row from price_history
    async with db.begin():
        result = await db.execute(
            select(PriceHistory)
            .where(PriceHistory.ticker == _MSFT_TICKER)
            .order_by(PriceHistory.price_date.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()

    if latest is None:
        return None

    lbd = _last_business_day()
    return LatestPriceRow(
        price_date=latest.price_date,
        close_usd=float(latest.close_usd),
        fx_eur_usd=float(latest.fx_eur_usd),
        close_eur=float(latest.close_eur),
        price_stale=latest.price_date < lbd,
    )


async def backfill_price_history(earliest_date: date, db: AsyncSession) -> int:
    """Fetch MSFT price history from *earliest_date* to today and bulk-insert.

    Every MSFT trading day is stored independently of FX availability.
    For days where the same-day EURUSD bar is absent (e.g. Fridays), the
    most recently fetched FX rate is used as a fill-forward value so no
    MSFT day is dropped.  If the entire FX series is unavailable, the
    backfill is skipped (NOT NULL constraint on fx_eur_usd cannot be met).

    Uses Yahoo Chart API (primary) → Stooq → yfinance fallback.
    Idempotent: ``INSERT ON CONFLICT (ticker, price_date) DO NOTHING``.
    Network fetch happens *outside* the DB transaction; the INSERT is a single
    bulk statement.

    Returns the number of row-inserts attempted (not counting skipped conflicts).
    """
    msft_rows, fx_rows = await asyncio.gather(
        _fetch_with_fallback(_MSFT_TICKER, "msft.us", _MSFT_TICKER, start=earliest_date),
        _fetch_with_fallback("EURUSD=X", "eurusd", "EURUSD=X", start=earliest_date),
    )

    if not msft_rows:
        log.warning("Backfill skipped: no MSFT data (eurusd=%d rows)", len(fx_rows))
        return 0

    # Build FX lookup (EUR per USD) with fill-forward for missing days (e.g. Fridays)
    fx_map: dict[date, float] = {}
    for r in fx_rows:
        eurusd_quote = r["close"]  # USD per EUR
        if eurusd_quote > 0:
            fx_map[r["date"]] = 1.0 / eurusd_quote  # EUR per USD

    latest_fx_eur_usd: float | None = fx_map[max(fx_map.keys())] if fx_map else None
    if latest_fx_eur_usd is None:
        log.warning("Backfill skipped: no FX data available (cannot populate fx_eur_usd NOT NULL)")
        return 0

    msft_map = {r["date"]: r["close"] for r in msft_rows}

    values = []
    for d in sorted(msft_map.keys()):
        close_usd = msft_map[d]
        fx = fx_map.get(d, latest_fx_eur_usd)   # exact same-day FX or latest fallback
        close_eur = close_usd * fx
        values.append({
            "ticker":     _MSFT_TICKER,
            "price_date": d,
            "close_usd":  Decimal(str(round(close_usd, 6))),
            "fx_eur_usd": Decimal(str(round(fx, 6))),
            "close_eur":  Decimal(str(round(close_eur, 6))),
        })

    if not values:
        return 0

    async with db.begin():
        await db.execute(
            pg_insert(PriceHistory)
            .values(values)
            .on_conflict_do_nothing(index_elements=["ticker", "price_date"])
        )

    log.info("Backfill: %d rows for MSFT from %s", len(values), earliest_date)
    return len(values)


async def get_current_fx_rate() -> float | None:
    """Return the current EUR/USD rate (EUR per USD) from the Yahoo EURUSD=X snapshot.

    Uses ``regularMarketPrice`` from the chart meta, which is the live quote
    (USD per EUR, e.g. 1.0823) — inverted to EUR per USD (e.g. 0.9239).
    Returns ``None`` on any network failure so callers can fall back to the
    most recently stored ``fx_eur_usd`` from price_history.
    """
    try:
        snap = await _fetch_yahoo_snapshot("EURUSD=X")
        if snap and snap.get("close", 0) > 0:
            return 1.0 / snap["close"]  # USD per EUR → EUR per USD
    except Exception as exc:
        log.warning("get_current_fx_rate: snapshot failed: %s", exc)
    return None
