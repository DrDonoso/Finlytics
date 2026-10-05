"""Fidelity cost and valuation semantics shared by all portfolio surfaces."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from finlytics.db.models import EsppLot
from finlytics.investments.market_data import LatestPriceRow


def cost_in_eur(
    amount: Decimal, currency: str, fx_eur_usd: Decimal | None,
) -> Decimal | None:
    if currency == "EUR":
        return amount
    if currency == "USD" and fx_eur_usd is not None and fx_eur_usd.is_finite() and fx_eur_usd > 0:
        return amount * fx_eur_usd
    return None


def total_cost_eur(
    amounts: Mapping[str, Decimal], fx_eur_usd: Decimal | None,
) -> Decimal | None:
    total = Decimal(0)
    for currency, amount in amounts.items():
        converted = cost_in_eur(amount, currency, fx_eur_usd)
        if converted is None:
            return None
        total += converted
    return total


@dataclass(frozen=True)
class FidelityValuation:
    total_shares: Decimal
    cost_basis_usd: Decimal | None
    invested_eur: Decimal | None
    current_value_eur: Decimal | None
    gain_loss_eur: Decimal | None
    gain_loss_pct: Decimal | None
    requires_usd_reimport: bool


def value_fidelity(
    lots: Sequence[EsppLot], price: LatestPriceRow | None,
) -> FidelityValuation:
    shares = sum((Decimal(str(lot.shares)) for lot in lots), Decimal(0))
    costs: dict[str, Decimal] = {}
    for lot in lots:
        costs[lot.source_currency] = (
            costs.get(lot.source_currency, Decimal(0)) + Decimal(str(lot.cost_basis))
        )
    legacy = any(currency != "USD" for currency in costs)
    cost_usd = None if legacy else costs.get("USD", Decimal(0))
    fx = Decimal(str(price.fx_eur_usd)) if price is not None else None
    invested = total_cost_eur(costs, fx)
    value = None
    if price is not None and shares > 0:
        value = cost_in_eur(shares * Decimal(str(price.close_usd)), "USD", fx)
    gain = value - invested if value is not None and invested is not None else None
    pct = gain / invested * 100 if gain is not None and invested is not None and invested > 0 else None
    return FidelityValuation(shares, cost_usd, invested, value, gain, pct, legacy)
