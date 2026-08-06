"""Tests for the French-system amortization engine."""

from datetime import date
from decimal import Decimal as D

import pytest

from finlytics.mortgage.schedule import (
    BonusSpec,
    MortgageSpec,
    PrepaymentSpec,
    RatePeriodSpec,
    add_months,
    build_schedule,
    french_payment,
    resolve_rate,
)

FIXED_3PCT = RatePeriodSpec(start_month=0, kind="fixed", fixed_rate=D("3"))


def _spec(**overrides) -> MortgageSpec:
    base = dict(
        initial_principal=D("200000"),
        start_date=date(2024, 1, 1),
        term_months=360,
        payment_day=1,
        rate_periods=(FIXED_3PCT,),
    )
    base.update(overrides)
    return MortgageSpec(**base)


# ── Instalment formula ───────────────────────────────────────────────────────

class TestFrenchPayment:
    def test_matches_textbook_value(self):
        """200,000 EUR at 3% over 30 years is 843.21 EUR/month."""
        assert french_payment(D("200000"), D("0.03") / 12, 360) == D("843.21")

    def test_zero_rate_splits_principal_evenly(self):
        assert french_payment(D("12000"), D("0"), 12) == D("1000.00")

    def test_zero_term_returns_zero(self):
        assert french_payment(D("200000"), D("0.0025"), 0) == D("0")

    def test_zero_principal_returns_zero(self):
        assert french_payment(D("0"), D("0.0025"), 360) == D("0")


# ── Core schedule ────────────────────────────────────────────────────────────

class TestFixedRateSchedule:
    def test_produces_one_row_per_month(self):
        assert len(build_schedule(_spec()).rows) == 360

    def test_balance_closes_at_exactly_zero(self):
        """The final instalment must absorb the rounding residue."""
        schedule = build_schedule(_spec())
        assert schedule.rows[-1].closing_balance == D("0.00")

    def test_principal_repaid_equals_amount_borrowed(self):
        schedule = build_schedule(_spec())
        assert schedule.totals.total_principal == D("200000.00")

    def test_first_instalment_splits_correctly(self):
        row = build_schedule(_spec()).rows[0]
        assert row.interest == D("500.00")        # 200000 * 3% / 12
        assert row.principal == D("343.21")
        assert row.payment == D("843.21")

    def test_interest_share_decreases_over_time(self):
        rows = build_schedule(_spec()).rows
        assert rows[0].interest > rows[180].interest > rows[-1].interest

    def test_total_interest_is_plausible(self):
        totals = build_schedule(_spec()).totals
        assert D("103000") < totals.total_interest < D("104000")

    def test_end_date_matches_term(self):
        assert build_schedule(_spec()).totals.end_date == date(2053, 12, 1)

    def test_empty_when_principal_is_zero(self):
        assert build_schedule(_spec(initial_principal=D("0"))).rows == []

    def test_empty_when_term_is_zero(self):
        assert build_schedule(_spec(term_months=0)).rows == []


class TestRealWorldTerms:
    """A term is not always a whole number of years.

    A loan signed mid-month usually charges interest-only for the stub period,
    so capital is amortized over 359 instalments rather than 360. Entering 360
    understates the instalment by a couple of euros, which reads like an engine
    bug rather than a data-entry one — these pin the difference down.
    """

    SIGNED = dict(
        initial_principal=D("291200"),
        start_date=date(2024, 1, 1),
        payment_day=1,
        rate_periods=(RatePeriodSpec(start_month=0, kind="fixed", fixed_rate=D("2")),),
    )

    def test_359_instalments(self):
        schedule = build_schedule(MortgageSpec(**self.SIGNED, term_months=359))
        assert schedule.rows[0].payment == D("1078.52")

    def test_360_instalments(self):
        schedule = build_schedule(MortgageSpec(**self.SIGNED, term_months=360))
        assert schedule.rows[0].payment == D("1076.33")

    def test_one_instalment_fewer_costs_more_per_month(self):
        shorter = build_schedule(MortgageSpec(**self.SIGNED, term_months=359))
        longer = build_schedule(MortgageSpec(**self.SIGNED, term_months=360))
        assert shorter.rows[0].payment > longer.rows[0].payment
        assert shorter.totals.total_interest < longer.totals.total_interest


class TestPaymentDay:
    def test_uses_contractual_pay_day(self):
        schedule = build_schedule(_spec(payment_day=15))
        assert schedule.rows[0].date == date(2024, 1, 15)

    def test_clamps_day_to_short_months(self):
        """Day 31 must fall back to the last day of February."""
        schedule = build_schedule(
            _spec(start_date=date(2024, 1, 31), payment_day=31, term_months=3)
        )
        assert schedule.rows[1].date == date(2024, 2, 29)  # 2024 is a leap year


