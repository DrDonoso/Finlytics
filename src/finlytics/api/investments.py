"""Investment endpoints: plugin registry + connection CRUD + portfolio aggregation.

Phase 2 — real Indexa Capital connector.

Security (Romanoff, mandatory):
- Token NEVER logged, never in any API response, never returned to frontend.
- Connections expose masked account labels only.
- EncryptionNotConfiguredError → 503 (never plaintext fallback).
- Only GET calls to Indexa; POST /auth/authenticate path not implemented.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.schemas import (
    AssetClassAllocationItem,
    CombinedOverviewOut,
    ConnectionOut,
    ConnectCreate,
    InvestmentPluginOut,
    InvestmentPortfolioOut,
    ProviderAllocationItem,
    ProviderCardOut,
    ValidateTokenRequest,
    ValidateTokenResponse,
)
from finlytics.db.models import EsppLot, InvestmentConnection
from finlytics.investments import service as inv_service
from finlytics.investments.crypto import EncryptionNotConfiguredError
from finlytics.investments.indexa import IndexaAuthError, IndexaConnectionError
from finlytics.investments.market_data import LatestPriceRow, get_latest_price
from finlytics.investments.service import NoValidAccountsError

log = logging.getLogger(__name__)

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


# ── Label maps for combined-overview ─────────────────────────────────────────

_PROVIDER_LABELS: dict[str, str] = {
    "indexa": "Indexa Capital",
    "fidelity": "Fidelity ESPP",
}

_ASSET_CLASS_LABELS: dict[str, str] = {
    "equity": "Renta Variable",
    "fixed_income": "Renta Fija",
    "cash": "Efectivo",
    "espp_stock": "ESPP Stock",
    "other": "Otros",
    "mixed": "Mixto",
}


def _empty_overview() -> CombinedOverviewOut:
    """Zero-state overview returned when no active connections exist."""
    return CombinedOverviewOut(
        total_value_eur=0.0,
        total_invested_eur=None,
        total_gain_loss_eur=None,
        total_gain_loss_pct=None,
        by_provider=[],
        by_asset_class=[],
        providers=[],
    )


@router.get("/combined-overview", response_model=CombinedOverviewOut)
async def combined_overview(
    background_tasks: BackgroundTasks,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CombinedOverviewOut:
    """Aggregated investments overview across all connected providers.

    Merges Indexa Capital (24h-cached portfolio) and Fidelity ESPP (lots + latest
    price) into:
    - KPI strip: total_value_eur, total_invested_eur, gain/loss
    - Donut: allocation by provider
    - Donut: allocation by asset class (Indexa asset types + espp_stock for Fidelity)
    - Provider cards: per-provider summary linking to detail pages

    Handles degraded providers gracefully — if price is unavailable, the provider
    card is included with null values but the provider is omitted from the donut
    allocations so percentages always sum to 100.

    Returns zeros/empty arrays (HTTP 200) when no connections are active.
    """
    # 1. Query all active connections
    active_conns = (
        await db.execute(
            select(InvestmentConnection).where(
                InvestmentConnection.user_id == user.id,
                InvestmentConnection.status == "active",
            )
        )
    ).scalars().all()

    if not active_conns:
        return _empty_overview()

    plugin_ids = {c.plugin_id for c in active_conns}
    has_indexa = "indexa-capital" in plugin_ids
    has_fidelity = "fidelity-espp" in plugin_ids

    # 2. Fetch Fidelity lots within the same autobegin (no extra round-trip)
    lots: list = []
    if has_fidelity:
        fidelity_conn = next(
            (c for c in active_conns if c.plugin_id == "fidelity-espp"), None
        )
        if fidelity_conn is not None:
            lots = (
                await db.execute(
                    select(EsppLot).where(EsppLot.connection_id == fidelity_conn.id)
                )
            ).scalars().all()
        else:
            has_fidelity = False

    # 3. Commit to reset the autobegin; get_latest_price requires a fresh session
    await db.commit()

    # 4. Fetch latest MSFT price (fresh session after commit)
    fidelity_price: LatestPriceRow | None = None
    if has_fidelity:
        try:
            fidelity_price = await get_latest_price(db)
        except Exception as exc:
            log.warning("combined_overview: get_latest_price failed (degraded): %s", exc)

    # 5. Fetch Indexa portfolio via the 24h DB cache — never bypass the cache
    indexa_portfolio: InvestmentPortfolioOut | None = None
    if has_indexa:
        try:
            indexa_portfolio = await inv_service.get_portfolio(
                user_id=user.id, db=db, background_tasks=background_tasks
            )
        except EncryptionNotConfiguredError:
            raise HTTPException(
                status_code=503,
                detail="Server not configured for encryption — cannot decrypt connection tokens.",
            )
        except Exception as exc:
            log.warning("combined_overview: Indexa portfolio fetch failed (degraded): %s", exc)

    # 6. Build per-provider summary rows; value_eur is None when price unavailable
    provider_rows: list[dict] = []

    if has_indexa:
        if indexa_portfolio is not None:
            iv: float | None = indexa_portfolio.total_value
            ii: float | None = indexa_portfolio.total_invested
            ig: float | None = indexa_portfolio.total_gain_loss
        else:
            iv = ii = ig = None
        provider_rows.append({
            "provider_id": "indexa",
            "plugin_id": "indexa-capital",
            "name": "Indexa Capital",
            "icon": "🏦",
            "value_eur": iv,
            "invested_eur": ii,
            "gain_loss_eur": ig,
        })

    if has_fidelity:
        total_shares = sum(float(lot.shares) for lot in lots)
        invested_eur = sum(float(lot.cost_basis) for lot in lots)

        fv: float | None = None
        fg: float | None = None
        if fidelity_price is not None and total_shares > 0:
            fv = total_shares * fidelity_price.close_usd * fidelity_price.fx_eur_usd
            fg = fv - invested_eur

        provider_rows.append({
            "provider_id": "fidelity",
            "plugin_id": "fidelity-espp",
            "name": "Fidelity ESPP",
            "icon": "📊",
            "value_eur": fv,
            "invested_eur": invested_eur if total_shares > 0 else None,
            "gain_loss_eur": fg,
        })

    # 7. Aggregate totals — only from providers with a known current value
    total_value = sum(r["value_eur"] for r in provider_rows if r["value_eur"] is not None)
    invested_contributors = [
        r["invested_eur"]
        for r in provider_rows
        if r["value_eur"] is not None and r["invested_eur"] is not None
    ]
    gain_contributors = [
        r["gain_loss_eur"]
        for r in provider_rows
        if r["gain_loss_eur"] is not None
    ]

    total_invested: float | None = sum(invested_contributors) if invested_contributors else None
    total_gain_loss: float | None = sum(gain_contributors) if gain_contributors else None
    total_gain_loss_pct: float | None = None
    if total_gain_loss is not None and total_invested and total_invested > 0:
        total_gain_loss_pct = round(total_gain_loss / total_invested * 100.0, 4)

    # 8. Allocation by provider (omit providers with null value — donut needs real numbers)
    by_provider: list[ProviderAllocationItem] = []
    for r in provider_rows:
        if r["value_eur"] is not None:
            pct = round(r["value_eur"] / total_value * 100.0, 2) if total_value > 0 else 0.0
            by_provider.append(ProviderAllocationItem(
                provider=r["provider_id"],
                label=_PROVIDER_LABELS.get(r["provider_id"], r["name"]),
                value_eur=round(r["value_eur"], 2),
                pct=pct,
            ))

    # 9. Allocation by asset class
    asset_class_values: dict[str, float] = {}
    if indexa_portfolio is not None:
        for h in indexa_portfolio.holdings:
            asset_class_values[h.asset_class] = (
                asset_class_values.get(h.asset_class, 0.0) + h.current_value
            )
    fidelity_row = next((r for r in provider_rows if r["provider_id"] == "fidelity"), None)
    if fidelity_row is not None and fidelity_row["value_eur"] is not None:
        asset_class_values["espp_stock"] = (
            asset_class_values.get("espp_stock", 0.0) + fidelity_row["value_eur"]
        )

    by_asset_class: list[AssetClassAllocationItem] = [
        AssetClassAllocationItem(
            asset_class=ac,
            label=_ASSET_CLASS_LABELS.get(ac, ac),
            value_eur=round(v, 2),
            pct=round(v / total_value * 100.0, 2) if total_value > 0 else 0.0,
        )
        for ac, v in sorted(asset_class_values.items(), key=lambda x: -x[1])
    ]

    # 10. Provider cards (all connected providers; value/gain may be null)
    providers: list[ProviderCardOut] = []
    for r in provider_rows:
        gl = r["gain_loss_eur"]
        ii_r = r.get("invested_eur")
        gain_pct: float | None = None
        if gl is not None and ii_r and ii_r > 0:
            gain_pct = round(gl / ii_r * 100.0, 4)
        providers.append(ProviderCardOut(
            id=r["plugin_id"],
            name=r["name"],
            icon=r["icon"],
            value_eur=round(r["value_eur"], 2) if r["value_eur"] is not None else None,
            gain_loss_eur=round(gl, 2) if gl is not None else None,
            gain_loss_pct=gain_pct,
            route=f"/investments/{r['plugin_id']}",
        ))

    return CombinedOverviewOut(
        total_value_eur=round(total_value, 2),
        total_invested_eur=round(total_invested, 2) if total_invested is not None else None,
        total_gain_loss_eur=round(total_gain_loss, 2) if total_gain_loss is not None else None,
        total_gain_loss_pct=total_gain_loss_pct,
        by_provider=by_provider,
        by_asset_class=by_asset_class,
        providers=providers,
    )
