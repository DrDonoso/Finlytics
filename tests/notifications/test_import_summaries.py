from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from finlytics.api.deps import get_current_user, get_db
from finlytics.app import app
from finlytics.assistant import settings as usage_queries
from finlytics.assistant.limits import message_limiters
from finlytics.config import settings
from finlytics.db.models import (
    Account,
    AssistantSettings,
    Base,
    Category,
    EuriborRate,
    ImportRun,
    ImportSummaryAttempt,
    ImportSummaryJob,
    ImportSummarySettings,
    Mortgage,
    MortgageRatePeriod,
    NotificationChannel,
    Transaction,
    User,
)
from finlytics.db.queries import import_summaries as queries
from finlytics.db.queries.summaries import compare_amounts
from finlytics.extraction.llm_client import LLMError, TextDelta, UsageReported
from finlytics.investments.crypto import encrypt_token
from finlytics.notifications import import_summaries as service
from finlytics.notifications.import_summary_prompt import (
    analysis_messages,
    render_import_summary,
    telegram_units,
)
from finlytics.notifications.telegram import TelegramError


class FakeLLM:
    def __init__(self):
        self.calls = []
        self.error = None
        self.report_usage = True

    async def stream_with_tools(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        yield TextDelta("Spending is concentrated in groceries.")
        if self.report_usage:
            yield UsageReported(prompt_tokens=40, completion_tokens=20, total_tokens=60)
        if self.error is not None:
            raise self.error

    async def close(self):
        pass


@pytest.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "async_session_factory", sessions)
    monkeypatch.setattr(settings, "finlytics_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "openai_api_key", "test-placeholder")
    monkeypatch.setattr(settings, "openai_base_url", "https://example.invalid/v1")
    monkeypatch.setattr(settings, "openai_model", "test-model")
    llm = FakeLLM()
    monkeypatch.setattr(service.LLMClient, "from_settings", lambda *_a, **_kw: llm)
    send = AsyncMock()
    monkeypatch.setattr(service, "telegram_send_message", send)
    message_limiters.clear()
    async with sessions() as db, db.begin():
        db.add_all([
            User(id=1, username="owner", password_hash="test"),
            User(id=2, username="other", password_hash="test"),
            Account(id=1, name="Checking", type="bank", currency="EUR"),
            Category(id=1, name="Groceries", is_base=True),
        ])
        await db.flush()
        db.add_all([
            ImportRun(id=1, account_id=1, source_filename="june.pdf", num_inserted=3, num_duplicates=1),
            ImportRun(id=2, account_id=1, source_filename="may.pdf", num_inserted=2),
            NotificationChannel(
                id=1, user_id=1, channel="telegram", enabled=True, label="Telegram test",
                config_enc=encrypt_token(json.dumps({
                    "bot_token": "test:placeholder", "chat_id": "-10012345", "message_thread_id": 42,
                })),
            ),
        ])
        await db.flush()
        db.add(ImportSummarySettings(user_id=1, enabled=True, channel_id=1, language="en"))
        for id_, month, day, amount, system in [
            (1, 6, 1, "-40", False), (2, 6, 30, "-60", False),
            (3, 6, 10, "2000", False), (4, 6, 1, "9000", True),
            (5, 5, 1, "-100", False), (6, 5, 31, "-100", False),
        ]:
            db.add(Transaction(
                id=id_, account_id=1, import_run_id=1 if month == 6 else 2,
                transaction_date=date(2026, month, day), amount=Decimal(amount),
                currency="EUR", description="Synthetic transaction", category_id=1,
                dedup_hash=f"test-{id_}", is_system=system,
            ))
    yield SimpleNamespace(sessions=sessions, llm=llm, send=send)
    message_limiters.clear()
    await engine.dispose()


async def enqueue(env, *, inserted=3, dates=None):
    async with env.sessions() as db, db.begin():
        return await queries.enqueue_import_summary(
            db, user_id=1, import_run_id=1, account=await db.get(Account, 1),
            dates=dates if dates is not None else [date(2026, 6, 1), date(2026, 6, 30)],
            num_inserted=inserted,
        )


async def stored(env, job_id):
    async with env.sessions() as db:
        return await db.get(ImportSummaryJob, job_id)


async def make_due(env, job_id):
    async with env.sessions() as db, db.begin():
        await db.execute(update(ImportSummaryJob).where(ImportSummaryJob.id == job_id).values(
            next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        ))


async def seed_mortgage(env, *, user_id=1, account_id=1, category_id=2, variable=False):
    async with env.sessions() as db, db.begin():
        if await db.get(Category, 2) is None:
            db.add(Category(id=2, name="Housing", is_base=True))
        mortgage = Mortgage(
            user_id=user_id, name=f"Mortgage {user_id}", initial_principal=Decimal("216000"),
            start_date=date(2026, 5, 31), term_months=240, payment_day=31,
            rate_type="variable" if variable else "fixed",
            linked_account_id=account_id, linked_category_id=category_id,
            rate_periods=[MortgageRatePeriod(
                start_month=0, kind="variable" if variable else "fixed",
                fixed_rate=None if variable else Decimal("0"),
                index_name="euribor_12m" if variable else None,
                spread=Decimal("0") if variable else None, review_months=12,
            )],
            bonuses=[], prepayments=[],
        )
        db.add(mortgage)
        await db.flush()
        return mortgage.id


async def seed_mortgage_charges(env, *, late_date=date(2026, 6, 1), amount="-900", account_id=1):
    async with env.sessions() as db, db.begin():
        run_id = 1 if account_id == 1 else 3
        if await db.get(ImportRun, run_id) is None:
            db.add(ImportRun(id=run_id, account_id=account_id, source_filename="mortgage.pdf"))
        for id_, charged_on in [(100, late_date), (101, date(2026, 6, 30))]:
            db.add(Transaction(
                id=id_, account_id=account_id, import_run_id=run_id, transaction_date=charged_on,
                amount=Decimal(amount), currency="EUR", description="Mortgage charge",
                category_id=2, dedup_hash=f"mortgage-{id_}", is_system=False,
            ))


async def facts_for(env, job_id):
    async with env.sessions() as db:
        return await queries.get_import_summary_facts(db, await db.get(ImportSummaryJob, job_id))


async def test_two_june_charges_are_assigned_to_may_and_june_without_moving_cash(env):
    await seed_mortgage(env)
    await seed_mortgage_charges(env)
    job_id = await enqueue(env)
    facts = await facts_for(env, job_id)
    matches = facts["mortgage_payments"]["matches"]
    assert [(match["charged_date"], match["due_date"]) for match in matches] == [
        ("2026-06-01", "2026-05-31"), ("2026-06-30", "2026-06-30"),
    ]
    assert all(match["timing_supported"] for match in matches)
    assert len({match["transaction_id"] for match in matches}) == 2
    assert facts["current"]["total_expense"] == 1900
    assert facts["previous"]["total_expense"] == 200
    await service.process_next_summary()
    sent_facts = json.loads(env.llm.calls[0][0][1]["content"])
    assert sent_facts["mortgage_payments"]["matches"] == matches
    assert "NEVER move those amounts" in env.llm.calls[0][0][0]["content"]


@pytest.mark.parametrize("language", ["es", "en"])
async def test_timing_explanation_is_rendered_but_generic_footer_is_not(env, language):
    await seed_mortgage(env)
    await seed_mortgage_charges(env)
    facts = await facts_for(env, await enqueue(env))
    text = render_import_summary(facts, "Specific analysis.", language)
    assert "2026-06-01" in text and "2026-05-31" in text
    assert ("conciliado" if language == "es" else "matched") in text
    assert "Basado solo en" not in text
    assert "Based only on" not in text
    assert text.index("Specific analysis.") < text.index(
        "conciliado" if language == "es" else "matched"
    )
    long_text = render_import_summary(facts, "\U0001f4b0" * 5000, language)
    assert telegram_units(long_text) <= 4096
    assert ("conciliado" if language == "es" else "matched") in long_text
    assert "Basado solo en" not in long_text and "Based only on" not in long_text


@pytest.mark.parametrize("category_only", [False, True])
async def test_only_the_users_linked_mortgage_is_considered(env, category_only):
    await seed_mortgage(env, user_id=2)
    assert (await facts_for(env, await enqueue(env)))["mortgage_payments"]["matches"] == []
    own_id = await seed_mortgage(env, account_id=None if category_only else 1)
    await seed_mortgage_charges(env)
    async with env.sessions() as db:
        job_id = await db.scalar(select(ImportSummaryJob.id))
    context = (await facts_for(env, job_id))["mortgage_payments"]
    assert {match["mortgage_id"] for match in context["matches"]} == {own_id}
    assert all(match["timing_supported"] for match in context["matches"])


async def test_category_only_matching_does_not_leak_another_accounts_charges(env):
    async with env.sessions() as db, db.begin():
        db.add(Account(id=2, name="Other checking", type="bank", currency="EUR"))
    await seed_mortgage(env, account_id=None)
    await seed_mortgage_charges(env, account_id=2)
    context = (await facts_for(env, await enqueue(env)))["mortgage_payments"]
    assert context["matches"] == []


async def test_amount_mismatches_are_not_used_as_certain_timing_explanations(env):
    await seed_mortgage(env)
    await seed_mortgage_charges(env, amount="-950")
    facts = await facts_for(env, await enqueue(env))
    assert facts["mortgage_payments"]["matches"]
    assert all(not match["timing_supported"] for match in facts["mortgage_payments"]["matches"])
    assert "conciliado" not in render_import_summary(facts, "Analysis.", "es")


async def test_overlapping_mortgage_links_do_not_claim_the_same_charge_twice_as_certain(env):
    await seed_mortgage(env)
    await seed_mortgage(env)
    await seed_mortgage_charges(env)
    facts = await facts_for(env, await enqueue(env))
    assert len(facts["mortgage_payments"]["matches"]) == 4
    assert all(not match["timing_supported"] for match in facts["mortgage_payments"]["matches"])
    assert "conciliado" not in render_import_summary(facts, "Analysis.", "es")


async def test_a_late_charge_outside_the_matching_window_is_not_reassigned(env):
    await seed_mortgage(env)
    await seed_mortgage_charges(env, late_date=date(2026, 6, 15))
    facts = await facts_for(env, await enqueue(env))
    matches = facts["mortgage_payments"]["matches"]
    assert [(match["charged_date"], match["due_date"]) for match in matches] == [
        ("2026-06-30", "2026-06-30"),
    ]
    assert facts["current"]["total_expense"] == 1900
    assert "conciliado" not in render_import_summary(facts, "Analysis.", "es")


async def test_a_charge_outside_the_current_month_explains_timing_without_entering_its_total(env):
    await seed_mortgage(env)
    await seed_mortgage_charges(env, late_date=date(2026, 5, 31))
    async with env.sessions() as db, db.begin():
        (await db.get(Transaction, 101)).transaction_date = date(2026, 7, 1)
    facts = await facts_for(env, await enqueue(env))
    assert facts["current"]["total_expense"] == 100
    text = render_import_summary(facts, "Analysis.", "en")
    assert "Expenses: 100.00 EUR" in text
    assert "charge on 2026-07-01" in text and "due on 2026-06-30" in text


def test_equally_plausible_charges_are_marked_ambiguous():
    from finlytics.mortgage.service import ChargeMatcher

    matcher = ChargeMatcher([
        (date(2026, 5, 30), Decimal("900")), (date(2026, 6, 1), Decimal("900")),
    ])
    assert matcher.match(date(2026, 5, 31), Decimal("900")) == Decimal("900")
    assert matcher.last_match_ambiguous


async def test_missing_cached_index_is_explicit_and_does_not_fetch_or_assume_zero(env, monkeypatch):
    from finlytics.mortgage import service as mortgage_service

    fetch = AsyncMock(side_effect=AssertionError("A summary must not fetch ECB data"))
    monkeypatch.setattr(mortgage_service, "ensure_series", fetch)
    await seed_mortgage(env, variable=True)
    await seed_mortgage_charges(env)
    facts = await facts_for(env, await enqueue(env))
    assert facts["mortgage_payments"] == {
        "matches": [], "unavailable": ["Mortgage 1"], "truncated": False,
    }
    assert facts["current"]["total_expense"] == 1900
    fetch.assert_not_called()


async def test_cached_variable_rate_can_support_the_same_timing_match(env):
    await seed_mortgage(env, variable=True)
    await seed_mortgage_charges(env)
    async with env.sessions() as db, db.begin():
        db.add(EuriborRate(index_name="euribor_12m", period=date(2026, 3, 1), rate=Decimal("0")))
    facts = await facts_for(env, await enqueue(env))
    assert len(facts["mortgage_payments"]["matches"]) == 2
    assert all(match["timing_supported"] for match in facts["mortgage_payments"]["matches"])


async def test_mortgage_context_reports_truncation(env, monkeypatch):
    from finlytics.mortgage import service as mortgage_service

    await seed_mortgage(env)
    await seed_mortgage_charges(env)
    monkeypatch.setattr(mortgage_service, "_MAX_SUMMARY_PAYMENT_MATCHES", 1)
    context = (await facts_for(env, await enqueue(env)))["mortgage_payments"]
    assert len(context["matches"]) == 1
    assert context["matches"][0]["cross_month"]
    assert context["truncated"] is True


async def test_generate_then_send_only_the_selected_destination(env):
    job_id = await enqueue(env)
    assert not env.llm.calls
    env.send.assert_not_called()
    assert await service.process_next_summary()
    job = await stored(env, job_id)
    assert job.status == "ready"
    assert "Income: 2,000.00 EUR" in job.message_text
    assert "Expenses: 100.00 EUR" in job.message_text
    assert "9,000" not in job.message_text
    assert "2026-05-01 - 2026-05-31" in job.message_text
    assert await service.process_next_summary()
    assert (await stored(env, job_id)).status == "sent"
    assert not await service.process_next_summary()
    assert len(env.llm.calls) == 1
    env.send.assert_awaited_once_with(
        "test:placeholder", "-10012345", job.message_text, message_thread_id=42,
    )
    async with env.sessions() as db:
        assert await usage_queries.tokens_used_since(db, 1, datetime(2000, 1, 1, tzinfo=UTC)) == 60
        totals = await usage_queries.usage_totals(db, 1)
        assert (totals.messages, totals.summaries, totals.total_tokens) == (0, 1, 60)


@pytest.mark.parametrize("inserted,dates", [(0, None), (3, [])])
async def test_duplicate_only_or_empty_imports_do_not_enqueue(env, inserted, dates):
    assert await enqueue(env, inserted=inserted, dates=dates) is None
    assert not await service.process_next_summary()


async def test_disabled_feature_does_not_enqueue(env):
    async with env.sessions() as db, db.begin():
        (await db.get(ImportSummarySettings, 1)).enabled = False
    assert await enqueue(env) is None


async def test_retries_reuse_analysis_and_stop_after_three_sends(env):
    job_id = await enqueue(env)
    await service.process_next_summary()
    env.send.side_effect = TelegramError("temporary", retryable=True)
    for _ in range(3):
        await make_due(env, job_id)
        await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.delivery_attempts) == ("failed", 3)
    assert len(env.llm.calls) == 1
    assert env.send.await_count == 3
    assert not await service.process_next_summary()


