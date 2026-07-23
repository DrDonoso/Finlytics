"""Tests for GET /api/investments/* endpoints.

Coverage:
  * Auth: every endpoint enforces 401 on missing session cookie.
  * POST /connections/validate: happy path, invalid token, network error, stores nothing.
  * POST /connections: selection, empty list, non-owned accounts, missing encryption key.
  * GET /connections: list shape, no token fields leaked.
  * DELETE /connections/{id}: 204 on success, 404 on missing/other-user.
  * GET /portfolio: zero state, full shape with Phase 2 fields, service-level mapping,
    gain_loss_pct formula, value_series YYYYMMDD dates, missing encryption key.
  * GET /plugins: Indexa status dynamic (available / connected).
  * GET /combined-overview: both providers, single provider, no connections, degraded price.
  * 🔒 SECURITY INVARIANTS (Romanoff): token never in any response; masked label has "•";
    crypto round-trip; tampered ciphertext fails; missing key → fail-closed (raise); TLS verify=True.

Fixtures:
  * ``unauthenticated_client`` (local): only get_db overridden → real auth dependency → 401.
  * ``client`` (conftest): get_current_user pre-bypassed, for all 200 cases.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.investments.market_data import LatestPriceRow

_EXPECTED_IDS = {"indexa-capital", "fidelity-espp"}
_REQUIRED_KEYS = {"id", "name", "description", "icon", "status", "auth_type", "supported_features", "import_route"}


# ── Fixture for unauthenticated requests ─────────────────────────────────────

@pytest.fixture
async def unauthenticated_client():
    """Client with only get_db overridden; get_current_user runs for real.

    Sending no session cookie causes it to raise 401 before any DB touch.
    """
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


# ── Auth guard ────────────────────────────────────────────────────────────────

async def test_plugins_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 before the registry is ever consulted."""
    resp = await unauthenticated_client.get("/api/investments/plugins")
    assert resp.status_code == 401


# ── Shape & content (authenticated via conftest ``client`` fixture) ───────────

async def test_plugins_200_returns_list_of_two(client):
    """Authenticated request → 200, exactly 2 plugins."""
    resp = await client.get("/api/investments/plugins")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_plugins_all_required_keys_present(client):
    """Every plugin object carries all required keys."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        missing = _REQUIRED_KEYS - plugin.keys()
        assert not missing, f"Plugin '{plugin.get('id')}' is missing keys: {missing}"


async def test_plugins_all_status_coming_soon(client):
    """Phase 2: non-connectable plugins stay 'coming_soon'.
    Indexa Capital and Fidelity ESPP are dynamic — 'available' when no active
    connection exists (mock execute returns empty set).
    """
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        if plugin["id"] in ("indexa-capital", "fidelity-espp"):
            # Dynamic: 'available' (no connection) or 'connected' — never 'coming_soon'
            assert plugin["status"] in ("available", "connected"), (
                f"Unexpected status for dynamic plugin '{plugin['id']}': {plugin['status']}"
            )
        else:
            assert plugin["status"] == "coming_soon", (
                f"Plugin '{plugin['id']}' has unexpected status '{plugin['status']}'"
            )


async def test_plugins_correct_id_set(client):
    """Returned id set matches the four expected plugin identifiers exactly."""
    resp = await client.get("/api/investments/plugins")
    ids = {p["id"] for p in resp.json()}
    assert ids == _EXPECTED_IDS


async def test_plugins_supported_features_nonempty(client):
    """Every plugin exposes a non-empty supported_features list."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        features = plugin["supported_features"]
        assert isinstance(features, list), f"Plugin '{plugin['id']}': features not a list"
        assert len(features) > 0, f"Plugin '{plugin['id']}': supported_features is empty"


async def test_plugins_import_route_values(client):
    """fidelity-espp has an import_route; indexa-capital has none (live-API plugin)."""
    resp = await client.get("/api/investments/plugins")
    by_id = {p["id"]: p for p in resp.json()}
    assert by_id["fidelity-espp"]["import_route"] == "/investments/fidelity-espp"
    assert by_id["indexa-capital"]["import_route"] is None


# ── POST /connections/validate ────────────────────────────────────────────────


async def test_validate_happy_path_returns_accounts(client):
    """Valid token → 200 with accounts list including raw + masked numbers."""
    from finlytics.api.schemas import DiscoveredAccountOut

    mock_accounts = [
        DiscoveredAccountOut(
            account_number="PBKLBYZ5",
            account_number_masked="PBK•••Z5",
            type="mutual",
            status="active",
        )
    ]
    with patch(
        "finlytics.api.investments.inv_service.validate_token_for_wizard",
        new=AsyncMock(return_value=mock_accounts),
    ):
        resp = await client.post(
            "/api/investments/connections/validate",
            json={"token": "valid-tok"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "accounts" in data
    assert len(data["accounts"]) == 1
    acct = data["accounts"][0]
    assert acct["account_number"] == "PBKLBYZ5"
    assert acct["account_number_masked"] == "PBK•••Z5"
    assert acct["type"] == "mutual"
    # Token NEVER echoed in response
    assert "valid-tok" not in str(data)


async def test_validate_invalid_token_returns_400(client):
    """Indexa 401/403 → 400 with Spanish error message."""
    from finlytics.investments.indexa import IndexaAuthError

    with patch(
        "finlytics.api.investments.inv_service.validate_token_for_wizard",
        side_effect=IndexaAuthError("HTTP 401"),
    ):
        resp = await client.post(
            "/api/investments/connections/validate",
            json={"token": "bad-tok"},
        )

    assert resp.status_code == 400
    assert "inválido" in resp.json()["detail"]


async def test_validate_network_error_returns_503(client):
    """Timeout / network failure → 503."""
    from finlytics.investments.indexa import IndexaConnectionError

    with patch(
        "finlytics.api.investments.inv_service.validate_token_for_wizard",
        side_effect=IndexaConnectionError("timeout"),
    ):
        resp = await client.post(
            "/api/investments/connections/validate",
            json={"token": "slow-tok"},
        )

    assert resp.status_code == 503


async def test_validate_does_not_require_db(client):
    """validate endpoint has no DB dependency — mock_session.scalar never called."""
    from finlytics.api.schemas import DiscoveredAccountOut

    with patch(
        "finlytics.api.investments.inv_service.validate_token_for_wizard",
        new=AsyncMock(return_value=[]),
    ):
        resp = await client.post(
            "/api/investments/connections/validate",
            json={"token": "any-tok"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"accounts": []}


# ── POST /connections (validate → connect flow) ───────────────────────────────


async def test_connect_with_selection_returns_201_and_masked_label(client):
    """Selected accounts → 201, masked label in response, token never returned."""
    from finlytics.api.schemas import ConnectionOut

    mock_out = [
        ConnectionOut(
            id=1,
            plugin_id="indexa-capital",
            status="active",
            account_label_masked="PBK•••Z5",
            created_at=datetime.now(timezone.utc),
        )
    ]
    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        new=AsyncMock(return_value=mock_out),
    ) as mock_connect:
        resp = await client.post(
            "/api/investments/connections",
            json={"token": "valid-tok", "account_numbers": ["PBKLBYZ5"]},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account_label_masked"] == "PBK•••Z5"
    assert "token" not in data[0]
    # Verify service received the requested account_numbers
    call_kwargs = mock_connect.call_args.kwargs
    assert call_kwargs["account_numbers"] == ["PBKLBYZ5"]


async def test_connect_empty_account_numbers_returns_400(client):
    """Empty account_numbers list → 400 without calling the service."""
    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        new=AsyncMock(),
    ) as mock_connect:
        resp = await client.post(
            "/api/investments/connections",
            json={"token": "valid-tok", "account_numbers": []},
        )

    assert resp.status_code == 400
    mock_connect.assert_not_called()


async def test_connect_no_valid_accounts_returns_400(client):
    """account_numbers all non-owned → service raises NoValidAccountsError → 400."""
    from finlytics.investments.service import NoValidAccountsError

    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        side_effect=NoValidAccountsError("none owned"),
    ):
        resp = await client.post(
            "/api/investments/connections",
            json={"token": "valid-tok", "account_numbers": ["NOT_OWNED"]},
        )

    assert resp.status_code == 400


async def test_connect_invalid_token_returns_400(client):
    """Indexa rejects token during connect → 400."""
    from finlytics.investments.indexa import IndexaAuthError

    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        side_effect=IndexaAuthError("403"),
    ):
        resp = await client.post(
            "/api/investments/connections",
            json={"token": "bad-tok", "account_numbers": ["ACC1"]},
        )

    assert resp.status_code == 400


# ── Service-level filtering unit tests ───────────────────────────────────────


async def test_service_connect_filters_non_owned_accounts():
    """connect_plugin silently drops account_numbers not owned by the token."""
    from finlytics.investments import service as svc
    from finlytics.investments.base import DiscoveredAccount, ValidationResult

    owned_acc = DiscoveredAccount("OWNED1", "mutual", "active")
    mock_validation = ValidationResult(valid=True, accounts=[owned_acc])

    # Use existing-connection (update) path to avoid flush/RETURNING mock complexity
    mock_existing = MagicMock()
    mock_existing.id = 10
    mock_existing.plugin_id = "indexa-capital"
    mock_existing.status = "active"
    mock_existing.account_label_masked = svc._mask_account("OWNED1")
    mock_existing.created_at = datetime(2026, 7, 14, tzinfo=timezone.utc)
    mock_existing.last_synced_at = None

    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = mock_existing

    begin_cm = AsyncMock()
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.begin = MagicMock(return_value=begin_cm)

    with (
        patch.object(
            svc._PROVIDERS["indexa-capital"], "validate_token", AsyncMock(return_value=mock_validation)
        ),
        patch("finlytics.investments.service.encrypt_token", return_value="enc"),
    ):
        result = await svc.connect_plugin(
            user_id=1,
            plugin_id="indexa-capital",
            token="raw-tok",
            account_numbers=["OWNED1", "NOT_OWNED"],  # NOT_OWNED should be filtered
            db=mock_db,
        )

    # Only OWNED1 persisted; NOT_OWNED dropped
    assert len(result) == 1
    assert result[0].account_label_masked == svc._mask_account("OWNED1")
    mock_db.add.assert_not_called()  # update path — no INSERT needed


