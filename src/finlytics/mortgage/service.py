"""Service layer bridging the ORM models and the pure amortization engine.

Keeps the router thin: it converts ``Mortgage`` rows into immutable engine
specs, resolves the index series, builds schedules and derives the KPI /
chart / reconciliation payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.db.models import Mortgage
from finlytics.mortgage.euribor import INDEX_EURIBOR_12M, ensure_series, make_resolver
from finlytics.mortgage.schedule import (
    BonusSpec,
    IndexResolver,
    MortgageSpec,
    PrepaymentSpec,
    RatePeriodSpec,
    Schedule,
    ScheduleRow,
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
    }


def group_by_year(rows: list[ScheduleRow], *, include_months: bool) -> list[dict]:
    """Roll instalments up per calendar year, optionally keeping the detail."""
    years: dict[int, dict] = {}
    for row in rows:
        bucket = years.setdefault(
            row.date.year,
            {
                "year": row.date.year,
                "payment": _ZERO,
                "interest": _ZERO,
                "principal": _ZERO,
                "prepayment": _ZERO,
                "closing_balance": _ZERO,
                "months": [],
            },
        )
        bucket["payment"] += row.payment
        bucket["interest"] += row.interest
        bucket["principal"] += row.principal
        bucket["prepayment"] += row.prepayment
        bucket["closing_balance"] = row.closing_balance
        if include_months:
            bucket["months"].append(row_payload(row))

    return [
        {
            "year": b["year"],
            "payment": _f(_q(b["payment"])),
            "interest": _f(_q(b["interest"])),
            "principal": _f(_q(b["principal"])),
            "prepayment": _f(_q(b["prepayment"])),
            "closing_balance": _f(_q(b["closing_balance"])),
            "months": b["months"],
        }
        for b in sorted(years.values(), key=lambda b: b["year"])
    ]


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
