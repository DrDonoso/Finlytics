# Shuri — Backend Engineer

**Owner:** DrDonoso  
**Role:** API design, schemas, database, business logic  
**Created:** 2026-07-14

---

## ⚠️ Merchant Normalization (Slice 1) — REVERTED

**Date:** 2026-07-16  
**Reason:** Owner rejected feature ("no me convence esta parte de los comercios"). No fault; product decision.

Merchant Normalization Slice 1 was fully implemented (1156 tests passing) but removed per owner request. Migration 0016 dropped; DB downgraded to 0015. Deterministic resolver logic was sound but feature not needed at this time.

---

## Key Phases — 2026-07-15 to 2026-07-16

| Phase | Status | Key Deliverables |
|-------|--------|------------------|
| **Fidelity ESPP** | ✅ | CSV parser, daily evolution, price top-up, reminder endpoint |
| **Indexa Capital** | ✅ | 24h portfolio cache, combined-overview endpoint |
| **UX Batch** | ✅ | `/api/summary/months`, connector i18n, nullability contracts |
| **Merchant Slice 1** | ⏭️ REVERTED | Deterministic resolver, merchants.py, 1156 tests |

---

## Backend Conventions

- **Schemas:** Pydantic `BaseModel`; amounts `float`, percentages raw (e.g., 12.5%)
- **Routers:** FastAPI `APIRouter(prefix="...")` per module; registered in `app.py` with auth gate
- **Auth:** All `/api/*` routes (except `/api/auth/*`) auth-gated via `get_current_user`
- **Encryption:** Fernet (AES-128-CBC + HMAC-SHA256) for connection tokens; fail-closed on missing key

---

## Learnings

- **0016 amended in-place for security fixes (2026-07-17):** Migration 0016 was created this session and never deployed. Per the AGENTS.md rule ("amend 0016 IN PLACE for schema fixes — do NOT create 0017 for a table that has never existed in production"), Romanoff's M1/M2 findings were applied directly to `0016_add_notifications.py` and `models.py` rather than introducing a 0017. Changes: `config_enc` `nullable=False` (M2); `UNIQUE(user_id, channel)` named `uq_notification_channels_user_type` added to `notification_channels` (M1).
- **UNIQUE(user_id, channel) on notification_channels:** Concurrent `POST /channels` from the same user could produce duplicate rows (race between SELECT and INSERT). The DB-level constraint is belt-and-suspenders; the SELECT-then-update upsert logic is already correct per-request. Added to both the migration and `NotificationChannel.__table_args__`.
- **config_enc NOT NULL + null guard:** `nullable=False` at the DB level removes the silent-null path. An explicit `if not channel.config_enc:` guard in `deliver_new` (service.py) and the test endpoint (api/notifications.py) provides a meaningful error message instead of an opaque `AttributeError`, recording the delivery as `status='failed'` with a safe error string.
- **httpx hardening for Telegram client:** Added `verify=True, follow_redirects=False` explicitly to both `AsyncClient` instantiations in `telegram.py`. httpx 0.20+ defaults are already correct, but explicit flags match the Indexa pattern and prevent a future copy-paste or default-change from accidentally forwarding the bot_token (embedded in the URL path) to a redirect target.

