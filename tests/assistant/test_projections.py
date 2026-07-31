"""Compound-interest maths for the assistant's projection tool.

These numbers are the ones a user acts on, so they are checked against closed-form
values rather than against the implementation's own output.
"""

from __future__ import annotations

import pytest

from finlytics.assistant import projections


class TestFutureValue:
    def test_zero_rate_is_plain_addition(self):
        # No growth: the balance is exactly what was paid in.
        result = projections.project(
            initial_amount=1000.0,
            monthly_contribution=100.0,
            years=2,
            annual_return_pct=0.0,
        )
        scenario = result.scenarios[0]
        assert scenario.final_balance == pytest.approx(1000.0 + 100.0 * 24)
        assert scenario.total_gain == pytest.approx(0.0)

    def test_lump_sum_compounds_monthly(self):
        # 1000 at 12 %/yr compounded monthly for 1 year = 1000 * 1.01**12
        result = projections.project(
            initial_amount=1000.0, monthly_contribution=0.0, years=1, annual_return_pct=12.0
        )
        assert result.scenarios[0].final_balance == pytest.approx(
            1000.0 * (1.01**12), abs=0.01
        )

    def test_contributions_are_end_of_month(self):
        # An ordinary annuity: the last payment earns nothing, so 12 payments of
        # 100 at 12%/yr come to 100 * ((1.01**12 - 1) / 0.01).
        result = projections.project(
            initial_amount=0.0, monthly_contribution=100.0, years=1, annual_return_pct=12.0
        )
        expected = 100.0 * ((1.01**12 - 1) / 0.01)
        assert result.scenarios[0].final_balance == pytest.approx(expected, abs=0.01)

    def test_gain_is_balance_minus_contributions(self):
        result = projections.project(
            initial_amount=5000.0, monthly_contribution=250.0, years=10, annual_return_pct=6.0
        )
        scenario = result.scenarios[0]
        assert scenario.total_contributed == pytest.approx(5000.0 + 250.0 * 120)
        assert scenario.total_gain == pytest.approx(
            scenario.final_balance - scenario.total_contributed, abs=0.01
        )
        assert scenario.total_gain > 0


class TestScenarios:
    def test_three_scenarios_by_default(self):
        result = projections.project(monthly_contribution=200.0, years=5)
        assert [s.name for s in result.scenarios] == ["conservative", "base", "optimistic"]

    def test_scenarios_are_ordered_by_outcome(self):
        result = projections.project(monthly_contribution=200.0, years=20)
        balances = [s.final_balance for s in result.scenarios]
        assert balances == sorted(balances)

    def test_custom_rate_collapses_to_one_scenario(self):
        result = projections.project(years=5, monthly_contribution=100.0, annual_return_pct=7.0)
        assert len(result.scenarios) == 1
        assert result.scenarios[0].name == "custom"
        assert result.scenarios[0].annual_return_pct == 7.0

    def test_configured_rates_are_used(self):
        result = projections.project(years=3, initial_amount=100.0, rates=(1.0, 2.0, 3.0))
        assert [s.annual_return_pct for s in result.scenarios] == [1.0, 2.0, 3.0]

    def test_yearly_series_has_one_point_per_year(self):
        result = projections.project(years=7, monthly_contribution=50.0)
        for scenario in result.scenarios:
            assert [p.year for p in scenario.yearly] == list(range(1, 8))


class TestGuards:
    def test_negative_amount_is_rejected(self):
        with pytest.raises(ValueError, match="negative"):
            projections.project(initial_amount=-1.0, years=5)

    def test_absurd_amount_is_rejected(self):
        with pytest.raises(ValueError, match="exceed"):
            projections.project(initial_amount=projections.MAX_AMOUNT * 2, years=5)

    def test_zero_horizon_is_rejected(self):
        with pytest.raises(ValueError, match="at least one year"):
            projections.project(monthly_contribution=100.0, years=0)

    def test_horizon_is_clamped(self):
        # A model asking for 500 years must not build 500 yearly points.
        result = projections.project(monthly_contribution=10.0, years=500)
        assert result.years == projections.MAX_YEARS

    def test_negative_return_erodes_the_balance(self):
        result = projections.project(
            initial_amount=10_000.0, monthly_contribution=0.0, years=5, annual_return_pct=-5.0
        )
        assert result.scenarios[0].final_balance < 10_000.0
        assert result.scenarios[0].total_gain < 0


class TestSerialisation:
    def test_disclaimer_is_always_present(self):
        data = projections.to_dict(projections.project(years=5, monthly_contribution=100.0))
        assert data["disclaimer"] == projections.DISCLAIMER
        assert "not financial advice" in data["disclaimer"].lower()

    def test_long_horizons_are_thinned_not_truncated(self):
        # Dropping the tail would hide the answer to "what about in 40 years?",
        # so the final year must survive the thinning.
        result = projections.project(years=60, monthly_contribution=100.0)
        data = projections.to_dict(result, max_yearly_points=10)
        yearly = data["scenarios"][0]["yearly"]
        assert len(yearly) <= 11
        assert yearly[-1]["year"] == 60

    def test_short_horizons_are_untouched(self):
        data = projections.to_dict(
            projections.project(years=5, monthly_contribution=100.0), max_yearly_points=30
        )
        assert len(data["scenarios"][0]["yearly"]) == 5
