"""Tests de edge-cases para opening_balance en POST /api/imports/confirm.

Contrato a verificar (diseñado por Fury, implementado por Shuri):
  - Cuenta NUEVA (por IBAN): opening_balance != 0 → se crea ImportRun "Saldo inicial"
    con date = min(tx_dates) - 1 dia.
  - Cuenta NUEVA (por nombre): mismo comportamiento.
  - Cuenta EXISTENTE: opening_balance ignorado, no se crea tx sintetica.
  - opening_balance = 0 o None: no se crea tx sintetica.
  - opening_balance negativo (sobregiro): se crea tx con amount negativo.
  - Inferencia de fecha: min(transaction_date) - 1, aunque las txs lleguen desordenadas.
  - Idempotencia DB-level: conflicto dedup_hash -> ImportRun creado pero num_inserted=0.
  - Idempotencia call-level: 2a llamada con cuenta ya existente -> no crea opening tx.
  - Lista de txs vacia con opening_balance -> no crash, no tx sintetica.

Happy-path test: Shuri la anhade en su PR. Aqui solo edge-cases.

Nota de implementacion: se parchea ``finlytics.api.imports.ImportRun`` para controlar
los ids (necesario para que ImportResult pase validacion Pydantic). El parche usa
``side_effect`` diferenciado por ``source_filename`` para distinguir ImportRun de
apertura (source_filename="manual:saldo-inicial", mock con atributos inspeccionables)
del ImportRun principal (mock con id=42). Los tests para "no opening tx" usan un
unico ``return_value=fake_run``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from finlytics.db.models import Account


_IBAN = "ES7921000813610123456789"
_NAME = "MiBBVA"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _no_match() -> MagicMock:
    """execute() -> None: cuenta no existe."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _match(account: MagicMock) -> MagicMock:
    """execute() -> cuenta existente."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = account
    return m


def _pg_insert_ok() -> MagicMock:
    """execute(pg_insert) -> id: INSERT exitoso."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = 999
    return m


def _pg_insert_conflict() -> MagicMock:
    """execute(pg_insert) -> None: ON CONFLICT DO NOTHING activado."""
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _fake_account(account_id: int = 10, name: str = _NAME) -> MagicMock:
    acc = MagicMock(spec=Account)
    acc.id = account_id
    acc.name = name
    return acc


def _fake_main_run() -> MagicMock:
    """ImportRun mock con id=42 para el import principal."""
    run = MagicMock()
    run.id = 42
    return run


def _tx(d: str, amount: float = -10.0, account_ref: str = _NAME) -> dict:
    return {
        "transaction_date": d,
        "amount": amount,
        "currency": "EUR",
        "description": "MERCADONA",
        "category": "Groceries",
        "account_ref": account_ref,
    }


def _make_ir_side_effect(opening_run: MagicMock, main_run: MagicMock):
    """Callable para patch(ImportRun) que distingue apertura de main por source_filename.

    - source_filename contiene 'saldo' -> devuelve opening_run (propagando atributos
      para inspeccion en asserts).
    - cualquier otro source_filename -> devuelve main_run (id=42, respuesta valida).
    """
    def _factory(**kw):
        sfn = kw.get("source_filename", "")
        if "saldo" in sfn.lower():
            opening_run.source_filename = sfn
            opening_run.period = kw.get("period")
            opening_run.num_parsed = kw.get("num_parsed")
            # id permanece None: sin DB real. pg_insert usa import_run_id=None,
            # lo cual es inocuo en tests donde execute() esta mockeado.
            return opening_run
        return main_run
    return _factory


# ---------------------------------------------------------------------------
# TC-1: Cuenta nueva por IBAN + opening_balance > 0
# ---------------------------------------------------------------------------

async def test_confirm_new_iban_with_opening_balance_creates_opening_run(
    client, mock_session
):
    """Cuenta nueva (IBAN no visto) + opening_balance > 0 -> ImportRun 'saldo-inicial'."""
    opening_run = MagicMock()
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        # _persist_import_run (imports.py) usa main_run con id=42
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        # create_opening_balance_tx (repository.py) usa su propio ImportRun
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    # opening_date = 2024-06-01 - 1 = 2024-05-31 -> period "2024-05"
    assert opening_run.source_filename is not None, (
        "Debe crearse un ImportRun de saldo inicial"
    )
    assert "saldo" in str(opening_run.source_filename).lower()
    assert opening_run.num_parsed == 1
    assert opening_run.period == "2024-05", (
        f"opening_date=2024-05-31 -> period='2024-05', got: {opening_run.period!r}"
    )


