"""Integration tests for the rules engine end-to-end — Wave 4 QA.

Covers cross-layer seams that existing unit tests leave unexercised.
Existing tests (NOT duplicated here):
  • apply_rules unit tests   (~50) in tests/extraction/test_rules.py
  • pre_match_rules units    (~50) in tests/extraction/test_prematch.py
  • Rules API CRUD           (~17) in tests/api/test_rules.py
  • Import wiring            (~10) in tests/api/test_imports.py

These tests go through the real FastAPI endpoints.
Only parse_statement, extract_transactions, and list_rules are patched.
pre_match_rules, apply_rules, and detect_statement_year run for real.

Scenarios covered:
  1. Mixed statement — matched line classified by rule, unmatched → LLM.
  2. All lines pre-matched — extract_transactions never called.
  3. Priority ordering — lower priority number wins end-to-end.
  4. Disabled rule — silently ignored; line falls through to LLM.
  5. Regex rule — matches end-to-end via pre_match_rules.
  6. Safety-net — description matches but line has no parseable date/amount;
       line is preserved for LLM, no partial tx emitted.
  7. Idempotency — rule-set merchant (apply_rules path) does not change
       the dedup hash; description is the stable identity field.
  8. add_tags merge — rule tags merged with LLM tags, case-insensitive dedup.
  9. Regression sanity — no-rules flows unaffected.
"""

from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.contracts import ExtractedTransaction
from finlytics.db.repository import compute_dedup_hash


# ── Rule factory ──────────────────────────────────────────────────────────────

