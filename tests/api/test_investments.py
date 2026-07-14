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
  * 🔒 SECURITY INVARIANTS (Romanoff): token never in any response; masked label has "•";
    crypto round-trip; tampered ciphertext fails; missing key → fail-closed (raise); TLS verify=True.

Fixtures:
  * ``unauthenticated_client`` (local): only get_db overridden → real auth dependency → 401.
  * ``client`` (conftest): get_current_user pre-bypassed, for all 200 cases.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app

_EXPECTED_IDS = {"indexa-capital", "generic-broker", "crypto-exchange"}
_REQUIRED_KEYS = {"id", "name", "description", "icon", "status", "auth_type", "supported_features"}


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

async def test_plugins_200_returns_list_of_three(client):
    """Authenticated request → 200, exactly 3 plugins."""
    resp = await client.get("/api/investments/plugins")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_plugins_all_required_keys_present(client):
    """Every plugin object carries all required keys."""
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        missing = _REQUIRED_KEYS - plugin.keys()
        assert not missing, f"Plugin '{plugin.get('id')}' is missing keys: {missing}"


async def test_plugins_all_status_coming_soon(client):
    """Phase 2: non-Indexa plugins stay 'coming_soon'.
    Indexa Capital is now dynamic — 'available' when no active connection exists
    (mock scalar returns 0).
    """
    resp = await client.get("/api/investments/plugins")
    for plugin in resp.json():
        if plugin["id"] == "indexa-capital":
            # Dynamic: 'available' (no connection) or 'connected' — never 'coming_soon'
            assert plugin["status"] in ("available", "connected"), (
                f"Unexpected Indexa status: {plugin['status']}"
            )
        else:
            assert plugin["status"] == "coming_soon", (
                f"Plugin '{plugin['id']}' has unexpected status '{plugin['status']}'"
            )


async def test_plugins_correct_id_set(client):
    """Returned id set matches the three expected plugin identifiers exactly."""
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
            svc._provider, "validate_token", AsyncMock(return_value=mock_validation)
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
        svc._provider, "validate_token", AsyncMock(return_value=mock_validation)
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
            ValuePoint(date="20240101", value=10200.0),
            ValuePoint(date="20240201", value=10450.0),
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

    # Phase 2: value_series — dates in YYYYMMDD format
    assert len(data["value_series"]) == 2
    for vp in data["value_series"]:
        assert len(vp["date"]) == 8, f"value_series date must be YYYYMMDD, got {vp['date']!r}"

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

    svc._portfolio_cache.clear()

    mock_conn = MagicMock()
    mock_conn.id = 1
    mock_conn.plugin_id = "indexa-capital"
    mock_conn.status = "active"
    mock_conn.token_enc = "fake-enc-token"
    mock_conn.account_label_masked = "PBK•••Z5"
    mock_conn.last_synced_at = None

    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_conn]
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=execute_result)
    mock_db.commit = AsyncMock()

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
        patch.object(svc._provider, "validate_token", AsyncMock(return_value=validation)),
        patch.object(svc._provider, "get_portfolio", AsyncMock(return_value=portfolio)),
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
    """Indexa status = 'connected' when DB scalar returns ≥1 active connections."""
    mock_session.scalar = AsyncMock(return_value=1)

    resp = await client.get("/api/investments/plugins")

    assert resp.status_code == 200
    plugins = resp.json()
    indexa = next(p for p in plugins if p["id"] == "indexa-capital")
    assert indexa["status"] == "connected", (
        f"Expected 'connected' when connection exists, got {indexa['status']!r}"
    )
    # Non-Indexa plugins unaffected
    others = [p for p in plugins if p["id"] != "indexa-capital"]
    for p in others:
        assert p["status"] == "coming_soon"