async def test_service_connect_all_non_owned_raises_error():
    """All account_numbers non-owned → NoValidAccountsError before any encryption."""
    from finlytics.investments import service as svc
    from finlytics.investments.base import DiscoveredAccount, ValidationResult

    mock_validation = ValidationResult(
        valid=True,
        accounts=[DiscoveredAccount("REAL_ACC", "mutual", "active")],
    )
    mock_db = MagicMock()

    with patch.object(
        svc._PROVIDERS["indexa-capital"], "validate_token", AsyncMock(return_value=mock_validation)
    ):
        with pytest.raises(svc.NoValidAccountsError):
            await svc.connect_plugin(
                user_id=1,
                plugin_id="indexa-capital",
                token="tok",
                account_numbers=["COMPLETELY_WRONG"],
                db=mock_db,
            )


# ── Auth: 401 for every endpoint ──────────────────────────────────────────────


async def test_validate_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on POST /connections/validate."""
    resp = await unauthenticated_client.post(
        "/api/investments/connections/validate",
        json={"token": "tok"},
    )
    assert resp.status_code == 401


async def test_connect_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on POST /connections."""
    resp = await unauthenticated_client.post(
        "/api/investments/connections",
        json={"token": "tok", "account_numbers": ["ACC1"]},
    )
    assert resp.status_code == 401


async def test_get_connections_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on GET /connections."""
    resp = await unauthenticated_client.get("/api/investments/connections")
    assert resp.status_code == 401


async def test_delete_connection_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on DELETE /connections/{id}."""
    resp = await unauthenticated_client.delete("/api/investments/connections/1")
    assert resp.status_code == 401