async def test_uncertain_send_requires_acknowledgement_and_keeps_the_text(env):
    job_id = await enqueue(env)
    await service.process_next_summary()
    env.send.side_effect = TelegramError("unknown", uncertain=True)
    await service.process_next_summary()
    assert (await stored(env, job_id)).status == "uncertain"
    assert not await service.process_next_summary()
    async with env.sessions() as db, db.begin():
        with pytest.raises(queries.SummaryConflictError, match="Acknowledge"):
            await queries.retry_summary(db, 1, job_id, acknowledge_uncertain=False)
    async with env.sessions() as db, db.begin():
        await queries.retry_summary(db, 1, job_id, acknowledge_uncertain=True)
    env.send.side_effect = None
    await service.process_next_summary()
    assert (await stored(env, job_id)).status == "sent"
    assert len(env.llm.calls) == 1


async def test_generation_failures_are_billed_and_the_shared_budget_stops_retry(env):
    job_id = await enqueue(env)
    env.llm.error = LLMError("temporary")
    await service.process_next_summary()
    assert (await stored(env, job_id)).status == "pending"
    async with env.sessions() as db, db.begin():
        db.add(AssistantSettings(user_id=1, monthly_token_budget=50))
        assert await usage_queries.tokens_used_since(db, 1, datetime(2000, 1, 1, tzinfo=UTC)) == 60
    await make_due(env, job_id)
    await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.error) == ("blocked", "token_budget")
    assert len(env.llm.calls) == 1
    env.send.assert_not_called()


