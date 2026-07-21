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

**Current Test Baseline:** 1275 passed, 2 skipped, 0 failed.

---

## Key Technical Learnings

### ImportRun for Manual Transactions
`Transaction.import_run_id` NOT NULL. For any transaction outside import flow (e.g., opening balance, future manual adjustments), create synthetic `ImportRun` with `source_filename="manual:<type>"`.

### Dedup Pattern for Opening Balances
`compute_dedup_hash(account_ref=account_name, transaction_date=opening_date, amount=Decimal(...), description="Saldo inicial")`. Protects idempotence via `ON CONFLICT DO NOTHING`.

### KPI Skew (Intentional)
Opening balance > 0 counts as "income" in its month (no filters in KPI queries). Documented. Follow-up: `is_system` flag + migration 0016 (deferred pending owner approval).

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

---

## Backend Conventions

- **Schemas:** Pydantic BaseModel; amounts float, percentages raw (12.5 = 12.5%)
- **Routers:** FastAPI APIRouter per module; registered in app.py with auth gate
- **Auth:** All `/api/*` (except `/api/auth/*`) require get_current_user
- **Encryption:** Fernet (AES-128-CBC + HMAC-SHA256); fail-closed on missing key

**See full history-archive.md for pre-2026-07-21 details.**

