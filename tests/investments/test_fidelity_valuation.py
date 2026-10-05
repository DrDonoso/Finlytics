from datetime import date
from decimal import Decimal

import pytest

from finlytics.api.fidelity import compute_evolution_series
from finlytics.db.models import EsppLot
from finlytics.investments.fidelity import _compute_dedup_hash
from finlytics.investments.fidelity_valuation import value_fidelity
from finlytics.investments.market_data import LatestPriceRow

DAY = date(2025, 3, 31)


def lot(shares="10", cost="50", currency="USD", source="SP"):
    return EsppLot(
        connection_id=1, ticker="MSFT", purchase_date=DAY, shares=Decimal(shares),
        cost_basis=Decimal(cost), cost_basis_per_share=Decimal(cost) / Decimal(shares),
        source_currency=currency, share_source=source, dedup_hash="synthetic",
    )


def price(fx):
    return LatestPriceRow(DAY, 10, fx, 10 * fx, False)


@pytest.mark.parametrize("fx", [0.8, 1.2])
def test_usd_cost_and_gain_use_the_same_fx_and_include_dividends(fx):
    lots = [lot(), lot("0.5", "5", source="DO")]
    result = value_fidelity(lots, price(fx))
    rate = Decimal(str(fx))
    assert result.total_shares == Decimal("10.5")
    assert result.cost_basis_usd == Decimal(55)
    assert result.invested_eur == Decimal(55) * rate
    assert result.current_value_eur == Decimal(105) * rate
    assert result.gain_loss_eur == Decimal(50) * rate
    assert result.gain_loss_pct == Decimal(50) / 55 * 100
    assert not result.requires_usd_reimport
    values, costs = compute_evolution_series(lots, {DAY: (10, fx)}, DAY, DAY)
    assert values[0].value == float(result.current_value_eur)
    assert costs[0].value == float(result.invested_eur)


def test_missing_fx_is_unknown_not_zero_or_an_unconverted_dollar_amount():
    result = value_fidelity([lot()], None)
    assert result.cost_basis_usd == 50
    assert result.invested_eur is None
    assert result.current_value_eur is None
    assert result.gain_loss_eur is None
    assert result.gain_loss_pct is None


def test_legacy_eur_costs_are_preserved_and_explicitly_flagged():
    result = value_fidelity([lot(currency="EUR")], price(0.8))
    assert result.invested_eur == 50
    assert result.cost_basis_usd is None
    assert result.requires_usd_reimport


def test_an_unsupported_legacy_currency_is_not_treated_as_euros():
    result = value_fidelity([lot(currency="GBP")], price(0.8))
    assert result.current_value_eur == 80
    assert result.invested_eur is None
    assert result.gain_loss_eur is None
    assert result.requires_usd_reimport


def test_lot_identity_is_scoped_to_connection_and_keeps_identical_dividends():
    key = dict(
        connection_id=1, ticker="MSFT", purchase_date=DAY, shares=Decimal("0.5"),
        share_source="DO", dedup_ordinal=0, grant_date=None,
    )
    original = _compute_dedup_hash(**key)
    assert original != _compute_dedup_hash(**(key | {"connection_id": 2}))
    assert original != _compute_dedup_hash(**(key | {"dedup_ordinal": 1}))
    assert original != _compute_dedup_hash(**(key | {"grant_date": DAY}))
    assert original == _compute_dedup_hash(**(key | {"shares": Decimal("0.50000000")}))
