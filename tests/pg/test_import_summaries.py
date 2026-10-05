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
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from finlytics.api import imports as import_api
from finlytics.api.deps import get_current_user, get_db, get_llm_client
from finlytics.app import app
from finlytics.assistant import settings as usage_queries
from finlytics.config import settings
from finlytics.db.models import (
    Account,
    ImportRun,
    ImportSummaryAttempt,
    ImportSummaryJob,
    ImportSummarySettings,
    NotificationChannel,
    Transaction,
    User,
)
from finlytics.db.queries import delete_account
from finlytics.db.queries import import_summaries as queries
from finlytics.investments.crypto import encrypt_token
from tests.pg.support import tx


@pytest.fixture
async def context(sessions, accounts, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "finlytics_encryption_key", Fernet.generate_key().decode())
    async with sessions() as db, db.begin():
        user = User(username="owner", password_hash="test")
        db.add(user)
        await db.flush()
        channel = NotificationChannel(
            user_id=user.id, channel="telegram", enabled=True,
            config_enc=encrypt_token(json.dumps({"bot_token": "test:placeholder", "chat_id": "123"})),
        )
        db.add(channel)
        await db.flush()
        db.add(ImportSummarySettings(user_id=user.id, enabled=True, channel_id=channel.id, language="en"))
    return SimpleNamespace(user=user, account_id=accounts[0], channel_id=channel.id)


async def new_job(sessions, context):
    async with sessions() as db, db.begin():
        account = await db.get(Account, context.account_id)
        result = await import_api._persist_import_run(
            db, account.id, "statement.pdf", [tx(amount=Decimal("-50"))],
        )
        return await queries.enqueue_import_summary(
            db, user_id=context.user.id, import_run_id=result.import_run_id, account=account,
            dates=[date(2025, 3, 14)], num_inserted=result.num_inserted,
        )


@pytest.fixture
async def client(sessions, context, monkeypatch):
    state = SimpleNamespace(wake_states=[], request_db=None)

    async def get_session():
        async with sessions() as db:
            state.request_db = db
            yield db

    async def get_user():
        return context.user

    monkeypatch.setattr(
        import_api, "wake_import_summaries",
        lambda: state.wake_states.append(state.request_db.in_transaction()),
    )
    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_current_user] = get_user
    app.dependency_overrides[get_llm_client] = lambda: AsyncMock()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
    ) as http:
        yield http, state
    for dependency in (get_db, get_current_user, get_llm_client):
        app.dependency_overrides.pop(dependency, None)


@pytest.mark.parametrize("one_shot", [False, True])
async def test_saving_routes_enqueue_atomically_and_wake_only_after_commit(
    sessions, context, client, monkeypatch, one_shot,
):
    http, state = client
    lines = [tx(amount=Decimal("-50"), description="Reviewed amount")]
    observed_uncommitted = []

    async def enqueue_and_check(db, **kwargs):
        job_id = await queries.enqueue_import_summary(db, **kwargs)
        async with sessions() as observer:
            observed_uncommitted.append(await observer.get(ImportSummaryJob, job_id) is None)
        return job_id

    monkeypatch.setattr(import_api, "enqueue_import_summary", enqueue_and_check)
    if one_shot:
        monkeypatch.setattr(import_api, "_parse_file", AsyncMock(return_value="Statement 2025"))
        monkeypatch.setattr(import_api, "extract_transactions", AsyncMock(return_value=lines))
        response = await http.post(
            "/api/imports", files={"file": ("statement.pdf", b"synthetic", "application/pdf")},
            data={"account_id": str(context.account_id)},
        )
        assert response.status_code == 201, response.text
    else:
        response = await http.post("/api/imports/confirm", json={
            "account_name": "BBVA", "source_filename": "statement.pdf",
            "transactions": [line.model_dump(mode="json") for line in lines],
        })
        assert response.status_code == 200, response.text
    job_id = response.json()["summary_job_id"]
    assert observed_uncommitted == [True]
    assert state.wake_states == [False]
    async with sessions() as db:
        job = await db.get(ImportSummaryJob, job_id)
        facts = await queries.get_import_summary_facts(db, job)
        assert job.status == "pending"
        assert facts["current"]["total_expense"] == 50
        assert await db.scalar(select(func.count()).select_from(ImportSummaryAttempt)) == 0


async def test_retrying_the_bank_import_does_not_enqueue_a_duplicate_summary(sessions, context, client):
    http, state = client
    body = {
        "account_name": "BBVA", "source_filename": "statement.pdf",
        "transactions": [tx().model_dump(mode="json")],
    }
    first, second = await http.post("/api/imports/confirm", json=body), await http.post(
        "/api/imports/confirm", json=body,
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["summary_job_id"] > 0
    assert "summary_job_id" not in second.json()
    assert second.json()["num_inserted"] == 0
    assert state.wake_states == [False]
    async with sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ImportSummaryJob)) == 1


