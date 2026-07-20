"""Seed script: insert sample notifications so the bell can be tested.

Usage
─────
    python scripts/seed_notifications.py                     # first user, insert only
    python scripts/seed_notifications.py --user-id 1         # explicit user id
    python scripts/seed_notifications.py --username david    # explicit username
    python scripts/seed_notifications.py --push              # also deliver via Telegram
    python scripts/seed_notifications.py --clear             # delete seed rows instead

Inside Docker:
    docker exec -it <container> python scripts/seed_notifications.py [flags]

The four demo rows use source='seed', which no detector owns, so they are never
auto-resolved by the background loop and persist through GET /notifications.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from finlytics.db.models import Notification, User
from finlytics.db.session import async_session_factory

# ── Sample notification specs ─────────────────────────────────────────────────
# source='seed' is intentionally not in the detector REGISTRY so the background
# loop's auto-resolve step (scoped to detector.id) never clears these rows.

_SEEDS: list[dict] = [
    {
        "dedup_key": "seed:demo:1",
        "source": "seed",
        "type": "missing_statement",
        "severity": "warning",
        "title_key": "notif.statement_missing",
        "title_args": {"account": "BBVA", "month": "2026-06"},
        "action_link": "/finances",
    },
    {
        "dedup_key": "seed:demo:2",
        "source": "seed",
        "type": "missing_statement",
        "severity": "warning",
        "title_key": "notif.statement_missing",
        "title_args": {"account": "ING", "month": "2026-05"},
        "action_link": "/finances",
    },
    {
        "dedup_key": "seed:demo:3",
        "source": "seed",
        "type": "espp_overdue",
        "severity": "warning",
        "title_key": "notif.espp_overdue",
        "title_args": {"period": "Q2 2026"},
        "action_link": "/investments/fidelity-espp",
    },
    {
        "dedup_key": "seed:demo:4",
        "source": "seed",
        "type": "espp_overdue",
        "severity": "info",
        "title_key": "notif.espp_overdue",
        "title_args": {"period": "Q1 2026"},
        "action_link": "/investments/fidelity-espp",
    },
]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def _resolve_user(session, user_id: int | None, username: str | None) -> User:
    if user_id is not None:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            print(f"[seed_notifications] ERROR: No user found with id={user_id}.", file=sys.stderr)
            sys.exit(1)
        return user
    if username is not None:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None:
            print(
                f"[seed_notifications] ERROR: No user found with username={username!r}.",
                file=sys.stderr,
            )
            sys.exit(1)
        return user
    # Default: first user by lowest id
    result = await session.execute(select(User).order_by(User.id.asc()).limit(1))
    user = result.scalar_one_or_none()
    if user is None:
        print(
            "[seed_notifications] ERROR: No users in the database. Run the app setup first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return user


async def run(user_id: int | None, username: str | None, push: bool, clear: bool) -> None:
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        async with session.begin():
            user = await _resolve_user(session, user_id, username)

            if clear:
                result = await session.execute(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.source == "seed",
                    )
                )
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                print(
                    f"{_ts()} seed_notifications — cleared {len(rows)} seed row(s) "
                    f"for user '{user.username}' (id={user.id})."
                )
                print(
                    "  Run again without --clear to re-insert them."
                )
                return

            inserted: list[Notification] = []
            skipped = 0

            for spec in _SEEDS:
                result = await session.execute(
                    select(Notification).where(
                        Notification.user_id == user.id,
                        Notification.dedup_key == spec["dedup_key"],
                    )
                )
                if result.scalar_one_or_none() is not None:
                    skipped += 1
                    continue

                notif = Notification(
                    user_id=user.id,
                    source=spec["source"],
                    type=spec["type"],
                    severity=spec["severity"],
                    dedup_key=spec["dedup_key"],
                    title_key=spec["title_key"],
                    title_args=spec["title_args"],
                    body_key=None,
                    body_args=None,
                    action_link=spec["action_link"],
                    created_at=now,
                    updated_at=now,
                )
                session.add(notif)
                await session.flush()  # populate notif.id
                inserted.append(notif)

        print(
            f"{_ts()} seed_notifications — "
            f"{len(inserted)} inserted, {skipped} skipped "
            f"(user '{user.username}', id={user.id})."
        )

    if push and inserted:
        from finlytics.notifications.service import deliver_new

        async with async_session_factory() as session:
            await deliver_new(session, user.id, inserted)
        print(f"  Telegram delivery attempted for {len(inserted)} notification(s).")
    elif push and not inserted:
        print("  --push: nothing new to deliver (all rows already existed).")

    if inserted:
        print("  Run again to verify idempotency (expect 0 inserted, 4 skipped).")
        print("  To clear:  python scripts/seed_notifications.py --clear")
    else:
        print("  All seed rows already present. Use --clear to reset.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert sample notifications for bell testing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--user-id", type=int, metavar="N", help="Target user by numeric id.")
    group.add_argument("--username", type=str, metavar="X", help="Target user by username.")
    parser.add_argument(
        "--push",
        action="store_true",
        help="Also deliver inserted notifications via Telegram (tests full pipeline).",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete seed rows (source='seed') for the target user instead of inserting.",
    )
    args = parser.parse_args()
    asyncio.run(run(args.user_id, args.username, args.push, args.clear))


if __name__ == "__main__":
    main()