async def test_generation_retries_are_bounded_and_each_attempt_is_recorded(env):
    job_id = await enqueue(env)
    env.llm.error = LLMError("temporary")
    for _ in range(3):
        await make_due(env, job_id)
        await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.generation_attempts) == ("failed", 3)
    assert not await service.process_next_summary()
    async with env.sessions() as db:
        attempts = (await db.scalars(select(ImportSummaryAttempt))).all()
        assert len(attempts) == 3
        assert sum(attempt.total_tokens for attempt in attempts) == 180


async def test_runtime_configuration_failure_does_not_call_ai(env, monkeypatch):
    job_id = await enqueue(env)
    monkeypatch.setattr(settings, "openai_model", "")
    await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.error) == ("blocked", "ai_not_configured")
    assert not env.llm.calls
    async with env.sessions() as db:
        assert list((await db.scalars(select(ImportSummaryAttempt))).all()) == []


async def test_changing_the_destination_cancels_instead_of_redirecting_a_ready_summary(env):
    job_id = await enqueue(env)
    await service.process_next_summary()
    async with env.sessions() as db, db.begin():
        (await db.get(NotificationChannel, 1)).config_enc = encrypt_token(json.dumps({
            "bot_token": "test:new-placeholder", "chat_id": "98765",
        }))
    await service.process_next_summary()
    assert (await stored(env, job_id)).status == "cancelled"
    env.send.assert_not_called()