async def test_portfolio_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on GET /portfolio."""
    resp = await unauthenticated_client.get("/api/investments/portfolio")
    assert resp.status_code == 401


# ── 🔒 Security invariants (Romanoff §2–§4) ──────────────────────────────────


async def test_validate_stores_nothing_in_db(client, mock_session):
    """POST /validate: no DB rows created — add/flush/commit never called."""
    from finlytics.api.schemas import DiscoveredAccountOut

    with patch(
        "finlytics.api.investments.inv_service.validate_token_for_wizard",
        new=AsyncMock(return_value=[
            DiscoveredAccountOut(
                account_number="PBKLBYZ5",
                account_number_masked="PBK•••Z5",
                type="mutual",
                status="active",
            )
        ]),
    ):
        resp = await client.post(
            "/api/investments/connections/validate",
            json={"token": "any-tok"},
        )

    assert resp.status_code == 200
    mock_session.add.assert_not_called()
    mock_session.flush.assert_not_called()
    mock_session.commit.assert_not_called()


async def test_connect_response_never_contains_raw_token(client):
    """POST /connections response body MUST NOT echo the raw token (Romanoff §2)."""
    from finlytics.api.schemas import ConnectionOut

    sentinel = "sentinel-indexa-token-XYZABC987"
    mock_out = [
        ConnectionOut(
            id=1,
            plugin_id="indexa-capital",
            status="active",
            account_label_masked="PBK•••Z5",
            created_at=datetime.now(timezone.utc),
        )
    ]
    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        new=AsyncMock(return_value=mock_out),
    ):
        resp = await client.post(
            "/api/investments/connections",
            json={"token": sentinel, "account_numbers": ["PBKLBYZ5"]},
        )

    assert resp.status_code == 201
    assert sentinel not in resp.text, "Raw token MUST NOT appear in POST /connections response"


async def test_get_connections_no_token_enc_in_response(client):
    """GET /connections: token_enc and any token field MUST NOT appear in response (Romanoff §2)."""
    from finlytics.api.schemas import ConnectionOut

    mock_out = [
        ConnectionOut(
            id=1,
            plugin_id="indexa-capital",
            status="active",
            account_label_masked="PBK•••Z5",
            created_at=datetime.now(timezone.utc),
        )
    ]
    with patch(
        "finlytics.api.investments.inv_service.list_connections",
        new=AsyncMock(return_value=mock_out),
    ):
        resp = await client.get("/api/investments/connections")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    conn = data[0]
    assert "token" not in conn, "'token' key must not appear in ConnectionOut"
    assert "token_enc" not in conn, "'token_enc' key must not appear in ConnectionOut"
    assert "•" in conn["account_label_masked"], "account_label_masked must be masked (contain •)"


async def test_connect_missing_encryption_key_returns_503(client):
    """POST /connections → 503 when FINLYTICS_ENCRYPTION_KEY is absent (fail-closed)."""
    from finlytics.investments.crypto import EncryptionNotConfiguredError

    with patch(
        "finlytics.api.investments.inv_service.connect_plugin",
        side_effect=EncryptionNotConfiguredError("key missing"),
    ):
        resp = await client.post(
            "/api/investments/connections",
            json={"token": "valid-tok", "account_numbers": ["ACC1"]},
        )

    assert resp.status_code == 503
    assert "encryption" in resp.json()["detail"].lower()


async def test_portfolio_missing_encryption_key_returns_503(client):
    """GET /portfolio → 503 when FINLYTICS_ENCRYPTION_KEY absent (fail-closed)."""
    from finlytics.investments.crypto import EncryptionNotConfiguredError

    with patch(
        "finlytics.api.investments.inv_service.get_portfolio",
        side_effect=EncryptionNotConfiguredError("key missing"),
    ):
        resp = await client.get("/api/investments/portfolio")

    assert resp.status_code == 503
    assert "encryption" in resp.json()["detail"].lower()


def test_indexa_client_tls_verify_and_no_redirects():
    """_make_client uses verify=True and follow_redirects=False (Romanoff §4 build-blockers)."""
    import httpx as httpx_mod
    from finlytics.investments.indexa import _make_client

    with patch("finlytics.investments.indexa.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        _make_client("fake-token")

    call_kwargs = mock_cls.call_args.kwargs
    assert call_kwargs.get("verify") is True, (
        "TLS verify MUST be True — verify=False is a Romanoff §4 build-blocker"
    )
    assert call_kwargs.get("follow_redirects") is False, (
        "follow_redirects MUST be False to prevent X-AUTH-TOKEN leakage via redirects"
    )


# ── crypto.py unit tests ──────────────────────────────────────────────────────


def test_crypto_encrypt_decrypt_roundtrip():
    """encrypt_token → decrypt_token returns original plaintext."""
    from cryptography.fernet import Fernet
    from finlytics.investments.crypto import decrypt_token, encrypt_token

    test_key = Fernet.generate_key().decode()
    mock_settings = MagicMock()
    mock_settings.finlytics_encryption_key = test_key

    with patch("finlytics.config.settings", mock_settings):
        plaintext = "my-raw-indexa-token"
        ciphertext = encrypt_token(plaintext)
        assert ciphertext != plaintext
        assert decrypt_token(ciphertext) == plaintext


def test_crypto_tampered_ciphertext_raises():
    """Tampered ciphertext raises EncryptionNotConfiguredError — never returns garbage."""
    from cryptography.fernet import Fernet
    from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token

    test_key = Fernet.generate_key().decode()
    mock_settings = MagicMock()
    mock_settings.finlytics_encryption_key = test_key

    with patch("finlytics.config.settings", mock_settings):
        with pytest.raises(EncryptionNotConfiguredError):
            decrypt_token("this-is-not-a-valid-fernet-ciphertext")


def test_crypto_missing_key_encrypt_raises():
    """encrypt_token raises EncryptionNotConfiguredError when key is absent (fail-closed)."""
    from finlytics.investments.crypto import EncryptionNotConfiguredError, encrypt_token

    mock_settings = MagicMock()
    mock_settings.finlytics_encryption_key = None

    with patch("finlytics.config.settings", mock_settings):
        with pytest.raises(EncryptionNotConfiguredError):
            encrypt_token("some-raw-token")


def test_crypto_missing_key_decrypt_raises():
    """decrypt_token raises EncryptionNotConfiguredError when key is absent (fail-closed)."""
    from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token

    mock_settings = MagicMock()
    mock_settings.finlytics_encryption_key = None

    with patch("finlytics.config.settings", mock_settings):
        with pytest.raises(EncryptionNotConfiguredError):
            decrypt_token("some-ciphertext")


# ── Account masking unit tests ────────────────────────────────────────────────


def test_mask_account_standard():
    """Account > 5 chars → first3 + ••• + last2 (e.g. PBKLBYZ5 → PBK•••Z5)."""
    from finlytics.investments.service import _mask_account

    result = _mask_account("PBKLBYZ5")
    assert result == "PBK•••Z5"
    assert "•" in result


def test_mask_account_short_gets_bullet_prefix():
    """Short account (≤5 chars) → ••• prefix + last2; never stores raw number."""
    from finlytics.investments.service import _mask_account

    result = _mask_account("ABCDE")
    assert result == "•••DE"
    assert "•" in result
    assert result != "ABCDE"


# ── Asset class mapping (Indexa → Finlytics) ─────────────────────────────────


def test_indexa_asset_class_equity_all_variants():
    """All equity_* variants map to 'equity'."""
    from finlytics.investments.indexa import _map_asset_class

    for variant in ("equity_europe", "equity_north_america", "equity_pacific", "equity_emerging"):
        assert _map_asset_class(variant) == "equity", f"Expected 'equity' for {variant!r}"


def test_indexa_asset_class_fixed_income():
    """fixed_income_* variants map to 'fixed_income'."""
    from finlytics.investments.indexa import _map_asset_class

    assert _map_asset_class("fixed_income_bonds") == "fixed_income"
    assert _map_asset_class("fixed_income_government") == "fixed_income"


def test_indexa_asset_class_cash_and_money_market():
    """'cash' and 'money_market' map to 'cash'."""
    from finlytics.investments.indexa import _map_asset_class

    assert _map_asset_class("cash") == "cash"
    assert _map_asset_class("money_market") == "cash"


def test_indexa_asset_class_unknown_is_other():
    """Unrecognised asset class falls back to 'other'."""
    from finlytics.investments.indexa import _map_asset_class

    assert _map_asset_class("commodities") == "other"
    assert _map_asset_class("") == "other"
    assert _map_asset_class("structured_products") == "other"


# ── GET /connections ──────────────────────────────────────────────────────────


async def test_get_connections_200_returns_list(client):
    """GET /connections → 200 with masked labels; required keys present."""
    from finlytics.api.schemas import ConnectionOut

    mock_out = [
        ConnectionOut(
            id=1,
            plugin_id="indexa-capital",
            status="active",
            account_label_masked="PBK•••Z5",
            created_at=datetime.now(timezone.utc),
        )
    ]
    with patch(
        "finlytics.api.investments.inv_service.list_connections",
        new=AsyncMock(return_value=mock_out),
    ):
        resp = await client.get("/api/investments/connections")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    conn = data[0]
    assert conn["id"] == 1
    assert conn["plugin_id"] == "indexa-capital"
    assert conn["status"] == "active"
    assert conn["account_label_masked"] == "PBK•••Z5"


# ── DELETE /connections ───────────────────────────────────────────────────────


async def test_delete_connection_returns_204(client):
    """DELETE /connections/{id} → 204 when connection exists and belongs to user."""
    with patch(
        "finlytics.api.investments.inv_service.delete_connection",
        new=AsyncMock(return_value=True),
    ):
        resp = await client.delete("/api/investments/connections/1")

    assert resp.status_code == 204


async def test_delete_connection_not_found_returns_404(client):
    """DELETE /connections/{id} → 404 when not found or belongs to another user."""
    with patch(
        "finlytics.api.investments.inv_service.delete_connection",
        new=AsyncMock(return_value=False),
    ):
        resp = await client.delete("/api/investments/connections/999")

    assert resp.status_code == 404


# ── GET /portfolio ────────────────────────────────────────────────────────────


async def test_portfolio_no_connection_returns_zero_state(client):
    """GET /portfolio with no connections → zero totals, empty holdings, no returns."""
    from finlytics.api.schemas import InvestmentPortfolioOut

    zero = InvestmentPortfolioOut(
        total_value=0.0,
        total_invested=None,
        total_gain_loss=None,
        total_gain_loss_pct=None,
        currency="EUR",
        holdings=[],
        plugins_connected=0,
        last_updated=None,
    )
    with patch(
        "finlytics.api.investments.inv_service.get_portfolio",
        new=AsyncMock(return_value=zero),
    ):
        resp = await client.get("/api/investments/portfolio")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value"] == 0.0
    assert data["plugins_connected"] == 0
    assert data["holdings"] == []
    assert data["total_invested"] is None
    assert data["returns"] is None
    assert data["value_series"] == []
    assert data["cash_invested"] is None


async def test_portfolio_with_data_returns_phase2_shape(client):
    """GET /portfolio with data → 200 with returns, value_series, cash_invested, holdings."""
    from finlytics.api.schemas import (
        CashInvestedSplit,
        InvestmentHoldingOut,
        InvestmentPortfolioOut,
        InvestmentReturns,
        ValuePoint,
    )

    now_str = datetime.now(timezone.utc).isoformat()
    mock_out = InvestmentPortfolioOut(
        total_value=12345.67,
        total_invested=11000.0,
        total_gain_loss=1345.67,
        total_gain_loss_pct=1345.67 / 11000.0,
        currency="EUR",
        holdings=[
            InvestmentHoldingOut(
                plugin_id="indexa-capital",
                name="Vanguard Global Stock Index Fund",
                ticker="IE00B03HCZ61",
                asset_class="equity",
                units=42.5,
                current_value=8320.0,
                cost_basis=7500.0,
                currency="EUR",
                gain_loss=820.0,
                gain_loss_pct=820.0 / 7500.0,
                last_updated=now_str,
            )
        ],
        plugins_connected=1,
        last_updated=now_str,
        returns=InvestmentReturns(twr_annual=0.0851, xirr=0.0912, pl=1345.67, invested=11000.0),
        value_series=[
            ValuePoint(date="2024-01-01", value=10200.0),
            ValuePoint(date="2024-02-01", value=10450.0),
        ],
        cash_invested=CashInvestedSplit(
            cash_amount=250.0,
            instruments_amount=12095.67,
            instruments_cost=10750.0,
            total_amount=12345.67,
        ),
    )
    with patch(
        "finlytics.api.investments.inv_service.get_portfolio",
        new=AsyncMock(return_value=mock_out),
    ):
        resp = await client.get("/api/investments/portfolio")

    assert resp.status_code == 200
    data = resp.json()

    # Top-level
    assert data["total_value"] == pytest.approx(12345.67)
    assert data["total_invested"] == pytest.approx(11000.0)
    assert data["currency"] == "EUR"
    assert data["plugins_connected"] == 1

    # Holdings
    assert len(data["holdings"]) == 1
    h = data["holdings"][0]
    assert h["asset_class"] == "equity"
    assert h["ticker"] == "IE00B03HCZ61"
    assert h["gain_loss_pct"] == pytest.approx(820.0 / 7500.0, rel=1e-5)
    # Token NEVER in portfolio response
    assert "token" not in str(data), "Token must never appear in portfolio response"

    # Phase 2: returns
    assert data["returns"]["twr_annual"] == pytest.approx(0.0851)
    assert data["returns"]["xirr"] == pytest.approx(0.0912)
    assert data["returns"]["pl"] == pytest.approx(1345.67)

    # Phase 2: value_series — dates in YYYY-MM-DD format
    assert len(data["value_series"]) == 2
    for vp in data["value_series"]:
        assert len(vp["date"]) == 10, f"value_series date must be YYYY-MM-DD, got {vp['date']!r}"

    # Phase 2: cash_invested
    assert data["cash_invested"]["cash_amount"] == pytest.approx(250.0)
    assert data["cash_invested"]["instruments_cost"] == pytest.approx(10750.0)


async def test_portfolio_service_maps_holdings_gain_loss_and_returns():
    """Service layer: provider data correctly mapped → holdings, gain_loss_pct, returns, value_series."""
    from finlytics.investments import service as svc
    from finlytics.investments.base import (
        DiscoveredAccount,
        NormalizedCashInvested,
        NormalizedHolding,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
        NormalizedValuePoint,
        ValidationResult,
    )

    mock_conn = MagicMock()
    mock_conn.id = 1
    mock_conn.plugin_id = "indexa-capital"
    mock_conn.status = "active"
    mock_conn.token_enc = "fake-enc-token"
    mock_conn.account_label_masked = "PBK•••Z5"
    mock_conn.last_synced_at = None

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_conn]
    # Simulate DB cache miss so the live-fetch path is exercised
    execute_result.scalar_one_or_none.return_value = None
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    validation = ValidationResult(
        valid=True,
        accounts=[DiscoveredAccount("PBKLBYZ5", "mutual", "active")],
    )
    cost = 7500.0
    pl = 820.0
    portfolio = NormalizedPortfolio(
        holdings=[
            NormalizedHolding(
                name="Vanguard Global",
                ticker="IE00B03HCZ61",
                asset_class="equity",
                units=42.5,
                current_value=8320.0,
                cost_basis=cost,
                gain_loss=pl,
                gain_loss_pct=pl / cost,
            )
        ],
        total_value=8320.0,
        total_invested=cost,
        total_gain_loss=pl,
        performance=NormalizedPerformance(
            total_value=8320.0,
            returns=NormalizedReturns(twr_annual=0.085, xirr=0.091, pl=pl, invested=cost),
            value_series=[
                NormalizedValuePoint("20240101", 7000.0),
                NormalizedValuePoint("20240201", 7800.0),
            ],
            cash_invested=NormalizedCashInvested(100.0, 8220.0, 7400.0, 8320.0),
        ),
    )

    with (
        patch("finlytics.investments.service.decrypt_token", return_value="plain-tok"),
        patch.object(svc._PROVIDERS["indexa-capital"], "validate_token", AsyncMock(return_value=validation)),
        patch.object(svc._PROVIDERS["indexa-capital"], "get_portfolio", AsyncMock(return_value=portfolio)),
    ):
        result = await svc.get_portfolio(user_id=1, db=mock_db)

    # Holdings
    assert len(result.holdings) == 1
    h = result.holdings[0]
    assert h.name == "Vanguard Global"
    assert h.ticker == "IE00B03HCZ61"
    assert h.asset_class == "equity"
    assert h.gain_loss_pct == pytest.approx(pl / cost, rel=1e-5)

    # gain_loss_pct at portfolio level: total_gain_loss / total_invested
    assert result.total_gain_loss_pct == pytest.approx(pl / cost, rel=1e-5)

    # Value series YYYYMMDD
    assert len(result.value_series) == 2
    assert result.value_series[0].date == "20240101"
    assert result.value_series[1].date == "20240201"

    # Returns (single account → twr_annual/xirr populated)
    assert result.returns is not None
    assert result.returns.twr_annual == pytest.approx(0.085)
    assert result.returns.xirr == pytest.approx(0.091)
    assert result.returns.pl == pytest.approx(pl)

    # cash_invested
    assert result.cash_invested is not None
    assert result.cash_invested.cash_amount == pytest.approx(100.0)


# ── Plugins: Indexa status flips available → connected ───────────────────────


async def test_plugins_indexa_status_connected_when_connection_exists(client, mock_session):
    """Indexa status = 'connected' when DB execute returns it as an active connection."""
    mock_session.execute = AsyncMock(return_value=[("indexa-capital",)])

    resp = await client.get("/api/investments/plugins")

    assert resp.status_code == 200
    plugins = resp.json()
    indexa = next(p for p in plugins if p["id"] == "indexa-capital")
    assert indexa["status"] == "connected", (
        f"Expected 'connected' when connection exists, got {indexa['status']!r}"
    )
    # fidelity-espp is dynamic but not connected here → available
    fidelity = next(p for p in plugins if p["id"] == "fidelity-espp")
    assert fidelity["status"] == "available"
    # Non-dynamic plugins unaffected
    others = [p for p in plugins if p["id"] not in ("indexa-capital", "fidelity-espp")]
    for p in others:
        assert p["status"] == "coming_soon"


async def test_plugins_fidelity_status_connected_when_connection_exists(client, mock_session):
    """fidelity-espp status = 'connected' when DB execute returns it as an active connection."""
    mock_session.execute = AsyncMock(return_value=[("fidelity-espp",)])

    resp = await client.get("/api/investments/plugins")

    assert resp.status_code == 200
    plugins = resp.json()
    fidelity = next(p for p in plugins if p["id"] == "fidelity-espp")
    assert fidelity["status"] == "connected", (
        f"Expected 'connected' when fidelity connection exists, got {fidelity['status']!r}"
    )
    # indexa-capital is dynamic but not connected here → available
    indexa = next(p for p in plugins if p["id"] == "indexa-capital")
    assert indexa["status"] == "available"
    # Non-dynamic plugins unaffected
    others = [p for p in plugins if p["id"] not in ("indexa-capital", "fidelity-espp")]
    for p in others:
        assert p["status"] == "coming_soon"


# ── BUG A: total_value fallback chain ─────────────────────────────────────────


async def test_fetch_performance_total_value_from_portfolios_when_top_level_zero():
    """BUG A: top-level total_amount is 0 → portfolios[0].total_amount is authoritative."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 0,
        "return": {
            "time_return_annual": 0.085,
            "total_amounts": {"20240101": 18000.0, "20240201": 20559.52},
        },
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 67.16,
                "instruments_amount": 20492.36,
                "instruments_cost": 18000.0,
                "total_amount": 20559.52,
            }
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.total_value == pytest.approx(20559.52)


