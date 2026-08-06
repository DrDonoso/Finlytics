"""Mortgage REST API.

Routes (all mounted under ``/api`` and auth-gated in ``app.py``):

  GET    /mortgages                        — list with live KPIs
  POST   /mortgages                        — create (contract + tranches + bonuses)
  GET    /mortgages/euribor                — cached index series for the chart
  GET    /mortgages/net-worth              — aggregate contribution to the net-worth KPI
  GET    /mortgages/{id}                   — full configuration
  PUT    /mortgages/{id}                   — replace configuration
  DELETE /mortgages/{id}                   — delete (cascades to every child row)
  GET    /mortgages/{id}/overview          — KPI payload
  GET    /mortgages/{id}/schedule          — amortization table (month | year)
  GET    /mortgages/{id}/charts            — balance curve + yearly principal/interest
  GET    /mortgages/{id}/reconciliation    — expected vs actually charged
  POST   /mortgages/{id}/prepayments       — register an overpayment
  DELETE /mortgages/{id}/prepayments/{pid} — remove an overpayment
  POST   /mortgages/{id}/simulate          — what-if, persists nothing

``/euribor` and `/net-worth`` are declared before ``/{mortgage_id}`` so the
static paths are not swallowed by the int path converter.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    EuriborSeriesOut,
    MortgageChartsOut,
    MortgageCreate,
    MortgageNetWorthOut,
    MortgageOut,
    MortgageOverview,
    MortgageSummary,
    MortgageUpdate,
    PaymentCandidatesOut,
    PrepaymentIn,
    PrepaymentOut,
    ReconciliationOut,
    ScheduleOut,
    SimulationOut,
    SimulationRequest,
)
from finlytics.db.models import (
    Account,
    Category,
    EuriborRate,
    Mortgage,
    MortgageBonus,
    MortgagePrepayment,
    MortgageRatePeriod,
    Transaction,
    User,
)
from finlytics.mortgage import service
from finlytics.mortgage.euribor import INDEX_EURIBOR_12M, ensure_series
from finlytics.mortgage.schedule import add_months
from finlytics.mortgage.simulator import simulate_prepayment

router = APIRouter(prefix="/mortgages", tags=["mortgages"])

# A charge has to repeat this many times before it looks like an instalment
# rather than a coincidence of equal amounts.
_MIN_RECURRING_CHARGES = 3
# ...and span more than a single month, so three purchases in one week do not
# qualify. Three monthly charges span ~59 days at the short end (Jan→Mar).
_MIN_RECURRING_SPAN_DAYS = 50
_MAX_CANDIDATES = 5

_RELATIONS = (
    selectinload(Mortgage.rate_periods),
    selectinload(Mortgage.bonuses),
    selectinload(Mortgage.prepayments),
)


def _dec(value: float | None) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


async def _load(db: AsyncSession, mortgage_id: int, user_id: int) -> Mortgage:
    """Fetch a mortgage with all relations, scoped to the calling user."""
    result = await db.execute(
        select(Mortgage)
        .where(Mortgage.id == mortgage_id, Mortgage.user_id == user_id)
        .options(*_RELATIONS)
    )
    mortgage = result.scalar_one_or_none()
    if mortgage is None:
        raise HTTPException(status_code=404, detail="Mortgage not found.")
    return mortgage


def _apply_children(mortgage: Mortgage, body: MortgageCreate) -> None:
    """Replace the tranche and bonus collections from the request body."""
    mortgage.rate_periods = [
        MortgageRatePeriod(
            start_month=p.start_month,
            kind=p.kind,
            fixed_rate=_dec(p.fixed_rate),
            index_name=p.index_name or (INDEX_EURIBOR_12M if p.kind == "variable" else None),
            spread=_dec(p.spread),
            review_months=p.review_months,
            review_lag_months=p.review_lag_months,
            floor_rate=_dec(p.floor_rate),
            cap_rate=_dec(p.cap_rate),
        )
        for p in body.rate_periods
    ]
    mortgage.bonuses = [
        MortgageBonus(
            name=b.name,
            spread_reduction=_dec(b.spread_reduction) or Decimal("0"),
            annual_cost=_dec(b.annual_cost) or Decimal("0"),
            active=b.active,
            start_date=b.start_date,
            end_date=b.end_date,
        )
        for b in body.bonuses
    ]


def _apply_contract(mortgage: Mortgage, body: MortgageCreate) -> None:
    mortgage.name = body.name.strip()
    mortgage.lender = body.lender
    mortgage.initial_principal = Decimal(str(body.initial_principal))
    mortgage.start_date = body.start_date
    mortgage.signature_date = body.signature_date
    mortgage.term_months = body.term_months
    mortgage.payment_day = body.payment_day
    mortgage.rate_type = body.rate_type
    mortgage.linked_account_id = body.linked_account_id
    mortgage.linked_category_id = body.linked_category_id
    mortgage.property_value = _dec(body.property_value)
    mortgage.property_value_date = body.property_value_date
    mortgage.include_in_net_worth = body.include_in_net_worth
    mortgage.notes = body.notes


# ── Collection ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[MortgageSummary])
async def list_mortgages(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    result = await db.execute(
        select(Mortgage).where(Mortgage.user_id == user.id).options(*_RELATIONS)
    )
    mortgages = result.scalars().all()
    today = date.today()
    out = []
    for mortgage in mortgages:
        schedules = await service.build_schedules(db, mortgage)
        out.append(service.summary_payload(mortgage, schedules.actual, today))
    return out


@router.post("", response_model=MortgageOut, status_code=201)
async def create_mortgage(
    body: MortgageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Mortgage:
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Name must not be empty.")

    async with db.begin():
        mortgage = Mortgage(user_id=user.id)
        _apply_contract(mortgage, body)
        _apply_children(mortgage, body)
        db.add(mortgage)
        await db.flush()
        mortgage_id = mortgage.id

    return await _load(db, mortgage_id, user.id)


@router.get("/euribor", response_model=EuriborSeriesOut)
async def get_euribor(
    # Constrained to the indices actually mapped to an ECB series: a free-form
    # string here would flow into a log line and into the series lookup.
    index_name: Literal["euribor_12m"] = Query(INDEX_EURIBOR_12M),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Cached index series, syncing from the ECB on first use."""
    series = await ensure_series(db, index_name)
    points = [{"period": period, "rate": float(rate)} for period, rate in sorted(series.items())]
    return {
        "index_name": index_name,
        "points": points,
        "latest": points[-1]["rate"] if points else None,
        "latest_period": points[-1]["period"] if points else None,
    }


