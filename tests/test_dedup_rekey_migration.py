"""Tests for migration 0024, which re-keys dedup_hash on the account id."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from finlytics.db.models import Account, Base, ImportRun, Transaction
from finlytics.db.repository import compute_dedup_hash

_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "0024_rekey_dedup_hash_on_account_id.py"
)
_spec = importlib.util.spec_from_file_location("migration_0024", _PATH)
assert _spec is not None and _spec.loader is not None
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


@pytest.fixture
def conn():
    engine = sa.create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            Account.__table__.insert(),
            [
                {"id": 1, "name": "BBVA", "type": "bank", "currency": "EUR"},
                {"id": 2, "name": "bbva", "type": "bank", "currency": "EUR"},
            ],
        )
        connection.execute(
            ImportRun.__table__.insert(),
            [
                {"id": 1, "account_id": 1, "source_filename": "a.pdf"},
                {"id": 2, "account_id": 2, "source_filename": "b.pdf"},
            ],
        )
        yield connection
    engine.dispose()


def _insert(conn, *rows: dict) -> None:
    conn.execute(
        Transaction.__table__.insert(),
        [
            {
                "import_run_id": row["account_id"],
                "currency": "EUR",
                "is_system": False,
                "detail": None,
                "dedup_hash": f"old-{row['id']}",
                **row,
            }
            for row in rows
        ],
    )


def _row(tx_id: int, account_id: int = 1, **overrides) -> dict:
    return {
        "id": tx_id,
        "account_id": account_id,
        "transaction_date": date(2024, 6, 1),
        "amount": Decimal("-42.50"),
        "description": "MERCADONA",
        **overrides,
    }


def _hashes(conn) -> dict[int, str]:
    t = Transaction.__table__
    return dict(conn.execute(sa.select(t.c.id, t.c.dedup_hash)).all())


def test_upgrade_writes_the_runtime_formula(conn):
    _insert(
        conn,
        _row(1),
        _row(2, amount=Decimal("3000.00"), description="Saldo inicial"),
        _row(3, description="ADEUDO", detail="GCREOCTOPUSENERGY"),
    )

    assert migration.rehash(conn, migration.account_id_key) == 0

    assert _hashes(conn) == {
        1: compute_dedup_hash(1, date(2024, 6, 1), Decimal("-42.5"), "MERCADONA"),
        2: compute_dedup_hash(1, date(2024, 6, 1), Decimal("3000"), "Saldo inicial"),
        3: compute_dedup_hash(
            1, date(2024, 6, 1), Decimal("-42.50"), "ADEUDO", detail="GCREOCTOPUSENERGY"
        ),
    }


def test_case_variant_accounts_no_longer_share_a_key(conn):
    _insert(conn, _row(1, account_id=1), _row(2, account_id=2))

    assert migration.rehash(conn, migration.account_id_key) == 0

    hashes = _hashes(conn)
    assert hashes[1] != hashes[2]


def test_key_survives_an_account_rename(conn):
    _insert(conn, _row(1))
    migration.rehash(conn, migration.account_id_key)
    before = _hashes(conn)

    conn.execute(sa.update(Account.__table__).where(Account.id == 1).values(name="Nómina"))
    migration.rehash(conn, migration.account_id_key)

    assert _hashes(conn) == before


def test_collisions_keep_the_oldest_row_and_delete_nothing(conn, monkeypatch):
    monkeypatch.setattr(migration, "_BATCH", 2)
    _insert(
        conn,
        _row(1, description="LIDL"),
        _row(2),
        _row(3),
        _row(4, amount=Decimal("-42.5")),
        _row(5, description="ALDI"),
    )

    assert migration.rehash(conn, migration.account_id_key) == 2

    natural = compute_dedup_hash(1, date(2024, 6, 1), Decimal("-42.50"), "MERCADONA")
    hashes = _hashes(conn)
    assert len(hashes) == 5
    assert hashes[2] == natural
    for tx_id in (3, 4):
        assert hashes[tx_id] == compute_dedup_hash(
            1, date(2024, 6, 1), Decimal("-42.50"), "MERCADONA",
            disambiguator=f"legacy:{tx_id}",
        )
    assert len(set(hashes.values())) == 5


def test_downgrade_restores_the_name_keyed_formula(conn):
    _insert(conn, _row(1), _row(2, account_id=2), _row(3, detail="Octopus"))
    migration.rehash(conn, migration.account_id_key)

    assert migration.rehash(conn, migration.account_name_key) == 1

    def legacy(amount: str, detail: str | None = None) -> str:
        text = json.dumps(
            {"account": "bbva", "date": "2024-06-01", "amount": amount,
             "description": "mercadona"},
            sort_keys=True,
        )
        if detail:
            text += "|" + detail
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    hashes = _hashes(conn)
    assert hashes[1] == legacy("-42.5")
    assert hashes[3] == legacy("-42.5", "octopus")
    assert hashes[2] not in (hashes[1], hashes[3])


@pytest.mark.parametrize(
    "amount, detail, disambiguator",
    [
        (Decimal("-42.10"), None, None),
        (Decimal("-42.1"), "  GCREOCTOPUSENERGY ", None),
        (Decimal("3000"), "", "legacy:9"),
        (Decimal("-0.00"), "   ", None),
        (Decimal("10.005"), None, "0f3c"),
    ],
)
def test_frozen_key_matches_compute_dedup_hash(amount, detail, disambiguator):
    """Tripwire: editing compute_dedup_hash without a new migration fails here."""
    row = SimpleNamespace(
        account_id=4,
        transaction_date=date(2025, 1, 31),
        amount=amount,
        description="  Mercadona ",
        detail=detail,
    )

    assert migration.account_id_key(row, disambiguator=disambiguator) == compute_dedup_hash(
        4, date(2025, 1, 31), amount, "  Mercadona ",
        detail=detail, disambiguator=disambiguator,
    )


def test_upgrade_logs_collisions(conn, monkeypatch, caplog):
    monkeypatch.setattr(
        migration,
        "op",
        SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=False), get_bind=lambda: conn),
    )
    _insert(conn, _row(1), _row(2))

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        migration.upgrade()

    assert "1 transaction(s)" in caplog.text


def test_offline_mode_is_refused(monkeypatch):
    monkeypatch.setattr(
        migration, "op", SimpleNamespace(get_context=lambda: SimpleNamespace(as_sql=True))
    )

    with pytest.raises(RuntimeError, match="offline"):
        migration.upgrade()