async def test_chat_rate_limit_is_shared_and_waiting_does_not_spend_attempts(env):
    from finlytics.assistant.limits import limiter_for

    async with env.sessions() as db, db.begin():
        db.add(AssistantSettings(user_id=1, rate_limit_messages=1, rate_limit_window_seconds=3600))
    limiter_for(1, 3600).check("user:1")
    job_id = await enqueue(env)
    await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.error, job.generation_attempts) == ("pending", "rate_limited", 0)
    assert not env.llm.calls


async def test_cancellation_keeps_reported_usage(env):
    job_id = await enqueue(env)
    env.llm.error = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.process_next_summary()
    assert (await stored(env, job_id)).status == "pending"
    async with env.sessions() as db:
        assert await usage_queries.tokens_used_since(db, 1, datetime(2000, 1, 1, tzinfo=UTC)) == 60


async def test_missing_usage_is_not_reported_as_free(env):
    env.llm.report_usage = False
    await enqueue(env)
    await service.process_next_summary()
    async with env.sessions() as db:
        assert await usage_queries.has_unknown_summary_usage(db, 1)


async def test_missing_history_and_mixed_currencies_are_not_zero_comparisons(env):
    job_id = await enqueue(env)
    async with env.sessions() as db, db.begin():
        await db.execute(delete(Transaction).where(Transaction.import_run_id == 2))
        facts = await queries.get_import_summary_facts(db, await db.get(ImportSummaryJob, job_id))
        assert facts["previous"] is None
        assert facts["spending_change"] is None
        assert facts["changes"] == []
        (await db.get(Transaction, 1)).currency = "USD"
    await service.process_next_summary()
    job = await stored(env, job_id)
    assert (job.status, job.error) == ("failed", "mixed_currencies")
    assert not env.llm.calls


