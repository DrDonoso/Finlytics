"""Investments plugin registry endpoint.

Phase 1 — stub only.  Returns the static list of known investment plugins;
all are ``coming_soon``.  No DB access, no migrations required.

Phase 2 will add: plugin config storage, credential vault, per-plugin
connectors, and GET /investments/portfolio aggregation.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from finlytics.api.deps import get_current_user
from finlytics.api.schemas import InvestmentPluginOut

router = APIRouter(prefix="/investments", tags=["investments"])

_PLUGIN_REGISTRY: list[InvestmentPluginOut] = [
    InvestmentPluginOut(
        id="indexa-capital",
        name="Indexa Capital",
        description="Automated index-fund portfolio management",
        icon="🏦",
        status="coming_soon",
        auth_type="token",
        supported_features=["holdings", "transactions", "performance"],
    ),
    InvestmentPluginOut(
        id="generic-broker",
        name="Broker (Stocks & ETFs)",
        description="Connect a stock/ETF broker account",
        icon="📈",
        status="coming_soon",
        auth_type="api_key",
        supported_features=["holdings", "transactions"],
    ),
    InvestmentPluginOut(
        id="crypto-exchange",
        name="Crypto Exchange",
        description="Track crypto holdings from an exchange",
        icon="🪙",
        status="coming_soon",
        auth_type="api_key",
        supported_features=["holdings"],
    ),
]


@router.get("/plugins", response_model=list[InvestmentPluginOut])
async def list_plugins(
    _user=Depends(get_current_user),
) -> list[InvestmentPluginOut]:
    """Return the static registry of known investment plugins."""
    return _PLUGIN_REGISTRY
