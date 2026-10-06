from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from finlytics.db.models import (
    EsppLot,
    InvestmentConnection,
    InvestmentImportRun,
    PriceHistory,
    User,
)
from finlytics.investments.market_data import LatestPriceRow
from tests.pg.test_backup import api, owner

HEADER = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,Grant date,Share source,Holding period\n"
)
ROWS = [
    "Mar-31-2025,10,50,5,100,50,-,-,Jan-01-2025,SP,Short",
    "Jun-02-2025,0.5,5,10,5,0,-,-,-,DO,Short",
    "Jun-02-2025,0.5,5,10,5,0,-,-,-,DO,Short",
]


def csv(rows=ROWS, currency="USD"):
    return (HEADER + "\n".join(rows) + f"\nThe values are displayed in {currency}\n").encode()


@pytest.fixture(autouse=True)
def market_data(monkeypatch):
    snapshot = LatestPriceRow(date(2025, 6, 3), 10, 0.8, 8, False)
    monkeypatch.setattr("finlytics.api.fidelity.backfill_price_history", AsyncMock())
    monkeypatch.setattr("finlytics.api.fidelity.get_latest_price", AsyncMock(return_value=snapshot))
    monkeypatch.setattr("finlytics.investments.overview.get_latest_price", AsyncMock(return_value=snapshot))


async def upload(client, action, content):
    return await client.post(
        f"/api/investments/fidelity/import/{action}",
        files={"file": ("synthetic.csv", content, "text/csv")},
    )


async def test_preview_confirm_repeat_cost_changes_and_all_eur_surfaces(sessions):
    async with api(sessions, await owner(sessions)) as client:
        preview = await upload(client, "preview", csv())
        assert preview.status_code == 200
        assert preview.json()["source_currency"] == "USD"
        assert preview.json()["new_lots"][0]["cost_basis_total_usd"] == 50
        assert (await upload(client, "confirm", csv())).json() == {"inserted": 3, "duplicates": 0}
        assert (await upload(client, "confirm", csv())).json() == {"inserted": 0, "duplicates": 3}
        revised = csv([row.replace(",5,10,5,0", ",6,12,5,0") for row in reversed(ROWS)])
        repeat = (await upload(client, "preview", revised)).json()
        assert repeat["new_lots"] == []
        assert repeat["duplicate_count"] == 3
        assert (await upload(client, "confirm", revised)).json() == {"inserted": 0, "duplicates": 3}

        kpis = (await client.get("/api/investments/fidelity/kpis")).json()
        lots = (await client.get("/api/investments/fidelity/lots")).json()["lots"]
        combined = (await client.get("/api/investments/combined-overview")).json()
        assert kpis["cost_basis_usd"] == 60
        assert kpis["invested_eur"] == combined["total_invested_eur"] == 48
        assert kpis["current_value_eur"] == combined["total_value_eur"] == 88
        assert kpis["gain_loss_eur"] == combined["total_gain_loss_eur"] == 40
        assert kpis["gain_loss_pct"] == pytest.approx(83.3333)
        assert combined["providers"][0]["cost_basis_at_current_fx"]
        assert sum(lot["cost_basis_total_eur"] for lot in lots) == 48
        assert len(lots) == 3
        assert not kpis["requires_usd_reimport"]


@pytest.mark.parametrize("action", ["preview", "confirm"])
@pytest.mark.parametrize("currency", ["EUR", "GBP", "", "USD\nThe values are displayed in EUR"])
async def test_non_usd_or_ambiguous_currency_is_rejected_without_writes(sessions, action, currency):
    async with api(sessions, await owner(sessions)) as client:
        response = await upload(client, action, csv(currency=currency))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "fidelity_usd_required"
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(InvestmentConnection)) == 0
        assert await s.scalar(select(func.count()).select_from(EsppLot)) == 0


async def test_the_same_file_belongs_to_each_users_own_connection(sessions):
    first = await owner(sessions)
    async with sessions() as s, s.begin():
        second = User(username="second", password_hash="not-a-real-hash")
        s.add(second)
    for user in (first, second):
        async with api(sessions, user) as client:
            response = await upload(client, "confirm", csv())
            assert response.status_code == 200
            assert response.json()["inserted"] == 3
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(EsppLot)) == 6
        assert await s.scalar(select(func.count()).select_from(InvestmentImportRun)) == 2