# ── Prepayments ──────────────────────────────────────────────────────────────

class TestReduceTerm:
    @pytest.fixture
    def schedule(self):
        return build_schedule(
            _spec(
                prepayments=(
                    PrepaymentSpec(
                        payment_date=date(2025, 1, 1),
                        amount=D("20000"),
                        mode="reduce_term",
                    ),
                )
            )
        )

    def test_shortens_the_loan(self, schedule):
        assert schedule.totals.months < 360

    def test_keeps_the_instalment_unchanged(self, schedule):
        assert schedule.rows[0].payment == schedule.rows[100].payment == D("843.21")

    def test_saves_interest(self, schedule):
        assert schedule.totals.total_interest < build_schedule(_spec()).totals.total_interest

    def test_still_closes_at_zero(self, schedule):
        assert schedule.rows[-1].closing_balance == D("0.00")

    def test_records_the_prepayment(self, schedule):
        assert schedule.totals.total_prepayments == D("20000.00")


class TestReducePayment:
    @pytest.fixture
    def schedule(self):
        return build_schedule(
            _spec(
                prepayments=(
                    PrepaymentSpec(
                        payment_date=date(2025, 1, 1),
                        amount=D("20000"),
                        mode="reduce_payment",
                    ),
                )
            )
        )

    def test_keeps_the_original_term(self, schedule):
        assert schedule.totals.months == 360

    def test_lowers_the_instalment(self, schedule):
        assert schedule.rows[13].payment < schedule.rows[0].payment

    def test_saves_less_interest_than_reducing_term(self, schedule):
        by_term = build_schedule(
            _spec(
                prepayments=(
                    PrepaymentSpec(
                        payment_date=date(2025, 1, 1),
                        amount=D("20000"),
                        mode="reduce_term",
                    ),
                )
            )
        )
        assert schedule.totals.total_interest > by_term.totals.total_interest

    def test_still_closes_at_zero(self, schedule):
        assert schedule.rows[-1].closing_balance == D("0.00")


class TestPrepaymentEdgeCases:
    def test_prepayment_larger_than_balance_is_capped(self):
        schedule = build_schedule(
            _spec(
                term_months=12,
                initial_principal=D("10000"),
                prepayments=(
                    PrepaymentSpec(
                        payment_date=date(2024, 3, 1),
                        amount=D("999999"),
                        mode="reduce_term",
                    ),
                ),
            )
        )
        assert schedule.rows[-1].closing_balance == D("0.00")
        assert schedule.totals.total_prepayments <= D("10000")

    def test_fee_is_tracked_separately_from_principal(self):
        schedule = build_schedule(
            _spec(
                prepayments=(
                    PrepaymentSpec(
                        payment_date=date(2025, 1, 1),
                        amount=D("10000"),
                        mode="reduce_term",
                        fee=D("50"),
                    ),
                )
            )
        )
        assert schedule.totals.total_fees == D("50.00")
        # The fee is a cost, not capital: scheduled principal plus the
        # prepayment must still add up to exactly what was borrowed.
        total = schedule.totals.total_principal + schedule.totals.total_prepayments
        assert total == D("200000.00")


# ── Rate tranches ────────────────────────────────────────────────────────────

class TestMixedRate:
    """A mixed mortgage must recompute the instalment when the tranche flips."""

    @pytest.fixture
    def schedule(self):
        def index(_name, _when):
            return D("2.5"), False

        return build_schedule(
            _spec(
                rate_periods=(
                    RatePeriodSpec(start_month=0, kind="fixed", fixed_rate=D("2.5")),
                    RatePeriodSpec(
                        start_month=60,
                        kind="variable",
                        index_name="euribor_12m",
                        spread=D("0.8"),
                        review_months=12,
                    ),
                )
            ),
            index,
        )

    def test_fixed_tranche_uses_the_fixed_rate(self, schedule):
        assert schedule.rows[59].annual_rate == D("2.50000")

    def test_variable_tranche_applies_index_plus_spread(self, schedule):
        assert schedule.rows[60].annual_rate == D("3.30000")

    def test_instalment_is_recomputed_at_the_transition(self, schedule):
        assert schedule.rows[60].payment != schedule.rows[59].payment

    def test_still_closes_at_zero(self, schedule):
        assert schedule.rows[-1].closing_balance == D("0.00")


