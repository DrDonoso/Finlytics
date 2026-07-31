"""Abstract base class and normalised result types for investment providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NormalizedDrawdown:
    """Max drawdown info from Indexa drawdowns object."""
    max_drawdown: float
    max_drawdown_eur: float
    start_date: str   # YYYY-MM-DD
    end_date: str     # YYYY-MM-DD


@dataclass
class NormalizedMonthlyReturnRow:
    """One calendar year row in the monthly returns matrix."""
    year: int
    months_pct: dict    # {month_int: float} — TWR return for each month
    months_eur: dict    # {month_int: float | None} — EUR P&L for each month
    total_pct: float | None
    total_eur: float | None
    benchmark_pct: float | None   # compounded annual benchmark return


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
    twr_total: float | None = None            # cumulative TWR (time_return)
    twr_last_week: float | None = None
    twr_last_month: float | None = None
    twr_last_year: float | None = None
    money_return: float | None = None         # money-weighted total return
    money_return_annual: float | None = None  # annualised money-weighted return
    volatility: float | None = None
    xirr: float | None = None
    pl: float | None = None
    invested: float | None = None
    # "Valor total" box numbers (mirror Indexa UI)
    aportaciones: float | None = None         # gross inflows (return.inflows)
    retenciones: float | None = None          # tax outflows, negative (return.tax_outflows)
    rentabilidad_eur: float | None = None     # P&L in EUR (return.pl)
    rentabilidad_pct: float | None = None     # money-weighted return (return.money_return)
    sharpe_ratio: float | None = None         # top-level data["sharpe_ratio"]


@dataclass
class NormalizedValuePoint:
    date: str
    value: float


@dataclass
class NormalizedContributionEvent:
    """A single contribution or withdrawal event derived from net_amounts deltas."""
    date: str         # YYYY-MM-DD
    amount: float     # positive = contribution, negative = withdrawal (rounded to cents)
    cumulative: float # running net invested after this event (rounded to cents)
    type: str         # "contribution" | "withdrawal"


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
    contributions_series: list[NormalizedValuePoint] = field(default_factory=list)
    contribution_events: list[NormalizedContributionEvent] = field(default_factory=list)
    monthly_returns: list[NormalizedMonthlyReturnRow] = field(default_factory=list)
    drawdown: NormalizedDrawdown | None = None
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
    # live_api: fetches data from an external API in real time (e.g. Indexa Capital).
    # statement_import: ingests pre-parsed statements (e.g. Fidelity ESPP CSV).
    provider_type: str = "live_api"

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

    async def import_statement(self, *args, **kwargs) -> None:
        """Non-abstract hook for statement-import providers.

        Override in subclasses that process file uploads rather than live APIs.
        The default no-op is intentional: live_api providers never call this.
        """
