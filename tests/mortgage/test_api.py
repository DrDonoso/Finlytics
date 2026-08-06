"""End-to-end API tests for the mortgage router.

Uses a real in-memory SQLite database (aiosqlite + StaticPool) so the ORM
relationships, cascades and the amortization engine are all exercised for
real — mocking the session would test almost nothing here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.db.models import Account, Base, Category, EuriborRate, ImportRun, Transaction

USER_ID = 1

FIXED_PAYLOAD = {
    "name": "Vivienda habitual",
    "lender": "Banco Test",
    "initial_principal": 200000,
    "start_date": "2024-01-01",
    "term_months": 360,
    "payment_day": 1,
    "rate_type": "fixed",
    "include_in_net_worth": True,
    "rate_periods": [{"start_month": 0, "kind": "fixed", "fixed_rate": 3.0}],
    "bonuses": [],
}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(factory):
    async def _get_db():
        async with factory() as s:
            yield s

    user = MagicMock()
    user.id = USER_ID

    async def _get_user():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _get_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


async def _create(client, **overrides) -> dict:
    resp = await client.post("/api/mortgages", json={**FIXED_PAYLOAD, **overrides})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── CRUD ─────────────────────────────────────────────────────────────────────

class TestCreate:
    async def test_returns_201_with_the_created_mortgage(self, client):
        body = await _create(client)
        assert body["id"] > 0
        assert body["name"] == "Vivienda habitual"

    async def test_persists_the_rate_period(self, client):
        body = await _create(client)
        assert len(body["rate_periods"]) == 1
        assert body["rate_periods"][0]["fixed_rate"] == 3.0

    async def test_persists_bonuses(self, client):
        body = await _create(
            client,
            bonuses=[{"name": "Seguro hogar", "spread_reduction": 0.3, "annual_cost": 320}],
        )
        assert body["bonuses"][0]["name"] == "Seguro hogar"

    async def test_rejects_a_fixed_mortgage_without_a_rate(self, client):
        resp = await client.post(
            "/api/mortgages",
            json={**FIXED_PAYLOAD, "rate_periods": [{"start_month": 0, "kind": "fixed"}]},
        )
        assert resp.status_code == 422

    async def test_rejects_a_negative_principal(self, client):
        resp = await client.post("/api/mortgages", json={**FIXED_PAYLOAD, "initial_principal": -1})
        assert resp.status_code == 422

    async def test_rejects_a_mismatched_rate_type(self, client):
        """A 'mixed' mortgage needs both a fixed and a variable tranche."""
        resp = await client.post(
            "/api/mortgages", json={**FIXED_PAYLOAD, "rate_type": "mixed"}
        )
        assert resp.status_code == 422

    async def test_rejects_periods_not_starting_at_month_zero(self, client):
        resp = await client.post(
            "/api/mortgages",
            json={
                **FIXED_PAYLOAD,
                "rate_periods": [{"start_month": 12, "kind": "fixed", "fixed_rate": 3.0}],
            },
        )
        assert resp.status_code == 422

    async def test_rejects_an_invalid_payment_day(self, client):
        resp = await client.post("/api/mortgages", json={**FIXED_PAYLOAD, "payment_day": 45})
        assert resp.status_code == 422


class TestRead:
    async def test_list_is_empty_initially(self, client):
        resp = await client.get("/api/mortgages")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_live_kpis(self, client):
        await _create(client)
        row = (await client.get("/api/mortgages")).json()[0]
        assert row["outstanding_balance"] > 0
        assert row["monthly_payment"] == pytest.approx(843.21, abs=0.01)

    async def test_get_by_id_returns_the_full_config(self, client):
        created = await _create(client)
        body = (await client.get(f"/api/mortgages/{created['id']}")).json()
        assert body["id"] == created["id"]
        assert body["prepayments"] == []

    async def test_unknown_id_returns_404(self, client):
        assert (await client.get("/api/mortgages/9999")).status_code == 404


class TestUpdate:
    async def test_replaces_the_contract_fields(self, client):
        created = await _create(client)
        resp = await client.put(
            f"/api/mortgages/{created['id']}",
            json={**FIXED_PAYLOAD, "name": "Renombrada", "lender": "Otro Banco"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renombrada"

    async def test_replaces_the_rate_periods(self, client):
        created = await _create(client)
        resp = await client.put(
            f"/api/mortgages/{created['id']}",
            json={
                **FIXED_PAYLOAD,
                "rate_periods": [{"start_month": 0, "kind": "fixed", "fixed_rate": 1.5}],
            },
        )
        periods = resp.json()["rate_periods"]
        assert len(periods) == 1
        assert periods[0]["fixed_rate"] == 1.5

    async def test_unknown_id_returns_404(self, client):
        assert (await client.put("/api/mortgages/9999", json=FIXED_PAYLOAD)).status_code == 404


class TestDelete:
    async def test_removes_the_mortgage(self, client):
        created = await _create(client)
        assert (await client.delete(f"/api/mortgages/{created['id']}")).status_code == 204
        assert (await client.get("/api/mortgages")).json() == []

    async def test_unknown_id_returns_404(self, client):
        assert (await client.delete("/api/mortgages/9999")).status_code == 404


# ── Derived payloads ─────────────────────────────────────────────────────────

class TestOverview:
    @pytest.fixture
    async def overview(self, client):
        created = await _create(client)
        return (await client.get(f"/api/mortgages/{created['id']}/overview")).json()

    def test_reports_the_textbook_instalment(self, overview):
        assert overview["current_payment"] == pytest.approx(843.21, abs=0.01)

    def test_outstanding_plus_amortized_equals_the_principal(self, overview):
        total = overview["outstanding_balance"] + overview["amortized_principal"]
        assert total == pytest.approx(overview["initial_principal"], abs=0.01)

    def test_interest_paid_plus_remaining_equals_the_total(self, overview):
        total = overview["interest_paid"] + overview["interest_remaining"]
        assert total == pytest.approx(overview["total_interest"], abs=0.01)

    def test_progress_is_a_percentage(self, overview):
        assert 0 <= overview["progress_pct"] <= 100

    def test_fixed_rate_mortgage_has_no_projection(self, overview):
        assert overview["has_projection"] is False

    def test_ltv_is_absent_without_a_property_value(self, overview):
        assert overview["ltv_pct"] is None

    async def test_ltv_is_computed_from_the_property_value(self, client):
        created = await _create(client, property_value=250000)
        body = (await client.get(f"/api/mortgages/{created['id']}/overview")).json()
        assert body["ltv_pct"] == pytest.approx(
            body["outstanding_balance"] / 250000 * 100, abs=0.05
        )


class TestSchedule:
    async def test_year_granularity_rolls_up_by_year(self, client):
        created = await _create(client)
        body = (await client.get(f"/api/mortgages/{created['id']}/schedule")).json()
        assert body["granularity"] == "year"
        assert len(body["years"]) == 30       # 2024-01 .. 2053-12 = 30 calendar years
        assert body["rows"] == []

    async def test_month_granularity_returns_every_instalment(self, client):
        created = await _create(client)
        body = (
            await client.get(f"/api/mortgages/{created['id']}/schedule?granularity=month")
        ).json()
        assert len(body["rows"]) == 360
        assert body["years"] == []

    async def test_total_principal_equals_the_amount_borrowed(self, client):
        created = await _create(client)
        body = (await client.get(f"/api/mortgages/{created['id']}/schedule")).json()
        assert body["total_principal"] == pytest.approx(200000, abs=0.01)

    async def test_rejects_an_unknown_granularity(self, client):
        created = await _create(client)
        resp = await client.get(f"/api/mortgages/{created['id']}/schedule?granularity=daily")
        assert resp.status_code == 422


class TestCharts:
    async def test_returns_both_series(self, client):
        created = await _create(client)
        body = (await client.get(f"/api/mortgages/{created['id']}/charts")).json()
        assert body["balance"]
        assert body["composition"]

    async def test_balance_series_decreases(self, client):
        created = await _create(client)
        balance = (await client.get(f"/api/mortgages/{created['id']}/charts")).json()["balance"]
        assert balance[0]["balance"] > balance[-1]["balance"]
        assert balance[-1]["balance"] == pytest.approx(0, abs=0.01)


# ── Prepayments ──────────────────────────────────────────────────────────────

class TestPrepayments:
    async def test_creates_a_prepayment(self, client):
        created = await _create(client)
        resp = await client.post(
            f"/api/mortgages/{created['id']}/prepayments",
            json={"payment_date": "2025-01-01", "amount": 20000, "mode": "reduce_term"},
        )
        assert resp.status_code == 201
        assert resp.json()["amount"] == 20000

    async def test_prepayment_shortens_the_schedule(self, client):
        created = await _create(client)
        await client.post(
            f"/api/mortgages/{created['id']}/prepayments",
            json={"payment_date": "2025-01-01", "amount": 20000, "mode": "reduce_term"},
        )
        body = (await client.get(f"/api/mortgages/{created['id']}/overview")).json()
        assert body["months_saved"] > 0
        assert body["interest_saved"] > 0

    async def test_rejects_a_non_positive_amount(self, client):
        created = await _create(client)
        resp = await client.post(
            f"/api/mortgages/{created['id']}/prepayments",
            json={"payment_date": "2025-01-01", "amount": 0, "mode": "reduce_term"},
        )
        assert resp.status_code == 422

    async def test_deletes_a_prepayment(self, client):
        created = await _create(client)
        prepayment = (
            await client.post(
                f"/api/mortgages/{created['id']}/prepayments",
                json={"payment_date": "2025-01-01", "amount": 20000, "mode": "reduce_term"},
            )
        ).json()
        resp = await client.delete(
            f"/api/mortgages/{created['id']}/prepayments/{prepayment['id']}"
        )
        assert resp.status_code == 204
        body = (await client.get(f"/api/mortgages/{created['id']}")).json()
        assert body["prepayments"] == []

    async def test_deleting_the_mortgage_cascades_to_prepayments(self, client, factory):
        created = await _create(client)
        await client.post(
            f"/api/mortgages/{created['id']}/prepayments",
            json={"payment_date": "2025-01-01", "amount": 20000, "mode": "reduce_term"},
        )
        await client.delete(f"/api/mortgages/{created['id']}")

        from sqlalchemy import func, select

        from finlytics.db.models import MortgagePrepayment

        async with factory() as s:
            count = await s.scalar(select(func.count()).select_from(MortgagePrepayment))
        assert count == 0


# ── Simulator ────────────────────────────────────────────────────────────────

class TestSimulate:
    @pytest.fixture
    async def mortgage_id(self, client):
        return (await _create(client))["id"]

    async def test_reduce_term_saves_interest_and_months(self, client, mortgage_id):
        body = (
            await client.post(
                f"/api/mortgages/{mortgage_id}/simulate",
                json={"amount": 20000, "payment_date": "2025-01-01", "mode": "reduce_term"},
            )
        ).json()
        assert body["interest_saved"] > 0
        assert body["months_saved"] > 0
        assert body["payment_delta"] == 0

    async def test_reduce_payment_lowers_the_instalment(self, client, mortgage_id):
        body = (
            await client.post(
                f"/api/mortgages/{mortgage_id}/simulate",
                json={"amount": 20000, "payment_date": "2025-01-01", "mode": "reduce_payment"},
            )
        ).json()
        assert body["payment_delta"] < 0
        assert body["months_saved"] == 0

    async def test_returns_both_balance_curves(self, client, mortgage_id):
        body = (
            await client.post(
                f"/api/mortgages/{mortgage_id}/simulate",
                json={"amount": 20000, "payment_date": "2025-01-01", "mode": "reduce_term"},
            )
        ).json()
        assert body["balance_before"] and body["balance_after"]

    async def test_compares_against_an_alternative_return(self, client, mortgage_id):
        body = (
            await client.post(
                f"/api/mortgages/{mortgage_id}/simulate",
                json={
                    "amount": 20000,
                    "payment_date": "2025-01-01",
                    "mode": "reduce_term",
                    "alt_return_pct": 12,
                },
            )
        ).json()
        assert body["alternative_gain"] > 0
        assert body["worth_it"] is False

    async def test_does_not_persist_the_simulated_prepayment(self, client, mortgage_id):
        await client.post(
            f"/api/mortgages/{mortgage_id}/simulate",
            json={"amount": 20000, "payment_date": "2025-01-01", "mode": "reduce_term"},
        )
        body = (await client.get(f"/api/mortgages/{mortgage_id}")).json()
        assert body["prepayments"] == []


# ── Net worth ────────────────────────────────────────────────────────────────

class TestNetWorth:
    async def test_zero_when_there_are_no_mortgages(self, client):
        body = (await client.get("/api/mortgages/net-worth")).json()
        assert body == {
            "outstanding_debt": 0.0,
            "property_value": 0.0,
            "net_contribution": 0.0,
            "count": 0,
        }

    async def test_subtracts_the_outstanding_debt(self, client):
        await _create(client)
        body = (await client.get("/api/mortgages/net-worth")).json()
        assert body["outstanding_debt"] > 0
        assert body["net_contribution"] < 0

    async def test_adds_the_property_value(self, client):
        await _create(client, property_value=250000)
        body = (await client.get("/api/mortgages/net-worth")).json()
        assert body["property_value"] == 250000
        assert body["net_contribution"] == pytest.approx(
            250000 - body["outstanding_debt"], abs=0.01
        )

    async def test_excluded_mortgage_does_not_count(self, client):
        """The include_in_net_worth toggle must actually keep the KPI unchanged."""
        await _create(client, include_in_net_worth=False, property_value=250000)
        body = (await client.get("/api/mortgages/net-worth")).json()
        assert body["count"] == 0
        assert body["net_contribution"] == 0.0


# ── Reconciliation ───────────────────────────────────────────────────────────

class TestReconciliation:
    async def test_reports_not_linked_when_no_account_or_category(self, client):
        created = await _create(client)
        body = (await client.get(f"/api/mortgages/{created['id']}/reconciliation")).json()
        assert body["linked"] is False
        assert body["rows"] == []

    async def test_matches_real_transactions_against_the_schedule(self, client, factory):
        async with factory() as s:
            account = Account(name="Banco Test", type="bank", currency="EUR")
            category = Category(name="Mortgage")
            s.add_all([account, category])
            await s.flush()
            run = ImportRun(account_id=account.id, source_filename="test.pdf")
            s.add(run)
            await s.flush()
            # Two real charges matching the first instalments of the schedule.
            # Transaction.id is a plain BigInteger PK, so SQLite needs it set.
            # is_system is set explicitly because the model's server_default is
            # the string "false", which SQLite coerces to True.
            for idx, (day, amount) in enumerate(
                ((date(2024, 1, 1), "-843.21"), (date(2024, 2, 1), "-843.21")), start=1
            ):
                s.add(
                    Transaction(
                        id=idx,
                        account_id=account.id,
                        import_run_id=run.id,
                        transaction_date=day,
                        amount=Decimal(amount),
                        currency="EUR",
                        description="Cuota hipoteca",
                        category_id=category.id,
                        dedup_hash=f"hash-{day}",
                        is_system=False,
                    )
                )
            await s.commit()
            account_id, category_id = account.id, category.id

        created = await _create(
            client, linked_account_id=account_id, linked_category_id=category_id
        )
        # The default window is the last 24 months; widen it to cover 2024.
        body = (
            await client.get(f"/api/mortgages/{created['id']}/reconciliation?months=360")
        ).json()

        assert body["linked"] is True
        matched = [r for r in body["rows"] if r["matched"]]
        assert len(matched) == 2
        assert matched[0]["deviation"] == pytest.approx(0, abs=0.01)

    async def test_flags_months_without_a_charge(self, client, factory):
        async with factory() as s:
            account = Account(name="Solo Cuenta", type="bank", currency="EUR")
            s.add(account)
            await s.flush()
            account_id = account.id
            await s.commit()

        created = await _create(client, linked_account_id=account_id)
        body = (await client.get(f"/api/mortgages/{created['id']}/reconciliation")).json()
        assert body["linked"] is True
        assert all(not row["matched"] for row in body["rows"])


# ── Euribor ──────────────────────────────────────────────────────────────────

class TestEuribor:
    async def test_returns_the_cached_series(self, client, factory):
        async with factory() as s:
            s.add_all([
                EuriborRate(
                    index_name="euribor_12m", period=date(2024, 1, 1),
                    rate=Decimal("3.609"), source="ecb",
                ),
                EuriborRate(
                    index_name="euribor_12m", period=date(2024, 2, 1),
                    rate=Decimal("3.671"), source="ecb",
                ),
            ])
            await s.commit()

        body = (await client.get("/api/mortgages/euribor")).json()
        assert len(body["points"]) == 2
        assert body["latest"] == pytest.approx(3.671)
        assert body["latest_period"] == "2024-02-01"

    async def test_rejects_an_unmapped_index(self, client):
        """The parameter is constrained: an arbitrary string must not reach the
        series lookup or the log line."""
        resp = await client.get("/api/mortgages/euribor?index_name=made-up")
        assert resp.status_code == 422


class TestVariableRateMortgage:
    async def test_uses_the_cached_index_and_flags_projection(self, client, factory):
        async with factory() as s:
            s.add(
                EuriborRate(
                    index_name="euribor_12m", period=date(2023, 11, 1),
                    rate=Decimal("4.0"), source="ecb",
                )
            )
            await s.commit()

        created = await _create(
            client,
            rate_type="variable",
            rate_periods=[{
                "start_month": 0,
                "kind": "variable",
                "index_name": "euribor_12m",
                "spread": 0.9,
                "review_months": 12,
                "review_lag_months": 2,
            }],
        )
        schedule = (
            await client.get(f"/api/mortgages/{created['id']}/schedule?granularity=month")
        ).json()
        # Instalment 0 is 2024-01, lag 2 -> reads the 2023-11 index: 4.0 + 0.9
        assert schedule["rows"][0]["annual_rate"] == pytest.approx(4.9, abs=0.001)
        assert schedule["rows"][0]["projected"] is False

        overview = (await client.get(f"/api/mortgages/{created['id']}/overview")).json()
        assert overview["has_projection"] is True   # future months fall back to the last known
