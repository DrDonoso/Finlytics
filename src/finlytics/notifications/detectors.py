"""Notification detectors: wrap existing pure-function reminders.

Each Detector:
  - has a stable ``id`` (used as the ``source`` column in notifications)
  - declares ``is_condition = True`` so the orchestrator auto-resolves rows
    whose dedup_key is no longer in the detected set
  - implements ``async evaluate(db, user_id, *, today) → list[DetectedNotification]``
    by gathering the same inputs used by the existing reminder endpoints and
    calling the UNCHANGED pure functions (compute_statement_reminder /
    compute_espp_reminder).  No reminder logic is duplicated here.

Adding a new detector = append to REGISTRY.  No other code changes needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


# ── Detected notification value object ────────────────────────────────────────

@dataclass
class DetectedNotification:
    """Immutable value object produced by a detector.

    Maps 1-to-1 to the columns that a Notification row carries.
    title_args / body_args will be stored as JSON and rendered i18n
    client-side — never pre-rendered strings.
    """

    source: str
    type: str
    severity: str           # "info" | "warning"
    dedup_key: str          # stable identity (e.g. "statement:missing:2026-06:acct-3")
    title_key: str          # i18n key (e.g. "notif.statement_missing")
    title_args: dict = field(default_factory=dict)
    body_key: str | None = None
    body_args: dict | None = None
    action_link: str | None = None


# ── Detector protocol ──────────────────────────────────────────────────────────

@runtime_checkable
class Detector(Protocol):
    """Contract every detector must satisfy."""

    id: str
    is_condition: bool  # True → rows auto-resolved when key disappears

    async def evaluate(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        today: date,
    ) -> list[DetectedNotification]: ...


# ── StatementDetector ─────────────────────────────────────────────────────────

class StatementDetector:
    """Emits one notification per account missing the previous calendar month.

    Reuses compute_statement_reminder() — the pure function behind
    GET /api/statements/reminder.  Gathers inputs the same way the endpoint
    does so the two stay in sync automatically.
    """

    id = "statement"
    is_condition = True

    async def evaluate(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        today: date,
    ) -> list[DetectedNotification]:
        from finlytics.api.statements import compute_statement_reminder
        from finlytics.db import queries

        accounts = await queries.get_accounts(db)
        # Build {account_id: account_name} map for notification args
        account_names: dict[int, str] = {int(a["id"]): a["name"] for a in accounts}

        per_account_months: dict[int, list[tuple[int, int]]] = {}
        for account in accounts:
            account_id = int(account["id"])
            rows = await queries.get_statement_months(db, account_id=account_id)
            per_account_months[account_id] = [
                (int(r["year"]), int(r["month"])) for r in rows
            ]

        reminder = compute_statement_reminder(today, per_account_months)
        if not reminder.missing_account_ids:
            return []

        # Month label for i18n args: "2026-06"
        month_label = f"{reminder.year}-{reminder.month:02d}"

        detected: list[DetectedNotification] = []
        for account_id in reminder.missing_account_ids:
            account_name = account_names.get(account_id, str(account_id))
            detected.append(
                DetectedNotification(
                    source=self.id,
                    type="missing_statement",
                    severity="warning",
                    dedup_key=f"statement:missing:{month_label}:acct-{account_id}",
                    title_key="notif.statement_missing",
                    title_args={"month": month_label, "account": account_name},
                    action_link=f"/finances?account_id={account_id}",
                )
            )
        return detected


# ── EsppDetector ──────────────────────────────────────────────────────────────

class EsppDetector:
    """Emits one notification when the most recent ESPP quarter upload is overdue.

    Reuses compute_espp_reminder() — the pure function behind
    GET /api/investments/fidelity/reminder.  Gathers inputs the same way the
    endpoint does.  Emits nothing if there is no Fidelity connection or the
    upload is not yet overdue.
    """

    id = "espp"
    is_condition = True

    async def evaluate(
        self,
        db: AsyncSession,
        user_id: int,
        *,
        today: date,
    ) -> list[DetectedNotification]:
        from finlytics.api.fidelity import _get_fidelity_connection, compute_espp_reminder
        from finlytics.db.models import EsppLot

        conn = await _get_fidelity_connection(user_id, db)
        if conn is None:
            return []

        lots = (
            await db.execute(
                select(EsppLot).where(
                    EsppLot.connection_id == conn.id,
                    EsppLot.share_source == "SP",
                )
            )
        ).scalars().all()

        reminder = compute_espp_reminder(lots, today=today)
        if not reminder.overdue:
            return []

        # Build a sortable dedup_key from period_label e.g. "Q2 2026" → "2026-Q2"
        period_key: str
        if reminder.period_label:
            parts = reminder.period_label.split()  # ["Q2", "2026"]
            period_key = f"{parts[1]}-{parts[0]}" if len(parts) == 2 else reminder.period_label
        elif reminder.expected_date:
            period_key = reminder.expected_date[:7]  # "2026-06"
        else:
            period_key = today.strftime("%Y-%m")

        return [
            DetectedNotification(
                source=self.id,
                type="espp_overdue",
                severity="warning",
                dedup_key=f"espp:overdue:{period_key}",
                title_key="notif.espp_overdue",
                title_args={"period": reminder.period_label or period_key},
                action_link="/investments/fidelity-espp",
            )
        ]


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: list[Detector] = [
    StatementDetector(),
    EsppDetector(),
]
"""All active detectors.  Append a new Detector instance here to add a
notification type — the orchestrator discovers it automatically."""
