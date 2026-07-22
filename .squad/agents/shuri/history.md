# Shuri — Backend Engineer

**Owner:** DrDonoso  
**Role:** API design, schemas, database, business logic  
**Created:** 2026-07-14

---

## SUMMARY

**Major Sessions:**
1. **Merchant Normalization Slice 1 (2026-07-16):** REVERTED per owner; fully implemented but not wanted.
2. **Fidelity ESPP, Indexa Capital, UX Batch (2026-07-15→16):** ✅ Complete.
3. **Notifications + Telegram (2026-07-17):** ✅ Complete; Telegram channel with Fernet encryption; 1239 tests pass.
4. **POST /api/accounts (2026-07-21):** ✅ Complete; manual account creation with optional opening balance.
5. **Import-time Opening Balance (2026-07-21):** ✅ Complete; opening_balance in ConfirmIn; DRY refactor of helper.
6. **is_system flag + KPI exclusion (2026-07-21):** ✅ Complete; migration 0017, model, helper, _apply_filters.
7. **is_system OPTION B — ledger visible (2026-07-21):** ✅ Complete; get_transactions muestra apertura, TransactionOut.is_system expuesto.
8. **FX Decouple Model-A — Evolution Chart Fix (2026-07-22):** ✅ Complete; viernes ya no caen del gráfico; period2 fix; single FX en read-time; gap recovery automático; no migración.

**Current Test Baseline:** 66 passed (targeted fidelity/evolution), suite completa pendiente de verificar.

---

## Key Technical Learnings

### ImportRun for Manual Transactions
`Transaction.import_run_id` NOT NULL. For any transaction outside import flow (e.g., opening balance, future manual adjustments), create synthetic `ImportRun` with `source_filename="manual:<type>"`.

### Dedup Pattern for Opening Balances
`compute_dedup_hash(account_ref=account_name, transaction_date=opening_date, amount=Decimal(...), description="Saldo inicial")`. Protects idempotence via `ON CONFLICT DO NOTHING`.

### KPI Skew — RESUELTO via is_system
Opening balance > 0 contaba como "income" en su mes (sin filtros en KPI queries). **Solucionado en migración 0017**: columna `is_system` Boolean (default false) + backfill via `source_filename = 'manual:saldo-inicial'` + `_apply_filters(exclude_system=True)` por defecto en todas las agregaciones. El ledger también excluye por defecto.

### Atomicity Pattern
Single `async with session.begin()` wraps Account + ImportRun + Transaction. Any failure → full rollback.

### pg_insert vs upsert_transactions
Use `pg_insert` directly when `category_id=None` (deliberate). `upsert_transactions` auto-resolves categories, incompatible with no-category transactions.

### Notifications Architecture
Detectors (statement_missing, espp_overdue) → UPSERT into `notifications` table → background loop evaluates daily → `deliver_new` sends Telegram. Telegram client: httpx AsyncClient, 10s timeout, token never logged. Message renderer: safe Spanish templates + generic fallback. Kill-switch: `telegram_send_enabled` env var.

### DRY Refactor: create_opening_balance_tx
Helper extracted to `repository.py` (shared by `POST /api/accounts` and `confirm_import`). Signature: `async def create_opening_balance_tx(session, account_id, account_name, account_currency, opening_balance, opening_date)`.

### was_created Detection in confirm_import
IBAN path: natural (SELECT returns None). Name path: add pre-SELECT `select(Account.id).where(Account.name == ...)` before `_resolve_account` to avoid changing its signature (preserves test assertions).

### Patch Paths in Tests
- `create_opening_balance_tx` in repository.py: patch `"finlytics.api.imports.create_opening_balance_tx"`
- `compute_dedup_hash` (now in repository.py, was in accounts.py): patch `"finlytics.db.repository.compute_dedup_hash"`

---

## Recent Slices (2026-07-21)

### 1. POST /api/accounts
- Creates account + optional opening balance transaction
- No migration required
- 10 new tests; 78 related tests pass

### 2. Import-time Opening Balance
- ConfirmIn += opening_balance field
- Auto-inferred opening_date = min(txs) − 1 day
- DRY: shared helper with POST /api/accounts
- 172 related tests pass; full suite 1275 passed

### 3. is_system flag + KPI exclusion (2026-07-21)
- Migration 0017: `is_system Boolean NOT NULL DEFAULT false` en `transactions`
- Backfill via `import_runs.source_filename = 'manual:saldo-inicial'` — señal fiable y estable
- `_apply_filters(exclude_system: bool = True)` — parámetro añadido; todas las agregaciones heredan el filtro por defecto sin cambios en sus call-sites
- Ledger (`get_transactions`) también excluye `is_system=True` por defecto → ledger y KPIs son coherentes
- **Flag para Vision**: si quieren mostrar saldo inicial en el ledger, necesitan `include_system=true` QP en `GET /api/transactions` (futuro trabajo de Shuri a petición)
- 4 tests nuevos en `tests/api/test_is_system.py`; suite 1279 passed

