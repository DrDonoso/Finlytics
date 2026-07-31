"""Deterministic investment projections.

The LLM is never asked to estimate a return.  It calls this module, which does
plain compound-interest arithmetic, and then narrates the numbers it gets back.
That is the whole point: a model inventing "you'd have around 40.000 €" is
indistinguishable, to the reader, from a real calculation.

Pure functions — no database, no network, no settings import at call time (rates
are passed in), so the maths is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "DISCLAIMER",
    "ProjectionScenario",
    "ProjectionResult",
    "project",
]

# Surfaced verbatim by the prompt.  Projections are arithmetic on an assumed
# rate, not a forecast, and the difference matters when the subject is someone's
# savings.
DISCLAIMER = (
    "These figures are arithmetic on an assumed constant rate of return, not a "
    "prediction. Real markets are volatile and returns are never guaranteed. "
    "This is not financial advice."
)

# Guard rails.  A model that passes years=10_000 would otherwise build a list of
# ten thousand yearly points and hand it straight back into the context window.
MAX_YEARS = 60
MAX_AMOUNT = 1_000_000_000.0


@dataclass(frozen=True)
class YearPoint:
    """Balance at the end of a given year."""

    year: int
    contributed: float
    balance: float
    gain: float


@dataclass(frozen=True)
class ProjectionScenario:
    """One rate assumption projected over the full horizon."""

    name: str
    annual_return_pct: float
    final_balance: float
    total_contributed: float
    total_gain: float
    yearly: list[YearPoint] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectionResult:
    """Full projection across every scenario, plus the inputs it used."""

    initial_amount: float
    monthly_contribution: float
    years: int
    scenarios: list[ProjectionScenario]
    disclaimer: str = DISCLAIMER


def _future_value(
    initial: float,
    monthly: float,
    months: int,
    annual_rate_pct: float,
) -> float:
    """Future value of a lump sum plus a monthly annuity, compounded monthly.

    Contributions are made at the *end* of each month (ordinary annuity), which
    is the conservative convention and matches how a standing order actually
    behaves — the first payment has one month less to grow than it would if it
    were made up front.
    """
    monthly_rate = annual_rate_pct / 100.0 / 12.0

    if monthly_rate == 0.0:
        return initial + monthly * months

    growth = (1.0 + monthly_rate) ** months
    # A rate of exactly -100 %/yr drives (1 + r) to zero; the annuity term below
    # divides by the rate, which is safe, but the lump sum simply vanishes.
    return initial * growth + monthly * ((growth - 1.0) / monthly_rate)


def _scenario(
    name: str,
    annual_rate_pct: float,
    initial: float,
    monthly: float,
    years: int,
) -> ProjectionScenario:
    yearly: list[YearPoint] = []
    for year in range(1, years + 1):
        months = year * 12
        balance = _future_value(initial, monthly, months, annual_rate_pct)
        contributed = initial + monthly * months
        yearly.append(
            YearPoint(
                year=year,
                contributed=round(contributed, 2),
                balance=round(balance, 2),
                gain=round(balance - contributed, 2),
            )
        )

    total_contributed = initial + monthly * years * 12
    final_balance = (
        yearly[-1].balance if yearly else round(initial, 2)
    )
    return ProjectionScenario(
        name=name,
        annual_return_pct=annual_rate_pct,
        final_balance=final_balance,
        total_contributed=round(total_contributed, 2),
        total_gain=round(final_balance - total_contributed, 2),
        yearly=yearly,
    )


def project(
    *,
    initial_amount: float = 0.0,
    monthly_contribution: float = 0.0,
    years: int = 10,
    rates: tuple[float, float, float] = (2.0, 5.0, 8.0),
    annual_return_pct: float | None = None,
) -> ProjectionResult:
    """Project a portfolio forward under three rate assumptions.

    Args:
        initial_amount:       Lump sum invested today.
        monthly_contribution: Added at the end of every month.
        years:                Horizon, clamped to ``MAX_YEARS``.
        rates:                (conservative, base, optimistic) annual % returns.
        annual_return_pct:    When given, overrides ``rates`` with a single
                              "custom" scenario.  Only used when the user states
                              an explicit expected return — the model must not
                              invent one.

    Raises:
        ValueError: on negative amounts or a non-positive horizon.
    """
    if initial_amount < 0 or monthly_contribution < 0:
        raise ValueError("Amounts cannot be negative.")
    if initial_amount > MAX_AMOUNT or monthly_contribution > MAX_AMOUNT:
        raise ValueError(f"Amounts cannot exceed {MAX_AMOUNT:.0f}.")
    if years < 1:
        raise ValueError("Horizon must be at least one year.")

    years = min(int(years), MAX_YEARS)

    if annual_return_pct is not None:
        scenarios = [
            _scenario(
                "custom",
                float(annual_return_pct),
                initial_amount,
                monthly_contribution,
                years,
            )
        ]
    else:
        conservative, base, optimistic = rates
        scenarios = [
            _scenario("conservative", conservative, initial_amount, monthly_contribution, years),
            _scenario("base", base, initial_amount, monthly_contribution, years),
            _scenario("optimistic", optimistic, initial_amount, monthly_contribution, years),
        ]

    return ProjectionResult(
        initial_amount=round(initial_amount, 2),
        monthly_contribution=round(monthly_contribution, 2),
        years=years,
        scenarios=scenarios,
    )


def to_dict(result: ProjectionResult, *, max_yearly_points: int = 30) -> dict:
    """Serialise a projection for the LLM.

    Long horizons are thinned rather than truncated: keeping years 1..30 and
    dropping 31..60 would hide the answer to "what about in 40 years?", whereas
    sampling every Nth year keeps both ends of the curve.  The final year is
    always present because it is usually the number the user asked for.
    """
    def thin(points: list[YearPoint]) -> list[dict]:
        if len(points) <= max_yearly_points:
            kept = points
        else:
            step = max(1, len(points) // max_yearly_points)
            kept = points[::step]
            if kept[-1] is not points[-1]:
                kept = [*kept, points[-1]]
        return [
            {
                "year": p.year,
                "contributed": p.contributed,
                "balance": p.balance,
                "gain": p.gain,
            }
            for p in kept
        ]

    return {
        "initial_amount": result.initial_amount,
        "monthly_contribution": result.monthly_contribution,
        "years": result.years,
        "scenarios": [
            {
                "name": s.name,
                "annual_return_pct": s.annual_return_pct,
                "final_balance": s.final_balance,
                "total_contributed": s.total_contributed,
                "total_gain": s.total_gain,
                "yearly": thin(s.yearly),
            }
            for s in result.scenarios
        ],
        "disclaimer": result.disclaimer,
    }
