"""French-system mortgage amortization engine.

The engine is pure and side-effect free: it takes an immutable ``MortgageSpec``
plus an index resolver and returns the full instalment schedule.  Nothing here
touches the database, which keeps it trivially testable and lets the simulator
build hypothetical schedules without persisting anything.

FRENCH SYSTEM
─────────────
Constant instalment within a rate tranche::

    payment = C · i / (1 − (1 + i)^−n)

where ``C`` is the outstanding balance, ``i`` the monthly rate and ``n`` the
remaining number of instalments.  The instalment is recomputed whenever:

  * a rate tranche starts (this is what makes a *mixed* mortgage work),
  * a variable tranche hits a review date,
  * a ``reduce_payment`` prepayment lands.

A ``reduce_term`` prepayment deliberately does NOT recompute the instalment —
the balance simply drops and the loan finishes earlier, which is what saves
the most interest.

PRECISION
─────────
Everything runs in ``Decimal``.  Money is quantized to 2 decimals at each step
and the final instalment absorbs the accumulated rounding residue so the
balance closes at exactly zero.  Using floats here drifts the closing balance
by several euros over 360 instalments.
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Protocol

# Money is rounded to cents; rates keep 5 decimals like the DB columns.
_CENTS = Decimal("0.01")
_RATE_Q = Decimal("0.00001")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")
_MONTHS_PER_YEAR = Decimal("12")

# Hard stop so a pathological input (instalment below the accrued interest)
# can never spin forever.
_MAX_PERIODS = 1200


# ── Value objects ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RatePeriodSpec:
    """One interest-rate tranche, offset from the first instalment."""

    start_month: int
    kind: str  # 'fixed' | 'variable'
    fixed_rate: Decimal | None = None
    index_name: str | None = None
    spread: Decimal | None = None
    review_months: int | None = None
    review_lag_months: int = 2
    floor_rate: Decimal | None = None
    cap_rate: Decimal | None = None


@dataclass(frozen=True)
class BonusSpec:
    """A linked product that discounts the applied rate while active."""

    spread_reduction: Decimal
    active: bool = True
    start_date: date | None = None
    end_date: date | None = None
    annual_cost: Decimal = _ZERO

    def applies_on(self, when: date) -> bool:
        if not self.active:
            return False
        if self.start_date and when < self.start_date:
            return False
        if self.end_date and when > self.end_date:
            return False
        return True


@dataclass(frozen=True)
class PrepaymentSpec:
    """A lump-sum overpayment applied after a scheduled instalment."""

    payment_date: date
    amount: Decimal
    mode: str  # 'reduce_term' | 'reduce_payment'
    fee: Decimal = _ZERO


@dataclass(frozen=True)
class MortgageSpec:
    """Everything the engine needs to build a schedule."""

    initial_principal: Decimal
    start_date: date
    term_months: int
    payment_day: int = 1
    rate_periods: tuple[RatePeriodSpec, ...] = ()
    bonuses: tuple[BonusSpec, ...] = ()
    prepayments: tuple[PrepaymentSpec, ...] = ()


@dataclass(frozen=True)
class ScheduleRow:
    """A single instalment of the amortization table."""

    period_index: int          # 1-based instalment number
    date: date
    opening_balance: Decimal
    payment: Decimal           # scheduled instalment (excludes prepayment/fee)
    interest: Decimal
    principal: Decimal
    prepayment: Decimal
    fee: Decimal
    closing_balance: Decimal
    annual_rate: Decimal       # applied TIN, as a percentage
    projected: bool            # True when the rate relies on an estimated index


@dataclass
class ScheduleTotals:
    """Aggregates over a whole schedule."""

    total_paid: Decimal = _ZERO
    total_interest: Decimal = _ZERO
    total_principal: Decimal = _ZERO
    total_prepayments: Decimal = _ZERO
    total_fees: Decimal = _ZERO
    months: int = 0
    end_date: date | None = None


@dataclass
class Schedule:
    """The full amortization table plus its aggregates."""

    rows: list[ScheduleRow] = field(default_factory=list)
    totals: ScheduleTotals = field(default_factory=ScheduleTotals)

    def balance_on(self, when: date) -> Decimal:
        """Outstanding balance after the last instalment on or before *when*."""
        balance = self.rows[0].opening_balance if self.rows else _ZERO
        for row in self.rows:
            if row.date > when:
                break
            balance = row.closing_balance
        return balance

    def row_on(self, when: date) -> ScheduleRow | None:
        """The last instalment falling on or before *when*."""
        found: ScheduleRow | None = None
        for row in self.rows:
            if row.date > when:
                break
            found = row
        return found

    def next_row_after(self, when: date) -> ScheduleRow | None:
        """The first instalment strictly after *when*."""
        for row in self.rows:
            if row.date > when:
                return row
        return None


class IndexResolver(Protocol):
    """Resolves a reference index for a given month.

    Returns ``(rate_percentage, projected)``.  ``projected`` is True when the
    exact month is not published yet and the caller fell back to an estimate,
    so the UI can render those instalments as provisional.
    """

    def __call__(self, index_name: str | None, when: date) -> tuple[Decimal, bool]: ...


def zero_index(index_name: str | None, when: date) -> tuple[Decimal, bool]:
    """Fallback resolver used when no index series is available."""
    return _ZERO, True


# ── Date helpers ─────────────────────────────────────────────────────────────

def add_months(anchor: date, months: int) -> date:
    """Shift *anchor* by *months*, clamping the day to the target month length."""
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _instalment_date(start: date, payment_day: int, offset: int) -> date:
    """Date of instalment *offset* (0-based), honouring the contractual pay day."""
    base = add_months(start, offset)
    day = min(max(payment_day, 1), calendar.monthrange(base.year, base.month)[1])
    return date(base.year, base.month, day)


def _month_key(value: date) -> tuple[int, int]:
    return value.year, value.month


# ── Money helpers ────────────────────────────────────────────────────────────

def _q(value: Decimal) -> Decimal:
    """Quantize to cents, half-up (the convention banks use)."""
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def monthly_rate(annual_pct: Decimal) -> Decimal:
    """Convert an annual nominal percentage into a monthly decimal rate."""
    return (annual_pct / _HUNDRED) / _MONTHS_PER_YEAR


def french_payment(principal: Decimal, i: Decimal, n: int) -> Decimal:
    """Constant instalment for *principal* over *n* months at monthly rate *i*."""
    if n <= 0 or principal <= _ZERO:
        return _ZERO
    if i <= _ZERO:
        return _q(principal / Decimal(n))
    factor = (Decimal(1) + i) ** n
    return _q(principal * i * factor / (factor - Decimal(1)))


def _remaining_periods(balance: Decimal, i: Decimal, payment: Decimal) -> int | None:
    """How many instalments of *payment* clear *balance* at monthly rate *i*.

    Returns ``None`` when the instalment does not even cover the accrued
    interest, in which case the loan would never amortize.
    """
    if balance <= _ZERO:
        return 0
    if payment <= _ZERO:
        return None
    if i <= _ZERO:
        return math.ceil(float(balance) / float(payment))
    if payment <= balance * i:
        return None
    ratio = 1 - (float(balance) * float(i) / float(payment))
    return math.ceil(-math.log(ratio) / math.log(1 + float(i)))


# ── Rate resolution ──────────────────────────────────────────────────────────

def _active_period(
    periods: tuple[RatePeriodSpec, ...], month: int
) -> RatePeriodSpec | None:
    """The tranche covering instalment *month* (the last one that has started)."""
    current: RatePeriodSpec | None = None
    for period in periods:
        if period.start_month <= month:
            current = period
        else:
            break
    return current


def _bonus_adjustment(bonuses: tuple[BonusSpec, ...], when: date) -> Decimal:
    """Total rate discount from the bonuses active on *when*."""
    return sum((b.spread_reduction for b in bonuses if b.applies_on(when)), _ZERO)


def _clamp(rate: Decimal, period: RatePeriodSpec) -> Decimal:
    if period.floor_rate is not None and rate < period.floor_rate:
        rate = period.floor_rate
    if period.cap_rate is not None and rate > period.cap_rate:
        rate = period.cap_rate
    if rate < _ZERO:
        rate = _ZERO
    return rate.quantize(_RATE_Q, rounding=ROUND_HALF_UP)


def base_rate(
    period: RatePeriodSpec, when: date, index: IndexResolver
) -> tuple[Decimal, bool]:
    """Contractual rate before bonuses: the TIN, or index + spread.

    Resolved only when a tranche starts or a review lands, so the index value
    stays pinned between reviews instead of drifting every month.
    """
    if period.kind == "variable":
        reference_month = add_months(when, -period.review_lag_months)
        index_value, projected = index(period.index_name, reference_month)
        return index_value + (period.spread or _ZERO), projected
    return period.fixed_rate or _ZERO, False


def resolve_rate(
    period: RatePeriodSpec,
    when: date,
    bonuses: tuple[BonusSpec, ...],
    index: IndexResolver,
) -> tuple[Decimal, bool]:
    """Applied annual rate (percentage) for *period* at *when*, plus projected flag.

    variable → ``index(when − review_lag_months) + spread``
    then bonuses are subtracted and the result is clamped to [floor, cap].
    """
    rate, projected = base_rate(period, when, index)
    return _clamp(rate - _bonus_adjustment(bonuses, when), period), projected


def _is_review_month(period: RatePeriodSpec, month: int) -> bool:
    """True when instalment *month* falls on a review boundary of *period*."""
    if period.kind != "variable" or not period.review_months:
        return False
    elapsed = month - period.start_month
    return elapsed > 0 and elapsed % period.review_months == 0


# ── Engine ───────────────────────────────────────────────────────────────────

def build_schedule(
    spec: MortgageSpec,
    index: IndexResolver | Callable[[str | None, date], tuple[Decimal, bool]] = zero_index,
) -> Schedule:
    """Build the full amortization schedule for *spec*.

    Handles tranche transitions, variable-rate reviews and both prepayment
    modes.  The loop exits as soon as the balance is cleared, so a
    ``reduce_term`` prepayment naturally shortens the table.
    """
    schedule = Schedule()
    balance = _q(spec.initial_principal)
    if balance <= _ZERO or spec.term_months <= 0:
        return schedule

    periods = tuple(sorted(spec.rate_periods, key=lambda p: p.start_month))
    if not periods:
        periods = (RatePeriodSpec(start_month=0, kind="fixed", fixed_rate=_ZERO),)

    # Prepayments grouped by calendar month of their payment date.
    prepay_by_month: dict[tuple[int, int], list[PrepaymentSpec]] = {}
    for prepayment in spec.prepayments:
        prepay_by_month.setdefault(_month_key(prepayment.payment_date), []).append(
            prepayment
        )

    scheduled_end = spec.term_months   # index of the last instalment (exclusive)
    payment = _ZERO
    rate_pct = _ZERO
    contract_rate = _ZERO   # rate before bonuses; pinned between reviews
    bonus_adj: Decimal | None = None
    i = _ZERO
    projected = False
    active: RatePeriodSpec | None = None
    repricing = False       # set by a reduce_payment prepayment

    month = 0
    while month < scheduled_end and month < _MAX_PERIODS:
        when = _instalment_date(spec.start_date, spec.payment_day, month)
        period = _active_period(periods, month) or periods[0]

        # The contractual rate is refreshed only when a tranche starts or a
        # review lands, so the index stays pinned in between.
        refresh_rate = period is not active or _is_review_month(period, month)
        active = period

        # A bonus starting or expiring mid-loan changes the applied rate even on
        # a fixed tranche, where no review would otherwise trigger.
        current_bonus = _bonus_adjustment(spec.bonuses, when)
        bonus_changed = bonus_adj is None or current_bonus != bonus_adj
        bonus_adj = current_bonus

        if refresh_rate:
            contract_rate, projected = base_rate(period, when, index)

        if refresh_rate or bonus_changed or repricing:
            rate_pct = _clamp(contract_rate - bonus_adj, period)
            i = monthly_rate(rate_pct)
            payment = french_payment(balance, i, scheduled_end - month)
            repricing = False

        opening = balance
        interest = _q(balance * i)
        principal = _q(payment - interest)

        # Final instalment (or an instalment that would overshoot): settle exactly.
        if principal >= balance or month == scheduled_end - 1:
            principal = balance
            actual_payment = _q(principal + interest)
        else:
            actual_payment = payment

        balance = _q(balance - principal)

        # Prepayments land after the scheduled instalment of the same month.
        prepaid = _ZERO
        fees = _ZERO
        for prepayment in prepay_by_month.get(_month_key(when), ()):
            if balance <= _ZERO:
                break
            applied = min(_q(prepayment.amount), balance)
            if applied <= _ZERO:
                continue
            balance = _q(balance - applied)
            prepaid += applied
            fees += _q(prepayment.fee)
            if prepayment.mode == "reduce_payment":
                repricing = True
            else:  # reduce_term — keep the instalment, shorten the loan
                remaining = _remaining_periods(balance, i, payment)
                if remaining is not None:
                    scheduled_end = month + 1 + remaining

        schedule.rows.append(
            ScheduleRow(
                period_index=month + 1,
                date=when,
                opening_balance=opening,
                payment=actual_payment,
                interest=interest,
                principal=principal,
                prepayment=prepaid,
                fee=fees,
                closing_balance=balance,
                annual_rate=rate_pct,
                projected=projected,
            )
        )

        if balance <= _ZERO:
            break
        month += 1

    _fill_totals(schedule)
    return schedule


def _fill_totals(schedule: Schedule) -> None:
    totals = ScheduleTotals()
    for row in schedule.rows:
        totals.total_paid += row.payment + row.prepayment + row.fee
        totals.total_interest += row.interest
        totals.total_principal += row.principal
        totals.total_prepayments += row.prepayment
        totals.total_fees += row.fee
    totals.months = len(schedule.rows)
    totals.end_date = schedule.rows[-1].date if schedule.rows else None
    schedule.totals = totals
