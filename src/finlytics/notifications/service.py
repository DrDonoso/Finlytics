"""Notification orchestrator: evaluate all detectors and upsert results.

Core function: evaluate_notifications(db, user_id, *, today) → list[Notification]

Algorithm per detector:
  1. Run detector → set of DetectedNotification objects.
  2. UPSERT by (user_id, dedup_key):
       - row exists → update mutable fields; clear resolved_at if re-activated;
         NEVER touch read_at / dismissed_at (user state must survive).
       - row absent  → INSERT; add to the "new notifications" list.
  3. AUTO-RESOLVE (is_condition=True detectors only):
       any active row (not dismissed, not resolved) for this source whose
       dedup_key is NOT in the current detected set → set resolved_at = now.

Idempotency: running twice in a row creates nothing new and resends nothing.

Slice 2 delivery seam:
  After all upserts, ``deliver_new(db, user_id, new_notifs)`` is called with
  the freshly inserted Notification rows.  In Slice 1 it is a NO-OP.
  Slice 2 fills it: iterate enabled NotificationChannels, guard with
  UNIQUE(notification_id, channel) in notification_deliveries, send.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.clock import today as local_today
from finlytics.db.models import Notification, NotificationChannel, NotificationDelivery
from finlytics.investments.crypto import EncryptionNotConfiguredError, decrypt_token
from finlytics.notifications.detectors import REGISTRY, DetectedNotification
from finlytics.notifications.messages import render_notification_text
from finlytics.notifications.telegram import TelegramError, telegram_send_message

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


async def evaluate_notifications(
    db: AsyncSession,
    user_id: int,
    *,
    today: date | None = None,
) -> list[Notification]:
    """Run all detectors for *user_id* and upsert results into the DB.

    Returns the list of **newly created** Notification rows (have IDs, both
    read_at and dismissed_at = None).  Existing rows that are re-detected or
    newly resolved are NOT included in the return value.

    The caller (API endpoint or background loop) can pass the return value to
    ``deliver_new`` as a delivery seam; calling it is a no-op in Slice 1.
    """
    if today is None:
        today = local_today()

    now = datetime.now(timezone.utc)
    new_notifications: list[Notification] = []

    async with db.begin():
        for detector in REGISTRY:
            # ── 1. Detect ──────────────────────────────────────────────────
            try:
                detected: list[DetectedNotification] = await detector.evaluate(
                    db, user_id, today=today
                )
            except Exception:
                log.exception(
                    "Detector %r raised during evaluate (user_id=%d) — skipping",
                    detector.id,
                    user_id,
                )
                detected = []

            detected_keys = {d.dedup_key for d in detected}

            # ── 2. Upsert detected notifications ───────────────────────────
            for d in detected:
                result = await db.execute(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.dedup_key == d.dedup_key,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing is not None:
                    # Update mutable fields; preserve user state (read/dismiss)
                    existing.title_key = d.title_key
                    existing.title_args = d.title_args
                    existing.body_key = d.body_key
                    existing.body_args = d.body_args
                    existing.action_link = d.action_link
                    existing.updated_at = now
                    if existing.resolved_at is not None:
                        # Condition re-activated — clear resolved mark
                        existing.resolved_at = None
                        log.debug(
                            "Re-activated notification dedup_key=%r (user_id=%d)",
                            d.dedup_key,
                            user_id,
                        )
                else:
                    notif = Notification(
                        user_id=user_id,
                        source=d.source,
                        type=d.type,
                        severity=d.severity,
                        dedup_key=d.dedup_key,
                        title_key=d.title_key,
                        title_args=d.title_args,
                        body_key=d.body_key,
                        body_args=d.body_args,
                        action_link=d.action_link,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(notif)
                    await db.flush()  # populate notif.id before appending
                    new_notifications.append(notif)
                    log.debug(
                        "New notification id=%d dedup_key=%r (user_id=%d)",
                        notif.id,
                        d.dedup_key,
                        user_id,
                    )

            # ── 3. Auto-resolve stale rows ─────────────────────────────────
            if detector.is_condition:
                result = await db.execute(
                    select(Notification).where(
                        Notification.user_id == user_id,
                        Notification.source == detector.id,
                        Notification.dismissed_at.is_(None),
                        Notification.resolved_at.is_(None),
                    )
                )
                active_rows = result.scalars().all()
                for row in active_rows:
                    if row.dedup_key not in detected_keys:
                        row.resolved_at = now
                        row.updated_at = now
                        log.debug(
                            "Auto-resolved notification id=%d dedup_key=%r (user_id=%d)",
                            row.id,
                            row.dedup_key,
                            user_id,
                        )

    # ── Slice 2 delivery seam ─────────────────────────────────────────────────
    # new_notifications have been committed above; pass them for delivery.
    await deliver_new(db, user_id, new_notifications)

    return new_notifications


async def deliver_new(
    db: AsyncSession,
    user_id: int,
    new_notifs: list[Notification],
) -> None:
    """Deliver newly created notifications to all enabled channels.

    For each enabled NotificationChannel × new Notification pair:
      1. INSERT INTO notification_deliveries ON CONFLICT (notification_id, channel)
         DO NOTHING (idempotency guard — prevents double-sending on concurrent calls).
      2. If the row was newly inserted: decrypt config and send via the channel.
      3. On success: status='sent', sent_at=now.
      4. On failure: status='failed', error=<safe message> (NEVER token).
         Failures are caught and recorded; they do NOT propagate to the caller.

    Safe to call when new_notifs is empty or no channels are configured
    (returns immediately — Slice 1 behaviour is preserved).
    """
    if not new_notifs:
        return

    from finlytics.config import settings  # deferred to avoid import-time side effects

    if not settings.telegram_send_enabled:
        return

    # ── Query enabled channels ────────────────────────────────────────────────
    async with db.begin():
        result = await db.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id == user_id,
                NotificationChannel.enabled.is_(True),
            )
        )
        channels = result.scalars().all()

    if not channels:
        return

    now = datetime.now(timezone.utc)

    for channel in channels:
        for notif in new_notifs:
            # ── Claim delivery slot (idempotency guard) ───────────────────
            async with db.begin():
                existing = await db.execute(
                    select(NotificationDelivery).where(
                        NotificationDelivery.notification_id == notif.id,
                        NotificationDelivery.channel == channel.channel,
                    )
                )
                if existing.scalar_one_or_none() is not None:
                    continue  # already delivered or previously attempted
                delivery = NotificationDelivery(
                    notification_id=notif.id,
                    channel=channel.channel,
                    status="pending",
                    created_at=now,
                )
                db.add(delivery)
                await db.flush()  # populate delivery.id before commit

            # ── Send ──────────────────────────────────────────────────────
            sent = False
            error_msg: str | None = None
            if not channel.config_enc:
                error_msg = "Channel has no config — cannot decrypt."
                log.error(
                    "Channel id=%d has no config_enc — skipping notification_id=%d",
                    channel.id,
                    notif.id,
                )
            else:
                try:
                    config_data = json.loads(decrypt_token(channel.config_enc))
                    text = render_notification_text(notif)
                    await telegram_send_message(
                        config_data["bot_token"],
                        str(config_data["chat_id"]),
                        text,
                        message_thread_id=config_data.get("message_thread_id"),
                    )
                    sent = True
                except EncryptionNotConfiguredError:
                    error_msg = "Encryption not configured"
                    log.error(
                        "Telegram delivery skipped for notification_id=%d: encryption not configured",
                        notif.id,
                    )
                except TelegramError as exc:
                    error_msg = str(exc)
                    log.warning(
                        "Telegram send failed for notification_id=%d channel_id=%d: %s",
                        notif.id,
                        channel.id,
                        exc,
                    )
                except Exception as exc:
                    error_msg = f"Unexpected error ({type(exc).__name__})"
                    log.exception(
                        "Unexpected error delivering notification_id=%d channel_id=%d",
                        notif.id,
                        channel.id,
                    )

            # ── Persist delivery result ────────────────────────────────────
            async with db.begin():
                delivery.status = "sent" if sent else "failed"
                if sent:
                    delivery.sent_at = datetime.now(timezone.utc)
                else:
                    delivery.error = (error_msg or "unknown")[:500]