# ---------------------------------------------------------------------------
# TC-2: Cuenta nueva por NOMBRE + opening_balance > 0
# ---------------------------------------------------------------------------

async def test_confirm_new_name_with_opening_balance_creates_opening_run(
    client, mock_session
):
    """Cuenta nueva (nombre no visto) + opening_balance > 0 -> ImportRun 'saldo-inicial'."""
    opening_run = MagicMock()
    opening_run.source_filename = None  # indica "no fue creado" si sigue None
    opening_run.id = None
    main_run = _fake_main_run()

    # Shuri puede hacer 1 o 2 SELECTs por nombre antes del pg_insert;
    # items extra en side_effect no usados son inocuos.
    mock_session.execute = AsyncMock(
        side_effect=[_no_match(), _no_match(), _pg_insert_ok()]
    )

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "source_filename": "banco.pdf",
                "opening_balance": 800.0,
                "transactions": [_tx("2024-07-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "Cuenta nueva por nombre: debe crearse ImportRun de saldo inicial"
    )
    assert "saldo" in str(opening_run.source_filename).lower()


# ---------------------------------------------------------------------------
# TC-3: Cuenta EXISTENTE + opening_balance -> ignorado
# ---------------------------------------------------------------------------

async def test_confirm_existing_iban_opening_balance_is_ignored(
    client, mock_session
):
    """Cuenta ya existente + opening_balance -> NO se crea ImportRun sintetico."""
    existing = _fake_account()
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(return_value=_match(existing))

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 9999.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    # Solo 1 ImportRun creado (el principal), nada de apertura
    assert mock_ir_class.call_count == 1, (
        "Cuenta existente: solo 1 ImportRun (el principal), no el de apertura"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-4: opening_balance = 0 -> no tx sintetica
# ---------------------------------------------------------------------------

async def test_confirm_zero_opening_balance_no_opening_tx(client, mock_session):
    """opening_balance=0 -> no se crea ImportRun de saldo inicial."""
    main_run = _fake_main_run()
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 0.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, "opening_balance=0 -> solo 1 ImportRun"
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-5: opening_balance = null -> no tx sintetica
# ---------------------------------------------------------------------------

async def test_confirm_null_opening_balance_no_opening_tx(client, mock_session):
    """opening_balance omitido (None) -> no se crea ImportRun de saldo inicial."""
    main_run = _fake_main_run()
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, "opening_balance=null -> solo 1 ImportRun"


# ---------------------------------------------------------------------------
# TC-6: opening_balance negativo (sobregiro)
# ---------------------------------------------------------------------------

async def test_confirm_negative_opening_balance_creates_opening_run(
    client, mock_session
):
    """opening_balance negativo -> ImportRun de saldo inicial creado (amount negativo valido)."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": -500.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "opening_balance negativo debe crear ImportRun de saldo inicial"
    )
    assert "saldo" in str(opening_run.source_filename).lower()
    assert opening_run.num_parsed == 1


# ---------------------------------------------------------------------------
# TC-7: Inferencia de fecha -- earliest tx - 1 dia (txs desordenadas)
# ---------------------------------------------------------------------------

async def test_confirm_opening_tx_date_is_earliest_tx_minus_one_day(
    client, mock_session
):
    """opening_date = min(transaction_date) - 1 dia, incluso con txs desordenadas."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    # Txs desordenadas: minimo es 2024-05-01 -> opening_date = 2024-04-30 -> period "2024-04"
    transactions = [
        _tx("2024-06-15"),
        _tx("2024-05-01"),  # <- minimo
        _tx("2024-06-01"),
    ]

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(3, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": transactions,
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None
    # min(2024-06-15, 2024-05-01, 2024-06-01) = 2024-05-01
    # opening_date = 2024-04-30 -> period = "2024-04"
    assert opening_run.period == "2024-04", (
        f"Txs desordenadas: opening_date debe ser 2024-04-30 (min-1), "
        f"period='2024-04'. Got: {opening_run.period!r}"
    )


# ---------------------------------------------------------------------------
# TC-8a: Idempotencia DB-level (conflicto dedup_hash)
# ---------------------------------------------------------------------------

async def test_confirm_opening_tx_dedup_conflict_sets_num_inserted_zero(
    client, mock_session
):
    """ON CONFLICT DO NOTHING -> ImportRun creado pero num_inserted=0, num_duplicates=1."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    # pg_insert devuelve None -> scalar_one_or_none()=None -> conflicto activado
    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_conflict()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(1, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run),
        patch("finlytics.db.repository.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1000.0,
                "transactions": [_tx("2024-06-01")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert opening_run.source_filename is not None, (
        "El ImportRun de apertura debe crearse aunque haya conflicto de dedup"
    )
    # Shuri asigna estos atributos despues del execute:
    assert opening_run.num_inserted == 0, (
        "Conflicto de dedup_hash: num_inserted debe ser 0"
    )
    assert opening_run.num_duplicates == 1, (
        "Conflicto de dedup_hash: num_duplicates debe ser 1"
    )


# ---------------------------------------------------------------------------
# TC-8b: Idempotencia call-level (2a llamada con cuenta existente)
# ---------------------------------------------------------------------------

async def test_confirm_second_call_existing_account_no_opening_tx(
    client, mock_session
):
    """2a confirm con la misma cuenta (ya creada) -> opening_balance ignorado."""
    existing = _fake_account(account_id=15)
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(return_value=_match(existing))

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(2, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco2.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-07-01"), _tx("2024-07-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    assert mock_ir_class.call_count == 1, (
        "2a llamada (cuenta existente): solo ImportRun principal, no el de apertura"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-9: Lista vacia de txs + opening_balance -> sin crash, sin opening tx
# ---------------------------------------------------------------------------

async def test_confirm_empty_transactions_with_opening_balance_no_crash(
    client, mock_session
):
    """transactions=[] con opening_balance -> 200 OK, sin tx sintetica.

    Bug potencial: min() de lista vacia lanzaria ValueError si Shuri no
    protege el bloque de calculo de opening_date con un guard previo.
    """
    main_run = _fake_main_run()

    # Sin txs, Shuri no debe llegar al pg_insert -> un solo execute (SELECT de IBAN)
    mock_session.execute = AsyncMock(return_value=_no_match())

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(0, 0)),
        patch("finlytics.api.imports.ImportRun", return_value=main_run) as mock_ir_class,
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [],
            },
        )

    assert resp.status_code == 200, (
        f"transactions=[] + opening_balance no debe causar crash. "
        f"Got {resp.status_code}: {resp.text}"
    )
    assert mock_ir_class.call_count == 1, (
        "Sin txs: solo el ImportRun principal, no el de apertura"
    )
    only_kw = mock_ir_class.call_args.kwargs
    assert "saldo" not in only_kw.get("source_filename", "").lower()


# ---------------------------------------------------------------------------
# TC-10: Sanidad -- response estructura valida con opening_balance
# ---------------------------------------------------------------------------

async def test_confirm_with_opening_balance_returns_valid_import_result(
    client, mock_session
):
    """El endpoint devuelve ImportResult completo y valido aunque haya opening_balance."""
    opening_run = MagicMock()
    opening_run.source_filename = None
    opening_run.id = None
    main_run = _fake_main_run()

    mock_session.execute = AsyncMock(side_effect=[_no_match(), _pg_insert_ok()])

    with (
        patch("finlytics.api.imports.upsert_transactions", new_callable=AsyncMock,
              return_value=(2, 0)),
        patch("finlytics.api.imports.ImportRun",
              side_effect=_make_ir_side_effect(opening_run, main_run)),
    ):
        resp = await client.post(
            "/api/imports/confirm",
            json={
                "account_name": _NAME,
                "account_number": _IBAN,
                "source_filename": "banco.pdf",
                "opening_balance": 1500.0,
                "transactions": [_tx("2024-06-01"), _tx("2024-06-15")],
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body.keys()) >= {"import_run_id", "num_parsed", "num_inserted", "num_duplicates"}
    assert body["import_run_id"] == 42  # id del ImportRun principal (main_run.id)
    assert body["num_parsed"] == 2
    assert body["num_inserted"] == 2
    assert body["num_duplicates"] == 0
