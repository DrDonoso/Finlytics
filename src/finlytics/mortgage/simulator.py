"""Prepayment simulator.

Answers the only question that matters before overpaying a mortgage: *is it
worth it?*  It builds two schedules — the current one and a hypothetical one
with the extra payment applied — and reports the delta between them.

The headline figure is the **implied return**: the interest saved, expressed as
an annualised rate on the money committed.  That is the number to compare
against what the same cash would earn invested elsewhere, and unlike investment
returns it is risk-free and untaxed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from finlytics.mortgage.schedule import (
    IndexResolver,
    MortgageSpec,
    PrepaymentSpec,
    Schedule,
    build_schedule,
    zero_index,
)

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")
_MONTHS_PER_YEAR = Decimal("12")


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


@dataclass
class SimulationOutcome:
    """One side of the comparison (before or after the prepayment)."""

    months: int
    end_date: date | None
    total_interest: Decimal
    total_paid: Decimal
    monthly_payment: Decimal


@dataclass
class SimulationResult:
    """Delta between the current schedule and the simulated one."""

    before: SimulationOutcome
    after: SimulationOutcome
    amount: Decimal
    fee: Decimal
    mode: str
    interest_saved: Decimal
    months_saved: int
    payment_delta: Decimal
    net_saving: Decimal            # interest saved minus the prepayment fee
    implied_annual_return: Decimal | None   # annualised return on the committed cash
    alternative_gain: Decimal | None        # what the cash would yield if invested
    worth_it: bool | None                   # net saving beats the alternative
    before_schedule: Schedule               # kept so callers can chart both curves
    after_schedule: Schedule


def _outcome(schedule: Schedule, reference: date) -> SimulationOutcome:
    """Summarise a schedule, reporting the instalment in force after *reference*."""
    upcoming = schedule.next_row_after(reference)
    current = upcoming or (schedule.rows[-1] if schedule.rows else None)
    return SimulationOutcome(
        months=schedule.totals.months,
        end_date=schedule.totals.end_date,
        total_interest=_q(schedule.totals.total_interest),
        total_paid=_q(schedule.totals.total_paid),
        monthly_payment=_q(current.payment) if current else _ZERO,
    )


def _implied_annual_return(
    interest_saved: Decimal, amount: Decimal, months_committed: int
) -> Decimal | None:
    """Annualise the saving as a simple return on the money put in.

    ``months_committed`` is how long the cash stays locked in the loan — the
    remaining life of the mortgage after the prepayment.
    """
    if amount <= _ZERO or months_committed <= 0:
        return None
    years = Decimal(months_committed) / _MONTHS_PER_YEAR
    if years <= _ZERO:
        return None
    return ((interest_saved / amount) / years * Decimal("100")).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def simulate_prepayment(
    spec: MortgageSpec,
    amount: Decimal,
    when: date,
    mode: str,
    fee: Decimal = _ZERO,
    alt_return_pct: Decimal | None = None,
    index: IndexResolver = zero_index,
) -> SimulationResult:
    """Compare *spec* against the same mortgage with an extra payment applied.

    ``mode`` is ``'reduce_term'`` (keep the instalment, finish earlier) or
    ``'reduce_payment'`` (keep the term, lower the instalment).

    When ``alt_return_pct`` is given, the same cash is compounded at that annual
    rate over the remaining life of the loan so the two options can be compared
    directly.  Nothing is persisted.
    """
    before = build_schedule(spec, index)

    # replace() rather than rebuilding by hand: a spec field added later would
    # otherwise be silently dropped, and the simulation would quietly model a
    # different loan than the one on screen.
    simulated = replace(
        spec,
        prepayments=(
            *spec.prepayments,
            PrepaymentSpec(payment_date=when, amount=amount, mode=mode, fee=fee),
        ),
    )
    after = build_schedule(simulated, index)

    before_summary = _outcome(before, when)
    after_summary = _outcome(after, when)

    interest_saved = _q(before_summary.total_interest - after_summary.total_interest)
    months_saved = before_summary.months - after_summary.months
    payment_delta = _q(after_summary.monthly_payment - before_summary.monthly_payment)
    net_saving = _q(interest_saved - fee)

    # The cash stays committed for whatever is left of the loan after the payment.
    months_committed = sum(1 for row in after.rows if row.date >= when)
    implied = _implied_annual_return(interest_saved, amount, months_committed)

    alternative_gain: Decimal | None = None
    worth_it: bool | None = None
    if alt_return_pct is not None and months_committed > 0:
        years = Decimal(months_committed) / _MONTHS_PER_YEAR
        growth = (Decimal(1) + alt_return_pct / Decimal("100")) ** years
        alternative_gain = _q(amount * growth - amount)
        worth_it = net_saving >= alternative_gain

    return SimulationResult(
        before=before_summary,
        after=after_summary,
        amount=_q(amount),
        fee=_q(fee),
        mode=mode,
        interest_saved=interest_saved,
        months_saved=months_saved,
        payment_delta=payment_delta,
        net_saving=net_saving,
        implied_annual_return=implied,
        alternative_gain=alternative_gain,
        worth_it=worth_it,
        before_schedule=before,
        after_schedule=after,
    )
