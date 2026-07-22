"""Integration / endpoint tests for the Fidelity ESPP connector.

Covers all five HTTP seams
──────────────────────────
  POST /api/investments/fidelity/import/preview
  POST /api/investments/fidelity/import/confirm
  GET  /api/investments/fidelity/kpis
  GET  /api/investments/fidelity/evolution
  GET  /api/investments/fidelity/lots

Test areas
──────────
1. Auth guards — every endpoint enforces 401 on missing session cookie.
2. Preview — no DB writes; file_already_imported flag; duplicate detection;
   new-lot count; 400 on empty/malformed CSV.
3. Confirm — calls provider.import_lots; triggers backfill when lots inserted;
   skips backfill when 0 inserted; backfill failure is non-fatal (still 200);
   400 on malformed CSV.
4. KPIs math — total_shares = Σ shares; invested_eur = Σ cost_basis;
   current_value = Σ shares × close_usd × fx_eur_usd; gain/loss correct;
   null-price path returns nulls without error; no-connection path returns zeros.
5. Evolution — empty states; date ISO format; series returned on data present.
6. Lots — shape; null valuations when no price; math correct with price.

Fixture conventions
───────────────────
* ``client`` / ``mock_session`` — from conftest.py (auth bypassed).
* ``unauthenticated_client``  — local fixture: only get_db overridden so
  the real get_current_user dependency enforces auth → 401.
* All CSV fixtures are SYNTHETIC — no real owner data.
* get_latest_price, backfill_price_history, and _PROVIDERS are patched at the
  ``finlytics.api.fidelity`` import path (post-import binding).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db
from finlytics.api.fidelity import compute_evolution_series
from finlytics.app import app
from finlytics.investments.fidelity import _compute_dedup_hash
from finlytics.investments.market_data import LatestPriceRow, topup_recent_prices


# ---------------------------------------------------------------------------
# Synthetic CSV fixtures — hand-crafted, no real financial values
# ---------------------------------------------------------------------------

# 2 SP lots (EUR currency) — 150 shares total, 6 100 EUR invested
_MINIMAL_CSV: bytes = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,"
    "Grant date,Share source,Holding period\n"
    "Jun-30-2024,100.0000,4000.00,40.00,4500.00,500.00,"
    "Sep-30-2024,Sep-30-2024,Apr-01-2024,SP,Long\n"
    "Mar-31-2025,50.0000,2100.00,42.00,2400.00,300.00,"
    "Jun-30-2025,Jun-30-2025,Jan-01-2025,SP,Short\n"
    ",\n"
    "The values are displayed in EUR\n"
).encode("utf-8")

# Two identical DO lots (same date/qty/price) — tests ordinal dedup
_DO_DEDUP_CSV: bytes = (
    "Date acquired,Quantity,Cost basis,Cost basis/share,Value,Gain/loss,"
    "Sale availability date,Transfer availability date,"
    "Grant date,Share source,Holding period\n"
    "Dec-15-2024,0.5500,22.00,40.00,27.50,5.50,"
    "Mar-15-2025,Mar-15-2025,-,DO,Long\n"
    "Dec-15-2024,0.5500,22.00,40.00,27.50,5.50,"
    "Mar-15-2025,Mar-15-2025,-,DO,Long\n"
    ",\n"
    "The values are displayed in EUR\n"
).encode("utf-8")

_EMPTY_CSV: bytes = b""
_MALFORMED_CSV: bytes = b"col1,col2,col3\nfoo,bar,baz\n"

# ---------------------------------------------------------------------------
# Mock price / lot objects
# ---------------------------------------------------------------------------

_MOCK_PRICE = LatestPriceRow(
    price_date=date(2026, 7, 15),
    close_usd=400.0,
    fx_eur_usd=1.0 / 1.08,      # EUR per USD  (EURUSD quote = 1.08)
    close_eur=400.0 / 1.08,
    price_stale=False,
)


def _make_conn(conn_id: int = 42) -> MagicMock:
    c = MagicMock()
    c.id = conn_id
    c.plugin_id = "fidelity-espp"
    c.status = "active"
    c.token_enc = None
    return c


def _make_lot(
    lot_id: int,
    purchase_date: date,
    shares: Decimal,
    cost_basis: Decimal,
    cbps: Decimal,
    share_source: str = "SP",
    grant_date: date | None = None,
) -> MagicMock:
    m = MagicMock()
    m.id = lot_id
    m.connection_id = 42
    m.purchase_date = purchase_date
    m.shares = shares
    m.cost_basis = cost_basis
    m.cost_basis_per_share = cbps
    m.source_currency = "EUR"
    m.share_source = share_source
    m.grant_date = grant_date
    m.holding_period = "Long"
    return m


_LOT1 = _make_lot(1, date(2024, 6, 30), Decimal("100.0000"), Decimal("4000.00"), Decimal("40.000000"), grant_date=date(2024, 4, 1))
_LOT2 = _make_lot(2, date(2025, 3, 31), Decimal("50.0000"),  Decimal("2100.00"), Decimal("42.000000"), grant_date=date(2025, 1, 1))


def _make_price_history_row(
    price_date: date = date(2026, 7, 15),
    close_usd: float = 400.0,
    fx_eur_usd: float = 1.0 / 1.08,
) -> MagicMock:
    p = MagicMock()
    p.price_date = price_date
    p.close_usd = Decimal(str(round(close_usd, 6)))
    p.fx_eur_usd = Decimal(str(round(fx_eur_usd, 6)))
    return p


# ---------------------------------------------------------------------------
# Helper: build mock execute side-effects
# ---------------------------------------------------------------------------

def _result(scalar=None, scalars_all=None) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = scalars_all if scalars_all is not None else []
    return r


# ---------------------------------------------------------------------------
# Local unauthenticated-client fixture (mirrors test_investments.py pattern)
# ---------------------------------------------------------------------------

@pytest.fixture
async def unauthenticated_client():
    """Only get_db overridden; real get_current_user enforces 401."""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.close = AsyncMock()
    begin_cm = AsyncMock()
    mock_session.begin = MagicMock(return_value=begin_cm)

    async def _override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ===========================================================================
# 1. Auth guards
# ===========================================================================

async def test_preview_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/investments/fidelity/import/preview",
        files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
    )
    assert resp.status_code == 401


async def test_confirm_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.post(
        "/api/investments/fidelity/import/confirm",
        files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
    )
    assert resp.status_code == 401


async def test_kpis_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/investments/fidelity/kpis")
    assert resp.status_code == 401


async def test_evolution_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/investments/fidelity/evolution")
    assert resp.status_code == 401


async def test_lots_401_unauthenticated(unauthenticated_client):
    resp = await unauthenticated_client.get("/api/investments/fidelity/lots")
    assert resp.status_code == 401


# ===========================================================================
# 2. Preview endpoint
# ===========================================================================

class TestFidelityImportPreview:
    """POST /api/investments/fidelity/import/preview — never persists."""

    # ── 200 shape ────────────────────────────────────────────────────────────

    async def test_preview_200_basic_shape(self, client, mock_session):
        # file check → not imported; conn ids → empty (no existing connection)
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),       # file_already_imported = False
            _result(scalars_all=[]),    # user_conn_ids = []
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        for key in ("new_lots", "duplicate_count", "total_in_file", "source_currency", "file_already_imported"):
            assert key in data, f"Missing key: {key}"

    async def test_preview_source_currency_is_eur(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        assert resp.json()["source_currency"] == "EUR"

    async def test_preview_total_in_file_equals_csv_lot_count(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        assert resp.json()["total_in_file"] == 2   # _MINIMAL_CSV has 2 lots

    async def test_preview_new_lots_count_when_no_existing_connection(self, client, mock_session):
        """When no connection exists (user_conn_ids=[]), all lots are reported as new."""
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        data = resp.json()
        assert len(data["new_lots"]) == 2
        assert data["duplicate_count"] == 0

    # ── file_already_imported flag ────────────────────────────────────────

    async def test_preview_file_already_imported_true(self, client, mock_session):
        """First execute returns an existing run → file_already_imported = True."""
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=MagicMock(id=7)),    # file was imported → True
            _result(scalars_all=[]),             # user_conn_ids
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["file_already_imported"] is True

    async def test_preview_file_not_yet_imported(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        assert resp.json()["file_already_imported"] is False

    # ── duplicate detection ───────────────────────────────────────────────

    async def test_preview_duplicate_detection_marks_known_hashes(self, client, mock_session):
        """When existing_hashes contains one lot's dedup_hash, duplicate_count = 1."""
        # Compute the hash for lot 1 (Jun-30-2024, 100 shares, cbps=40, SP, ordinal=0)
        hash_lot1 = _compute_dedup_hash(
            ticker="MSFT",
            purchase_date=date(2024, 6, 30),
            shares=Decimal("100.0000"),
            cost_basis_per_share=Decimal("40.00"),
            share_source="SP",
            dedup_ordinal=0,
        )
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),                        # file not yet imported
            _result(scalars_all=[42]),                   # user_conn_ids = [42]
            _result(scalars_all=[hash_lot1]),            # existing_hashes = {hash_lot1}
        ])
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        data = resp.json()
        assert data["duplicate_count"] == 1
        assert len(data["new_lots"]) == 1   # only lot 2 is new

    # ── preview never writes ──────────────────────────────────────────────

    async def test_preview_never_calls_db_add(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        mock_session.add.assert_not_called()

    async def test_preview_never_calls_db_commit(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=None),
            _result(scalars_all=[]),
        ])
        await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
        )
        mock_session.commit.assert_not_called()

    # ── edge cases ────────────────────────────────────────────────────────

    async def test_preview_empty_csv_returns_400(self, client, mock_session):
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("empty.csv", _EMPTY_CSV, "text/csv")},
        )
        assert resp.status_code == 400

    async def test_preview_malformed_csv_returns_400(self, client, mock_session):
        resp = await client.post(
            "/api/investments/fidelity/import/preview",
            files={"file": ("bad.csv", _MALFORMED_CSV, "text/csv")},
        )
        assert resp.status_code == 400


