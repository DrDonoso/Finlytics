"""Push notification devices (``notifications/push.py``).

Routes
──────
  GET  /api/push               — the key browsers subscribe with (null: unavailable)
  PUT  /api/push/subscription  — register this device, or refresh its registration
  POST /api/push/unsubscribe   — stop this device's notifications
  POST /api/push/test          — send this device a test notification

The interface registers the device again each time it opens, so its session,
language and origin stay current. Push services' addresses are never logged.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finlytics.api.deps import CurrentSession, get_current_session, get_current_user, get_db
from finlytics.api.schemas import PushConfigOut, PushEndpointIn, PushSubscriptionIn, PushTestOut
from finlytics.db.models import PushSubscription, User
from finlytics.notifications import push, webpush

router = APIRouter(prefix="/push", tags=["push"])

_UNAVAILABLE = "Push notifications need AUTH_SECRET to be set on the server."


@router.get("", response_model=PushConfigOut)
async def push_config() -> PushConfigOut:
    return PushConfigOut(public_key=push.public_key())


@router.put("/subscription", status_code=204)
async def subscribe(
    body: PushSubscriptionIn,
    request: Request,
    session: CurrentSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Register the device for the signed-in session. 422 when its browser uses a push service
    Finlytics does not send to, or the page is not served over HTTPS (or localhost)."""
    if not push.push_available():
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    if webpush.push_service(body.endpoint) is None:
        raise HTTPException(status_code=422, detail="This browser's push service is not supported.")
    try:
        webpush.browser_key(body.keys.p256dh)
        webpush.browser_auth(body.keys.auth)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid push subscription keys.") from None
    origin = push.device_origin(request.headers.get("origin"))
    if origin is None:
        raise HTTPException(
            status_code=422, detail="Push notifications need Finlytics to be served over HTTPS."
        )
    await push.register_device(
        db,
        user_id=session.user.id,
        token_version=session.user.token_version,
        session_jti=session.jti,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        origin=origin,
        locale=body.locale,
        now=datetime.now(UTC),
    )
    await db.commit()


@router.post("/unsubscribe", status_code=204)
async def unsubscribe(
    body: PushEndpointIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Forget this device (nothing happens unless it is registered for the signed-in user)."""
    await push.forget_devices(
        db, PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id
    )
    await db.commit()


@router.post("/test", response_model=PushTestOut)
async def send_test(
    body: PushEndpointIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PushTestOut:
    """Send this device a test notification; 404 when it is not registered."""
    device = await db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id
        )
    )
    if device is None:
        raise HTTPException(status_code=404, detail="This device has no notifications turned on.")
    sender = push.new_sender()
    if sender is None:
        raise HTTPException(status_code=503, detail=_UNAVAILABLE)
    locale: push.Locale = "en" if device.locale == "en" else "es"
    try:
        result = await sender.send(
            webpush.Subscription(device.endpoint, device.p256dh, device.auth),
            push.test_message(device.origin, locale),
            subject=device.origin,
            ttl=600,
            urgency="high",
            topic="test",
        )
    finally:
        await sender.close()
    if result == "delivered":
        return PushTestOut(ok=True)
    if result == "gone":
        await push.forget_devices(db, PushSubscription.id == device.id)
        await db.commit()
        return PushTestOut(ok=False, error="gone")
    return PushTestOut(ok=False, error="unreachable" if result == "retry" else "rejected")
