"""Push notifications: the devices that receive them, and the worker that tells them.

A browser, or the app installed on a phone's Home Screen, registers from Settings →
Notifications (``api/push.py``) with its push address and keys (``webpush``) and the language of
the interface; the interface registers it again each time it opens. The registration belongs to
the session of the device: signing out there deletes it, and a password change or "sign out other
devices" pauses the other devices until they sign in again.

Each alert a detector creates is queued for every active device of its user in the transaction
that creates it (``enqueue``), unless its type is muted (``preferences``), and ``push_loop`` sends
it at once, at any time of day: one notification per device and type, so the statements missing
on the 1st of a month arrive together. Tapping it opens the alert's page and marks the alerts it
tells as read; the app's badge counts the unread ones. An alert read, dismissed or resolved, or
whose type was muted, before it went out is no longer sent. A failed send is tried again for
``DELIVERY_WINDOW``; a device its push service no longer knows is forgotten, as is one refused
``MAX_FAILURES`` times in a row.

The messages use the declarative format (``"web_push": 8030``) that Safari shows by itself since
iOS 18.4; the service worker ``frontend/public/sw.js`` shows them everywhere else.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import ColumnElement, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.config import settings
from finlytics.db.models import Notification, PushDelivery, PushSubscription, User
from finlytics.db.session import async_session_factory
from finlytics.notifications import webpush
from finlytics.notifications.preferences import muted_sources

log = logging.getLogger(__name__)

Locale = Literal["es", "en"]

# An alert not delivered within a day is no longer worth a notification.
DELIVERY_WINDOW = timedelta(days=1)
# Minutes to wait after a push service or the network failed (the last one repeats).
RETRY_MINUTES = (2, 5, 15, 30, 60)
# How long a round owns the deliveries it claimed: a send lost in a crash is retried after it.
CLAIM_LEASE = timedelta(minutes=5)
MAX_FAILURES = 3
# Devices kept per user: registering one more forgets the one unused for longest.
MAX_DEVICES = 10
POLL_SECONDS = 60
BATCH = 500
MAX_TITLE = 120
MAX_BODY = 300
# The query parameter that tells the interface which alerts a notification told (read on open).
INTENT_PARAM = "notif"
MAX_INTENT_IDS = 50
LANGUAGE_TAGS: dict[Locale, str] = {"es": "es-ES", "en": "en-GB"}
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
UNSYNCHRONIZED = {"synchronize_session": False}

_wake_event: asyncio.Event | None = None


# ── Availability ──────────────────────────────────────────────────────────────

def push_available() -> bool:
    """Push needs a configured AUTH_SECRET: its signing key derives from it, and a secret
    generated at startup would change on every restart, breaking every subscription."""
    return settings.auth_secret_is_persistent


@functools.lru_cache(maxsize=2)
def _public_key(secret: str) -> str:
    return webpush.b64encode(webpush.public_bytes(webpush.vapid_key(secret)))


def public_key() -> str | None:
    """The key browsers subscribe with (``applicationServerKey``); None when unavailable."""
    return _public_key(settings.auth_secret) if push_available() else None


def new_sender() -> webpush.WebPush | None:
    """A sender with its own HTTP client (close it); None when push is unavailable."""
    return webpush.WebPush(settings.auth_secret) if push_available() else None


def device_origin(value: str | None) -> str | None:
    """The origin a device registers from (its ``Origin`` header), when push can work there: an
    HTTPS origin, or ``http://localhost`` (browsers only offer push in a secure context)."""
    if not value or len(value) > 255 or not value.isascii():
        return None
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        return None
    host = parts.hostname
    if (
        not host
        or parts.path
        or parts.query
        or parts.fragment
        or parts.username is not None
        or parts.password is not None
    ):
        return None
    if parts.scheme == "https" or (parts.scheme == "http" and host in LOCAL_HOSTS):
        return f"{parts.scheme}://{parts.netloc.lower()}"
    return None


# ── Devices ───────────────────────────────────────────────────────────────────

def _insert(db: AsyncSession, model: type[PushSubscription]) -> Any:
    if db.get_bind().dialect.name == "postgresql":
        return pg_insert(model)
    return sqlite_insert(model)