# ===========================================================================
# 3. Confirm endpoint
# ===========================================================================

class TestFidelityImportConfirm:
    """POST /api/investments/fidelity/import/confirm — persists and backfills."""

    def _mock_provider(self, inserted: int, skipped: int) -> MagicMock:
        p = MagicMock()
        p.import_lots = AsyncMock(return_value=(inserted, skipped))
        return p

    async def test_confirm_200_returns_inserted_and_skipped(self, client, mock_session):
        # Inside _get_or_create_fidelity_connection: conn found
        mock_session.execute.return_value = _result(scalar=_make_conn())

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": self._mock_provider(2, 0)}),
            patch("finlytics.api.fidelity.backfill_price_history", new=AsyncMock(return_value=10)),
        ):
            resp = await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 2
        assert data["duplicates"] == 0

    async def test_confirm_calls_import_lots_with_parsed_lots(self, client, mock_session):
        mock_session.execute.return_value = _result(scalar=_make_conn())
        mock_provider = self._mock_provider(2, 0)

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": mock_provider}),
            patch("finlytics.api.fidelity.backfill_price_history", new=AsyncMock(return_value=10)),
        ):
            await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        mock_provider.import_lots.assert_awaited_once()
        _, kwargs = mock_provider.import_lots.call_args
        assert kwargs["source_currency"] == "EUR"

    async def test_confirm_backfill_called_when_lots_inserted(self, client, mock_session):
        mock_session.execute.return_value = _result(scalar=_make_conn())
        mock_backfill = AsyncMock(return_value=50)

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": self._mock_provider(5, 0)}),
            patch("finlytics.api.fidelity.backfill_price_history", new=mock_backfill),
        ):
            await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        mock_backfill.assert_awaited_once()

    async def test_confirm_backfill_not_called_when_zero_inserted(self, client, mock_session):
        mock_session.execute.return_value = _result(scalar=_make_conn())
        mock_backfill = AsyncMock(return_value=0)

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": self._mock_provider(0, 2)}),
            patch("finlytics.api.fidelity.backfill_price_history", new=mock_backfill),
        ):
            await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        mock_backfill.assert_not_awaited()

    async def test_confirm_backfill_failure_is_non_fatal_still_200(self, client, mock_session):
        mock_session.execute.return_value = _result(scalar=_make_conn())

        async def _raise(*args, **kwargs):
            raise RuntimeError("Stooq down")

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": self._mock_provider(2, 0)}),
            patch("finlytics.api.fidelity.backfill_price_history", new=_raise),
        ):
            resp = await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        assert resp.status_code == 200

    async def test_confirm_malformed_csv_returns_400(self, client, mock_session):
        resp = await client.post(
            "/api/investments/fidelity/import/confirm",
            files={"file": ("bad.csv", _MALFORMED_CSV, "text/csv")},
        )
        assert resp.status_code == 400

    async def test_confirm_empty_csv_returns_400(self, client, mock_session):
        resp = await client.post(
            "/api/investments/fidelity/import/confirm",
            files={"file": ("empty.csv", _EMPTY_CSV, "text/csv")},
        )
        assert resp.status_code == 400

    async def test_confirm_idempotency_second_call_returns_zero_inserted(self, client, mock_session):
        """Re-importing the same file returns (0, 0) when provider already recorded it."""
        mock_session.execute.return_value = _result(scalar=_make_conn())

        with (
            patch("finlytics.api.fidelity._PROVIDERS", {"fidelity-espp": self._mock_provider(0, 0)}),
            patch("finlytics.api.fidelity.backfill_price_history", new=AsyncMock()),
        ):
            resp = await client.post(
                "/api/investments/fidelity/import/confirm",
                files={"file": ("test.csv", _MINIMAL_CSV, "text/csv")},
            )

        data = resp.json()
        assert data["inserted"] == 0
        assert data["duplicates"] == 0