---

## Learnings

### Migración 0017 — is_system
- Número: `0017_add_transaction_is_system.py`, `down_revision = "0016"`.
- Backfill: `WHERE import_run_id IN (SELECT id FROM import_runs WHERE source_filename = 'manual:saldo-inicial')`.
- El backfill va DESPUÉS del `op.add_column` (la columna debe existir antes del UPDATE).

### _apply_filters exclude_system
- Parámetro `exclude_system: bool = True` al final de la firma.
- Filtro añadido como último `stmt.where(Transaction.is_system == False)` con `# noqa: E712` (SQLAlchemy requiere `==`, no `is`).
- Todos los call-sites heredan el default; no se necesita modificar ninguna función de agregación.

### Decisión de ledger
- ~~`get_transactions` excluye `is_system=True` por defecto~~ → **REVERTIDO a OPTION B (2026-07-21)**.
- `get_transactions` ahora pasa `exclude_system=False` → apertura VISIBLE en el ledger con campo `is_system=True` para badge frontend.
- KPIs siguen con `exclude_system=True` (default de `_apply_filters`) — no se tocaron.

### is_system — OPTION B: ledger visible (2026-07-21)

- `Transaction.is_system` proyectado en el SELECT de `get_transactions`; incluido en dict de items como `"is_system": bool(row["is_system"])`.
- `TransactionOut.is_system: bool = False` — default False para retrocompatibilidad de mocks.
- TC-9 y TC-10 en `test_is_system.py` actualizados: apertura visible, `total == 3`. **Barton NO debe tocar TC-9/TC-10.**
- `test_transactions.py` fixture `_TX` + dos tests de schema keys actualizados para incluir `is_system`.
- Nota a Vision: totales de importe en página de transacciones deben venir de `get_overview`, NO de sumar rows del ledger.
- Suite tras cambios: **225 passed, 473 deselected** (subconjunto transaction/summary/overview/opening/system).

### FX Decouple — Model-A (2026-07-22)

**Causa raíz viernes caídos:** `EURUSD=X` en Yahoo NUNCA devuelve barras los viernes (rollover FX fin de semana). La lógica `common = set(msft_map) & set(fx_map)` descartaba todos los viernes. También `period2 = _to_unix(date.today())` era medianoche UTC → excluía el día actual.

**Model-A aprobado:** Desacoplar FX del almacenamiento diario de equity. Almacenar TODOS los días MSFT; convertir a EUR en read-time con UN SOLO FX latest.

**Lookback 90 días en topup**: La primera ejecución post-fix recupera automáticamente todos los viernes de los últimos 90 días. Para viernes históricos (> 90 días), `fidelity_evolution` detecta la brecha (< 50% de viernes esperados en prices) y dispara `backfill_price_history` automáticamente.

**FX forward-fill en escritura**: `fx_map.get(d, latest_fx_eur_usd)` → para cada día sin FX exacto, se usa el FX más reciente del batch (o el almacenado en DB si el batch FX falla). Columnas `fx_eur_usd` / `close_eur` siguen NOT NULL → no se necesita migración.

**Single FX en lectura**: `fidelity_evolution` usa `get_current_fx_rate()` (Yahoo snapshot) con fallback a `max(prices, key=price_date).fx_eur_usd`. Mismo FX para todas las fechas en `price_map`. `compute_evolution_series` sin cambios de firma.

**Threshold gap detection**: `len(prices) >= 30 and actual_fridays < expected_fridays // 2`. Mínimo 30 filas evita falsos positivos en fixtures de test con 1 fila mock.

**Contribuciones**: `lot.cost_basis` ya está en EUR (CSV Fidelity EU) → no necesita conversión FX. Series de valor y contribuciones coherentes bajo el mismo FX.

**No migration, no frontend changes.** Tests: 66 passed (5 nuevos en `TestFxDecoupleHappyPath`).

---

## Backend Conventions

- **Schemas:** Pydantic BaseModel; amounts float, percentages raw (12.5 = 12.5%)
- **Routers:** FastAPI APIRouter per module; registered in app.py with auth gate
- **Auth:** All `/api/*` (except `/api/auth/*`) require get_current_user
- **Encryption:** Fernet (AES-128-CBC + HMAC-SHA256); fail-closed on missing key

**See full history-archive.md for pre-2026-07-21 details.**



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

