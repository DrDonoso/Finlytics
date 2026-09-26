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