# ===========================================================================
# 4. KPIs endpoint
# ===========================================================================

class TestFidelityKpis:
    """GET /api/investments/fidelity/kpis — aggregated portfolio math."""

    # ── no-connection / empty states ──────────────────────────────────────

    async def test_kpis_no_connection_returns_200_zeros(self, client, mock_session):
        """No fidelity-espp connection → 200 with total_shares=0, nulls."""
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=None)):
            # _get_fidelity_connection → scalar_one_or_none → None
            mock_session.execute.return_value = _result(scalar=None)
            resp = await client.get("/api/investments/fidelity/kpis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_shares"] == 0.0
        assert data["current_value_eur"] is None
        assert data["gain_loss_eur"] is None

    async def test_kpis_connection_but_no_price_returns_null_value(self, client, mock_session):
        """Price unavailable → current_value_eur and gain_loss_eur are null."""
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=None)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),       # connection found
                _result(scalars_all=[_LOT1, _LOT2]),  # lots
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value_eur"] is None
        assert data["gain_loss_eur"] is None
        assert data["gain_loss_pct"] is None

    # ── math correctness ─────────────────────────────────────────────────

    async def test_kpis_total_shares_is_sum_of_lot_shares(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1, _LOT2]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        # LOT1: 100 shares + LOT2: 50 shares = 150
        assert resp.json()["total_shares"] == pytest.approx(150.0)

    async def test_kpis_invested_eur_is_sum_of_cost_basis(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1, _LOT2]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        # LOT1: 4000 + LOT2: 2100 = 6100
        assert resp.json()["invested_eur"] == pytest.approx(6100.0)

    async def test_kpis_current_value_formula_correct(self, client, mock_session):
        """current_value = total_shares × close_usd × fx_eur_usd."""
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1, _LOT2]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        data = resp.json()
        expected_value = round(150.0 * _MOCK_PRICE.close_usd * _MOCK_PRICE.fx_eur_usd, 2)
        assert data["current_value_eur"] == pytest.approx(expected_value, abs=0.01)

    async def test_kpis_gain_loss_is_value_minus_invested(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1, _LOT2]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        data = resp.json()
        expected_gl = round(data["current_value_eur"] - 6100.0, 2)
        assert data["gain_loss_eur"] == pytest.approx(expected_gl, abs=0.01)

    async def test_kpis_gain_loss_pct_formula_correct(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1, _LOT2]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        data = resp.json()
        expected_pct = round(data["gain_loss_eur"] / 6100.0 * 100.0, 4)
        assert data["gain_loss_pct"] == pytest.approx(expected_pct, rel=1e-4)

    async def test_kpis_price_stale_flag_propagated(self, client, mock_session):
        stale_price = LatestPriceRow(
            price_date=date(2026, 7, 10),
            close_usd=400.0,
            fx_eur_usd=1.0 / 1.08,
            close_eur=400.0 / 1.08,
            price_stale=True,
        )
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=stale_price)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),
            ])
            resp = await client.get("/api/investments/fidelity/kpis")

        assert resp.json()["price_stale"] is True

    async def test_kpis_get_latest_price_raises_returns_degraded_200(self, client, mock_session):
        """BUG #KPI-1 FIXED: get_latest_price is wrapped in try/except.

        When get_latest_price raises (e.g. on a DB error), the endpoint
        degrades to the no-price code path and returns HTTP 200 with null
        price fields instead of propagating the exception as a 500.
        """
        async def _raise(db):
            raise RuntimeError("simulated DB error")

        with patch("finlytics.api.fidelity.get_latest_price", new=_raise):
            mock_session.execute.return_value = _result(scalar=None)
            resp = await client.get("/api/investments/fidelity/kpis")

        assert resp.status_code == 200
        data = resp.json()
        assert data["current_value_eur"] is None
        assert data["total_shares"] == 0.0
        assert data["price_stale"] is True