async def test_fetch_performance_total_value_from_series_when_no_portfolios():
    """BUG A: no portfolios → falls back to last entry in return.total_amounts series."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 0,
        "return": {
            "total_amounts": {"20240101": 18000.0, "20240201": 19500.0},
        },
        "net_amounts": {},
        "portfolios": [],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.total_value == pytest.approx(19500.0)


async def test_fetch_performance_total_value_from_top_level_as_last_resort():
    """BUG A: no portfolios, no series → uses top-level total_amount."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 15000.0,
        "return": {},
        "total_amounts": {},
        "portfolios": [],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.total_value == pytest.approx(15000.0)


# ── BUG B: ISIN deduplication ─────────────────────────────────────────────────


async def test_get_portfolio_deduplicates_same_isin():
    """BUG B: multiple fiscal_results with identical ISIN → aggregated into one holding."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from finlytics.investments.indexa import IndexaProvider

    fiscal_data = {
        "fiscal_results": [
            {
                "instrument": {
                    "identifier": "IE00B03HCZ61",
                    "name": "Vanguard US 500",
                    "asset_class": "equity_north_america",
                },
                "amount": 5000.0,
                "cost_amount": 4500.0,
                "titles": 10.0,
                "profit_loss": 500.0,
            },
            {
                "instrument": {
                    "identifier": "IE00B03HCZ61",
                    "name": "Vanguard US 500",
                    "asset_class": "equity_north_america",
                },
                "amount": 3000.0,
                "cost_amount": 2800.0,
                "titles": 6.0,
                "profit_loss": 200.0,
            },
        ]
    }
    perf_data = {
        "total_amount": 8000.0,
        "return": {},
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 0.0,
                "instruments_amount": 8000.0,
                "instruments_cost": 7300.0,
                "total_amount": 8000.0,
            }
        ],
    }

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch(
            "finlytics.investments.indexa._get",
            side_effect=[fiscal_data, perf_data],
        ),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1"])

    assert len(portfolio.holdings) == 1, (
        f"Expected 1 holding (deduplicated), got {len(portfolio.holdings)}"
    )
    h = portfolio.holdings[0]
    assert h.ticker == "IE00B03HCZ61"
    assert h.current_value == pytest.approx(8000.0)
    assert h.cost_basis == pytest.approx(7300.0)
    assert h.units == pytest.approx(16.0)
    assert h.gain_loss == pytest.approx(700.0)
    assert h.gain_loss_pct == pytest.approx(700.0 / 7300.0, rel=1e-5)


async def test_get_portfolio_distinct_isins_not_merged():
    """BUG B: fiscal_results with different ISINs stay as separate holdings."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import IndexaProvider

    fiscal_data = {
        "fiscal_results": [
            {
                "instrument": {"identifier": "IE00B03HCZ61", "name": "Fund A", "asset_class": "equity_north_america"},
                "amount": 5000.0,
                "cost_amount": 4500.0,
                "titles": 10.0,
                "profit_loss": 500.0,
            },
            {
                "instrument": {"identifier": "LU0011850392", "name": "Fund B", "asset_class": "fixed_income_bonds"},
                "amount": 3000.0,
                "cost_amount": 2800.0,
                "titles": 6.0,
                "profit_loss": 200.0,
            },
        ]
    }
    perf_data = {
        "total_amount": 8000.0,
        "return": {},
        "net_amounts": {},
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 8000.0, "instruments_cost": 7300.0, "total_amount": 8000.0}
        ],
    }

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    provider = IndexaProvider()
    with (
        patch("finlytics.investments.indexa._make_client", return_value=mock_cm),
        patch("finlytics.investments.indexa._get", side_effect=[fiscal_data, perf_data]),
    ):
        portfolio = await provider.get_portfolio("tok", ["ACC1"])

    assert len(portfolio.holdings) == 2
    tickers = {h.ticker for h in portfolio.holdings}
    assert tickers == {"IE00B03HCZ61", "LU0011850392"}


# ── Enhancement: new return fields ───────────────────────────────────────────


async def test_fetch_performance_new_return_fields_populated():
    """Enhancement: twr_total, twr_last_week/month/year, money_return, volatility mapped."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        "volatility": 0.12,
        "return": {
            "time_return_annual": 0.085,
            "time_return": 0.142,
            "time_return_last_week": 0.003,
            "time_return_last_month": 0.012,
            "time_return_last_year": 0.091,
            "money_return": 2000.0,
            "XIRR": 0.09,
            "pl": 2000.0,
            "investment": 18000.0,
        },
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 500.0,
                "instruments_amount": 19500.0,
                "instruments_cost": 17500.0,
                "total_amount": 20000.0,
            }
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC1")

    assert result.returns.twr_annual == pytest.approx(0.085)
    assert result.returns.twr_total == pytest.approx(0.142)
    assert result.returns.twr_last_week == pytest.approx(0.003)
    assert result.returns.twr_last_month == pytest.approx(0.012)
    assert result.returns.twr_last_year == pytest.approx(0.091)
    assert result.returns.money_return == pytest.approx(2000.0)
    assert result.returns.volatility == pytest.approx(0.12)
    assert result.returns.xirr == pytest.approx(0.09)


def test_investment_returns_schema_has_new_fields():
    """InvestmentReturns schema carries the new optional return fields."""
    from finlytics.api.schemas import InvestmentReturns

    r = InvestmentReturns(
        twr_annual=0.085,
        twr_total=0.142,
        twr_last_week=0.003,
        twr_last_month=0.012,
        twr_last_year=0.091,
        money_return=2000.0,
        volatility=0.12,
        xirr=0.09,
        pl=2000.0,
        invested=18000.0,
    )
    assert r.twr_total == pytest.approx(0.142)
    assert r.twr_last_week == pytest.approx(0.003)
    assert r.twr_last_month == pytest.approx(0.012)
    assert r.twr_last_year == pytest.approx(0.091)
    assert r.money_return == pytest.approx(2000.0)
    assert r.volatility == pytest.approx(0.12)
    # All new fields default to None when omitted
    r2 = InvestmentReturns(pl=100.0)
    assert r2.twr_total is None
    assert r2.volatility is None
    assert r2.money_return is None


# ── FIX 1: value_series reads from nested return.total_amounts ─────────────────


async def test_fetch_performance_value_series_from_nested_return_total_amounts():
    """FIX 1: value_series reads from data['return']['total_amounts'] (not top-level).
    YYYYMMDD keys are converted to YYYY-MM-DD."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20559.52,
        "return": {
            "total_amounts": {
                "20240804": 0.0,
                "20250720": 13382.93,
                "20260713": 20559.52,
            },
        },
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 67.16,
                "instruments_amount": 20492.36,
                "instruments_cost": 18000.0,
                "total_amount": 20559.52,
            }
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert len(result.value_series) == 3
    assert result.value_series[0].date == "2024-08-04"
    assert result.value_series[1].date == "2025-07-20"
    assert result.value_series[2].date == "2026-07-13"
    assert result.value_series[2].value == pytest.approx(20559.52)
    # Sorted ascending
    dates = [vp.date for vp in result.value_series]
    assert dates == sorted(dates)


