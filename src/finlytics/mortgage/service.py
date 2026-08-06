"""Service layer bridging the ORM models and the pure amortization engine.

Keeps the router thin: it converts ``Mortgage`` rows into immutable engine
specs, resolves the index series, builds schedules and derives the KPI /
chart / reconciliation payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Mortgage, Transaction
from finlytics.mortgage.euribor import INDEX_EURIBOR_12M, ensure_series, make_resolver
from finlytics.mortgage.schedule import (
    BonusSpec,
    IndexResolver,
    MortgageSpec,
    PrepaymentSpec,
    RatePeriodSpec,
    Schedule,
    ScheduleRow,
    add_months,
    build_schedule,
    zero_index,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _f(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


# ── Model → spec ─────────────────────────────────────────────────────────────

def spec_from_model(mortgage: Mortgage, *, with_prepayments: bool = True) -> MortgageSpec:
    """Convert an ORM ``Mortgage`` (with relations loaded) into an engine spec."""
    periods = tuple(
        RatePeriodSpec(
            start_month=p.start_month,
            kind=p.kind,
            fixed_rate=p.fixed_rate,
            index_name=p.index_name,
            spread=p.spread,
            review_months=p.review_months,
            review_lag_months=p.review_lag_months,
            floor_rate=p.floor_rate,
            cap_rate=p.cap_rate,
        )
        for p in sorted(mortgage.rate_periods, key=lambda p: p.start_month)
    )
    bonuses = tuple(
        BonusSpec(
            spread_reduction=b.spread_reduction,
            active=b.active,
            start_date=b.start_date,
            end_date=b.end_date,
            annual_cost=b.annual_cost,
        )
        for b in mortgage.bonuses
    )
    prepayments: tuple[PrepaymentSpec, ...] = ()
    if with_prepayments:
        prepayments = tuple(
            PrepaymentSpec(
                payment_date=p.payment_date,
                amount=p.amount,
                mode=p.mode,
                fee=p.fee,
            )
            for p in sorted(mortgage.prepayments, key=lambda p: p.payment_date)
        )
    return MortgageSpec(
        initial_principal=mortgage.initial_principal,
        start_date=mortgage.start_date,
        signature_date=mortgage.signature_date,
        term_months=mortgage.term_months,
        payment_day=mortgage.payment_day,
        rate_periods=periods,
        bonuses=bonuses,
        prepayments=prepayments,
    )


def needs_index(mortgage: Mortgage) -> bool:
    """True when any tranche is variable and therefore needs the index series."""
    return any(p.kind == "variable" for p in mortgage.rate_periods)


async def resolver_for(db: AsyncSession, mortgage: Mortgage) -> IndexResolver:
    """Build the index resolver for *mortgage*, syncing the series when needed."""
    if not needs_index(mortgage):
        return zero_index
    index_name = next(
        (p.index_name for p in mortgage.rate_periods if p.index_name),
        INDEX_EURIBOR_12M,
    )
    series = await ensure_series(db, index_name)
    return make_resolver(series)


@dataclass
class MortgageSchedules:
    """The live schedule plus the counterfactual without any prepayment."""

    actual: Schedule
    baseline: Schedule


async def build_schedules(db: AsyncSession, mortgage: Mortgage) -> MortgageSchedules:
    """Build both the real schedule and the no-prepayment baseline."""
    index = await resolver_for(db, mortgage)
    actual = build_schedule(spec_from_model(mortgage), index)
    if mortgage.prepayments:
        baseline = build_schedule(
            spec_from_model(mortgage, with_prepayments=False), index
        )
    else:
        baseline = actual
    return MortgageSchedules(actual=actual, baseline=baseline)


# ── Derived payloads ─────────────────────────────────────────────────────────

def overview_payload(
    mortgage: Mortgage, schedules: MortgageSchedules, today: date
) -> dict:
    """KPI payload for GET /api/mortgages/{id}/overview."""
    schedule = schedules.actual
    baseline = schedules.baseline

    initial = mortgage.initial_principal
    outstanding = schedule.balance_on(today)
    amortized = _q(initial - outstanding)
    progress = float(amortized / initial * 100) if initial > _ZERO else 0.0

    upcoming = schedule.next_row_after(today)
    current = upcoming or (schedule.rows[-1] if schedule.rows else None)

    interest_paid = _q(sum((r.interest for r in schedule.rows if r.date <= today), _ZERO))
    total_interest = _q(schedule.totals.total_interest)
    months_elapsed = sum(1 for r in schedule.rows if r.date <= today)

    ltv = None
    if mortgage.property_value and mortgage.property_value > _ZERO:
        ltv = float(outstanding / mortgage.property_value * 100)

    annual_bonus_cost = _q(
        sum((b.annual_cost for b in mortgage.bonuses if b.active), _ZERO)
    )

    return {
        "id": mortgage.id,
        "name": mortgage.name,
        "lender": mortgage.lender,
        "rate_type": mortgage.rate_type,
        "initial_principal": _f(initial),
        "outstanding_balance": _f(outstanding),
        "amortized_principal": _f(amortized),
        "progress_pct": round(progress, 2),
        "current_payment": _f(current.payment) if current else 0.0,
        "current_rate": _f(current.annual_rate) if current else 0.0,
        "next_payment_date": upcoming.date if upcoming else None,
        "interest_paid": _f(interest_paid),
        "interest_remaining": _f(_q(total_interest - interest_paid)),
        "total_interest": _f(total_interest),
        "total_cost": _f(_q(schedule.totals.total_paid)),
        "months_elapsed": months_elapsed,
        "months_remaining": max(schedule.totals.months - months_elapsed, 0),
        "end_date": schedule.totals.end_date,
        "original_end_date": baseline.totals.end_date,
        "months_saved": max(baseline.totals.months - schedule.totals.months, 0),
        "interest_saved": _f(
            _q(baseline.totals.total_interest - schedule.totals.total_interest)
        ),
        "property_value": _f(mortgage.property_value) if mortgage.property_value else None,
        "ltv_pct": round(ltv, 2) if ltv is not None else None,
        "total_prepaid": _f(_q(schedule.totals.total_prepayments)),
        "annual_bonus_cost": _f(annual_bonus_cost),
        "has_projection": any(r.projected for r in schedule.rows),
        "include_in_net_worth": mortgage.include_in_net_worth,
        "linked_account_id": mortgage.linked_account_id,
        "linked_category_id": mortgage.linked_category_id,
    }


def summary_payload(mortgage: Mortgage, schedule: Schedule, today: date) -> dict:
    """Lightweight payload for the mortgage list."""
    outstanding = schedule.balance_on(today)
    initial = mortgage.initial_principal
    upcoming = schedule.next_row_after(today)
    current = upcoming or (schedule.rows[-1] if schedule.rows else None)
    progress = float((initial - outstanding) / initial * 100) if initial > _ZERO else 0.0
    return {
        "id": mortgage.id,
        "name": mortgage.name,
        "lender": mortgage.lender,
        "rate_type": mortgage.rate_type,
        "outstanding_balance": _f(outstanding),
        "monthly_payment": _f(current.payment) if current else 0.0,
        "progress_pct": round(progress, 2),
    }


def row_payload(row: ScheduleRow) -> dict:
    return {
        "period_index": row.period_index,
        "date": row.date,
        "opening_balance": _f(row.opening_balance),
        "payment": _f(row.payment),
        "interest": _f(row.interest),
        "principal": _f(row.principal),
        "prepayment": _f(row.prepayment),
        "fee": _f(row.fee),
        "closing_balance": _f(row.closing_balance),
        "annual_rate": _f(row.annual_rate),
        "projected": row.projected,
        "status": "pending",
        "charged": None,
    }


def annotate_status(
    rows: list[dict],
    today: date,
    matcher: "ChargeMatcher | None" = None,
) -> None:
    """Tag each instalment as paid, elapsed or pending, in place.

    The distinction matters: a due date in the past is not proof of payment,
    only of time passing. Marking those as paid would be the app asserting
    something it cannot know — and the schedule already diverged from reality
    once. So:

      paid    — a real charge was matched to it (only possible when linked)
      elapsed — its due date has passed, but nothing confirms it
      pending — still in the future

    Without a matcher every past row is 'elapsed', which is an honest
    "time has passed" rather than a claim about money.
    """
    for row in rows:
        if row["date"] > today:
            continue
        charged = (
            matcher.match(row["date"], Decimal(str(row["payment"])))
            if matcher is not None
            else None
        )
        if charged is not None:
            row["status"] = "paid"
            row["charged"] = _f(charged)
        else:
            row["status"] = "elapsed"


def group_by_year(rows: list[dict], *, include_months: bool) -> list[dict]:
    """Roll instalment payloads up per calendar year, optionally keeping detail.

    Takes payloads rather than engine rows so the caller can annotate them with
    payment status first, and the yearly counts stay consistent with the months
    they summarise.
    """
    years: dict[int, dict] = {}
    for row in rows:
        year = row["date"].year
        bucket = years.setdefault(
            year,
            {
                "year": year,
                "payment": 0.0,
                "interest": 0.0,
                "principal": 0.0,
                "prepayment": 0.0,
                "closing_balance": 0.0,
                "months": [],
            },
        )
        bucket["payment"] += row["payment"]
        bucket["interest"] += row["interest"]
        bucket["principal"] += row["principal"]
        bucket["prepayment"] += row["prepayment"]
        bucket["closing_balance"] = row["closing_balance"]
        bucket["months"].append(row)

    out = []
    for b in sorted(years.values(), key=lambda b: b["year"]):
        months = b["months"]
        out.append({
            "year": b["year"],
            "payment": round(b["payment"], 2),
            "interest": round(b["interest"], 2),
            "principal": round(b["principal"], 2),
            "prepayment": round(b["prepayment"], 2),
            "closing_balance": round(b["closing_balance"], 2),
            # Counts so a collapsed year still shows how far along it is.
            "months_total": len(months),
            "months_paid": sum(1 for m in months if m["status"] == "paid"),
            "months_elapsed": sum(1 for m in months if m["status"] != "pending"),
            "months": months if include_months else [],
        })
    return out


def balance_series(schedule: Schedule, *, max_points: int = 480) -> list[dict]:
    """Outstanding-balance curve, thinned to stay light on the wire."""
    rows = schedule.rows
    if not rows:
        return []
    step = max(1, len(rows) // max_points)
    points = [
        {
            "date": row.date,
            "balance": _f(row.closing_balance),
            "projected": row.projected,
        }
        for idx, row in enumerate(rows)
        if idx % step == 0
    ]
    last = rows[-1]
    if points[-1]["date"] != last.date:
        points.append(
            {
                "date": last.date,
                "balance": _f(last.closing_balance),
                "projected": last.projected,
            }
        )
    return points


# ── Matching instalments to real charges ─────────────────────────────────────

# How far a charge may sit from its due date and still be that instalment.
# Covers last-working-day drift across a month boundary and a weekend.
MATCH_WINDOW_DAYS = 10


def is_linked(mortgage: Mortgage) -> bool:
    """True when the mortgage points at an account or a category."""
    return (
        mortgage.linked_account_id is not None
        or mortgage.linked_category_id is not None
    )


async def load_charges(
    db: AsyncSession, mortgage: Mortgage, since: date
) -> list[tuple[date, Decimal]]:
    """Expenses in the linked account/category from *since*, oldest first.

    Expenses only: a linked category also holds the loan disbursement, which is
    income, and treating its absolute value as a charge reports a quarter of a
    million euros for that month.
    """
    if not is_linked(mortgage):
        return []

    conditions = [
        Transaction.transaction_date >= since,
        Transaction.amount < 0,
        Transaction.is_system.is_(False),
    ]
    if mortgage.linked_account_id is not None:
        conditions.append(Transaction.account_id == mortgage.linked_account_id)
    if mortgage.linked_category_id is not None:
        conditions.append(Transaction.category_id == mortgage.linked_category_id)

    result = await db.execute(
        select(Transaction.transaction_date, Transaction.amount).where(*conditions)
    )
    return sorted((d, abs(a)) for d, a in result.all())


class ChargeMatcher:
    """Assigns each due instalment the real charge that most likely paid it.

    Matching is by proximity in time, not by calendar month: banks charge on the
    last working day, so an instalment routinely lands on the 1st of the next
    month. Bucketing by month loses it and picks up whatever else shares the
    category instead.

    Within the window the nearest amount wins, and each charge is consumed, so
    two instalments falling in one calendar month are not paid by the same
    transaction twice.

    Stateful by design: call ``match`` in due order.
    """

    def __init__(self, charges: list[tuple[date, Decimal]]) -> None:
        self._charges = charges
        self._used: set[int] = set()

    @property
    def covers_from(self) -> date | None:
        """Earliest charge on record, or None when there is nothing to match.

        Before this date the ledger simply has no data, which is not the same
        as an instalment going unpaid — a mortgage usually predates the oldest
        imported statement. Callers use it to stay quiet instead of reporting
        a confident zero.
        """
        return min((when for when, _ in self._charges), default=None)

    def match(self, due: date, expected: Decimal) -> Decimal | None:
        best_idx: int | None = None
        best_key: tuple[Decimal, int] | None = None
        for idx, (charged_on, charged) in enumerate(self._charges):
            if idx in self._used:
                continue
            distance = abs((charged_on - due).days)
            if distance > MATCH_WINDOW_DAYS:
                continue
            key = (abs(charged - expected), distance)
            if best_key is None or key < best_key:
                best_idx, best_key = idx, key
        if best_idx is None:
            return None
        self._used.add(best_idx)
        return self._charges[best_idx][1]