async def test_enqueue_is_rolled_back_together_with_the_bank_import(sessions, context, client, monkeypatch):
    http, state = client

    async def enqueue_then_fail(db, **kwargs):
        await queries.enqueue_import_summary(db, **kwargs)
        raise RuntimeError("Synthetic transaction failure")

    monkeypatch.setattr(import_api, "enqueue_import_summary", enqueue_then_fail)
    response = await http.post("/api/imports/confirm", json={
        "account_name": "BBVA", "source_filename": "statement.pdf",
        "transactions": [tx().model_dump(mode="json")],
    })
    assert response.status_code == 500
    assert state.wake_states == []
    async with sessions() as db:
        for model in (Transaction, ImportRun, ImportSummaryJob):
            assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_only_one_concurrent_worker_can_claim_a_job(sessions, context):
    job_id = await new_job(sessions, context)

    async def claim():
        async with sessions() as db, db.begin():
            return await queries.claim_summary(db)

    claims = await asyncio.gather(claim(), claim())
    assert [job.id for job in claims if job is not None] == [job_id]


async def test_stale_generation_claims_cannot_overwrite_the_new_worker(sessions, context):
    job_id = await new_job(sessions, context)
    async with sessions() as db, db.begin():
        old = await queries.claim_summary(db)
    async with sessions() as db, db.begin():
        (await db.get(ImportSummaryJob, job_id)).lease_until = datetime.now(UTC) - timedelta(seconds=1)
    async with sessions() as db, db.begin():
        new = await queries.claim_summary(db)
    assert new.id == old.id
    assert new.claim_token != old.claim_token
    async with sessions() as db, db.begin():
        assert not await queries.update_claim(db, old, message_text="stale")
        assert await queries.update_claim(db, new, message_text="current")
    async with sessions() as db:
        assert (await db.get(ImportSummaryJob, job_id)).message_text == "current"


async def test_a_crash_during_send_becomes_uncertain_not_automatically_retried(sessions, context):
    job_id = await new_job(sessions, context)
    async with sessions() as db, db.begin():
        job = await db.get(ImportSummaryJob, job_id)
        job.message_text = "Already generated"
        job.status = "ready"
    async with sessions() as db, db.begin():
        assert (await queries.claim_summary(db)).status == "sending"
    async with sessions() as db, db.begin():
        (await db.get(ImportSummaryJob, job_id)).lease_until = datetime.now(UTC) - timedelta(seconds=1)
    async with sessions() as db, db.begin():
        assert await queries.claim_summary(db) is None
    async with sessions() as db:
        assert (await db.get(ImportSummaryJob, job_id)).status == "uncertain"


async def test_source_deletion_keeps_usage_and_cancels_pending_work(sessions, context):
    job_id = await new_job(sessions, context)
    async with sessions() as db, db.begin():
        db.add(ImportSummaryAttempt(
            job_id=job_id, user_id=context.user.id, prompt_tokens=40,
            completion_tokens=20, total_tokens=60, answered=True,
        ))
    async with sessions() as db:
        assert await delete_account(db, context.account_id) == 1
    async with sessions() as db, db.begin():
        assert await queries.claim_summary(db) is None
        job = await db.get(ImportSummaryJob, job_id)
        assert job.account_id is None and job.import_run_id is None
        assert job.status == "cancelled"
        assert await usage_queries.tokens_used_since(
            db, context.user.id, datetime(2000, 1, 1, tzinfo=UTC),
        ) == 60


async def test_retry_usage_is_attributed_to_each_call_month(sessions, context):
    job_id = await new_job(sessions, context)
    async with sessions() as db, db.begin():
        db.add_all([
            ImportSummaryAttempt(
                job_id=job_id, user_id=context.user.id, prompt_tokens=30, completion_tokens=10,
                total_tokens=40, answered=False, created_at=datetime(2026, 3, 31, tzinfo=UTC),
            ),
            ImportSummaryAttempt(
                job_id=job_id, user_id=context.user.id, prompt_tokens=60, completion_tokens=20,
                total_tokens=80, answered=True, created_at=datetime(2026, 4, 1, tzinfo=UTC),
            ),
        ])
    async with sessions() as db:
        assert await usage_queries.tokens_used_since(
            db, context.user.id, datetime(2026, 4, 1, tzinfo=UTC),
        ) == 80
        assert await usage_queries.usage_by_day(db, context.user.id, datetime(2000, 1, 1, tzinfo=UTC)) == [
            {"day": "2026-03-31", "tokens": 40, "messages": 0, "summaries": 0},
            {"day": "2026-04-01", "tokens": 80, "messages": 0, "summaries": 1},
        ]


async def test_database_guards_the_user_import_identity(sessions, context):
    job_id = await new_job(sessions, context)
    async with sessions() as db:
        job = await db.get(ImportSummaryJob, job_id)
    with pytest.raises(IntegrityError):
        async with sessions() as db, db.begin():
            db.add(ImportSummaryJob(
                user_id=job.user_id, import_run_id=job.import_run_id, account_id=job.account_id,
                channel_id=job.channel_id, channel_version=job.channel_version,
                account_name=job.account_name, from_date=job.from_date, to_date=job.to_date,
                language=job.language,
            ))
