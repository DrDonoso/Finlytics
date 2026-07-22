## Learnings — 2026-07-22T17:04:25+02:00: FX-decouple (Model A) regression tests

**Context:** Shuri refactorizó el pipeline ESPP («Model A»): almacenar MSFT close_usd
para todos los días de mercado, sin depender del FX diario (intersección eliminada),
y convertir a EUR con un único rate en tiempo de lectura.

**Bugs corregidos (confirmados con probe Yahoo en vivo):**
- Bug-1: EURUSD=X no tiene filas de viernes → la intersección msft∩fx eliminaba viernes
- Bug-2: EURUSD close=null ciertos días → intersección descartaba ese cierre MSFT
- Bug-3: period2 = today-00:00-UTC excluía la barra en curso de hoy

**Tests añadidos — 30 tests en `tests/api/test_fx_decouple.py`:**
- TC-1 (3 pure + 1 async): Viernes aparece en serie y en upsert
- TC-2 (2 pure + 1 async): Día con FX nulo sigue produciendo punto; `_multi_values[0]` verifica 2 filas
- TC-3 (3 pure + 2 async): Hoy aparece; `_yahoo_get` params capturados para verificar period2=tomorrow
- TC-4 (4 pure): FX único consistente en ambas series; ratio vie/jue = ratio USD puro
- TC-5 (3 async + 1 pure): `backfill` retorna 5 (no 4) y 2 (no 1); `topup` upsert tiene N filas
- TC-6 (8 pure): Regresión completa — lunes/jueves sin cambios, KPI = último punto, contributions FX-free

**Técnica clave — `_multi_values[0]`:**
`pg_insert(Table).values(list_of_dicts)._multi_values[0]` tiene `len == número_de_filas`.
Permite verificar cuántas filas incluye el upsert sin compilar SQL ni parsear strings.
Válido en SQLAlchemy 2.x con PostgreSQL dialect.

**Técnica clave — captura de parámetros Yahoo:**
Para verificar que `_fetch_yahoo_history` pasa `period2=tomorrow`, parchear `_yahoo_get`
(no `httpx.AsyncClient`) y capturar el dict `params`. Más limpio que interceptar a nivel HTTP.

**Bug de infraestructura detectado y resuelto:**
`_make_db_session` en `tests/investments/test_market_data.py` solo configuraba
`scalar_one_or_none.return_value`. El nuevo `topup_recent_prices` usa `result.first()`.
Fix: añadir `first.return_value = None` (o fila mock) según `max_date_row`.

**Verificación:**
- Primera ejecución (código antiguo): 3 tests fallaban (Bug-1, Bug-2, Bug-3 detectados)
- Tras implementación Shuri + fix mock: **1325 passed, 2 skipped, 0 failed**



**Context:** El owner eligió OPTION B: las transacciones `is_system=True` ("Saldo inicial")
ahora son VISIBLES en el ledger pero siguen EXCLUIDAS de todos los KPIs.
Shuri implementó los cambios en `queries.py`, `schemas.py`, `models.py` y `repository.py`.

**Cambios en tests/api/test_is_system.py (este trabajo):**
- Docstring del módulo actualizado para reflejar OPTION B (ledger visible, KPIs excluyen).
- Comentario de cabecera TC-9 corregido de "excluido del ledger" a "VISIBLE en el ledger (OPTION B)".
- Nombre de función TC-9 renombrado: `test_integration_transactions_ledger_excludes_opening_balance`
  → `test_integration_transactions_ledger_includes_opening_balance`.

**Estado pre-tarea:** El archivo ya tenía las ASERCIONES de TC-9 correctas (total==3, is_system checks)
y TC-10 actualizado (total==3, "Saldo inicial" in descs). Solo los nombres/comentarios estaban desactualizados.

**Hallazgos — 0 bugs:**
- TC-1..TC-7 (KPIs): PASAN — aggregaciones siguen excluyendo is_system=True ✅
- TC-9 (ledger): PASA — `get_transactions` retorna 3 txs con `is_system` en el dict ✅
- TC-9 is_system field: `opening_item["is_system"] is True`, normales tienen False ✅
- `TransactionOut.is_system: bool = False` presente en schemas.py ✅
- test_transactions.py ya verifica `is_system` en el schema del endpoint HTTP ✅
- TC-8a/b, TC-10: sin cambios, todos PASAN ✅

**Cambios de Shuri verificados:**
- `get_transactions` → `Transaction.is_system` en SELECT + `exclude_system=False` + `"is_system": bool(row["is_system"])` en items ✅
- `TransactionOut` → campo `is_system: bool = False` añadido ✅
- `_apply_filters(exclude_system: bool = True)` → parámetro que todas las agregaciones KPI usan por defecto (sin cambiar sus call-sites) ✅