# ===========================================================================
# 5. Evolution endpoint
# ===========================================================================

class TestFidelityEvolution:
    """GET /api/investments/fidelity/evolution — value + contributions series."""

    async def test_evolution_no_connection_returns_200_empty(self, client, mock_session):
        mock_session.execute.return_value = _result(scalar=None)  # no connection
        resp = await client.get("/api/investments/fidelity/evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value_series"] == []
        assert data["contributions_series"] == []

    async def test_evolution_connection_no_lots_returns_200_empty(self, client, mock_session):
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),   # connection found
            _result(scalars_all=[]),         # no lots
        ])
        resp = await client.get("/api/investments/fidelity/evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value_series"] == []
        assert data["contributions_series"] == []

    async def test_evolution_with_data_returns_200(self, client, mock_session):
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])
        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=AsyncMock()),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            resp = await client.get("/api/investments/fidelity/evolution")
        assert resp.status_code == 200

    async def test_evolution_series_keys_present(self, client, mock_session):
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])
        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=AsyncMock()),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            resp = await client.get("/api/investments/fidelity/evolution")
        data = resp.json()
        assert "value_series" in data
        assert "contributions_series" in data

    async def test_evolution_contributions_series_non_empty_when_lots_exist(self, client, mock_session):
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])
        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=AsyncMock()),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            resp = await client.get("/api/investments/fidelity/evolution")
        data = resp.json()
        assert len(data["contributions_series"]) >= 1

    async def test_evolution_date_points_are_iso_format(self, client, mock_session):
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])
        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=AsyncMock()),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            resp = await client.get("/api/investments/fidelity/evolution")
        data = resp.json()
        for pt in data["contributions_series"][:3]:  # check first few
            # Must match YYYY-MM-DD
            date.fromisoformat(pt["date"])   # raises ValueError if wrong format

    async def test_evolution_calls_topup_recent_prices(self, client, mock_session):
        """fidelity_evolution calls topup_recent_prices before reading prices."""
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])
        mock_topup = AsyncMock()
        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=mock_topup),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            await client.get("/api/investments/fidelity/evolution")

        mock_topup.assert_awaited_once()

    async def test_evolution_topup_failure_non_fatal(self, client, mock_session):
        """topup_recent_prices failure in evolution is non-fatal (still 200)."""
        ph = _make_price_history_row(date(2024, 6, 30))
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_LOT1]),
            _result(scalars_all=[ph]),
        ])

        async def _raise_topup(db):
            raise RuntimeError("network error")

        with (
            patch("finlytics.api.fidelity.topup_recent_prices", new=_raise_topup),
            patch("finlytics.api.fidelity.get_current_fx_rate", new=AsyncMock(return_value=None)),
        ):
            resp = await client.get("/api/investments/fidelity/evolution")

        assert resp.status_code == 200


