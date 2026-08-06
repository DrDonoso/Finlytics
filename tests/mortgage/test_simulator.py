"""Tests for the prepayment simulator."""

from datetime import date
from decimal import Decimal as D

import pytest

from finlytics.mortgage.schedule import MortgageSpec, PrepaymentSpec, RatePeriodSpec
from finlytics.mortgage.simulator import simulate_prepayment

SPEC = MortgageSpec(
    initial_principal=D("200000"),
    start_date=date(2024, 1, 1),
    term_months=360,
    payment_day=1,
    rate_periods=(RatePeriodSpec(start_month=0, kind="fixed", fixed_rate=D("3")),),
)


def _simulate(mode: str, **kw):
    return simulate_prepayment(
        SPEC, amount=D("20000"), when=date(2025, 1, 1), mode=mode, **kw
    )


class TestReduceTerm:
    @pytest.fixture
    def result(self):
        return _simulate("reduce_term")

    def test_shortens_the_loan(self, result):
        assert result.months_saved > 0
        assert result.after.months < result.before.months

    def test_brings_the_end_date_forward(self, result):
        assert result.after.end_date < result.before.end_date

    def test_saves_interest(self, result):
        assert result.interest_saved > 0

    def test_leaves_the_instalment_untouched(self, result):
        assert result.payment_delta == D("0.00")


class TestReducePayment:
    @pytest.fixture
    def result(self):
        return _simulate("reduce_payment")

    def test_keeps_the_end_date(self, result):
        assert result.after.end_date == result.before.end_date
        assert result.months_saved == 0

    def test_lowers_the_instalment(self, result):
        assert result.payment_delta < 0

    def test_saves_interest(self, result):
        assert result.interest_saved > 0


class TestComparison:
    def test_reducing_term_beats_reducing_payment(self):
        """Same money, more interest saved — the whole point of the simulator."""
        assert _simulate("reduce_term").interest_saved > _simulate("reduce_payment").interest_saved


class TestFees:
    def test_fee_is_subtracted_from_the_saving(self):
        result = _simulate("reduce_term", fee=D("500"))
        assert result.net_saving == result.interest_saved - D("500")

    def test_no_fee_means_net_equals_gross(self):
        result = _simulate("reduce_term")
        assert result.net_saving == result.interest_saved


class TestImpliedReturn:
    def test_is_reported_as_a_positive_rate(self):
        assert _simulate("reduce_term").implied_annual_return > 0

    def test_reducing_term_implies_a_better_return(self):
        by_term = _simulate("reduce_term").implied_annual_return
        by_payment = _simulate("reduce_payment").implied_annual_return
        assert by_term > by_payment


class TestAlternativeInvestment:
    def test_not_computed_when_no_rate_is_given(self):
        result = _simulate("reduce_term")
        assert result.alternative_gain is None
        assert result.worth_it is None

    def test_a_high_alternative_return_wins(self):
        result = _simulate("reduce_term", alt_return_pct=D("12"))
        assert result.worth_it is False

    def test_a_zero_alternative_return_loses(self):
        result = _simulate("reduce_term", alt_return_pct=D("0"))
        assert result.alternative_gain == D("0.00")
        assert result.worth_it is True


class TestPurity:
    def test_the_original_spec_is_not_mutated(self):
        before = len(SPEC.prepayments)
        _simulate("reduce_term")
        assert len(SPEC.prepayments) == before

    def test_schedules_are_returned_for_charting(self):
        result = _simulate("reduce_term")
        assert result.before_schedule.rows
        assert result.after_schedule.rows
        assert len(result.after_schedule.rows) < len(result.before_schedule.rows)


class TestStacking:
    def test_simulates_on_top_of_existing_prepayments(self):
        spec = MortgageSpec(
            initial_principal=SPEC.initial_principal,
            start_date=SPEC.start_date,
            term_months=SPEC.term_months,
            payment_day=SPEC.payment_day,
            rate_periods=SPEC.rate_periods,
            prepayments=(
                PrepaymentSpec(
                    payment_date=date(2024, 6, 1),
                    amount=D("10000"),
                    mode="reduce_term",
                ),
            ),
        )
        result = simulate_prepayment(
            spec, amount=D("10000"), when=date(2025, 1, 1), mode="reduce_term"
        )
        # The baseline already includes the first prepayment.
        assert result.before.months < 360
        assert result.after.months < result.before.months