**Suite completa:** 1290 passed, 2 skipped, 0 failed.



**Context:** Shuri implementó `Transaction.is_system` (migración 0017) para marcar
transacciones sintéticas ("Saldo inicial") y excluirlas de todas las agregaciones KPI.
Escribí tests de integración comprensivos para verificar la exclusión end-to-end.

**Tests añadidos — 15 tests en `tests/api/test_is_system.py` (archivo pre-existente):**
Shuri ya había creado 4 tests básicos (SQL unit + 1 API happy-path). Extendí a 15
tests en 3 capas:
1. SQL unit: `_apply_filters` genera `WHERE is_system = false` por defecto.
2. API mock: happy-path de GET /api/summary/overview (de Shuri).
3. Integration (StaticPool + aiosqlite): TC-1 al TC-10, SQL real ejecutado.

**Técnica clave — BigInteger PRIMARY KEY en SQLite:**
`Transaction.id` usa `BigInteger`, que SQLAlchemy renderiza como `BIGINT NOT NULL` en
SQLite (NO como `INTEGER PRIMARY KEY`). SQLite solo auto-genera rowid para columnas
exactamente `INTEGER PRIMARY KEY`. Solución: **proveer IDs explícitos** (`id=1`, `id=2`,
`id=3`) al crear `Transaction` en tests de integración.

**Técnica clave — shim to_char para SQLite:**
`get_by_month` y `get_by_day` usan `func.to_char(date, "YYYY-MM")` (PostgreSQL).
En SQLite, se registra `to_char` como función custom vía:
```python
@event.listen(eng.sync_engine, "connect")
def _register_to_char(dbapi_conn, _):
    dbapi_conn.create_function("to_char", 2, _to_char_shim)
```
`dbapi_conn` es `AsyncAdapt_aiosqlite_connection` cuyo `.create_function()` es
**síncrono** (verificado con `inspect.iscoroutinefunction == False`). El shim extrae
el prefijo de la fecha string (`str(val)[:7]` para "YYYY-MM").

**Resultado:** NO se encontraron bugs. Todos los 10 TCs pasan. La implementación de
Shuri es correcta — `_apply_filters(exclude_system=True)` cubre todas las funciones
de agregación que lo usan (`get_overview`, `get_by_category`, `get_by_merchant`,
`get_by_month`, `get_by_day`, `get_by_account`, `get_cashflow`, `get_transactions`).

**Comportamiento de get_transactions con is_system:** Excluye por defecto
(llama a `_apply_filters` sin `exclude_system=False`), igual que las demás agregaciones.

**Suite completa:** 1290 passed, 2 skipped, 0 failed.

---

## Learnings — 2026-07-21T13:31:05+02:00: confirm_import opening_balance edge-case tests

**Context:** Fury propuso captura de `opening_balance` en el flujo de importación para
cuentas nuevas. Shuri implementará en `ConfirmIn` + `confirm_import`. Escribí los
edge-case tests (10 tests) antes de que Shuri termine, en modo TDD.

**Key implementation insight — patch de ImportRun para tests multi-run:**
Al usar `session.add(real_ImportRun)` en el código, el `import_run.id` queda `None`
porque no hay DB real. `_persist_import_run` construye `ImportResult(import_run_id=None)`
→ Pydantic ValidationError. La solución: **parchear `finlytics.api.imports.ImportRun`
con un `side_effect` diferenciado por `source_filename`:**
```python
def _make_ir_side_effect(opening_run, main_run):
    def _factory(**kw):
        sfn = kw.get("source_filename", "")
        if "saldo" in sfn.lower():
            opening_run.source_filename = sfn
            opening_run.period = kw.get("period")
            opening_run.num_parsed = kw.get("num_parsed")
            return opening_run  # MagicMock inspeccionable
        return main_run  # MagicMock con id=42
    return _factory
```
- `opening_run` recibe los atributos para inspección de fecha/num_parsed/source_filename.
- `main_run` tiene `id=42` para que ImportResult pase validación Pydantic.
- `mock_ir_class.call_count` distingue "opening tx creado" (2 calls) de "no creado" (1 call).

**Para tests "no opening tx":** usar `return_value=fake_main_run` (1 solo valor),
NO `side_effect`, para que el único ImportRun call devuelva el main_run correcto.