async def test_concurrent_first_imports_share_one_connection_and_skip_duplicates(sessions):
    async with api(sessions, await owner(sessions)) as client:
        results = await asyncio.gather(
            upload(client, "confirm", csv()),
            upload(client, "confirm", csv()),
        )
    assert [response.status_code for response in results] == [200, 200]
    assert sorted((r.json()["inserted"], r.json()["duplicates"]) for r in results) == [(0, 3), (3, 0)]
    async with sessions() as s:
        assert await s.scalar(select(func.count()).select_from(InvestmentConnection)) == 1
        assert await s.scalar(select(func.count()).select_from(EsppLot)) == 3
        assert await s.scalar(select(func.count()).select_from(InvestmentImportRun)) == 1


async def test_legacy_lots_require_an_explicit_scoped_reset(sessions):
    user = await owner(sessions)
    async with sessions() as s, s.begin():
        fidelity = InvestmentConnection(user_id=user.id, plugin_id="fidelity-espp")
        indexa = InvestmentConnection(user_id=user.id, plugin_id="indexa-capital")
        s.add_all([fidelity, indexa])
        await s.flush()
        s.add(EsppLot(
            connection_id=fidelity.id, purchase_date=date(2025, 3, 31), shares=10,
            cost_basis=50, cost_basis_per_share=5, source_currency="EUR",
            share_source="SP", dedup_hash="legacy-synthetic",
        ))
        s.add(InvestmentImportRun(
            connection_id=fidelity.id, file_hash="legacy-file", source_currency="EUR",
            lots_inserted=1, lots_skipped=0,
        ))
        s.add(PriceHistory(
            ticker="MSFT", price_date=date(2025, 3, 31), close_usd=10,
            fx_eur_usd=Decimal("0.8"), close_eur=8,
        ))
    async with api(sessions, user) as client:
        kpis = (await client.get("/api/investments/fidelity/kpis")).json()
        assert kpis["requires_usd_reimport"]
        assert kpis["invested_eur"] == 50
        for action in ("preview", "confirm"):
            response = await upload(client, action, csv())
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "fidelity_legacy_lots"
        assert (await client.delete(f"/api/investments/connections/{fidelity.id}")).status_code == 204
        async with sessions() as s:
            assert await s.scalar(select(func.count()).select_from(EsppLot)) == 0
            assert await s.scalar(select(func.count()).select_from(InvestmentImportRun)) == 0
            assert await s.get(InvestmentConnection, indexa.id) is not None
            assert await s.scalar(select(func.count()).select_from(PriceHistory)) == 1
        assert (await upload(client, "confirm", csv())).json() == {"inserted": 3, "duplicates": 0}


async def test_sixty_one_existing_lots_and_five_new_ones_ignore_cost_changes(sessions):
    rows = []
    for i in range(66):
        day = date(2024, 1, 1) + timedelta(days=i)
        rows.append(f"{day.strftime('%b-%d-%Y')},1,10,10,20,10,-,-,-,DO,Long")
    async with api(sessions, await owner(sessions)) as client:
        assert (await upload(client, "confirm", csv(rows[:61]))).json()["inserted"] == 61
        revised = csv([row.replace(",1,10,10,", ",1,12,12,") for row in rows])
        preview = (await upload(client, "preview", revised)).json()
        assert preview["duplicate_count"] == 61
        assert len(preview["new_lots"]) == 5
        assert (await upload(client, "confirm", revised)).json() == {"inserted": 5, "duplicates": 61}


async def test_restore_rekeys_lots_for_new_connection_ids(sessions):
    user = await owner(sessions)
    async with api(sessions, user) as client:
        await upload(client, "confirm", csv())
        backup = (await client.get("/api/backup/export", params={"sections": "investments"})).json()
        connection = (await client.get("/api/investments/connections")).json()[0]
        await client.delete(f"/api/investments/connections/{connection['id']}")
        restored = await client.post("/api/backup/import", json=backup)
        assert restored.status_code == 200
        assert restored.json()["espp_lots_inserted"] == 3
        assert (await upload(client, "preview", csv())).json()["duplicate_count"] == 3
        assert (await upload(client, "confirm", csv())).json() == {"inserted": 0, "duplicates": 3}
        after = (await client.get("/api/backup/export", params={"sections": "investments"})).json()
        assert after["investments"]["espp_lots"][0]["dedup_hash"] != backup["investments"]["espp_lots"][0]["dedup_hash"]
import asyncio
