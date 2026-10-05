"""The Alembic chain, which only ever runs against PostgreSQL."""

from __future__ import annotations

import importlib.util
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy.engine import URL

from finlytics.db.repository import compute_dedup_hash
from tests.pg.support import REPO, query, run_alembic

_spec = importlib.util.spec_from_file_location(
    "m0024", REPO / "alembic" / "versions" / "0024_rekey_dedup_hash_on_account_id.py"
)
assert _spec and _spec.loader
m0024 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m0024)


def public_tables(url: URL) -> set[str]:
    rows = query(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {r["tablename"] for r in rows}


def public_types(url: URL) -> set[str]:
    rows = query(
        url,
        "SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
        "WHERE n.nspname = 'public' AND t.typtype = 'e'",
    )
    return {r["typname"] for r in rows}


def test_the_chain_downgrades_to_base_and_upgrades_again(empty_database):
    run_alembic(empty_database, "upgrade", "head")
    tables, types = public_tables(empty_database), public_types(empty_database)

    run_alembic(empty_database, "downgrade", "base")
    assert public_tables(empty_database) <= {"alembic_version"}
    assert public_types(empty_database) == set()

    run_alembic(empty_database, "upgrade", "head")
    assert (public_tables(empty_database), public_types(empty_database)) == (tables, types)


def transactions(url: URL) -> list[SimpleNamespace]:
    rows = query(
        url,
        "SELECT t.id, t.account_id, t.transaction_date, t.amount, t.description, t.detail, "
        "t.dedup_hash, a.name AS account_name "
        "FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id ORDER BY t.id",
    )
    return [SimpleNamespace(**dict(r)) for r in rows]


def new_key(row: SimpleNamespace, disambiguator: str | None = None) -> str:
    return compute_dedup_hash(
        row.account_id,
        row.transaction_date,
        row.amount,
        row.description,
        row.detail,
        disambiguator=disambiguator,
    )


def test_0024_rekeys_every_row_without_dropping_any(empty_database):
    url = empty_database
    run_alembic(url, "upgrade", "0023")
    query(
        url, "INSERT INTO accounts (id, name, type) VALUES (1, 'BBVA', 'bank'), (2, 'bbva', 'bank')"
    )
    query(
        url,
        "INSERT INTO import_runs (id, account_id, source_filename) "
        "VALUES (1, 1, 'bbva.pdf'), (2, 2, 'bbva-twin.pdf')",
    )
    june = date(2025, 6, 15)
    seed = [
        (1, Decimal("-42.1"), "LIDL", None),
        (1, Decimal("-42.10"), "LIDL", None),
        (2, Decimal("-42.10"), "LIDL", None),
        (1, Decimal(-60), "ADEUDO", "Recibo luz"),
        (1, Decimal(-60), "ADEUDO", "Recibo agua"),
    ]
    for i, (account_id, amount, description, detail) in enumerate(seed):
        # 0024 ignores the old keys, so any unique placeholder stands in for them.
        query(
            url,
            "INSERT INTO transactions (account_id, import_run_id, transaction_date, amount, "
            "currency, description, detail, dedup_hash) VALUES ($1, $1, $2, $3, 'EUR', $4, $5, $6)",
            account_id,
            june,
            amount,
            description,
            detail,
            f"pre-0024-{i}",
        )

    output = run_alembic(url, "upgrade", "head")

    assert "0024: 1 transaction(s)" in output
    rows = transactions(url)
    assert len(rows) == len(seed)
    upgraded = {r.id: r.dedup_hash for r in rows}
    spelled_twice = rows[1]
    assert upgraded == {
        r.id: new_key(r, f"legacy:{r.id}") if r is spelled_twice else new_key(r) for r in rows
    }

    run_alembic(url, "downgrade", "0023")

    # The old key ignored the case of the account name, so the twin collides too.
    rows = transactions(url)
    assert [r.dedup_hash for r in rows] == [
        m0024.account_name_key(r, f"legacy:{r.id}") if i in (1, 2) else m0024.account_name_key(r)
        for i, r in enumerate(rows)
    ]

    run_alembic(url, "upgrade", "head")
    assert {r.id: r.dedup_hash for r in transactions(url)} == upgraded


def category_colors(url: URL) -> dict[str, str]:
    return {r["name"]: r["color"] for r in query(url, "SELECT name, color FROM categories")}


def test_0025_recolours_only_categories_still_on_the_seeded_palette(empty_database):
    url = empty_database
    run_alembic(url, "upgrade", "0024")
    query(
        url,
        "INSERT INTO categories (name, is_base, color) VALUES "
        "('Groceries', true, '#22c55e'), ('Transport', true, '#3B82F6'), "
        "('Dining', true, '#123456'), ('Holidays', false, '#22c55e')",
    )

    run_alembic(url, "upgrade", "0025")
    assert category_colors(url) == {
        "Groceries": "#70912f",
        "Transport": "#4f86c6",
        "Dining": "#123456",
        "Holidays": "#22c55e",
    }

    run_alembic(url, "downgrade", "0024")
    assert category_colors(url) == {
        "Groceries": "#22c55e",
        "Transport": "#3b82f6",
        "Dining": "#123456",
        "Holidays": "#22c55e",
    }


def test_0026_backfills_the_usage_ledger(empty_database):
    url = empty_database
    run_alembic(url, "upgrade", "0025")
    user_id = query(
        url, "INSERT INTO users (username, password_hash) VALUES ('ada', 'x') RETURNING id"
    )[0]["id"]
    conversation_id = query(
        url,
        "INSERT INTO assistant_conversations (user_id, title) VALUES ($1, 'Budget') RETURNING id",
        user_id,
    )[0]["id"]
    query(
        url,
        "INSERT INTO assistant_messages "
        "(conversation_id, role, content, prompt_tokens, completion_tokens, total_tokens) VALUES "
        "($1, 'assistant', 'An answer', 100, 20, 120), "
        "($1, 'user', 'A failed turn', 50, 0, 50), "
        "($1, 'user', 'A question', NULL, NULL, NULL)",
        conversation_id,
    )

    run_alembic(url, "upgrade", "0026")
    rows = query(
        url,
        "SELECT user_id, conversation_id, total_tokens, answered FROM assistant_usage "
        "ORDER BY total_tokens DESC",
    )
    assert [tuple(r) for r in rows] == [
        (user_id, conversation_id, 120, True),
        (user_id, conversation_id, 50, False),
    ]

    run_alembic(url, "downgrade", "0025")
    assert "assistant_usage" not in public_tables(url)