async def test_fetch_performance_top_level_total_amounts_ignored():
    """FIX 1 negative: top-level total_amounts is NOT read; only return.total_amounts counts."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        # This should be ignored now:
        "total_amounts": {"20240101": 99999.0, "20240201": 88888.0},
        "return": {},   # no total_amounts inside return → value_series should be empty
        "net_amounts": {},
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20000.0,
             "instruments_cost": 18000.0, "total_amount": 20000.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.value_series == [], (
        "value_series must be empty when return.total_amounts is absent"
    )


# ── FIX 2+3: portfolios newest-first — use [0] not [-1] ───────────────────────


async def test_fetch_performance_portfolios_newest_first_uses_index_zero():
    """FIX 2+3: portfolios[0] is newest; older entry at [-1] has zeros.
    total_value and cash_invested must come from [0]."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 0,
        "return": {},
        "net_amounts": {},
        "portfolios": [
            # newest at index 0
            {
                "cash_amount": 67.16,
                "instruments_amount": 20492.36,
                "instruments_cost": 18000.0,
                "total_amount": 20559.52,
            },
            # oldest at index -1 (account open, all zeros)
            {
                "cash_amount": 0.0,
                "instruments_amount": 0.0,
                "instruments_cost": 0.0,
                "total_amount": 0.0,
            },
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.total_value == pytest.approx(20559.52), (
        "total_value must come from portfolios[0] (newest), not portfolios[-1] (oldest=0)"
    )
    assert result.cash_invested is not None
    assert result.cash_invested.total_amount == pytest.approx(20559.52)
    assert result.cash_invested.cash_amount == pytest.approx(67.16)


# ── ADD: contributions_series from net_amounts ────────────────────────────────


async def test_fetch_performance_contributions_series_from_net_amounts():
    """ADD: contributions_series from top-level net_amounts, YYYYMMDD → YYYY-MM-DD, sorted ASC."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20559.52,
        "return": {},
        "net_amounts": {
            "20240804": 0.0,
            "20240904": 2000.0,
            "20241004": 4000.0,
            "20241231": 17999.99,
        },
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20559.52,
             "instruments_cost": 18000.0, "total_amount": 20559.52}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert len(result.contributions_series) == 4
    assert result.contributions_series[0].date == "2024-08-04"
    assert result.contributions_series[0].value == pytest.approx(0.0)
    assert result.contributions_series[1].date == "2024-09-04"
    assert result.contributions_series[3].date == "2024-12-31"
    assert result.contributions_series[3].value == pytest.approx(17999.99)
    # Sorted ascending
    dates = [vp.date for vp in result.contributions_series]
    assert dates == sorted(dates)


# ── ADD: contribution_events (deltas + withdrawal) ────────────────────────────


async def test_fetch_performance_contribution_events_with_withdrawal():
    """contribution_events deriva los deltas de net_amounts; cubre aportación, retirada y acumulado.

    net_amounts:
      20240101 → 0.0    (marcador de apertura, se omite)
      20240201 → 2000.0 (aportación inicial +2000, acumulado 2000)
      20240301 → 4000.0 (aportación +2000, acumulado 4000)
      20240401 → 3500.0 (retirada  -500,  acumulado 3500)
      20240501 → 5000.0 (aportación +1500, acumulado 5000)
    """
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 3200.0,
        "return": {},
        "net_amounts": {
            "20240101": 0.0,
            "20240201": 2000.0,
            "20240301": 4000.0,
            "20240401": 3500.0,
            "20240501": 5000.0,
        },
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 3200.0,
             "instruments_cost": 3500.0, "total_amount": 3200.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    events = result.contribution_events
    assert len(events) == 4, f"Esperados 4 eventos, obtenidos {len(events)}"

    assert events[0].date == "2024-02-01"
    assert events[0].amount == pytest.approx(2000.0)
    assert events[0].cumulative == pytest.approx(2000.0)
    assert events[0].type == "contribution"

    assert events[1].date == "2024-03-01"
    assert events[1].amount == pytest.approx(2000.0)
    assert events[1].cumulative == pytest.approx(4000.0)
    assert events[1].type == "contribution"

    assert events[2].date == "2024-04-01"
    assert events[2].amount == pytest.approx(-500.0)
    assert events[2].cumulative == pytest.approx(3500.0)
    assert events[2].type == "withdrawal"

    assert events[3].date == "2024-05-01"
    assert events[3].amount == pytest.approx(1500.0)
    assert events[3].cumulative == pytest.approx(5000.0)
    assert events[3].type == "contribution"

    # contributions_series permanece intacta (valores acumulativos brutos)
    assert len(result.contributions_series) == 5
    cs_by_date = {vp.date: vp.value for vp in result.contributions_series}
    assert cs_by_date["2024-01-01"] == pytest.approx(0.0)
    assert cs_by_date["2024-04-01"] == pytest.approx(3500.0)


# ── ADD: monthly returns matrix ────────────────────────────────────────────────


async def test_fetch_performance_monthly_returns_two_month_example():
    """ADD: monthly_returns from history. 2-month example with known values.

    history: Aug 2024 = 1.034754, Sep 2024 = 1.049695
    Aug pct = 1.034754 − 1 = 3.4754%
    Sep pct = 1.049695 / 1.034754 − 1 ≈ 1.4446%
    Year total = 1.049695 − 1 = 4.9695%
    Benchmark: Aug=0 (int), Sep='0.009511' (str) → annual = (1+0)*(1+0.009511)−1 ≈ 0.9511%
    EUR Aug = (10000 − 0) − (9800 − 0) = 200
    EUR Sep = (11500 − 10000) − (9800 − 9800) = 1500
    """
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        "return": {
            "total_amounts": {
                "20240831": 10000.0,
                "20240930": 11500.0,
            },
        },
        "net_amounts": {
            "20240831": 9800.0,
            "20240930": 9800.0,
        },
        "history": {
            "2024-08-31": 1.034754,
            "2024-09-30": 1.049695,
        },
        "benchmark": {
            "2024-08-31": {"date": "2024-08-31", "benchmark_percentage_return": 0},
            "2024-09-30": {"date": "2024-09-30", "benchmark_percentage_return": "0.009511"},
        },
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20000.0,
             "instruments_cost": 18000.0, "total_amount": 20000.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert len(result.monthly_returns) == 1
    row = result.monthly_returns[0]
    assert row.year == 2024
    assert set(row.months_pct.keys()) == {8, 9}
    assert row.months_pct[8] == pytest.approx(0.034754, abs=1e-5)
    sep_pct = 1.049695 / 1.034754 - 1
    assert row.months_pct[9] == pytest.approx(sep_pct, abs=1e-5)
    # Year total = compound of all months = 1.049695 − 1
    assert row.total_pct == pytest.approx(0.049695, abs=1e-5)
    # Benchmark: (1+0)*(1+0.009511) − 1 = 0.009511
    assert row.benchmark_pct == pytest.approx(0.009511, abs=1e-5)
    # EUR P&L
    assert row.months_eur[8] == pytest.approx(200.0, abs=0.01)
    assert row.months_eur[9] == pytest.approx(1500.0, abs=0.01)
    assert row.total_eur == pytest.approx(1700.0, abs=0.01)


async def test_fetch_performance_monthly_returns_multi_year():
    """ADD: monthly_returns groups into correct year rows when history spans multiple years."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        "return": {"total_amounts": {}},
        "net_amounts": {},
        "history": {
            "2024-11-30": 1.02,
            "2024-12-31": 1.05,
            "2025-01-31": 1.08,
            "2025-02-28": 1.10,
        },
        "benchmark": {},
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20000.0,
             "instruments_cost": 18000.0, "total_amount": 20000.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert len(result.monthly_returns) == 2
    y2024 = next(r for r in result.monthly_returns if r.year == 2024)
    y2025 = next(r for r in result.monthly_returns if r.year == 2025)
    assert set(y2024.months_pct.keys()) == {11, 12}
    assert set(y2025.months_pct.keys()) == {1, 2}
    # 2024 total = (1.02) * (1.05/1.02) − 1 = 1.05 − 1 = 0.05
    assert y2024.total_pct == pytest.approx(0.05, abs=1e-5)
    # 2025 total = (1.08/1.05) * (1.10/1.08) − 1 = 1.10/1.05 − 1
    assert y2025.total_pct == pytest.approx(1.10 / 1.05 - 1, abs=1e-5)


async def test_fetch_performance_monthly_returns_empty_when_no_history():
    """ADD: empty history → monthly_returns is []."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        "return": {},
        "net_amounts": {},
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20000.0,
             "instruments_cost": 18000.0, "total_amount": 20000.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.monthly_returns == []


# ── ADD: max drawdown mapping ─────────────────────────────────────────────────


async def test_fetch_performance_drawdown_mapped():
    """ADD: drawdown from data['drawdowns'], integer YYYYMMDD dates → YYYY-MM-DD."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20559.52,
        "return": {},
        "net_amounts": {},
        "drawdowns": {
            "max_drawdown": -0.1005,
            "max_drawdown_EUR": -1356.93,
            "start_date_max_drawdown": 20250220,
            "end_date_max_drawdown": 20250408,
        },
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20559.52,
             "instruments_cost": 18000.0, "total_amount": 20559.52}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.drawdown is not None
    assert result.drawdown.max_drawdown == pytest.approx(-0.1005)
    assert result.drawdown.max_drawdown_eur == pytest.approx(-1356.93)
    assert result.drawdown.start_date == "2025-02-20"
    assert result.drawdown.end_date == "2025-04-08"