- **Backup v2:** `/api/backup/export` now emits schema version 2 with optional top-level `rules` and `investments` sections. Investments include connections, ESPP lots, and price history; Indexa `token_enc` is exported/imported as stored ciphertext and is never decrypted.
- **Selective backup export:** `/api/backup/export` accepts boolean section flags `accounts`, `categories`, `tags`, `transactions`, `rules`, and `investments`. With no flags it exports every section for backward compatibility; when any flag is present only truthy sections are included.
- **Version-aware backup import:** `/api/backup/import` accepts v1 and v2 documents, restores whichever sections are present, and skips missing sections. Rules upsert by name, investment connections by `(user, plugin_id)`, ESPP lots dedupe by `dedup_hash`, and price history upserts by `(ticker, price_date)`.
- **Duplicate override:** `/api/imports/confirm` transactions now carry `allow_duplicate` through `ExtractedTransaction` / `ConfirmIn`. Default `False` preserves idempotent imports; `True` force-imports one row.
- **Dedup disambiguator:** `compute_dedup_hash(..., disambiguator=None)` keeps the legacy byte-identical payload. `upsert_transactions()` supplies a UUID hex disambiguator only for `allow_duplicate=True`, hashing it into the JSON payload so the stored `dedup_hash` remains a 64-char SHA-256 digest and bypasses `ON CONFLICT DO NOTHING`.
- **Statement reminder:** `/api/statements/reminder` returns `{year, month, missing_account_ids}` for the previous calendar month. `compute_statement_reminder()` watches only accounts with statement history on/before that month, uses grace 0, and flags watched accounts missing that exact previous month.
- **Notifications Slice 2 — Telegram channel (2026-07-17):** Full Telegram delivery channel implemented. See `.squad/decisions/inbox/shuri-telegram-backend.md` for the canonical contract. Summary:
  - **Telegram client:** `src/finlytics/notifications/telegram.py` — `telegram_get_me(bot_token) -> dict` (token validation), `telegram_send_message(bot_token, chat_id, text) -> None`. Both module-level and patchable. `TelegramError` exception with safe messages (token NEVER in message or URL logged). Uses `httpx.AsyncClient`, 10s timeout.
  - **Message renderer:** `src/finlytics/notifications/messages.py` — `render_notification_text(notification) -> str`. Spanish templates: `notif.statement_missing {account, month}` → "⚠️ Falta subir el extracto de {account} — {month}"; `notif.espp_overdue {period}` → "⚠️ Subida ESPP pendiente — {period}"; unknown keys → "📌 Finlytics: {key}" (safe generic fallback). NEVER interpolates secrets.
  - **deliver_new:** Implemented in `service.py`. Queries `NotificationChannel WHERE user_id=user_id AND enabled=True`. For each channel × notification: check-then-insert delivery row (idempotency guard). If newly inserted: decrypt config → render text → send. On success: status='sent', sent_at=now. On failure: status='failed', error=safe_msg. Failures NEVER raise. Gated by `settings.telegram_send_enabled` (default True).
  - **Channel CRUD API:** Added to `src/finlytics/api/notifications.py`. See below.
  - **Schemas:** `NotificationChannelOut`, `TelegramChannelIn`, `TelegramTestIn`, `TelegramTestOut` added to `schemas.py`.
  - **Config kill-switch:** `telegram_send_enabled: bool = True` in `config.py`. Set `TELEGRAM_SEND_ENABLED=false` to suppress all Telegram sends globally.

