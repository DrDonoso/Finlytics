"""Abstract base class and normalised result types for investment providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DiscoveredAccount:
    account_number: str
    account_type: str
    account_status: str


@dataclass
class ValidationResult:
    valid: bool
    accounts: list[DiscoveredAccount] = field(default_factory=list)


@dataclass
class NormalizedHolding:
    name: str
    ticker: str | None
    asset_class: str   # equity | fixed_income | cash | other
    units: float | None
    current_value: float
    cost_basis: float | None
    gain_loss: float | None
    gain_loss_pct: float | None


@dataclass
class NormalizedReturns:
    twr_annual: float | None = None
    xirr: float | None = None
    pl: float | None = None
    invested: float | None = None


@dataclass
class NormalizedValuePoint:
    date: str
    value: float


@dataclass
class NormalizedCashInvested:
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float


@dataclass
class NormalizedPerformance:
    total_value: float
    returns: NormalizedReturns
    value_series: list[NormalizedValuePoint] = field(default_factory=list)
    cash_invested: NormalizedCashInvested | None = None


@dataclass
class NormalizedPortfolio:
    holdings: list[NormalizedHolding]
    total_value: float
    total_invested: float | None
    total_gain_loss: float | None
    performance: NormalizedPerformance | None = None


class InvestmentProvider(ABC):
    """Base interface that every investment connector must implement."""

    plugin_id: str

    @abstractmethod
    async def validate_token(self, token: str) -> ValidationResult:
        """Call the external API to verify the token; return discovered accounts."""
        ...

    @abstractmethod
    async def get_portfolio(
        self, token: str, account_numbers: list[str]
    ) -> NormalizedPortfolio:
        """Fetch holdings + performance for the listed accounts."""
        ...

    @abstractmethod
    async def get_performance(
        self, token: str, account_number: str
    ) -> NormalizedPerformance:
        """Fetch return metrics + value series for one account."""
        ...