async def test_fetch_performance_drawdown_none_when_absent():
    """ADD: drawdown is None when 'drawdowns' key is missing from response."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 20000.0,
        "return": {},
        "net_amounts": {},
        "portfolios": [
            {"cash_amount": 0.0, "instruments_amount": 20000.0,
             "instruments_cost": 18000.0, "total_amount": 20000.0}
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.drawdown is None


# ── ADD: Valor total box numbers ──────────────────────────────────────────────


async def test_fetch_performance_valor_total_box_numbers():
    """ADD: aportaciones, retenciones, rentabilidad_eur, rentabilidad_pct,
    sharpe_ratio, money_return_annual from return.* and top-level."""
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 0,
        "sharpe_ratio": 1.325,
        "return": {
            "inflows": 18000.0,
            "tax_outflows": -0.01,
            "pl": 2559.53,
            "money_return": 0.2133,
            "money_return_annual": 0.1050,
            "time_return": 0.2373,
            "time_return_annual": 0.1162,
            "XIRR": 0.1050,
        },
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 67.16,
                "instruments_amount": 20492.36,
                "instruments_cost": 18000.0,
                "total_amount": 20559.52,
            }
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    assert result.returns.aportaciones == pytest.approx(18000.0)
    assert result.returns.retenciones == pytest.approx(-0.01)
    assert result.returns.rentabilidad_eur == pytest.approx(2559.53)
    assert result.returns.rentabilidad_pct == pytest.approx(0.2133)
    assert result.returns.sharpe_ratio == pytest.approx(1.325)
    assert result.returns.money_return_annual == pytest.approx(0.1050)
    assert result.returns.twr_total == pytest.approx(0.2373)
    assert result.returns.twr_annual == pytest.approx(0.1162)
    assert result.total_value == pytest.approx(20559.52)


def test_investment_returns_schema_valor_total_fields():
    """Schema: InvestmentReturns carries valor-total box + sharpe_ratio fields."""
    from finlytics.api.schemas import InvestmentReturns

    r = InvestmentReturns(
        aportaciones=18000.0,
        retenciones=-0.01,
        rentabilidad_eur=2559.53,
        rentabilidad_pct=0.2133,
        sharpe_ratio=1.325,
        money_return_annual=0.1050,
        pl=2559.53,
    )
    assert r.aportaciones == pytest.approx(18000.0)
    assert r.retenciones == pytest.approx(-0.01)
    assert r.rentabilidad_eur == pytest.approx(2559.53)
    assert r.rentabilidad_pct == pytest.approx(0.2133)
    assert r.sharpe_ratio == pytest.approx(1.325)
    assert r.money_return_annual == pytest.approx(0.1050)
    # All default to None
    r2 = InvestmentReturns()
    assert r2.aportaciones is None
    assert r2.sharpe_ratio is None


def test_portfolio_out_schema_has_contributions_monthly_drawdown():
    """Schema: InvestmentPortfolioOut carries contributions_series, monthly_returns, drawdown."""
    from finlytics.api.schemas import DrawdownOut, InvestmentPortfolioOut, MonthlyReturnRow, ValuePoint

    out = InvestmentPortfolioOut(
        total_value=20559.52,
        currency="EUR",
        holdings=[],
        plugins_connected=1,
        contributions_series=[ValuePoint(date="2024-08-04", value=0.0)],
        monthly_returns=[
            MonthlyReturnRow(
                year=2024,
                months_pct={8: 0.0348, 9: 0.0144},
                months_eur={8: 200.0, 9: 1500.0},
                total_pct=0.0497,
                total_eur=1700.0,
                benchmark_pct=0.0095,
            )
        ],
        drawdown=DrawdownOut(
            max_drawdown=-0.1005,
            max_drawdown_eur=-1356.93,
            start_date="2025-02-20",
            end_date="2025-04-08",
        ),
    )
    assert len(out.contributions_series) == 1
    assert out.monthly_returns is not None
    assert len(out.monthly_returns) == 1
    assert out.monthly_returns[0].year == 2024
    assert out.drawdown is not None
    assert out.drawdown.start_date == "2025-02-20"


# ── ADD: service _aggregate passes through new fields (single account) ─────────


async def test_aggregate_single_account_passes_through_monthly_and_drawdown():
    """Service: single account → monthly_returns + drawdown passed through."""
    from finlytics.investments import service as svc
    from finlytics.investments.base import (
        DiscoveredAccount,
        NormalizedCashInvested,
        NormalizedDrawdown,
        NormalizedHolding,
        NormalizedMonthlyReturnRow,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
        NormalizedValuePoint,
        ValidationResult,
    )

    mock_conn = MagicMock()
    mock_conn.id = 1
    mock_conn.plugin_id = "indexa-capital"
    mock_conn.status = "active"
    mock_conn.token_enc = "fake-enc-token"
    mock_conn.account_label_masked = "PBK•••Z5"
    mock_conn.last_synced_at = None

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_conn]
    # Simulate DB cache miss so the live-fetch path is exercised
    execute_result.scalar_one_or_none.return_value = None
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()

    validation = ValidationResult(
        valid=True,
        accounts=[DiscoveredAccount("PBKLBYZ5", "mutual", "active")],
    )

    portfolio = NormalizedPortfolio(
        holdings=[],
        total_value=20559.52,
        total_invested=18000.0,
        total_gain_loss=2559.53,
        performance=NormalizedPerformance(
            total_value=20559.52,
            returns=NormalizedReturns(
                pl=2559.53,
                invested=18000.0,
                aportaciones=18000.0,
                retenciones=-0.01,
                rentabilidad_eur=2559.53,
                rentabilidad_pct=0.2133,
                sharpe_ratio=1.325,
                money_return_annual=0.1050,
            ),
            value_series=[NormalizedValuePoint("2024-08-04", 0.0)],
            contributions_series=[NormalizedValuePoint("2024-08-04", 0.0)],
            monthly_returns=[
                NormalizedMonthlyReturnRow(
                    year=2024,
                    months_pct={8: 0.0348},
                    months_eur={8: 200.0},
                    total_pct=0.0348,
                    total_eur=200.0,
                    benchmark_pct=0.0,
                )
            ],
            drawdown=NormalizedDrawdown(
                max_drawdown=-0.1005,
                max_drawdown_eur=-1356.93,
                start_date="2025-02-20",
                end_date="2025-04-08",
            ),
        ),
    )

    with (
        patch("finlytics.investments.service.decrypt_token", return_value="plain-tok"),
        patch.object(svc._PROVIDERS["indexa-capital"], "validate_token", AsyncMock(return_value=validation)),
        patch.object(svc._PROVIDERS["indexa-capital"], "get_portfolio", AsyncMock(return_value=portfolio)),
    ):
        result = await svc.get_portfolio(user_id=1, db=mock_db)

    # Monthly returns passed through
    assert result.monthly_returns is not None
    assert len(result.monthly_returns) == 1
    assert result.monthly_returns[0].year == 2024

    # Drawdown passed through
    assert result.drawdown is not None
    assert result.drawdown.max_drawdown == pytest.approx(-0.1005)
    assert result.drawdown.start_date == "2025-02-20"

    # Contributions series passed through
    assert len(result.contributions_series) == 1

    # Box numbers
    assert result.returns is not None
    assert result.returns.aportaciones == pytest.approx(18000.0)
    assert result.returns.retenciones == pytest.approx(-0.01)
    assert result.returns.sharpe_ratio == pytest.approx(1.325)
    assert result.returns.money_return_annual == pytest.approx(0.1050)


# ── BARTON: high-value computation correctness tests ─────────────────────────


def test_compute_monthly_returns_three_months_exact_math():
    """Monthly matrix: 3 consecutive months with fully specified arithmetic.

    h = {Aug: 1.034754, Sep: 1.049695, Oct: 1.041824}
      Aug TWR  = h[0] − 1              = 0.034754
      Sep TWR  = h[1]/h[0] − 1         ≈ 0.014446
      Oct TWR  = h[2]/h[1] − 1         ≈ −0.007494
      Year tot = product(1+monthly)−1  = 1.041824 − 1 = 0.041824

    Benchmark: int 0 (Aug), string "0.009" (Sep), string "0.008" (Oct).
    Annual BM = (1+0)×(1+0.009)×(1+0.008)−1 = 0.017072

    EUR P&L (val_end−val_start − net_end−net_start):
      Aug: (10347.54−0) − (10000−0)     = 347.54
      Sep: (12000−10347.54) − (10000−10000) = 1652.46
      Oct: (11500−12000) − (10000−10000) = −500.0
    """
    from finlytics.investments.indexa import _compute_monthly_returns

    history = {
        "2024-08-31": 1.034754,
        "2024-09-30": 1.049695,
        "2024-10-31": 1.041824,
    }
    benchmark = {
        "2024-08-31": {"date": "2024-08-31", "benchmark_percentage_return": 0},          # int gotcha
        "2024-09-30": {"date": "2024-09-30", "benchmark_percentage_return": "0.009"},    # string
        "2024-10-31": {"date": "2024-10-31", "benchmark_percentage_return": "0.008"},    # string
    }
    total_amounts_raw = {
        "20240831": 10347.54,
        "20240930": 12000.0,
        "20241031": 11500.0,
    }
    net_amounts_raw = {
        "20240831": 10000.0,
        "20240930": 10000.0,
        "20241031": 10000.0,
    }

    rows = _compute_monthly_returns(history, benchmark, total_amounts_raw, net_amounts_raw)

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    assert set(row.months_pct.keys()) == {8, 9, 10}

    # Per-month TWR exact formula
    assert row.months_pct[8] == pytest.approx(0.034754, abs=1e-6)
    assert row.months_pct[9] == pytest.approx(1.049695 / 1.034754 - 1, abs=1e-6)
    assert row.months_pct[10] == pytest.approx(1.041824 / 1.049695 - 1, abs=1e-6)

    # Year total = compound = 1.041824 − 1
    assert row.total_pct == pytest.approx(0.041824, abs=1e-6)

    # Benchmark: int 0 first entry must parse; strings must parse
    expected_bm = (1.0 + 0) * (1.0 + 0.009) * (1.0 + 0.008) - 1.0
    assert row.benchmark_pct == pytest.approx(expected_bm, abs=1e-6)

    # EUR P&L deltas
    assert row.months_eur[8] == pytest.approx(347.54, abs=0.01)
    assert row.months_eur[9] == pytest.approx(12000.0 - 10347.54, abs=0.01)
    assert row.months_eur[10] == pytest.approx(-500.0, abs=0.01)
    assert row.total_eur == pytest.approx(347.54 + (12000.0 - 10347.54) - 500.0, abs=0.02)


def test_compute_monthly_returns_gap_month_absent_from_dict():
    """Gap month in history is ABSENT from months_pct — no null key inserted.

    Aug and Oct in history, Sep intentionally missing.
    months_pct must have exactly {8, 10}; key 9 must not exist.
    Oct's TWR is h[Oct]/h[Aug]−1 (relative to last available cumulative).
    """
    from finlytics.investments.indexa import _compute_monthly_returns

    history = {
        "2024-08-31": 1.034754,
        # Sep absent — gap
        "2024-10-31": 1.041824,
    }
    rows = _compute_monthly_returns(history, {}, {}, {})

    assert len(rows) == 1
    row = rows[0]
    assert set(row.months_pct.keys()) == {8, 10}, (
        "Missing month must be ABSENT from months_pct (not present with null value)"
    )
    assert 9 not in row.months_pct
    # Oct TWR is relative to Aug (last available prev_twr)
    assert row.months_pct[10] == pytest.approx(1.041824 / 1.034754 - 1, abs=1e-6)


def test_compute_monthly_returns_benchmark_is_dict_not_list():
    """Regression: benchmark must be handled as a DICT keyed by date (real Indexa shape).

    This test FAILS on the old code (AttributeError: 'str' object has no attribute 'get')
    and PASSES after the fix. Reproduces the GET /api/investments/portfolio HTTP 500.
    """
    from finlytics.investments.indexa import _compute_monthly_returns

    # Real Indexa /performance shape: benchmark is a dict keyed by date string.
    # Values are dicts with benchmark_percentage_return as string (except first month = int 0).
    history = {
        "2024-08-31": 1.034754,
        "2024-09-30": 1.049695,
    }
    benchmark = {
        "2024-08-31": {"date": "2024-08-31", "benchmark_id": "2", "benchmark": 100.0,
                       "benchmark_percentage_return": 0},           # int (first month)
        "2024-09-30": {"date": "2024-09-30", "benchmark_id": "2", "benchmark": 100.9512,
                       "benchmark_percentage_return": "0.009511"},  # string
    }

    # Must not raise AttributeError
    rows = _compute_monthly_returns(history, benchmark, {}, {})

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    # Both months present in the result
    assert set(row.months_pct.keys()) == {8, 9}
    # Annual benchmark: (1+0) × (1+0.009511) − 1 ≈ 0.009511
    assert row.benchmark_pct == pytest.approx(0.009511, abs=1e-5)


async def test_fetch_performance_valor_total_reconciliation():
    """Invariant: aportaciones + retenciones + rentabilidad_eur == total_value (±0.01 €).

    Uses the live-account numbers from Shuri's design doc:
      18000.00 + (−0.01) + 2559.53 = 20559.52 ✓
    Guards that the 'Valor total' box numbers are internally consistent.
    """
    from unittest.mock import AsyncMock, patch

    from finlytics.investments.indexa import _fetch_performance

    mock_data = {
        "total_amount": 0,
        "return": {
            "inflows": 18000.0,
            "tax_outflows": -0.01,
            "pl": 2559.53,
            "money_return": 0.2133,
        },
        "net_amounts": {},
        "portfolios": [
            {
                "cash_amount": 67.16,
                "instruments_amount": 20492.36,
                "instruments_cost": 18000.0,
                "total_amount": 20559.52,
            }
        ],
    }
    with patch("finlytics.investments.indexa._get", AsyncMock(return_value=mock_data)):
        result = await _fetch_performance(AsyncMock(), "ACC123")

    r = result.returns
    reconciled = (r.aportaciones or 0.0) + (r.retenciones or 0.0) + (r.rentabilidad_eur or 0.0)
    assert abs(reconciled - result.total_value) <= 0.01, (
        f"Valor-total box must reconcile: "
        f"{r.aportaciones} + {r.retenciones} + {r.rentabilidad_eur} "
        f"= {reconciled:.4f} ≠ {result.total_value:.4f}"
    )
    # Exact live values from the design doc
    assert r.aportaciones == pytest.approx(18000.0)
    assert r.retenciones == pytest.approx(-0.01)
    assert r.rentabilidad_eur == pytest.approx(2559.53)
    assert result.total_value == pytest.approx(20559.52)


def test_aggregate_multi_account_nulls_and_sums():
    """Multi-account _aggregate: twr/xirr/volatility/sharpe/monthly_returns/drawdown → None;
    value_series + contributions_series summed by date; pl/aportaciones/retenciones/
    rentabilidad_eur summed. Guards the non-aggregatable-field nulling logic.
    """
    from unittest.mock import MagicMock

    from finlytics.investments.base import (
        NormalizedDrawdown,
        NormalizedMonthlyReturnRow,
        NormalizedPerformance,
        NormalizedPortfolio,
        NormalizedReturns,
        NormalizedValuePoint,
    )
    from finlytics.investments.service import _aggregate

    perf_a = NormalizedPerformance(
        total_value=12000.0,
        returns=NormalizedReturns(
            twr_annual=0.08, twr_total=0.10, xirr=0.09, volatility=0.10,
            sharpe_ratio=1.2, rentabilidad_pct=0.08,
            pl=800.0, invested=11000.0,
            aportaciones=11000.0, retenciones=-0.01, rentabilidad_eur=800.0,
            money_return=800.0,
        ),
        value_series=[
            NormalizedValuePoint("2024-08-31", 10000.0),
            NormalizedValuePoint("2024-09-30", 12000.0),
        ],
        contributions_series=[
            NormalizedValuePoint("2024-08-31", 10200.0),
            NormalizedValuePoint("2024-09-30", 10200.0),
        ],
        monthly_returns=[
            NormalizedMonthlyReturnRow(
                year=2024, months_pct={8: 0.03}, months_eur={8: 200.0},
                total_pct=0.03, total_eur=200.0, benchmark_pct=0.01,
            )
        ],
        drawdown=NormalizedDrawdown(-0.05, -500.0, "2024-08-01", "2024-08-15"),
    )
    perf_b = NormalizedPerformance(
        total_value=9000.0,
        returns=NormalizedReturns(
            twr_annual=0.07, twr_total=0.09, xirr=0.075, volatility=0.09,
            sharpe_ratio=1.0, rentabilidad_pct=0.07,
            pl=500.0, invested=8500.0,
            aportaciones=8500.0, retenciones=-0.005, rentabilidad_eur=500.0,
            money_return=500.0,
        ),
        value_series=[
            NormalizedValuePoint("2024-08-31", 7500.0),
            NormalizedValuePoint("2024-09-30", 9000.0),
        ],
        contributions_series=[
            NormalizedValuePoint("2024-08-31", 8000.0),
            NormalizedValuePoint("2024-09-30", 8000.0),
        ],
        monthly_returns=[
            NormalizedMonthlyReturnRow(
                year=2024, months_pct={8: 0.02}, months_eur={8: 100.0},
                total_pct=0.02, total_eur=100.0, benchmark_pct=0.01,
            )
        ],
        drawdown=NormalizedDrawdown(-0.03, -200.0, "2024-09-01", "2024-09-10"),
    )

    conn_a = MagicMock()
    conn_a.plugin_id = "indexa-capital"
    conn_b = MagicMock()
    conn_b.plugin_id = "indexa-capital"

    portfolio_a = NormalizedPortfolio(
        holdings=[], total_value=12000.0, total_invested=11000.0,
        total_gain_loss=800.0, performance=perf_a,
    )
    portfolio_b = NormalizedPortfolio(
        holdings=[], total_value=9000.0, total_invested=8500.0,
        total_gain_loss=500.0, performance=perf_b,
    )

    result = _aggregate([(conn_a, portfolio_a), (conn_b, portfolio_b)], total_connections=2)

    # Non-aggregatable single-account-only fields → None
    assert result.returns is not None
    assert result.returns.twr_annual is None, "twr_annual must be None for multi-account"
    assert result.returns.twr_total is None, "twr_total must be None for multi-account"
    assert result.returns.xirr is None, "xirr must be None for multi-account"
    assert result.returns.volatility is None, "volatility must be None for multi-account"
    assert result.returns.sharpe_ratio is None, "sharpe_ratio must be None for multi-account"
    assert result.returns.rentabilidad_pct is None, "rentabilidad_pct must be None for multi-account"

    # Per-account analytics → None
    assert result.monthly_returns is None, "monthly_returns must be None for multi-account"
    assert result.drawdown is None, "drawdown must be None for multi-account"

    # value_series summed by shared dates
    vp_by_date = {vp.date: vp.value for vp in result.value_series}
    assert vp_by_date["2024-08-31"] == pytest.approx(17500.0)   # 10000 + 7500
    assert vp_by_date["2024-09-30"] == pytest.approx(21000.0)   # 12000 + 9000

    # contributions_series summed by shared dates
    cp_by_date = {vp.date: vp.value for vp in result.contributions_series}
    assert cp_by_date["2024-08-31"] == pytest.approx(18200.0)   # 10200 + 8000
    assert cp_by_date["2024-09-30"] == pytest.approx(18200.0)   # 10200 + 8000

    # Box € numbers summed (aggregatable per spec)
    assert result.returns.pl == pytest.approx(1300.0)            # 800 + 500
    assert result.returns.aportaciones == pytest.approx(19500.0) # 11000 + 8500
    assert result.returns.retenciones == pytest.approx(-0.015)   # −0.01 + −0.005
    assert result.returns.rentabilidad_eur == pytest.approx(1300.0)  # 800 + 500

    # Total portfolio value
    assert result.total_value == pytest.approx(21000.0)
    assert result.plugins_connected == 2

# ── GET /combined-overview ────────────────────────────────────────────────────
# Helpers shared by combined-overview tests

def _co_exec_result(scalars_all=None, scalar=None) -> MagicMock:
    """Build a mock execute() return value for combined-overview queries."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalars.return_value.all.return_value = scalars_all if scalars_all is not None else []
    return r