def _rule(**overrides) -> SimpleNamespace:
    """Return a minimal SimpleNamespace satisfying RuleProtocol."""
    defaults = dict(
        id=1,
        name="Hipoteca",
        priority=100,
        enabled=True,
        description_mode="contains",
        description_value="hipoteca",
        amount_sign=None,
        amount_min=None,
        amount_max=None,
        account_ref=None,
        currency=None,
        set_category="Housing",
        set_merchant=None,
        add_tags=[],
        skip_ai=True,
        detail_mode=None,
        detail_value=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── BBVA-format statement fixtures ───────────────────────────────────────────
# Lines satisfy _EURO_STMT_LINE_RE in prematch.py:
#   DD/MM/YYYY + spaces + description + ≥2-space separator + signed-amount
# Synthetic data only — no real personal data.

_LINE_HIPOTECA = "02/05/2026   PAGO HIPOTECA BANCO SANTANDER   -800,00   1.200,00"
_LINE_MERCADONA = "03/05/2026   COMPRA EN MERCADONA CAMPANAR   -45,30   1.154,70"
_LINE_HIPOTECO = "04/05/2026   PAGO HIPOTECO VARIABLE   -600,00   600,00"  # "O" for regex
_MIXED_STMT = f"{_LINE_HIPOTECA}\n{_LINE_MERCADONA}"


def _mercadona_tx() -> ExtractedTransaction:
    """Simulate what the LLM returns for the MERCADONA line."""
    return ExtractedTransaction(
        transaction_date=date(2026, 5, 3),
        amount=Decimal("-45.30"),
        currency="EUR",
        description="COMPRA EN MERCADONA CAMPANAR",
        category="Groceries",
        account_ref="BBVA",
    )


# ── Scenario 1: Full E2E, mixed statement ────────────────────────────────────

async def test_e2e_prematch_rule_classifies_matched_line_unmatched_to_llm(client_with_llm):
    """Full E2E: real pre_match_rules processes BBVA-format text.

    The hipoteca line is pre-matched and classified by the rule
    (category="Housing", category_confidence=1.0, matched_rule_name set,
    rule tags applied).  The mercadona line is NOT matched — it reaches
    extract_transactions, and only that line is in the LLM input.
    """
    client, _ = client_with_llm
    rule = _rule(set_merchant="Banco Santander", add_tags=["hipoteca", "fijo"])
    mock_extract = AsyncMock(return_value=[_mercadona_tx()])

    with (
        patch("finlytics.api.imports.parse_statement", return_value=_MIXED_STMT),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[rule]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    txs = resp.json()["transactions"]
    assert len(txs) == 2

    # Pre-matched tx: rule applied via pre_match_rules
    hip = next(t for t in txs if t.get("matched_rule_id") == 1)
    assert hip["category"] == "Housing"
    assert hip["category_confidence"] == 1.0
    assert hip["matched_rule_name"] == "Hipoteca"
    assert "hipoteca" in hip["tags"]
    assert "fijo" in hip["tags"]

    # Unmatched tx: LLM result, untouched by any rule
    grocery = next(t for t in txs if t["matched_rule_id"] is None)
    assert grocery["category"] == "Groceries"
    assert grocery["matched_rule_name"] is None

    # extract_transactions received ONLY the unmatched line — hipoteca line stripped
    mock_extract.assert_called_once()
    llm_input: str = mock_extract.call_args[0][0]
    assert "MERCADONA" in llm_input
    assert "HIPOTECA" not in llm_input.upper()


# ── Scenario 2: All lines pre-matched, LLM never called ──────────────────────

async def test_e2e_all_lines_prematch_llm_never_called(client_with_llm):
    """When every statement line is pre-matched, extract_transactions is never called."""
    client, _ = client_with_llm
    rule = _rule()
    mock_extract = AsyncMock(return_value=[])

    with (
        patch("finlytics.api.imports.parse_statement", return_value=_LINE_HIPOTECA),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[rule]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    txs = resp.json()["transactions"]
    assert len(txs) == 1
    assert txs[0]["matched_rule_id"] == 1
    assert txs[0]["category"] == "Housing"
    assert txs[0]["category_confidence"] == 1.0
    mock_extract.assert_not_called()


# ── Scenario 3: Priority ordering ─────────────────────────────────────────────

async def test_e2e_priority_lower_number_wins(client_with_llm):
    """Two rules both matching the same line: lower priority number wins end-to-end.

    list_rules returns them in reverse-priority order to confirm that
    pre_match_rules sorts by (priority, id) ascending regardless of input order.
    """
    client, _ = client_with_llm
    rule_a = _rule(id=1, priority=5,  name="Primary Housing", set_category="Housing")
    rule_b = _rule(id=2, priority=50, name="Debt",            set_category="Debt")
    mock_extract = AsyncMock(return_value=[])

    # Deliberately return rules out of priority order to test that sorting is applied
    with (
        patch("finlytics.api.imports.parse_statement", return_value=_LINE_HIPOTECA),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock,
              return_value=[rule_b, rule_a]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    txs = resp.json()["transactions"]
    assert len(txs) == 1
    assert txs[0]["category"] == "Housing"            # rule_a (priority=5) wins
    assert txs[0]["matched_rule_name"] == "Primary Housing"
    mock_extract.assert_not_called()


# ── Scenario 4: Disabled rule is ignored ─────────────────────────────────────

async def test_e2e_disabled_rule_is_ignored(client_with_llm):
    """A disabled rule is silently skipped; its matching lines fall through to the LLM."""
    client, _ = client_with_llm
    disabled_rule = _rule(enabled=False)
    # LLM returns something for the hipoteca line since the rule didn't pre-match it
    mock_extract = AsyncMock(return_value=[_mercadona_tx()])

    with (
        patch("finlytics.api.imports.parse_statement", return_value=_LINE_HIPOTECA),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock,
              return_value=[disabled_rule]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    # Hipoteca line NOT pre-matched → LLM received it
    mock_extract.assert_called_once()
    llm_input: str = mock_extract.call_args[0][0]
    assert "HIPOTECA" in llm_input.upper()

    # No tx has a matched_rule_id (rule was disabled, apply_rules skips disabled rules)
    for tx in resp.json()["transactions"]:
        assert tx["matched_rule_id"] is None


# ── Scenario 5: Regex rule matches end-to-end ────────────────────────────────

async def test_e2e_regex_rule_matches_end_to_end(client_with_llm):
    """Regex rule HIPOTEC[AO] pre-matches the 'HIPOTECO' line end-to-end.

    A plain 'contains' rule for 'hipoteca' would NOT match 'HIPOTECO' — only a
    regex can match both variants.  This confirms the regex evaluation path works
    across the full pipeline.
    """
    client, _ = client_with_llm
    regex_rule = _rule(
        description_mode="regex",
        description_value=r"HIPOTEC[AO]",
        set_category="Housing",
    )
    mock_extract = AsyncMock(return_value=[])

    with (
        patch("finlytics.api.imports.parse_statement", return_value=_LINE_HIPOTECO),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock,
              return_value=[regex_rule]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    txs = resp.json()["transactions"]
    assert len(txs) == 1
    assert txs[0]["category"] == "Housing"
    assert txs[0]["matched_rule_id"] == 1
    assert txs[0]["category_confidence"] == 1.0
    mock_extract.assert_not_called()  # all lines pre-matched


# ── Scenario 6: Safety-net — unparseable line preserved for LLM ──────────────

async def test_e2e_safety_net_unparseable_line_falls_through_to_llm(client_with_llm):
    """Safety net: line whose description matches the rule but has no DD/MM/YYYY prefix.

    pre_match_rules detects the description match, finds the line is not
    parseable as a transaction (extractor returns None), logs a WARNING, and
    leaves the line in remaining_text unchanged.  No partial transaction is
    emitted; the LLM processes the line normally.
    """
    client, _ = client_with_llm
    rule = _rule(set_category="Housing")

    # No date prefix → _EURO_STMT_LINE_RE will not match from '^'
    header_line = "HIPOTECA BANCO SANTANDER: RESUMEN MENSUAL   -800,00"
    mock_extract = AsyncMock(return_value=[])

    with (
        patch("finlytics.api.imports.parse_statement", return_value=header_line),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[rule]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    # Safety net fired — no pre-matched tx at all
    assert resp.json()["transactions"] == []

    # LLM was called with the unparseable line (it was NOT silently dropped)
    mock_extract.assert_called_once()
    llm_input: str = mock_extract.call_args[0][0]
    assert "HIPOTECA" in llm_input.upper()


# ── Scenario 7: Idempotency — rule merchant does not change dedup hash ────────

async def test_e2e_idempotency_rule_set_merchant_does_not_change_dedup_hash(client_with_llm):
    """Rule sets merchant via apply_rules (post-LLM); description stays unchanged.

    compute_dedup_hash uses (account_ref, date, amount, description) — NOT
    merchant.  Re-importing the same statement always produces the same hash
    even when a rule sets a friendly merchant name.
    """
    client, _ = client_with_llm

    original_description = "PAGO HIPOTECA BANCO SANTANDER"
    rule_merchant = "Banco Santander"

    llm_tx = ExtractedTransaction(
        transaction_date=date(2026, 5, 2),
        amount=Decimal("-800.00"),
        currency="EUR",
        description=original_description,
        category="Otros",
        account_ref="BBVA",
    )

    # Rule matches post-LLM (apply_rules) because the plain text statement won't
    # pre-match (no DD/MM/YYYY date on the statement text itself).
    rule = _rule(
        set_merchant=rule_merchant,
        set_category="Housing",
        description_mode="contains",
        description_value="hipoteca",
    )

    # Non-parseable statement text → pre_match_rules produces no matches → full LLM path
    non_bbva_text = "MOVIMIENTOS DE MAYO 2026"

    fake_account = MagicMock()
    fake_account.id = 1
    fake_account.name = "BBVA"
    fake_import_run = MagicMock()
    fake_import_run.id = 42

    captured: list[ExtractedTransaction] = []

    async def _capture_upsert(session, import_run, transactions, **kw):
        captured.extend(transactions)
        return (1, 0)

    with (
        patch("finlytics.api.imports.parse_statement", return_value=non_bbva_text),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[rule]),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=[llm_tx]),
        patch("finlytics.api.imports._resolve_account", new_callable=AsyncMock,
              return_value=fake_account),
        patch("finlytics.api.imports.upsert_transactions", side_effect=_capture_upsert),
        patch("finlytics.api.imports.ImportRun", return_value=fake_import_run),
    ):
        resp = await client.post(
            "/api/imports",
            files={"file": ("stmt.pdf", io.BytesIO(b"x"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 201
    assert len(captured) == 1
    persisted = captured[0]

    # Rule changed merchant but description is the original LLM value
    assert persisted.merchant == rule_merchant
    assert persisted.description == original_description

    # Dedup hash is stable: same description → same hash with or without the rule
    hash_with_rule = compute_dedup_hash(
        account_ref=persisted.account_ref,
        transaction_date=persisted.transaction_date,
        amount=persisted.amount,
        description=persisted.description,
    )
    hash_without_rule = compute_dedup_hash(
        account_ref="BBVA",
        transaction_date=date(2026, 5, 2),
        amount=Decimal("-800.00"),
        description=original_description,
    )
    assert hash_with_rule == hash_without_rule

    # Sanity: if merchant were used as description, the hash would differ
    hash_if_merchant_used = compute_dedup_hash(
        account_ref="BBVA",
        transaction_date=date(2026, 5, 2),
        amount=Decimal("-800.00"),
        description=rule_merchant,
    )
    assert hash_with_rule != hash_if_merchant_used


# ── Scenario 8: add_tags merge end-to-end ────────────────────────────────────

async def test_e2e_add_tags_merge_with_llm_tags_deduped(client_with_llm):
    """Rule tags are merged with LLM-returned tags; case-insensitive duplicates dropped.

    LLM returns tags=["alimentacion"].
    Rule add_tags=["supermercado", "ALIMENTACION"].
    Expected merged result: ["alimentacion", "supermercado"]
      — "ALIMENTACION" is a case-insensitive duplicate of "alimentacion" and is dropped.
    """
    client, _ = client_with_llm

    llm_tx = ExtractedTransaction(
        transaction_date=date(2026, 5, 3),
        amount=Decimal("-45.30"),
        currency="EUR",
        description="COMPRA EN MERCADONA",
        category="Groceries",
        account_ref="BBVA",
        tags=["alimentacion"],
    )

    # set_category=None → pre_match_rules skips this rule (requires a category to
    # produce a complete tx); apply_rules still runs it post-LLM for tag merging.
    rule = _rule(
        description_mode="contains",
        description_value="mercadona",
        set_category=None,
        add_tags=["supermercado", "ALIMENTACION"],
        skip_ai=False,
    )

    with (
        patch("finlytics.api.imports.parse_statement", return_value="MOVIMIENTOS"),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[rule]),
        patch("finlytics.api.imports.extract_transactions", new_callable=AsyncMock,
              return_value=[llm_tx]),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    txs = resp.json()["transactions"]
    assert len(txs) == 1

    tx_tags = txs[0]["tags"]
    assert "alimentacion" in tx_tags        # LLM original preserved
    assert "supermercado" in tx_tags        # Rule tag appended
    assert "ALIMENTACION" not in tx_tags    # Case-insensitive duplicate dropped
    assert len(tx_tags) == 2               # No extras

    # Category unchanged (set_category=None in rule)
    assert txs[0]["category"] == "Groceries"
    # Rule still stamped the match
    assert txs[0]["matched_rule_id"] == 1


# ── Scenario 9: Regression sanity ────────────────────────────────────────────

async def test_e2e_regression_no_rules_preview_unaffected(client_with_llm):
    """No rules → existing preview flow is completely unaffected.

    apply_rules and pre_match_rules are no-ops with an empty rule list.
    All transactions come from the LLM unchanged, matched_rule_id stays null.
    """
    client, _ = client_with_llm
    extracted = [_mercadona_tx()]
    mock_extract = AsyncMock(return_value=extracted)

    with (
        patch("finlytics.api.imports.parse_statement", return_value="STATEMENT TEXT"),
        patch("finlytics.api.imports.list_rules", new_callable=AsyncMock, return_value=[]),
        patch("finlytics.api.imports.extract_transactions", mock_extract),
    ):
        resp = await client.post(
            "/api/imports/preview",
            files={"file": ("bank.pdf", io.BytesIO(b"fake"), "application/pdf")},
            data={"account_name": "BBVA"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["transactions"]) == 1

    tx = body["transactions"][0]
    assert tx["category"] == "Groceries"
    assert tx["matched_rule_id"] is None
    assert tx["matched_rule_name"] is None

    # LLM received the full, unmodified statement text
    mock_extract.assert_called_once()
    assert mock_extract.call_args[0][0] == "STATEMENT TEXT"