class TestVariableReviews:
    def test_instalment_follows_the_index(self):
        """A rising index must push the instalment up at the review date.

        With review_lag_months=2, instalment 0 (2024-01) reads the index for
        2023-11 and instalment 12 (2025-01) reads 2024-11.
        """
        def index(_name, when):
            return (D("1") if when < date(2024, 1, 1) else D("4")), False

        schedule = build_schedule(
            _spec(
                rate_periods=(
                    RatePeriodSpec(
                        start_month=0,
                        kind="variable",
                        index_name="euribor_12m",
                        spread=D("1"),
                        review_months=12,
                        review_lag_months=2,
                    ),
                )
            ),
            index,
        )
        assert schedule.rows[12].payment > schedule.rows[0].payment

    def test_projected_flag_propagates_from_the_index(self):
        def index(_name, _when):
            return D("2"), True

        schedule = build_schedule(
            _spec(
                rate_periods=(
                    RatePeriodSpec(
                        start_month=0,
                        kind="variable",
                        index_name="euribor_12m",
                        spread=D("1"),
                        review_months=12,
                    ),
                )
            ),
            index,
        )
        assert all(row.projected for row in schedule.rows)


class TestRateResolution:
    def _variable(self, **kw):
        base = dict(
            start_month=0,
            kind="variable",
            index_name="euribor_12m",
            spread=D("1"),
            review_months=12,
        )
        base.update(kw)
        return RatePeriodSpec(**base)

    def test_floor_clamps_the_rate(self):
        rate, _ = resolve_rate(
            self._variable(floor_rate=D("2")),
            date(2024, 1, 1),
            (),
            lambda _n, _w: (D("0"), False),
        )
        assert rate == D("2.00000")

    def test_cap_clamps_the_rate(self):
        rate, _ = resolve_rate(
            self._variable(cap_rate=D("3")),
            date(2024, 1, 1),
            (),
            lambda _n, _w: (D("10"), False),
        )
        assert rate == D("3.00000")

    def test_rate_never_goes_negative(self):
        rate, _ = resolve_rate(
            self._variable(spread=D("0.2")),
            date(2024, 1, 1),
            (),
            lambda _n, _w: (D("-1"), False),
        )
        assert rate == D("0.00000")

    def test_review_lag_selects_an_earlier_index_month(self):
        seen: list[date] = []

        def index(_name, when):
            seen.append(when)
            return D("2"), False

        resolve_rate(self._variable(review_lag_months=2), date(2024, 6, 1), (), index)
        assert seen == [date(2024, 4, 1)]


class TestBonuses:
    def test_active_bonus_reduces_the_rate(self):
        schedule = build_schedule(
            _spec(bonuses=(BonusSpec(spread_reduction=D("0.5")),))
        )
        assert schedule.rows[0].annual_rate == D("2.50000")

    def test_inactive_bonus_is_ignored(self):
        schedule = build_schedule(
            _spec(bonuses=(BonusSpec(spread_reduction=D("0.5"), active=False),))
        )
        assert schedule.rows[0].annual_rate == D("3.00000")

    def test_bonus_outside_its_window_is_ignored(self):
        schedule = build_schedule(
            _spec(
                bonuses=(
                    BonusSpec(
                        spread_reduction=D("0.5"),
                        start_date=date(2030, 1, 1),
                    ),
                )
            )
        )
        assert schedule.rows[0].annual_rate == D("3.00000")
        assert schedule.rows[80].annual_rate == D("2.50000")


# ── Queries ──────────────────────────────────────────────────────────────────

class TestScheduleQueries:
    def test_balance_on_returns_outstanding_capital(self):
        schedule = build_schedule(_spec())
        assert schedule.balance_on(date(2024, 1, 1)) == D("199656.79")

    def test_balance_before_first_instalment_is_the_full_principal(self):
        schedule = build_schedule(_spec())
        assert schedule.balance_on(date(2023, 1, 1)) == D("200000.00")

    def test_next_row_after_returns_the_upcoming_instalment(self):
        schedule = build_schedule(_spec())
        assert schedule.next_row_after(date(2024, 1, 1)).date == date(2024, 2, 1)

    def test_next_row_after_the_end_is_none(self):
        schedule = build_schedule(_spec())
        assert schedule.next_row_after(date(2099, 1, 1)) is None


class TestAddMonths:
    def test_rolls_over_the_year(self):
        assert add_months(date(2024, 11, 1), 3) == date(2025, 2, 1)

    def test_clamps_day_to_shorter_month(self):
        assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    def test_supports_negative_offsets(self):
        assert add_months(date(2024, 1, 1), -2) == date(2023, 11, 1)