**Channel CRUD contract:**
| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/api/notifications/channels` | List channels; NEVER returns config_enc, bot_token, chat_id |
| `POST` | `/api/notifications/channels` | Upsert single Telegram channel (one per user). Validates via getMe (400 on bad token). Encrypts config. Returns masked label. 503 on missing key. |
| `DELETE` | `/api/notifications/channels/{id}` | Remove channel (scoped to user). 404 if not owned. 204. |
| `POST` | `/api/notifications/channels/telegram/test` | Test send. Body `{bot_token?, chat_id?}`: if both provided → use those; else use stored. Returns `{ok, error}` HTTP 200 always (400 on partial input or missing stored channel). |

**Test result:** 1212 passed, 2 skipped (baseline was 1205; added 7 new deliver_new unit tests).
  - **Schema:** Migration `0016_add_notifications.py` — three tables: `notifications` (UNIQUE(user_id, dedup_key)), `notification_channels`, `notification_deliveries`. Models in `db/models.py`.
  - **Dedup_key scheme:** `statement:missing:{YYYY-MM}:acct-{id}` (one per account×month); `espp:overdue:{YYYY-Q#}` (one per ESPP quarter).
  - **Detector registry:** `src/finlytics/notifications/detectors.py` — `StatementDetector` wraps `compute_statement_reminder`, `EsppDetector` wraps `compute_espp_reminder`. Both unchanged pure functions. `REGISTRY: list[Detector]` — append to add future notification types.
  - **Orchestrator:** `src/finlytics/notifications/service.py` — `evaluate_notifications(db, user_id, *, today)`: UPSERT by (user_id, dedup_key); read_at/dismissed_at NEVER touched on upsert; auto-resolves stale rows by setting resolved_at; returns newly-inserted rows. `deliver_new` is a NO-OP stub — Slice 2 fills it.
  - **API contract:** `GET /api/notifications`, `GET /api/notifications/unread-count`, `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`, `POST /api/notifications/{id}/dismiss`. DTO: `NotificationOut` (id, source, type, severity, title_key, title_args, body_key, body_args, action_link, created_at, read_at, dismissed_at). Router registered in `app.py` with `_auth`.
  - **Background loop:** `lifespan` asynccontextmanager in `app.py`. Gated by `settings.notifications_loop_enabled` (default True) and `"pytest" not in sys.modules`. Configured via `NOTIFICATIONS_LOOP_ENABLED` / `NOTIFICATIONS_EVAL_INTERVAL_SECONDS` env vars.
  - **SQLAlchemy session:** `evaluate_notifications` manages its own `async with db.begin()`. After commit, callers must `await db.rollback()` or `commit()` before calling it again with the same session (autobegin issue — tested and documented in orchestrator tests).

---

**Detailed API logs and implementation history:** see `.squad/agents/shuri/history-archive.md`

---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

---

*2026-07-21T08:31:35Z:* Fury proposal on old account onboarding awaits owner validation — may require category system flag or reserved-name filter (`decisions.md` PROPOSAL section).

---

## 2026-07-21T11:30:12+02:00 — POST /api/accounts (onboarding de cuentas antiguas)

**Contexto:** Owner aprobó Fury's Option C para onboarding de cuentas sin extractos históricos.

**Entregables:**
- `POST /api/accounts` → 201, `AccountOut`. Sin migración Alembic.
- Schema `AccountCreate` con `model_validator` que exige `opening_date` cuando `opening_balance` es not-null.
- Transacción sintética "Saldo inicial" creada via `pg_insert` + `ON CONFLICT DO NOTHING` (mismo dedup que importaciones).
- `ImportRun` sintético con `source_filename="manual:saldo-inicial"` para no violar el NOT NULL de `Transaction.import_run_id`.
- 10 nuevos tests en `tests/api/test_accounts.py`; 78 tests de accounts pasan.

**Learnings clave:**

- **ImportRun obligatorio para transacciones manuales:** `Transaction.import_run_id` es NOT NULL. Para cualquier transacción insertada fuera del flujo de importación (ej: saldo inicial, ajustes manuales futuros), hay que crear un `ImportRun` sintético con `source_filename` descriptivo (patrón: `"manual:<tipo>"`). El modelo no permite rutas sin ImportRun.

- **Patrón de dedup para transacciones de apertura:** `compute_dedup_hash(account_ref=account_name, transaction_date=opening_date, amount=Decimal(str(val)), description="Saldo inicial")`. El `account_ref` usa el nombre de cuenta, consistente con el path de importación. Si el mismo account name + fecha + importe + "Saldo inicial" se vuelve a insertar, el `ON CONFLICT DO NOTHING` protege idempotencia.

- **KPI Skew es intencional en este slice:** Un `opening_balance > 0` cuenta como "ingreso" en el mes de apertura porque las queries KPI suman `Transaction.amount` sin filtros. Documentado explícitamente. El follow-up (`is_system` flag + migración 0016) está propuesto en `decisions/inbox/shuri-post-accounts-contract.md`.

- **`pg_insert` directo vs `upsert_transactions`:** Cuando `category_id=None` (no se quiere inventar categoría), es preferible el `pg_insert` directo. `upsert_transactions` siempre resuelve/crea una categoría vía `_resolve_category`, incompatible con transacciones que deliberadamente no tienen categoría.

- **Atomicidad account+transaction:** `async with session.begin()` único envuelve todos los pasos (Account, ImportRun, Transaction insert). Si falla cualquier flush/insert, toda la operación se revierte — la cuenta no queda a medias.

**Contrato canónico:** `.squad/decisions/inbox/shuri-post-accounts-contract.md`

**Tests:** 78 passed (78 related), 0 failed.


---

## 2026-07-21: Old Account Onboarding — POST /api/accounts (Slice: Fury Option C)

**Status:** ✅ Implemented — APPROVED by Fury, 10 tests pass (total 669).

**Summary:** Implemented POST /api/accounts endpoint for manual account creation with optional opening balance as synthetic "Saldo inicial" transaction. No schema migration required.

**Key Implementation:**
- Atomicity: single transaction; full rollback on error
- Synthetic transaction created only when opening_balance != 0; uses dedup_hash for collision detection
- Error handling: 409 Conflict (duplicate name/IBAN), 422 Unprocessable Entity (balance without date, empty name)
- ImportRun metadata: source_filename="manual:saldo-inicial", period in YYYY-MM format
- Guard: opening_balance=0 creates no ImportRun or Transaction

**Files modified:**
- src/finlytics/api/accounts.py — POST endpoint
- src/finlytics/api/schemas.py — AccountCreate + model_validator
- tests/api/test_accounts.py — 10 new tests

**KPI Skew note:** Positive opening_balance appears as "income" in its month. Intentional per Option C. Follow-up: is_system flag + migration 0016 (deferred per Fury recommendation).

**Related:** Orchestration log: .squad/orchestration-log/2026-07-21T09-23-28Z-shuri.md