@router.get("/payment-candidates", response_model=PaymentCandidatesOut)
async def get_payment_candidates(
    amount: float | None = Query(None, gt=0),
    months: int = Query(24, ge=3, le=120),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Find recurring charges in the ledger that look like a mortgage instalment.

    A mortgage is a fixed charge repeated every month, which is a strong enough
    signal to spot without asking the user to hunt for it. Passing the expected
    instalment additionally reports the deviation, which is what turns a silent
    couple-of-euros gap into something visible while the terms can still be
    corrected.

    Suggestion only: nothing is linked or modified here.
    """
    window_start = add_months(date(date.today().year, date.today().month, 1), -months)

    result = await db.execute(
        select(
            Transaction.account_id,
            Transaction.category_id,
            Transaction.amount,
            Transaction.transaction_date,
        )
        .where(
            Transaction.transaction_date >= window_start,
            Transaction.amount < 0,
            Transaction.is_system.is_(False),
        )
    )

    # A mortgage instalment repeats to the cent, so an exact grouping on the
    # amount is both precise and cheap. A variable-rate loan simply produces one
    # cluster per review period, which still surfaces.
    groups: dict[tuple[int, int | None, Decimal], list[date]] = {}
    for account_id, category_id, tx_amount, tx_date in result.all():
        key = (account_id, category_id, abs(tx_amount))
        groups.setdefault(key, []).append(tx_date)

    account_names = dict(
        (await db.execute(select(Account.id, Account.name))).all()
    )
    category_names = dict(
        (await db.execute(select(Category.id, Category.name))).all()
    )

    expected = Decimal(str(amount)) if amount is not None else None
    candidates: list[dict] = []
    for (account_id, category_id, charged), dates in groups.items():
        # Counting occurrences rather than distinct calendar months: banks charge
        # on the last working day, so a payment can land on the 1st of the next
        # month and two consecutive instalments share a calendar month. Counting
        # months there reports fewer charges than the ledger visibly holds.
        first_seen, last_seen = min(dates), max(dates)
        span_days = (last_seen - first_seen).days
        if len(dates) < _MIN_RECURRING_CHARGES or span_days < _MIN_RECURRING_SPAN_DAYS:
            continue
        entry: dict = {
            "account_id": account_id,
            "account_name": account_names.get(account_id, "?"),
            "category_id": category_id,
            "category_name": category_names.get(category_id) if category_id else None,
            "amount": float(charged),
            "occurrences": len(dates),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "deviation": None,
            "deviation_pct": None,
        }
        if expected is not None and expected > 0:
            deviation = charged - expected
            entry["deviation"] = float(deviation)
            entry["deviation_pct"] = round(float(deviation / expected * 100), 2)
        candidates.append(entry)

    # Closest to the expected instalment first; without one, the most frequent.
    if expected is not None:
        candidates.sort(key=lambda c: (abs(c["deviation"] or 0), -c["occurrences"]))
    else:
        candidates.sort(key=lambda c: -c["occurrences"])

    return {
        "expected_payment": float(expected) if expected is not None else None,
        "candidates": candidates[:_MAX_CANDIDATES],
    }


@router.get("/net-worth", response_model=MortgageNetWorthOut)
async def get_net_worth(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Aggregate mortgage contribution to the Dashboard net-worth KPI.

    Only mortgages with ``include_in_net_worth`` enabled are counted, which is
    the toggle that lets the user keep the KPI unchanged.
    """
    result = await db.execute(
        select(Mortgage)
        .where(Mortgage.user_id == user.id, Mortgage.include_in_net_worth.is_(True))
        .options(*_RELATIONS)
    )
    mortgages = result.scalars().all()

    today = date.today()
    debt = Decimal("0")
    property_value = Decimal("0")
    for mortgage in mortgages:
        schedules = await service.build_schedules(db, mortgage)
        debt += schedules.actual.balance_on(today)
        if mortgage.property_value:
            property_value += mortgage.property_value

    return {
        "outstanding_debt": float(debt),
        "property_value": float(property_value),
        "net_contribution": float(property_value - debt),
        "count": len(mortgages),
    }


# ── Single mortgage ──────────────────────────────────────────────────────────

@router.get("/{mortgage_id}", response_model=MortgageOut)
async def get_mortgage(
    mortgage_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Mortgage:
    return await _load(db, mortgage_id, user.id)


@router.put("/{mortgage_id}", response_model=MortgageOut)
async def update_mortgage(
    mortgage_id: int,
    body: MortgageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Mortgage:
    async with db.begin():
        result = await db.execute(
            select(Mortgage)
            .where(Mortgage.id == mortgage_id, Mortgage.user_id == user.id)
            .options(*_RELATIONS)
        )
        mortgage = result.scalar_one_or_none()
        if mortgage is None:
            raise HTTPException(status_code=404, detail="Mortgage not found.")
        _apply_contract(mortgage, body)
        _apply_children(mortgage, body)
        await db.flush()

    return await _load(db, mortgage_id, user.id)


@router.delete("/{mortgage_id}", status_code=204)
async def delete_mortgage(
    mortgage_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    async with db.begin():
        result = await db.execute(
            select(Mortgage).where(
                Mortgage.id == mortgage_id, Mortgage.user_id == user.id
            )
        )
        mortgage = result.scalar_one_or_none()
        if mortgage is None:
            raise HTTPException(status_code=404, detail="Mortgage not found.")
        await db.delete(mortgage)


@router.get("/{mortgage_id}/overview", response_model=MortgageOverview)
async def get_overview(
    mortgage_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    mortgage = await _load(db, mortgage_id, user.id)
    schedules = await service.build_schedules(db, mortgage)
    return service.overview_payload(mortgage, schedules, date.today())


@router.get("/{mortgage_id}/schedule", response_model=ScheduleOut)
async def get_schedule(
    mortgage_id: int,
    granularity: str = Query("year", pattern="^(month|year)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    mortgage = await _load(db, mortgage_id, user.id)
    schedules = await service.build_schedules(db, mortgage)
    schedule = schedules.actual

    rows = [service.row_payload(r) for r in schedule.rows]

    # Mark what has actually been charged. Without a link the rows are only
    # tagged as elapsed: a past due date proves time passed, not payment.
    matcher = None
    if rows and service.is_linked(mortgage):
        charges = await service.load_charges(
            db, mortgage, add_months(rows[0]["date"], -1)
        )
        matcher = service.ChargeMatcher(charges)
    service.annotate_status(rows, date.today(), matcher)

    payload: dict = {
        "mortgage_id": mortgage_id,
        "granularity": granularity,
        "linked": service.is_linked(mortgage),
        "charges_from": matcher.covers_from if matcher else None,
        "rows": [],
        "years": [],
        "total_payment": float(schedule.totals.total_paid),
        "total_interest": float(schedule.totals.total_interest),
        "total_principal": float(schedule.totals.total_principal),
    }
    if granularity == "month":
        payload["rows"] = rows
    else:
        payload["years"] = service.group_by_year(rows, include_months=True)
    return payload


@router.get("/{mortgage_id}/charts", response_model=MortgageChartsOut)
async def get_charts(
    mortgage_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    mortgage = await _load(db, mortgage_id, user.id)
    schedules = await service.build_schedules(db, mortgage)
    return {
        "balance": service.balance_series(schedules.actual),
        "composition": service.group_by_year(
            [service.row_payload(r) for r in schedules.actual.rows],
            include_months=False,
        ),
    }


@router.get("/{mortgage_id}/reconciliation", response_model=ReconciliationOut)
async def get_reconciliation(
    mortgage_id: int,
    months: int = Query(24, ge=1, le=360),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Compare the theoretical instalment against what was actually charged.

    Returns ``linked: false`` with an empty table when no account or category
    is configured — the link is optional by design.
    """
    mortgage = await _load(db, mortgage_id, user.id)
    if not service.is_linked(mortgage):
        return {
            "mortgage_id": mortgage_id,
            "linked": False,
            "account_id": None,
            "category_id": None,
            "rows": [],
            "total_expected": 0.0,
            "total_actual": 0.0,
        }

    schedules = await service.build_schedules(db, mortgage)
    today = date.today()
    past = [r for r in schedules.actual.rows if r.date <= today][-months:]

    charges = (
        await service.load_charges(db, mortgage, add_months(past[0].date, -1))
        if past
        else []
    )
    matcher = service.ChargeMatcher(charges)

    rows = []
    total_expected = Decimal("0")
    total_actual = Decimal("0")
    for row in past:
        # The instalment alone: a prepayment is usually a separate transfer and
        # already has its own table, so folding it in here only adds noise.
        expected = row.payment
        actual = matcher.match(row.date, expected)
        total_expected += expected
        entry: dict = {
            "period": row.date,
            "expected": float(expected),
            "actual": None,
            "deviation": None,
            "deviation_pct": None,
            "matched": actual is not None,
        }
        if actual is not None:
            total_actual += actual
            deviation = actual - expected
            entry["actual"] = float(actual)
            entry["deviation"] = float(deviation)
            entry["deviation_pct"] = (
                round(float(deviation / expected * 100), 2) if expected > 0 else None
            )
        rows.append(entry)

    return {
        "mortgage_id": mortgage_id,
        "linked": True,
        "account_id": mortgage.linked_account_id,
        "category_id": mortgage.linked_category_id,
        "rows": rows,
        "total_expected": float(total_expected),
        "total_actual": float(total_actual),
    }


# ── Prepayments ──────────────────────────────────────────────────────────────

@router.post("/{mortgage_id}/prepayments", response_model=PrepaymentOut, status_code=201)
async def create_prepayment(
    mortgage_id: int,
    body: PrepaymentIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MortgagePrepayment:
    # The ownership check runs inside the transaction: querying first would
    # autobegin the session and make the explicit begin() blow up.
    async with db.begin():
        owner = await db.scalar(
            select(Mortgage.id).where(
                Mortgage.id == mortgage_id, Mortgage.user_id == user.id
            )
        )
        if owner is None:
            raise HTTPException(status_code=404, detail="Mortgage not found.")
        prepayment = MortgagePrepayment(
            mortgage_id=mortgage_id,
            payment_date=body.payment_date,
            amount=Decimal(str(body.amount)),
            mode=body.mode,
            fee=Decimal(str(body.fee)),
            notes=body.notes,
        )
        db.add(prepayment)
        await db.flush()
        prepayment_id = prepayment.id

    result = await db.execute(
        select(MortgagePrepayment).where(MortgagePrepayment.id == prepayment_id)
    )
    return result.scalar_one()


@router.delete("/{mortgage_id}/prepayments/{prepayment_id}", status_code=204)
async def delete_prepayment(
    mortgage_id: int,
    prepayment_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    async with db.begin():
        owner = await db.scalar(
            select(Mortgage.id).where(
                Mortgage.id == mortgage_id, Mortgage.user_id == user.id
            )
        )
        if owner is None:
            raise HTTPException(status_code=404, detail="Mortgage not found.")
        result = await db.execute(
            select(MortgagePrepayment).where(
                MortgagePrepayment.id == prepayment_id,
                MortgagePrepayment.mortgage_id == mortgage_id,
            )
        )
        prepayment = result.scalar_one_or_none()
        if prepayment is None:
            raise HTTPException(status_code=404, detail="Prepayment not found.")
        await db.delete(prepayment)


# ── Simulator ────────────────────────────────────────────────────────────────

@router.post("/{mortgage_id}/simulate", response_model=SimulationOut)
async def simulate(
    mortgage_id: int,
    body: SimulationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Preview a prepayment without persisting anything."""
    mortgage = await _load(db, mortgage_id, user.id)
    index = await service.resolver_for(db, mortgage)
    spec = service.spec_from_model(mortgage)

    result = simulate_prepayment(
        spec,
        amount=Decimal(str(body.amount)),
        when=body.payment_date,
        mode=body.mode,
        fee=Decimal(str(body.fee)),
        alt_return_pct=_dec(body.alt_return_pct),
        index=index,
    )

    def side(outcome) -> dict:
        return {
            "months": outcome.months,
            "end_date": outcome.end_date,
            "total_interest": float(outcome.total_interest),
            "total_paid": float(outcome.total_paid),
            "monthly_payment": float(outcome.monthly_payment),
        }

    return {
        "before": side(result.before),
        "after": side(result.after),
        "amount": float(result.amount),
        "fee": float(result.fee),
        "mode": result.mode,
        "interest_saved": float(result.interest_saved),
        "months_saved": result.months_saved,
        "payment_delta": float(result.payment_delta),
        "net_saving": float(result.net_saving),
        "implied_annual_return": (
            float(result.implied_annual_return)
            if result.implied_annual_return is not None
            else None
        ),
        "alternative_gain": (
            float(result.alternative_gain) if result.alternative_gain is not None else None
        ),
        "worth_it": result.worth_it,
        "balance_before": service.balance_series(result.before_schedule),
        "balance_after": service.balance_series(result.after_schedule),
    }
