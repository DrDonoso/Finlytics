"""Euribor index feed backed by the ECB Data Portal.

SOURCE
──────
https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA

Series ``FM.M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA`` is *Euribor 1-year — historical
close, average of observations through period*, i.e. the monthly average of the
12-month Euribor.  That is precisely the index Spanish variable-rate mortgages
are referenced to.  The endpoint is public, needs no API key and serves the
full history back to 1994.

The series is monthly, so a full backfill is only ~380 rows.  Fetching
everything is cheaper than negotiating incremental windows, and
``UNIQUE(index_name, period)`` makes the UPSERT idempotent.

All network failures degrade silently: callers fall back to whatever is already
cached in ``euribor_rates`` so a dead network never breaks the mortgage page.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import EuriborRate

log = logging.getLogger(__name__)

INDEX_EURIBOR_12M = "euribor_12m"

_ECB_BASE = "https://data-api.ecb.europa.eu/service/data"
_ECB_SERIES: dict[str, str] = {
    INDEX_EURIBOR_12M: "FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA",
}
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)


# ── Parsing ──────────────────────────────────────────────────────────────────

def _parse_period(raw: str) -> date | None:
    """Parse an ECB ``TIME_PERIOD`` (``YYYY-MM``) into the first day of the month."""
    try:
        year, month = raw.strip().split("-")[:2]
        return date(int(year), int(month), 1)
    except (ValueError, IndexError):
        return None


def parse_ecb_csv(text: str) -> list[tuple[date, Decimal]]:
    """Parse an ECB ``csvdata`` payload into sorted ``(period, rate)`` pairs."""
    rows: list[tuple[date, Decimal]] = []
    reader = csv.DictReader(io.StringIO(text.strip()))
    for record in reader:
        period = _parse_period(record.get("TIME_PERIOD") or "")
        raw_value = (record.get("OBS_VALUE") or "").strip()
        if period is None or not raw_value:
            continue
        try:
            rows.append((period, Decimal(raw_value)))
        except InvalidOperation:
            continue
    rows.sort(key=lambda r: r[0])
    return rows


# ── Fetch ────────────────────────────────────────────────────────────────────

async def fetch_ecb_series(index_name: str = INDEX_EURIBOR_12M) -> list[tuple[date, Decimal]]:
    """Download the full monthly series for *index_name*.  Returns ``[]`` on failure."""
    series = _ECB_SERIES.get(index_name)
    if series is None:
        log.warning("Unknown index %r — no ECB series mapped", index_name)
        return []

    url = f"{_ECB_BASE}/{series}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                url, params={"format": "csvdata"}, follow_redirects=True
            )
            resp.raise_for_status()
        return parse_ecb_csv(resp.text)
    except Exception as exc:
        log.warning("ECB fetch failed for %r: %s", index_name, exc)
        return []


async def sync_index(db: AsyncSession, index_name: str = INDEX_EURIBOR_12M) -> int:
    """Fetch the series and UPSERT it into ``euribor_rates``.

    Returns the number of rows written (0 when the network call failed, leaving
    whatever is already cached untouched).

    **Transaction contract**: call with a fresh AsyncSession — the network fetch
    happens outside any transaction and the UPSERT opens its own ``db.begin()``.
    """
    rows = await fetch_ecb_series(index_name)
    if not rows:
        return 0

    values = [
        {
            "index_name": index_name,
            "period": period,
            "rate": rate,
            "source": "ecb",
        }
        for period, rate in rows
    ]

    stmt = pg_insert(EuriborRate).values(values)
    async with db.begin():
        await db.execute(
            stmt.on_conflict_do_update(
                index_elements=["index_name", "period"],
                set_={"rate": stmt.excluded.rate, "source": stmt.excluded.source},
            )
        )

    log.info("Euribor sync: upserted %d rows for %r", len(values), index_name)
    return len(values)


# ── Read path ────────────────────────────────────────────────────────────────

async def load_series(
    db: AsyncSession, index_name: str = INDEX_EURIBOR_12M
) -> dict[date, Decimal]:
    """Load the cached monthly series as ``{period: rate}``."""
    result = await db.execute(
        select(EuriborRate.period, EuriborRate.rate)
        .where(EuriborRate.index_name == index_name)
        .order_by(EuriborRate.period)
    )
    return {period: rate for period, rate in result.all()}


async def ensure_series(
    db: AsyncSession, index_name: str = INDEX_EURIBOR_12M
) -> dict[date, Decimal]:
    """Return the cached series, syncing from the ECB first if it is empty."""
    series = await load_series(db, index_name)
    if series:
        return series
    if await sync_index(db, index_name):
        return await load_series(db, index_name)
    return series


def make_resolver(series: dict[date, Decimal]):
    """Build an ``IndexResolver`` closure over a cached series.

    Months that are not published yet fall back to the most recent known value
    and are flagged ``projected=True``, so the UI can render those instalments
    as an estimate rather than passing them off as fact.
    """
    known = sorted(series.keys())

    def resolve(index_name: str | None, when: date) -> tuple[Decimal, bool]:
        if not known:
            return Decimal("0"), True
        target = date(when.year, when.month, 1)
        exact = series.get(target)
        if exact is not None:
            return exact, False
        # Most recent published month before the target; else the earliest known.
        fallback = None
        for period in known:
            if period <= target:
                fallback = period
            else:
                break
        if fallback is None:
            return series[known[0]], True
        return series[fallback], True

    return resolve