# ===========================================================================
# 6. Lots endpoint
# ===========================================================================

class TestFidelityLots:
    """GET /api/investments/fidelity/lots — per-lot detail with valuation."""

    # ── empty states ─────────────────────────────────────────────────────

    async def test_lots_no_connection_returns_200_empty_list(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=None)):
            mock_session.execute.return_value = _result(scalar=None)
            resp = await client.get("/api/investments/fidelity/lots")
        assert resp.status_code == 200
        assert resp.json()["lots"] == []

    # ── shape ────────────────────────────────────────────────────────────

    async def test_lots_response_has_lots_array(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        assert "lots" in resp.json()
        assert len(resp.json()["lots"]) == 1

    async def test_lots_required_fields_present(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        lot = resp.json()["lots"][0]
        for field in ("id", "purchase_date", "shares", "cost_basis_per_share_eur",
                      "cost_basis_total_eur", "current_value_eur", "gain_loss_eur",
                      "gain_loss_pct", "share_source"):
            assert field in lot, f"Missing field: {field}"

    async def test_lots_grant_date_is_iso_format_string(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),   # _LOT1 has grant_date=date(2024, 4, 1)
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        lot = resp.json()["lots"][0]
        assert lot["grant_date"] == "2024-04-01"

    # ── null-price path ───────────────────────────────────────────────────

    async def test_lots_no_price_all_valuations_null(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=None)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        lot = resp.json()["lots"][0]
        assert lot["current_value_eur"] is None
        assert lot["gain_loss_eur"] is None
        assert lot["gain_loss_pct"] is None

    # ── math ─────────────────────────────────────────────────────────────

    async def test_lots_current_value_formula_correct(self, client, mock_session):
        """current_value_eur = shares × close_usd × fx_eur_usd."""
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),   # 100 shares
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        lot = resp.json()["lots"][0]
        expected = round(100.0 * _MOCK_PRICE.close_usd * _MOCK_PRICE.fx_eur_usd, 2)
        assert lot["current_value_eur"] == pytest.approx(expected, abs=0.01)

    async def test_lots_gain_loss_is_value_minus_cost_basis(self, client, mock_session):
        with patch("finlytics.api.fidelity.get_latest_price", new=AsyncMock(return_value=_MOCK_PRICE)):
            mock_session.execute = AsyncMock(side_effect=[
                _result(scalar=_make_conn()),
                _result(scalars_all=[_LOT1]),
            ])
            resp = await client.get("/api/investments/fidelity/lots")
        lot = resp.json()["lots"][0]
        expected_gl = round(lot["current_value_eur"] - lot["cost_basis_total_eur"], 2)
        assert lot["gain_loss_eur"] == pytest.approx(expected_gl, abs=0.01)


# ===========================================================================
# 7. Reminder endpoint
# ===========================================================================

# Reference dates for reminder tests (Q2 2026 expected purchase: 2026-06-30)
# Jun 30, 2026 is a Friday → last weekday of June 2026 → expected_date = "2026-06-30"
# Grace deadline = 2026-06-30 + 5 days = 2026-07-05

_SP_LOT_Q2_2026 = _make_lot(
    10,
    date(2026, 6, 30),
    Decimal("80.0000"),
    Decimal("3200.00"),
    Decimal("40.000000"),
    share_source="SP",
)


class TestFidelityReminder:
    """GET /api/investments/fidelity/reminder — ESPP quarter-end upload reminder."""

    async def test_reminder_not_overdue_when_lot_present(self, client, mock_session):
        """Past grace window BUT SP lot for Q2 2026 is present → overdue=False."""
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[_SP_LOT_Q2_2026]),
        ])
        with patch("finlytics.api.fidelity._get_today", return_value=date(2026, 7, 10)):
            resp = await client.get("/api/investments/fidelity/reminder")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overdue"] is False
        assert data["expected_date"] == "2026-06-30"
        assert data["period_label"] == "Q2 2026"
        assert data["last_lot_date"] == "2026-06-30"

    async def test_reminder_overdue_when_grace_passed_and_no_lot(self, client, mock_session):
        """Grace window closed, no SP lot for Q2 2026 → overdue=True."""
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[]),
        ])
        with patch("finlytics.api.fidelity._get_today", return_value=date(2026, 7, 10)):
            resp = await client.get("/api/investments/fidelity/reminder")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overdue"] is True
        assert data["expected_date"] == "2026-06-30"
        assert data["period_label"] == "Q2 2026"
        assert data["last_lot_date"] is None

    async def test_reminder_not_overdue_within_grace_window(self, client, mock_session):
        """3 days after quarter-end, still within 5-day grace → overdue=False."""
        mock_session.execute = AsyncMock(side_effect=[
            _result(scalar=_make_conn()),
            _result(scalars_all=[]),
        ])
        with patch("finlytics.api.fidelity._get_today", return_value=date(2026, 7, 3)):
            resp = await client.get("/api/investments/fidelity/reminder")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overdue"] is False
        assert data["expected_date"] == "2026-06-30"

    async def test_reminder_no_connection_returns_false(self, client, mock_session):
        """No fidelity connection → overdue=False, expected_date=None (nothing to remind)."""
        mock_session.execute.return_value = _result(scalar=None)
        with patch("finlytics.api.fidelity._get_today", return_value=date(2026, 7, 10)):
            resp = await client.get("/api/investments/fidelity/reminder")

        assert resp.status_code == 200
        data = resp.json()
        assert data["overdue"] is False
        assert data["expected_date"] is None
        assert data["period_label"] is None