async def register_device(
    db: AsyncSession,
    *,
    user_id: int,
    token_version: int,
    session_jti: str,
    endpoint: str,
    p256dh: str,
    auth: str,
    origin: str,
    locale: Locale,
    now: datetime,
) -> None:
    """Register a device, or refresh its registration (an address another account registered
    becomes this one's); keeps the user's ``MAX_DEVICES`` most recent. No commit."""
    values = {
        "user_id": user_id,
        "token_version": token_version,
        "session_jti": session_jti,
        "p256dh": p256dh,
        "auth": auth,
        "origin": origin,
        "locale": locale,
        "failures": 0,
        "updated_at": now,
    }
    statement = _insert(db, PushSubscription).values(endpoint=endpoint, created_at=now, **values)
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[PushSubscription.endpoint],
            set_={name: getattr(statement.excluded, name) for name in values},
        )
    )
    oldest = (
        select(PushSubscription.id)
        .where(PushSubscription.user_id == user_id)
        .order_by(PushSubscription.updated_at.desc(), PushSubscription.id.desc())
        .offset(MAX_DEVICES)
    )
    await forget_devices(db, PushSubscription.id.in_(oldest))


async def forget_devices(db: AsyncSession, *where: ColumnElement[bool]) -> None:
    """Delete the devices matching ``where`` and what was queued for them. No commit."""
    devices = select(PushSubscription.id).where(*where)
    await db.execute(
        delete(PushDelivery).where(PushDelivery.subscription_id.in_(devices)),
        execution_options=UNSYNCHRONIZED,
    )
    await db.execute(delete(PushSubscription).where(*where), execution_options=UNSYNCHRONIZED)


async def forget_session(db: AsyncSession, session_jti: str) -> None:
    """A device signed out: its notifications stop. No commit."""
    await forget_devices(db, PushSubscription.session_jti == session_jti)


async def follow_session(
    db: AsyncSession, old_jti: str, new_jti: str, token_version: int
) -> None:
    """The session of a device was re-issued (password change, "sign out other devices"): its
    notifications go on under the new one. No commit."""
    await db.execute(
        update(PushSubscription)
        .where(PushSubscription.session_jti == old_jti)
        .values(session_jti=new_jti, token_version=token_version),
        execution_options=UNSYNCHRONIZED,
    )


# ── Queue ─────────────────────────────────────────────────────────────────────

async def enqueue(
    db: AsyncSession, user_id: int, alerts: Sequence[Notification], now: datetime
) -> int:
    """Queue alerts just created, in the caller's transaction, for every active device of the
    user; the number of deliveries queued. None while push is unavailable."""
    if not alerts or not push_available():
        return 0
    muted = await muted_sources(db, user_id)
    wanted = [alert for alert in alerts if alert.source not in muted]
    if not wanted:
        return 0
    devices = (
        await db.scalars(
            select(PushSubscription.id)
            .join(User, User.id == PushSubscription.user_id)
            .where(
                PushSubscription.user_id == user_id,
                PushSubscription.token_version == User.token_version,
            )
        )
    ).all()
    db.add_all(
        PushDelivery(
            subscription_id=device,
            notification_id=alert.id,
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )
        for device in devices
        for alert in wanted
    )
    return len(devices) * len(wanted)


def wake_push() -> None:
    if _wake_event is not None:
        _wake_event.set()


# ── Messages ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Texts:
    """The notifications' texts in one language. ``statement``: one account; ``statements``:
    several, of the same month. ``modelo720``: whether the Fidelity shares exceeded the
    threshold, never with the figures."""

    statement_title: str
    statement_body: str
    statements_title: str
    statements_body: str
    espp_title: str
    espp_body: str
    modelo720_exceeds_title: str
    modelo720_exceeds_body: str
    modelo720_below_title: str
    modelo720_below_body: str
    other_title: str
    other_body: str
    test_title: str
    test_body: str
    conjunction: str
    months: tuple[str, ...]
    month: str