**Bug potencial documentado:**
`min()` en lista vacía lanza `ValueError`. Si `transactions=[]` y `opening_balance != 0`,
Shuri DEBE añadir guard `if body.transactions:` antes de calcular `opening_date`.
TC-9 verifica este caso. Actualmente pasa porque `opening_balance` aún no existe en
`ConfirmIn` (Pydantic ignora el campo extra), pero fallará el bug si no se añade guard.

**Señal observable para "opening tx creado":**
- `mock_ir_class.call_count == 2` (opening + main)
- Primer call tiene `source_filename` con "saldo"
- `opening_run.period == "2024-04"` verifica inferencia de fecha (TC-7)
- `opening_run.num_inserted == 0` + `num_duplicates == 1` verifica dedup DB-level (TC-8a)

**Estado tests:** **11/11 PASS** contra la implementación de Shuri. Suite completa: 683 tests, 0 fallos.

---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

## Learnings — 2026-07-21T11:30:13+02:00: POST /api/accounts edge-case tests

**Context:** Shuri implemented `POST /api/accounts` with synthetic "Saldo inicial" transaction. I wrote the edge-case tests.

**Key implementation details discovered:**
- Transaction is inserted via `pg_insert(...).on_conflict_do_nothing()` → `session.execute()`, NOT `session.add()`. Cannot inspect Transaction via `mock_session.add.call_args_list`.
- ImportRun IS created via `session.add()` — serves as the observable proxy for "a transaction was created".
- Duplicate detection uses SELECT-first (not IntegrityError catch). Configure `mock_session.execute.side_effect=[no_conflict, conflict]` for multi-check tests.
- `_make_no_conflict_session` (Shuri's helper) uses `return_value` (same mock for all calls). Tests needing distinct returns per call must use `side_effect=[m1, m2, ...]`.
- `compute_dedup_hash` is importable from `finlytics.db.repository` and patchable via `finlytics.api.accounts.compute_dedup_hash` to inspect exact call kwargs.

**Pattern confirmed:** `AsyncMock.__aexit__` returns falsy → HTTPException raised inside `async with session.begin():` propagates correctly to FastAPI.

**Test helpers added:**
- `_pg_insert_ok()` — simulates a real insert return (scalar_one_or_none = 999).
- `_track_session_adds(mock_session)` — captures session.add() args for type inspection.

**Result:** 11 edge-case tests added; 669 total pass, 0 failures.


---

## 2026-07-21: QA Report — POST /api/accounts edge-case tests

**Status:** ✅ All 669 tests pass (11 new edge-case tests added).

**Summary:** Tested Shuri's POST /api/accounts implementation for edge cases. No bugs found. Test coverage spans negative balances, opening transaction fields, dedup determinism, ImportRun metadata, zero-balance guard, and currency pass-through.

**Test Coverage:**
- Negative opening_balance (overdraft) — dedup amount is negative
- Opening transaction fields — description, date, amount validation
- Dedup hash determinism — SHA-256, 64 hex chars
- ImportRun metadata — source_filename, period, insert counters
- Zero opening_balance guard — no ImportRun/Transaction created
- Currency pass-through — EUR/USD stored correctly
- IBAN masking verification
- Duplicate name/IBAN rejection (409)
- Empty/whitespace name rejection (422)

**Test Infrastructure:**
- Added _pg_insert_ok() helper for mock pg_insert success
- Added _track_session_adds() helper to capture session.add() calls

**Design Observations:**
- pg_insert design is testable via ImportRun proxy + hash validation
- KPI skew is documented, not a bug

**Related:** Orchestration log: .squad/orchestration-log/2026-07-21T09-23-28Z-barton.md


## Session: 2026-07-21 — is_system implementation (slice complete)

**Collaborators:** Shuri, Vision, Barton, Fury  
**Status:** ✅ IMPLEMENTED + APPROVED  
**Decisions:** .squad/decisions.md (merged from inbox), .squad/orchestration-log/  
**Session Log:** .squad/log/2026-07-21T16-59-22Z-is-system-kpi-exclusion.md

**Summary:** Full squad execution: migration 0017 (Shuri), frontend badge (Vision), 15 tests (Barton), architecture review (Fury). Owner approved OPTION B (ledger-visible, KPI-excluded). No defects. Ready for merge.

**Cross-agent refs:**
- Shuri: orchestration-log/2026-07-21T16-59-22Z-shuri.md
- Vision: orchestration-log/2026-07-21T16-59-22Z-vision.md
- Barton: orchestration-log/2026-07-21T16-59-22Z-barton.md
- Fury: orchestration-log/2026-07-21T16-59-22Z-fury.md

