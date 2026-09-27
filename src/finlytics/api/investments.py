"""Investment endpoints: plugin registry + connection CRUD + portfolio aggregation.

Phase 2 — real Indexa Capital connector.

Security (Romanoff, mandatory):
- Token NEVER logged, never in any API response, never returned to frontend.
- Connections expose masked account labels only.
- EncryptionNotConfiguredError → 503 (never plaintext fallback).
- Only GET calls to Indexa; POST /auth/authenticate path not implemented.
"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    CombinedOverviewOut,
    ConnectCreate,
    ConnectionOut,
    InvestmentPluginOut,
    InvestmentPortfolioOut,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from finlytics.db.models import InvestmentConnection
from finlytics.investments import service as inv_service
from finlytics.investments.crypto import EncryptionNotConfiguredError
from finlytics.investments.indexa import IndexaAuthError, IndexaConnectionError
from finlytics.investments.overview import build_combined_overview
from finlytics.investments.service import NoValidAccountsError

router = APIRouter(prefix="/investments", tags=["investments"])

_PLUGIN_REGISTRY: list[InvestmentPluginOut] = [
    InvestmentPluginOut(
        id="indexa-capital",
        name="Indexa Capital",
        description="Automated index-fund portfolio management",
        icon="🏦",
        status="available",  # base value — overridden dynamically in list_plugins
        auth_type="token",
        supported_features=["holdings", "transactions", "performance"],
    ),
    InvestmentPluginOut(
        id="fidelity-espp",
        name="Fidelity ESPP",
        description="Import your Fidelity ESPP (MSFT) open-lots CSV",
        icon="💼",
        status="available",  # base value — overridden dynamically in list_plugins
        auth_type="none",
        supported_features=["holdings", "performance"],
        import_route="/investments/fidelity-espp",
    ),
]

# Plugin IDs whose status is resolved dynamically against active DB connections.
_DYNAMIC_PLUGIN_IDS: frozenset[str] = frozenset({"indexa-capital", "fidelity-espp"})


@router.get("/plugins", response_model=list[InvestmentPluginOut])
async def list_plugins(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InvestmentPluginOut]:
    """Plugin registry. Dynamic plugins resolve status from active DB connections."""
    result = await db.execute(
        select(InvestmentConnection.plugin_id)
        .where(
            InvestmentConnection.user_id == user.id,
            InvestmentConnection.status == "active",
            InvestmentConnection.plugin_id.in_(list(_DYNAMIC_PLUGIN_IDS)),
        )
        .distinct()
    )
    connected_ids = {row[0] for row in result}
    return [
        p.model_copy(update={"status": "connected" if p.id in connected_ids else "available"})
        if p.id in _DYNAMIC_PLUGIN_IDS
        else p
        for p in _PLUGIN_REGISTRY
    ]


@router.post("/connections/validate", response_model=ValidateTokenResponse)
async def validate_token(
    body: ValidateTokenRequest,
    _user=Depends(get_current_user),
) -> ValidateTokenResponse:
    """Validate an Indexa token and return discovered accounts.

    Step 1 of the wizard: stores NOTHING — no DB writes, no token persisted,
    no encryption required.  The raw account_numbers are returned transiently
    so the wizard can show checkboxes for the connect step.
    """
    try:
        accounts = await inv_service.validate_token_for_wizard(token=body.token)
        return ValidateTokenResponse(accounts=accounts)
    except IndexaAuthError:
        raise HTTPException(
            status_code=400,
            detail="Invalid token — check it in Indexa Capital.",
        )
    except IndexaConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not verify the token — network error talking to Indexa Capital.",
        )


@router.post("/connections", response_model=list[ConnectionOut], status_code=201)
async def connect(
    body: ConnectCreate,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionOut]:
    """Step 2 of the wizard: re-validate token, persist only selected accounts.

    Server enforces ownership: any account_number not owned by the token is
    silently dropped.  Token is NEVER stored in plaintext or returned.
    """
    if not body.account_numbers:
        raise HTTPException(status_code=400, detail="account_numbers must not be empty.")
    try:
        return await inv_service.connect_plugin(
            user_id=user.id,
            plugin_id="indexa-capital",
            token=body.token,
            account_numbers=body.account_numbers,
            db=db,
        )
    except EncryptionNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Server not configured for encryption — contact the administrator.",
        )
    except IndexaAuthError:
        raise HTTPException(
            status_code=400,
            detail="Invalid token — check it in Indexa Capital.",
        )
    except IndexaConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not verify the token — network error talking to Indexa Capital.",
        )
    except NoValidAccountsError:
        raise HTTPException(
            status_code=400,
            detail="The selected account_numbers do not belong to this token.",
        )


@router.get("/connections", response_model=list[ConnectionOut])
async def get_connections(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectionOut]:
    """List connected plugins (masked labels + status only; token excluded)."""
    return await inv_service.list_connections(user_id=user.id, db=db)


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: int,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Hard-delete the connection and its encrypted token.  Clears cache entry."""
    found = await inv_service.delete_connection(
        connection_id=connection_id, user_id=user.id, db=db
    )
    if not found:
        raise HTTPException(status_code=404, detail="Connection not found.")


@router.get("/portfolio", response_model=InvestmentPortfolioOut)
async def get_portfolio(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InvestmentPortfolioOut:
    """Aggregate portfolio across all active connections.

    Returns KPIs, holdings table, value series, allocation data, and returns
    metrics sufficient for the full Inversiones page visualisation.

    Cache: fresh data (<24h) is returned instantly from the DB.  Stale data is
    returned immediately while a background task re-fetches from Indexa so the
    next page open is fresh.  cache_stale=True in the response signals this.
    """
    try:
        return await inv_service.get_portfolio(
            user_id=user.id, db=db, background_tasks=background_tasks
        )
    except EncryptionNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Server not configured for encryption — cannot decrypt connection tokens.",
        )


@router.get("/combined-overview", response_model=CombinedOverviewOut)
async def combined_overview(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CombinedOverviewOut:
    """Aggregated investments overview across all connected providers.

    Built by ``investments.overview.build_combined_overview``, which the
    assistant's investment tool calls too, so both read the same figures.
    Returns zeros/empty arrays (HTTP 200) when no connections are active.
    """
    try:
        return await build_combined_overview(
            user_id=user.id, db=db, background_tasks=background_tasks
        )
    except EncryptionNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Server not configured for encryption — cannot decrypt connection tokens.",
        )