TEXTS: dict[Locale, Texts] = {
    "es": Texts(
        statement_title="Extracto pendiente: {account}",
        statement_body="Falta subir el extracto de {month}.",
        statements_title="{count} extractos pendientes",
        statements_body="Falta subir el extracto de {month} de {accounts}.",
        espp_title="Subida ESPP pendiente",
        espp_body="Falta importar el CSV del ESPP de {period}.",
        modelo720_exceeds_title="Modelo 720 (ejercicio {year}): superas el umbral",
        modelo720_exceeds_body=(
            "Tus acciones de Fidelity lo superaban a 31 de diciembre. "
            "El plazo acaba el 31 de marzo."
        ),
        modelo720_below_title="Modelo 720 (ejercicio {year}): no superas el umbral",
        modelo720_below_body=(
            "Tus acciones de Fidelity no lo superaban a 31 de diciembre: "
            "por ellas no tienes que presentarlo."
        ),
        other_title="Nueva alerta",
        other_body="Ábrela en Finlytics para ver los detalles.",
        test_title="Notificación de prueba",
        test_body="Las alertas de Finlytics llegarán a este dispositivo.",
        conjunction="y",
        months=(
            "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
            "septiembre", "octubre", "noviembre", "diciembre",
        ),
        month="{month} de {year}",
    ),
    "en": Texts(
        statement_title="Missing statement: {account}",
        statement_body="The {month} statement hasn't been imported yet.",
        statements_title="{count} missing statements",
        statements_body="The {month} statements of {accounts} haven't been imported yet.",
        espp_title="ESPP upload overdue",
        espp_body="The ESPP CSV for {period} hasn't been imported yet.",
        modelo720_exceeds_title="Modelo 720 (tax year {year}): above the threshold",
        modelo720_exceeds_body=(
            "Your Fidelity shares exceeded it on 31 December. The deadline is 31 March."
        ),
        modelo720_below_title="Modelo 720 (tax year {year}): below the threshold",
        modelo720_below_body=(
            "Your Fidelity shares did not exceed it on 31 December, "
            "so they don't require filing."
        ),
        other_title="New alert",
        other_body="Open it in Finlytics to see the details.",
        test_title="Test notification",
        test_body="Finlytics alerts will arrive on this device.",
        conjunction="and",
        months=(
            "January", "February", "March", "April", "May", "June", "July", "August",
            "September", "October", "November", "December",
        ),
        month="{month} {year}",
    ),
}


@dataclass(frozen=True)
class Alert:
    """What a notification needs from one detector alert."""

    id: int
    source: str
    type: str
    args: dict[str, Any]
    link: str | None


def month_label(value: str, locale: Locale) -> str:
    """``2026-10`` as «octubre de 2026» / "October 2026" (the value itself when malformed)."""
    year, _, month = value.partition("-")
    if not (year.isdigit() and month.isdigit() and 1 <= int(month) <= 12):
        return value or "—"
    texts = TEXTS[locale]
    return texts.month.format(month=texts.months[int(month) - 1], year=year)


def sounds_like_i(word: str) -> bool:
    """Whether Spanish «y» becomes «e» before ``word``: it starts with the sound /i/ («ING»,
    «Hipotecas»), not with the diphthongs ``hia``/``hie``."""
    letters = "".join(
        character
        for character in unicodedata.normalize("NFD", word.casefold())
        if not unicodedata.combining(character)
    )
    return letters.startswith("i") or (
        letters.startswith("hi") and not letters.startswith(("hia", "hie"))
    )


def listed(names: Sequence[str], locale: Locale) -> str:
    """``names`` in running text: «BBVA, Revolut y Santander» («BBVA e ING» in Spanish)."""
    if len(names) < 2:
        return "".join(names)
    conjunction = TEXTS[locale].conjunction
    if locale == "es" and sounds_like_i(names[-1]):
        conjunction = "e"
    return f"{', '.join(names[:-1])} {conjunction} {names[-1]}"