# ===========================================================================
# 8. FX-decouple happy-path tests (Model-A)
# ===========================================================================

class TestFxDecoupleHappyPath:
    """Verify that Fridays and null-FX days produce price points after Model-A fix.

    Root cause: Yahoo EURUSD=X never returns Friday bars → old intersection
    logic dropped every Friday.  These tests confirm the fix is effective.
    """

    # ── compute_evolution_series (pure function) ──────────────────────────

    def test_friday_in_price_map_produces_value_point(self):
        """Friday date in price_map must appear in value_series."""
        friday = date(2026, 7, 17)   # July 17, 2026 is a Friday
        thursday = date(2026, 7, 16)
        fx = 1.0 / 1.083  # EUR per USD

        price_map = {
            thursday: (450.0, fx),
            friday:   (455.0, fx),  # Friday — was dropped pre-fix
        }
        lot = _make_lot(99, thursday, Decimal("10.0000"), Decimal("3000.00"), Decimal("300.000000"))

        value_series, _ = compute_evolution_series([lot], price_map, thursday, friday)

        dates_in_series = {pt.date for pt in value_series}
        assert friday.isoformat() in dates_in_series, \
            "Friday must produce a value point after the FX-decouple fix"

    def test_null_fx_day_via_fallback_still_produces_point(self):
        """A day whose FX is filled by fallback still appears in value_series.

        Simulates a day where Yahoo returned close=null for EURUSD — the
        stored row uses the latest available FX, which compute_evolution_series
        accepts transparently.
        """
        monday = date(2026, 7, 21)
        fx_fallback = 1.0 / 1.085  # EUR per USD — filled-forward at write time

        price_map = {monday: (460.0, fx_fallback)}
        lot = _make_lot(99, monday, Decimal("10.0000"), Decimal("3000.00"), Decimal("300.000000"))

        value_series, _ = compute_evolution_series([lot], price_map, monday, monday)

        assert len(value_series) == 1
        assert value_series[0].date == monday.isoformat()

    def test_single_fx_applied_uniformly_across_all_dates(self):
        """value_series uses the same FX rate for all dates (Model-A).

        When a caller builds price_map with the same fx for every entry,
        compute_evolution_series returns a coherent series with no per-day
        FX divergence.
        """
        thursday = date(2026, 7, 16)
        friday = date(2026, 7, 17)
        latest_fx = 1.0 / 1.083  # single rate applied to all dates

        price_map = {
            thursday: (450.0, latest_fx),
            friday:   (455.0, latest_fx),  # same FX as Thursday
        }
        lot = _make_lot(99, thursday, Decimal("5.0000"), Decimal("1500.00"), Decimal("300.000000"))

        value_series, _ = compute_evolution_series([lot], price_map, thursday, friday)

        # Both dates present
        assert len(value_series) == 2
        # Thursday: 5 × 450 × latest_fx
        assert value_series[0].value == pytest.approx(5 * 450.0 * latest_fx, abs=0.01)
        # Friday: 5 × 455 × same latest_fx
        assert value_series[1].value == pytest.approx(5 * 455.0 * latest_fx, abs=0.01)

    # ── backfill_price_history (unit) ────────────────────────────────────

    async def test_backfill_stores_friday_when_fx_has_no_friday_entry(self):
        """backfill stores a Friday row even when EURUSD returns no Friday bar."""
        from finlytics.investments.market_data import backfill_price_history

        thursday = date(2026, 7, 16)
        friday = date(2026, 7, 17)

        msft_rows = [
            {"date": thursday, "close": 450.0},
            {"date": friday,   "close": 455.0},   # Friday — no matching FX entry
        ]
        fx_rows = [
            {"date": thursday, "close": 1.083},   # Thursday FX only (no Friday)
        ]

        mock_db = MagicMock()
        begin_cm = AsyncMock()
        mock_db.begin = MagicMock(return_value=begin_cm)
        mock_db.execute = AsyncMock()

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            count = await backfill_price_history(thursday, mock_db)

        # Both Thursday AND Friday must be stored
        assert count == 2, f"Expected 2 rows (Thu+Fri), got {count}"

    async def test_backfill_returns_zero_when_fx_completely_missing(self):
        """backfill returns 0 gracefully when all FX data is unavailable."""
        from finlytics.investments.market_data import backfill_price_history

        thursday = date(2026, 7, 16)
        msft_rows = [{"date": thursday, "close": 450.0}]
        fx_rows: list = []  # no FX at all

        mock_db = MagicMock()
        begin_cm = AsyncMock()
        mock_db.begin = MagicMock(return_value=begin_cm)
        mock_db.execute = AsyncMock()

        with patch(
            "finlytics.investments.market_data._fetch_with_fallback",
            side_effect=[msft_rows, fx_rows],
        ):
            count = await backfill_price_history(thursday, mock_db)

        assert count == 0