@pytest.mark.parametrize(("previous", "current", "delta", "percentage"), [
    (100, 80, -20, -20), (0, 100, 100, None), (0, 0, 0, None),
    (100, 100, 0, 0), (400, 460, 60, 15), (-100, -50, 50, 50),
])
def test_spending_change_handles_direction_and_zero_baselines(previous, current, delta, percentage):
    assert compare_amounts(previous, current) == {"delta": delta, "delta_pct": percentage}


async def test_total_spending_change_includes_uncategorized_expenses(env):
    async with env.sessions() as db, db.begin():
        db.add(Transaction(
            id=99, account_id=1, import_run_id=1, transaction_date=date(2026, 6, 15),
            amount=Decimal("-25"), currency="EUR", description="Uncategorized expense",
            category_id=None, dedup_hash="uncategorized", is_system=False,
        ))
    facts = await facts_for(env, await enqueue(env))
    assert facts["current"]["total_expense"] == 125
    assert facts["previous"]["total_expense"] == 200
    assert facts["spending_change"] == {"delta": -75, "delta_pct": -37.5}
    assert sum(category["amount"] for category in facts["categories"]) == 100


async def test_model_receives_calculated_evolution_and_spending_first_instructions(env):
    job_id = await enqueue(env)
    await service.process_next_summary()
    messages = env.llm.calls[0][0]
    facts = json.loads(messages[1]["content"])
    assert facts["spending_change"] == {"delta": -100, "delta_pct": -50}
    assert "analytical spending digest" in messages[0]["content"]
    assert "increases, decreases or stability" in messages[0]["content"]
    assert "Do not calculate additional totals" in messages[0]["content"]
    assert (await stored(env, job_id)).status == "ready"