def shortened(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def with_intent(path: str | None, ids: Sequence[int]) -> str:
    """The page a notification opens (an in-app path, else the dashboard), telling the interface
    which alerts it told."""
    if not path or not path.startswith("/") or path.startswith("//"):
        path = "/"
    parts = urlsplit(path)
    query = [*parse_qsl(parts.query), (INTENT_PARAM, ",".join(map(str, ids[:MAX_INTENT_IDS])))]
    return urlunsplit(("", "", parts.path, urlencode(query, safe=","), parts.fragment))


def notification_message(
    origin: str, locale: Locale, *, title: str, body: str, path: str, tag: str
) -> dict[str, Any]:
    """A declarative push message: the notification, and the page of ``origin`` it opens. Its
    title says what it is about: iOS already adds "from Finlytics" under it."""
    return {
        "web_push": 8030,
        "notification": {
            "title": shortened(title, MAX_TITLE),
            "body": shortened(body, MAX_BODY),
            "lang": LANGUAGE_TAGS[locale],
            "dir": "ltr",
            "navigate": origin + path,
            "tag": tag,
            "silent": False,
            "icon": f"{origin}/icon-192.png",
            # Android's status bar (a white silhouette); Safari ignores it.
            "badge": f"{origin}/badge-96.png",
        },
    }


def alert_message(
    alerts: Sequence[Alert], origin: str, locale: Locale, unread: int
) -> dict[str, Any]:
    """The notification of one or more alerts of the same type (statements of one month); the
    app's badge shows ``unread``."""
    texts = TEXTS[locale]
    first = alerts[0]
    path = first.link
    if first.source == "statement":
        month = month_label(str(first.args.get("month", "")), locale)
        if len(alerts) == 1:
            title = texts.statement_title.format(account=first.args.get("account", "—"))
            body = texts.statement_body.format(month=month)
        else:
            accounts = [str(alert.args.get("account", "—")) for alert in alerts]
            title = texts.statements_title.format(count=len(alerts))
            body = texts.statements_body.format(month=month, accounts=listed(accounts, locale))
            path = "/"
    elif first.source == "espp":
        title = texts.espp_title
        body = texts.espp_body.format(period=first.args.get("period", "—"))
    elif first.source == "modelo720":
        if first.type == "modelo720_exceeds":
            title, body = texts.modelo720_exceeds_title, texts.modelo720_exceeds_body
        else:
            title, body = texts.modelo720_below_title, texts.modelo720_below_body
        title = title.format(year=first.args.get("year", "—"))
    else:
        title, body = texts.other_title, texts.other_body
    ids = sorted(alert.id for alert in alerts)
    message = notification_message(
        origin, locale, title=title, body=body, path=with_intent(path, ids), tag=f"alert-{ids[0]}"
    )
    message["app_badge"] = unread
    return message


def test_message(origin: str, locale: Locale) -> dict[str, Any]:
    texts = TEXTS[locale]
    return notification_message(
        origin,
        locale,
        title=texts.test_title,
        body=texts.test_body,
        path="/settings/notifications",
        tag="test",
    )


def group_key(alert: Alert) -> str:
    """Alerts told by one notification share it: the statements of one month, else one each."""
    if alert.source == "statement":
        return f"statement:{alert.args.get('month', '')}"
    return f"{alert.source}:{alert.id}"


# ── Worker ────────────────────────────────────────────────────────────────────

@dataclass
class Group:
    """The alerts one notification tells one device."""

    subscription_id: int
    subscription: webpush.Subscription
    user_id: int
    origin: str
    locale: Locale
    expires_at: datetime
    attempts: int = 0
    unread: int = 0
    alerts: list[Alert] = field(default_factory=list)
    delivery_ids: list[int] = field(default_factory=list)


def aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; every stored one is UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def _claim(now: datetime) -> tuple[list[Group], list[int], int]:
    """Claim the deliveries due at ``now``: the notifications to send, the deliveries no longer
    worth sending, and how many were claimed."""
    async with async_session_factory() as db, db.begin():
        due = (
            await db.scalars(
                select(PushDelivery.id)
                .where(PushDelivery.next_attempt_at <= now)
                .order_by(PushDelivery.id)
                .limit(BATCH)
            )
        ).all()
        if not due:
            return [], [], 0
        claimed = (
            await db.scalars(
                update(PushDelivery)
                .where(PushDelivery.id.in_(due), PushDelivery.next_attempt_at <= now)
                .values(next_attempt_at=now + CLAIM_LEASE)
                .returning(PushDelivery.id),
                execution_options=UNSYNCHRONIZED,
            )
        ).all()
        if not claimed:
            return [], [], 0
        rows = (
            await db.execute(
                select(PushDelivery, PushSubscription, Notification, User.token_version)
                .join(PushSubscription, PushSubscription.id == PushDelivery.subscription_id)
                .join(Notification, Notification.id == PushDelivery.notification_id)
                .join(User, User.id == PushSubscription.user_id)
                .where(PushDelivery.id.in_(claimed))
                .order_by(PushDelivery.subscription_id, PushDelivery.notification_id)
            )
        ).all()
        found = {delivery.id for delivery, *_ in rows}
        dropped = [delivery_id for delivery_id in claimed if delivery_id not in found]
        muted: dict[int, set[str]] = {}
        groups: dict[tuple[int, str], Group] = {}
        for delivery, device, notification, token_version in rows:
            expires_at = aware(delivery.created_at) + DELIVERY_WINDOW
            if device.user_id not in muted:
                muted[device.user_id] = await muted_sources(db, device.user_id)
            if (
                expires_at <= now
                or device.token_version != token_version
                or notification.user_id != device.user_id
                or notification.read_at is not None
                or notification.dismissed_at is not None
                or notification.resolved_at is not None
                or notification.source in muted[device.user_id]
            ):
                dropped.append(delivery.id)
                continue
            alert = Alert(
                id=notification.id,
                source=notification.source,
                type=notification.type,
                args=dict(notification.title_args or {}),
                link=notification.action_link,
            )
            key = (device.id, group_key(alert))
            group = groups.get(key)
            if group is None:
                group = groups[key] = Group(
                    subscription_id=device.id,
                    subscription=webpush.Subscription(device.endpoint, device.p256dh, device.auth),
                    user_id=device.user_id,
                    origin=device.origin,
                    locale="en" if device.locale == "en" else "es",
                    expires_at=expires_at,
                )
            group.alerts.append(alert)
            group.delivery_ids.append(delivery.id)
            group.attempts = max(group.attempts, delivery.attempts)
            group.expires_at = min(group.expires_at, expires_at)
        if groups:
            users = {group.user_id for group in groups.values()}
            unread = dict(
                (
                    await db.execute(
                        select(Notification.user_id, func.count())
                        .where(
                            Notification.user_id.in_(users),
                            Notification.read_at.is_(None),
                            Notification.dismissed_at.is_(None),
                            Notification.resolved_at.is_(None),
                        )
                        .group_by(Notification.user_id)
                    )
                ).all()
            )
            for group in groups.values():
                group.unread = unread.get(group.user_id, 0)
    return list(groups.values()), dropped, len(claimed)


async def _deliver(sender: webpush.WebPush, group: Group, now: datetime) -> webpush.Outcome:
    """Send one notification; never fails (a device that cannot be told now is tried again)."""
    try:
        return await sender.send(
            group.subscription,
            alert_message(group.alerts, group.origin, group.locale, group.unread),
            subject=group.origin,
            ttl=max(60, int((group.expires_at - now).total_seconds())),
            topic=f"alert-{min(alert.id for alert in group.alerts)}",
        )
    except Exception:
        log.exception("Push notification not sent to a device")
        return "retry"


async def _record(
    now: datetime, dropped: Sequence[int], results: Sequence[tuple[Group, webpush.Outcome]]
) -> None:
    done = list(dropped)
    async with async_session_factory() as db, db.begin():
        for group, result in results:
            if result == "gone":
                await forget_devices(db, PushSubscription.id == group.subscription_id)
                continue
            if result == "retry":
                attempts = group.attempts + 1
                wait = RETRY_MINUTES[min(attempts, len(RETRY_MINUTES)) - 1]
                retry_at = now + timedelta(minutes=wait)
                if retry_at < group.expires_at:
                    await db.execute(
                        update(PushDelivery)
                        .where(PushDelivery.id.in_(group.delivery_ids))
                        .values(attempts=attempts, next_attempt_at=retry_at),
                        execution_options=UNSYNCHRONIZED,
                    )
                else:
                    done.extend(group.delivery_ids)
                continue
            done.extend(group.delivery_ids)
            await db.execute(
                update(PushSubscription)
                .where(PushSubscription.id == group.subscription_id)
                .values(failures=0 if result == "delivered" else PushSubscription.failures + 1),
                execution_options=UNSYNCHRONIZED,
            )
        if done:
            await db.execute(
                delete(PushDelivery).where(PushDelivery.id.in_(done)),
                execution_options=UNSYNCHRONIZED,
            )
        await forget_devices(db, PushSubscription.failures >= MAX_FAILURES)


async def _send_all(groups: Sequence[Group], now: datetime) -> list[tuple[Group, webpush.Outcome]]:
    results: list[tuple[Group, webpush.Outcome]] = []
    sender = new_sender()
    if sender is None:
        return results
    try:
        gone: set[int] = set()
        for group in groups:
            # Its push service forgot the device: what else was queued for it goes with it.
            if group.subscription_id in gone:
                continue
            result = await _deliver(sender, group, now)
            if result == "gone":
                gone.add(group.subscription_id)
            results.append((group, result))
    finally:
        await sender.close()
    return results


async def push_round(now: datetime | None = None) -> int:
    """Send the notifications due at ``now`` and record the outcome; how many deliveries the round
    claimed (a full ``BATCH`` means more may be waiting)."""
    if not push_available():
        return 0
    now = now or datetime.now(UTC)
    groups, dropped, claimed = await _claim(now)
    results = await _send_all(groups, now) if groups else []
    if dropped or results:
        await _record(now, dropped, results)
    delivered = sum(result == "delivered" for _, result in results)
    if delivered:
        log.info("Push notifications delivered: %d", delivered)
    return claimed


async def push_loop() -> None:
    """Send queued notifications as soon as ``wake_push`` says there are new ones, and the
    retries every ``POLL_SECONDS``. Runs in the web process, started by the app's lifespan."""
    global _wake_event
    _wake_event = asyncio.Event()
    try:
        while True:
            _wake_event.clear()
            try:
                while await push_round() >= BATCH:
                    pass
            except Exception:
                log.exception("Push notification round failed; queued notifications retained")
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=POLL_SECONDS)
            except TimeoutError:
                pass
    finally:
        _wake_event = None