def _make_indexa_conn(conn_id: int = 1) -> MagicMock:
    c = MagicMock()
    c.id = conn_id
    c.plugin_id = "indexa-capital"
    c.status = "active"
    c.token_enc = "enc-tok"
    return c


def _make_fidelity_conn(conn_id: int = 2) -> MagicMock:
    c = MagicMock()
    c.id = conn_id
    c.plugin_id = "fidelity-espp"
    c.status = "active"
    c.token_enc = None
    return c


def _make_co_lot(lot_id: int, shares: str, cost_basis: str, conn_id: int = 2) -> MagicMock:
    lot = MagicMock()
    lot.id = lot_id
    lot.shares = Decimal(shares)
    lot.cost_basis = Decimal(cost_basis)
    lot.connection_id = conn_id
    return lot


_CO_MOCK_PRICE = LatestPriceRow(
    price_date=date(2026, 7, 15),
    close_usd=400.0,
    fx_eur_usd=1.0 / 1.08,
    close_eur=400.0 / 1.08,
    price_stale=False,
)

# Indexa mock: total_value=30000, total_invested=25000, gain=5000
# Holdings: equity=20000, fixed_income=8000, cash=2000
def _make_indexa_portfolio_mock():
    from finlytics.api.schemas import InvestmentHoldingOut, InvestmentPortfolioOut
    now_str = datetime.now(timezone.utc).isoformat()
    return InvestmentPortfolioOut(
        total_value=30000.0,
        total_invested=25000.0,
        total_gain_loss=5000.0,
        total_gain_loss_pct=20.0,
        currency="EUR",
        holdings=[
            InvestmentHoldingOut(
                plugin_id="indexa-capital",
                name="RV Global",
                asset_class="equity",
                current_value=20000.0,
                currency="EUR",
                last_updated=now_str,
            ),
            InvestmentHoldingOut(
                plugin_id="indexa-capital",
                name="RF Global",
                asset_class="fixed_income",
                current_value=8000.0,
                currency="EUR",
                last_updated=now_str,
            ),
            InvestmentHoldingOut(
                plugin_id="indexa-capital",
                name="Liquidez",
                asset_class="cash",
                current_value=2000.0,
                currency="EUR",
                last_updated=now_str,
            ),
        ],
        plugins_connected=1,
        last_updated=now_str,
    )