async def test_redaction_preserves_numeric_facts_and_long_output_fits_telegram(env):
    job_id = await enqueue(env)
    async with env.sessions() as db:
        facts = await queries.get_import_summary_facts(db, await db.get(ImportSummaryJob, job_id))
    facts["account"] = "ES7921000813610123456789"
    facts["current"]["total_income"] = 100000000.0
    payload = json.loads(analysis_messages(facts, "es")[1]["content"])
    assert payload["account"] == "[redacted]"
    assert payload["current"]["total_income"] == 100000000.0
    message = render_import_summary(facts, "\U0001f4b0" * 5000, "es")
    assert telegram_units(message) <= 4096
    assert "[Resumen abreviado]" in message
    assert "100.000.000,00 EUR" in message
    assert facts["account"] not in message


@pytest.mark.parametrize(("start", "end", "expected"), [
    (date(2024, 3, 1), date(2024, 3, 31), (date(2024, 2, 1), date(2024, 2, 29))),
    (date(2026, 1, 1), date(2026, 1, 31), (date(2025, 12, 1), date(2025, 12, 31))),
    (date(2026, 6, 10), date(2026, 6, 19), (date(2026, 5, 31), date(2026, 6, 9))),
])
def test_comparable_period_bounds(start, end, expected):
    assert queries.previous_summary_period(start, end) == expected


@pytest.fixture
async def api(env):
    async def get_session():
        async with env.sessions() as db:
            yield db

    async def get_user():
        return User(id=1, username="owner", password_hash="test")

    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_current_user] = get_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize("operation", ["settings", "retry"])
async def test_summary_writes_reject_plain_text_but_accept_the_same_json_body(env, api, operation):
    if operation == "settings":
        method = "PUT"
        path = "/api/notifications/import-summary-settings"
        payload = {"enabled": True, "channel_id": 1, "language": "es"}
    else:
        job_id = await enqueue(env)
        async with env.sessions() as db, db.begin():
            (await db.get(ImportSummaryJob, job_id)).status = "failed"
        method = "POST"
        path = f"/api/notifications/import-summaries/{job_id}/retry"
        payload = {"acknowledge_uncertain": False}
    body = json.dumps(payload)

    rejected = await api.request(
        method, path, content=body, headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"][0]["loc"] == ["body"]

    accepted = await api.request(
        method, path, content=body, headers={"Content-Type": "application/json"},
    )
    assert accepted.status_code == 200
    if operation == "settings":
        assert accepted.json() == {**payload, "ai_available": True}
        assert (await api.get(path)).json() == accepted.json()
    else:
        assert accepted.json()["status"] == "pending"
        assert (await stored(env, job_id)).status == "pending"
    assert not env.llm.calls
    env.send.assert_not_called()


async def test_settings_require_owned_channel_and_ai(env, api):
    response = await api.put("/api/notifications/import-summary-settings", json={
        "enabled": True, "channel_id": 999, "language": "es",
    })
    assert response.status_code == 422
    response = await api.put("/api/notifications/import-summary-settings", json={
        "enabled": True, "channel_id": 1, "language": "es",
    })
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "channel_id": 1, "language": "es", "ai_available": True}
    assert "bot_token" not in response.text
    async with env.sessions() as db, db.begin():
        (await db.get(NotificationChannel, 1)).user_id = 2
    response = await api.put("/api/notifications/import-summary-settings", json={
        "enabled": True, "channel_id": 1,
    })
    assert response.status_code == 422


async def test_disabling_and_disconnecting_cancel_pending_jobs(env, api):
    job_id = await enqueue(env)
    response = await api.delete("/api/notifications/channels/1")
    assert response.status_code == 204
    assert (await stored(env, job_id)).status == "cancelled"
    assert not await service.process_next_summary()
    response = await api.get("/api/notifications/import-summary-settings")
    assert response.json()["enabled"] is False
    assert response.json()["channel_id"] is None


async def test_status_is_read_only_owned_and_never_exposes_report_or_credentials(env, api):
    job_id = await enqueue(env)
    response = await api.get("/api/notifications/import-summaries")
    assert response.status_code == 200
    assert response.json()[0]["id"] == job_id
    assert not env.llm.calls
    for field in ("message_text", "config_enc", "bot_token", "channel_version", "claim_token"):
        assert field not in response.text
    async with env.sessions() as db, db.begin():
        (await db.get(ImportSummaryJob, job_id)).user_id = 2
    assert (await api.get("/api/notifications/import-summaries")).json() == []
    assert (await api.post(f"/api/notifications/import-summaries/{job_id}/retry", json={})).status_code == 404