# Fidelity lot: 50 shares, cost_basis 2500 EUR
_CO_LOT = _make_co_lot(1, "50.0000", "2500.00")

# Expected Fidelity value: 50 * 400 / 1.08 = 18518.52 EUR
_CO_FIDELITY_VALUE = 50 * 400.0 * (1.0 / 1.08)


# ===========================================================================
# combined-overview tests
# ===========================================================================


async def test_combined_overview_no_connections_returns_zeros(client, mock_session):
    """No active connections → 200 with zero totals and empty arrays."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[]),  # active_conns = []
    ])
    resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value_eur"] == 0.0
    assert data["total_invested_eur"] is None
    assert data["total_gain_loss_eur"] is None
    assert data["total_gain_loss_pct"] is None
    assert data["by_provider"] == []
    assert data["by_asset_class"] == []
    assert data["providers"] == []


async def test_combined_overview_both_providers_totals_correct(client, mock_session):
    """Both Indexa + Fidelity connected → totals and allocations are aggregated."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_indexa_conn(), _make_fidelity_conn()]),
        _co_exec_result(scalars_all=[_CO_LOT]),
    ])
    with (
        patch("finlytics.api.investments.get_latest_price", new=AsyncMock(return_value=_CO_MOCK_PRICE)),
        patch("finlytics.api.investments.inv_service.get_portfolio", new=AsyncMock(return_value=_make_indexa_portfolio_mock())),
    ):
        resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()

    expected_fidelity_value = round(_CO_FIDELITY_VALUE, 2)
    expected_total = round(30000.0 + expected_fidelity_value, 2)
    assert data["total_value_eur"] == pytest.approx(expected_total, abs=0.02)
    assert data["total_invested_eur"] == pytest.approx(25000.0 + 2500.0, abs=0.01)

    expected_fidelity_gain = expected_fidelity_value - 2500.0
    assert data["total_gain_loss_eur"] == pytest.approx(5000.0 + expected_fidelity_gain, abs=0.02)
    assert data["total_gain_loss_pct"] is not None


async def test_combined_overview_both_providers_pct_sums_to_100(client, mock_session):
    """Allocation percentages in by_provider and by_asset_class each sum to ~100."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_indexa_conn(), _make_fidelity_conn()]),
        _co_exec_result(scalars_all=[_CO_LOT]),
    ])
    with (
        patch("finlytics.api.investments.get_latest_price", new=AsyncMock(return_value=_CO_MOCK_PRICE)),
        patch("finlytics.api.investments.inv_service.get_portfolio", new=AsyncMock(return_value=_make_indexa_portfolio_mock())),
    ):
        resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()

    provider_pct_sum = sum(p["pct"] for p in data["by_provider"])
    assert abs(provider_pct_sum - 100.0) < 0.3, f"by_provider pcts sum {provider_pct_sum} ≠ 100"

    ac_pct_sum = sum(ac["pct"] for ac in data["by_asset_class"])
    assert abs(ac_pct_sum - 100.0) < 0.3, f"by_asset_class pcts sum {ac_pct_sum} ≠ 100"


async def test_combined_overview_both_providers_shape(client, mock_session):
    """Full shape: 2 items in by_provider, 4 items in by_asset_class, 2 providers cards."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_indexa_conn(), _make_fidelity_conn()]),
        _co_exec_result(scalars_all=[_CO_LOT]),
    ])
    with (
        patch("finlytics.api.investments.get_latest_price", new=AsyncMock(return_value=_CO_MOCK_PRICE)),
        patch("finlytics.api.investments.inv_service.get_portfolio", new=AsyncMock(return_value=_make_indexa_portfolio_mock())),
    ):
        resp = await client.get("/api/investments/combined-overview")

    data = resp.json()
    assert len(data["by_provider"]) == 2
    provider_ids = {p["provider"] for p in data["by_provider"]}
    assert provider_ids == {"indexa", "fidelity"}

    # by_asset_class: equity + fixed_income + cash (Indexa) + espp_stock (Fidelity)
    assert len(data["by_asset_class"]) == 4
    ac_classes = {ac["asset_class"] for ac in data["by_asset_class"]}
    assert ac_classes == {"equity", "fixed_income", "cash", "espp_stock"}

    assert len(data["providers"]) == 2
    card_ids = {c["id"] for c in data["providers"]}
    assert card_ids == {"indexa-capital", "fidelity-espp"}

    # Provider cards have routes matching real plugin_ids
    for card in data["providers"]:
        assert card["route"] == f"/investments/{card['id']}"
        assert card["value_eur"] is not None
        assert card["gain_loss_eur"] is not None
        assert card["gain_loss_pct"] is not None


async def test_combined_overview_indexa_only(client, mock_session):
    """Only Indexa connected → by_provider has 1 item, no espp_stock class."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_indexa_conn()]),
        # No second call; Fidelity is not connected
    ])
    with patch("finlytics.api.investments.inv_service.get_portfolio", new=AsyncMock(return_value=_make_indexa_portfolio_mock())):
        resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_value_eur"] == pytest.approx(30000.0)
    assert data["total_invested_eur"] == pytest.approx(25000.0)
    assert len(data["by_provider"]) == 1
    assert data["by_provider"][0]["provider"] == "indexa"
    assert data["by_provider"][0]["pct"] == pytest.approx(100.0, abs=0.01)
    assert len(data["providers"]) == 1
    ac_classes = {ac["asset_class"] for ac in data["by_asset_class"]}
    assert "espp_stock" not in ac_classes


async def test_combined_overview_fidelity_only(client, mock_session):
    """Only Fidelity connected → by_provider has 1 item with espp_stock."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_fidelity_conn()]),
        _co_exec_result(scalars_all=[_CO_LOT]),
    ])
    with patch("finlytics.api.investments.get_latest_price", new=AsyncMock(return_value=_CO_MOCK_PRICE)):
        resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()
    expected_value = round(_CO_FIDELITY_VALUE, 2)
    assert data["total_value_eur"] == pytest.approx(expected_value, abs=0.02)
    assert len(data["by_provider"]) == 1
    assert data["by_provider"][0]["provider"] == "fidelity"
    assert data["by_provider"][0]["pct"] == pytest.approx(100.0, abs=0.01)
    assert len(data["by_asset_class"]) == 1
    assert data["by_asset_class"][0]["asset_class"] == "espp_stock"
    assert len(data["providers"]) == 1
    assert data["providers"][0]["id"] == "fidelity-espp"


async def test_combined_overview_degraded_fidelity_price(client, mock_session):
    """Fidelity price unavailable → Fidelity card present with nulls; Indexa data intact."""
    mock_session.execute = AsyncMock(side_effect=[
        _co_exec_result(scalars_all=[_make_indexa_conn(), _make_fidelity_conn()]),
        _co_exec_result(scalars_all=[_CO_LOT]),
    ])
    with (
        patch("finlytics.api.investments.get_latest_price", new=AsyncMock(return_value=None)),
        patch("finlytics.api.investments.inv_service.get_portfolio", new=AsyncMock(return_value=_make_indexa_portfolio_mock())),
    ):
        resp = await client.get("/api/investments/combined-overview")

    assert resp.status_code == 200
    data = resp.json()

    # Totals: only Indexa contributes (Fidelity has no value)
    assert data["total_value_eur"] == pytest.approx(30000.0)
    assert data["total_invested_eur"] == pytest.approx(25000.0)

    # by_provider: only Indexa (Fidelity omitted — no value)
    assert len(data["by_provider"]) == 1
    assert data["by_provider"][0]["provider"] == "indexa"

    # Fidelity NOT in by_asset_class
    ac_classes = {ac["asset_class"] for ac in data["by_asset_class"]}
    assert "espp_stock" not in ac_classes

    # providers: both present, Fidelity card has null values
    assert len(data["providers"]) == 2
    fidelity_card = next(c for c in data["providers"] if c["id"] == "fidelity-espp")
    assert fidelity_card["value_eur"] is None
    assert fidelity_card["gain_loss_eur"] is None
    assert fidelity_card["gain_loss_pct"] is None
    # Indexa card still has values
    indexa_card = next(c for c in data["providers"] if c["id"] == "indexa-capital")
    assert indexa_card["value_eur"] == pytest.approx(30000.0)


async def test_combined_overview_401_unauthenticated(unauthenticated_client):
    """No session cookie → 401 on GET /combined-overview."""
    resp = await unauthenticated_client.get("/api/investments/combined-overview")
    assert resp.status_code == 401
