# Fury — Code Reviewer & Technical Lead

**Owner:** DrDonoso  
**Role:** Design review, architecture validation, proposal authoring  
**Created:** 2026-07-14  
**File size:** Condensed 2026-07-16 (see history-archive.md for detailed session logs)

---

## Current Architecture Decisions Locked

| Component | Scope | Status |
|-----------|-------|--------|
| **Investments plugin system** | Frontend plugin registry, expandable nav, per-plugin views | ✅ Approved (2026-07-14) |
| **Indexa Capital Phase 2** | Token encryption, portfolio cache, combined-overview | ✅ Approved (2026-07-14) |
| **Fidelity ESPP** | Statement-import connector type, CSV parser, DB schema | ✅ Approved (2026-07-15) |
| **Merchant normalization** | Deterministic resolver, Slice 1 schema, soft-delete | ✅ Approved (2026-07-16) |

---

## Key Technical Learnings

- **Plugin architecture:** Provider ABC with `provider_type` (live_api vs statement_import) enables coexistence of token-based (Indexa) and statement-based (Fidelity) connectors.
- **CSS tokens:** Single `index.css` with design system custom properties; palette-awareness via `data-palette` attribute.
- **Frontend pattern:** `AsyncState<T>`, `GlobalFilterBar`, `KpiCards`, standalone page routes under Layout.
- **Auth model:** All `/api/*` routes (except /auth) require session cookie via `get_current_user` dependency.

---

## Review Status Summary

✅ Investments skeleton architecture approved  
✅ Indexa Phase 2 design locked (with schema + security constraints)  
✅ Fidelity ESPP connector architecture approved  
✅ Merchant-normalization Slice 1 locked  
✅ InvestmentSnapshotCard + Inicio/Finanzas split validated  
✅ Palette-aware colors + merchant UI Slice 2 approved  

---

## Learnings

### Notifications + Telegram design (2026-07-17)

**Existing "reminders" are stateless standing-conditions, not events:**
- `compute_statement_reminder(today, per_account_months)` → `StatementReminderOut` (`api/statements.py`), endpoint `GET /api/statements/reminder`. Pure fn, no persistence.
- `compute_espp_reminder(lots, today, grace_days)` → `FidelityReminderOut` (`api/fidelity.py:214`), endpoint `GET /api/investments/fidelity/reminder`. Pure fn.
- Both render inline on Dashboard (`StatementWarning` chips ~211-300; `.espp-reminder-banner` ~328) and FidelityView. They flip off the moment data arrives (upload). This "condition, not event" nature drives the model choice → chose **hybrid: detectors upsert into a `notifications` table keyed by a stable `dedup_key`** (identity + dedup + Telegram idempotency in one).

**No scheduler exists in the app** — key infra fact:
- `docker-entrypoint.sh` = `alembic upgrade head` → `python seed.py` → `python -m finlytics` (single uvicorn worker, `__main__.py`, no `workers=`).
- `app.py` has NO lifespan/startup hook. Async side-effects use FastAPI `BackgroundTasks` (Indexa cache refresh in `investments/service.py`; `market_data.topup_recent_prices` runs lazily on-request, not scheduled).
- Consequence: prefer evaluate-on-request + BackgroundTasks first; a future in-process `asyncio` interval loop in a lifespan hook needs **no lock** (single worker). Avoid APScheduler/cron unless truly needed.

**Connector pattern to mirror (Indexa) — reusable for any new connector:**
- ABC `InvestmentProvider` (`investments/base.py`) w/ `plugin_id` + `provider_type` (`live_api`|`statement_import`); registry `_PROVIDERS` dict in `investments/service.py:64`.
- Table `investment_connections` (`db/models.py:282`): user_id FK CASCADE, plugin_id, status, account_label_masked, `token_enc` (Fernet, nullable), timestamps.
- Crypto `investments/crypto.py`: `encrypt_token`/`decrypt_token` encrypt **arbitrary strings** (so a `{bot_token,chat_id}` JSON blob → one ciphertext works). `EncryptionNotConfiguredError → HTTP 503`, fail-closed. Env `FINLYTICS_ENCRYPTION_KEY`. Tokens never logged/returned; responses expose masked labels only.
- Wizard `frontend/src/components/IndexaWizard.tsx`: steps intro → token(password) → validate (`POST /connections/validate`, stores nothing) → account checkboxes → connect (`POST /connections`) → success. Reuses `inv-wizard__*` CSS + i18n `t.*`.
- Registries: backend `_PLUGIN_REGISTRY` (`api/investments.py:44`); frontend `PLUGIN_VIEW_REGISTRY` (`investments/registry.ts`).
- Migration style: `alembic/versions/`, head `0015`; `op.create_table` + FK CASCADE + UNIQUE/Index; next = `0016`.

**Frontend seams:** topbar `header.app-topbar` (Layout.tsx:80) has no right-side actions yet → bell goes there. `client.ts` = `apiFetch<T>()`/`buildUrl()` + `getX/postX` with `USE_MOCK` fallback. i18n = 3 files (`index.ts` Dict, `en.ts`, `es.ts`) all updated. Tokens in `index.css`.

**Cross-cutting decision:** because Telegram push is a backend concern, notification read/dismiss state must be **backend-owned from Slice 1** (supersedes Wanda's localStorage-first idea for this feature; localStorage would be thrown away in Slice 2). Wanda's `wanda-notifications-ux.md` owns all bell/panel/wizard visuals + i18n copy + a proposed `--warning` token family.

**Proposal delivered:** `.squad/decisions/inbox/fury-notifications-design.md` (sections A–F, options + recommendations, 6 open questions w/ defaults). Awaiting David's validation before any code.

---

## For detailed reviews and session notes, see `history-archive.md`

---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

---

### Onboarding cuentas antiguas — Flows vs Balance (2026-07-21)

**Framing clave:** Finlytics mide *flujos* (gasto/ingreso por periodo sumando `Transaction.amount`), NO patrimonio/saldo por cuenta. No existe `Account.initial_balance` ni concepto de saldo de apertura. `balance_after` es nullable, per-row, y no se agrega en ningún KPI.

**Opciones evaluadas:**
- **A (subir +5 años de extractos):** histórico completo pero costoso en OpenAI/tiempo y formatos antiguos parsean peor.
- **B (campo saldo inicial en Account):** rápido, pero rompe el modelo de flujos — los KPIs ignoran un campo nuevo, y genera incoherencia conceptual.
- **C (transacción de apertura sintética + extractos selectivos) — RECOMENDADA:** respeta el modelo actual, cero migraciones, el owner elige granularidad. Necesita categoría excluible para no contaminar gráficos de ingreso.

**Propuesta entregada:** `.squad/decisions/inbox/fury-old-account-onboarding.md` — pendiente validación del owner.

---

### Revisión slice "Old Account Onboarding" — Opción C (2026-07-21)

**Veredicto: ✅ APROBADO** — Backend (Shuri), Frontend (Vision), Tests (Barton+Shuri).

**Hallazgos clave:**
- Atomicidad correcta: todo dentro de `session.begin()`, rollback automático en fallo.
- Dedup sólido: `compute_dedup_hash` determinista + `ON CONFLICT DO NOTHING` previene doble conteo en retry. Hash usa nombre de cuenta (no ID) + fecha + monto + descripción fija.
- ImportRun metadata correcta: `source_filename="manual:saldo-inicial"`, period ISO, contadores de insert/duplicates.
- Frontend `createAccount` usa raw fetch (no `apiFetch`): aceptable, sigue precedente de `authPost` — necesario para exponer status code al caller (409/422). `apiFetch` pierde el status en el throw.
- Mock tiene inconsistencia menor (opening_balance=0 → tx_count=1 en mock vs 0 en backend). Solo afecta modo mock, no bloqueante.
- 41 tests pasan (0.28s). Cobertura de happy path, errores, edge cases, determinismo de hash, metadata ImportRun.
- Sin migración Alembic. ✅

**Follow-up `is_system`:** Recomendado DESPUÉS, no ahora. Cuando el owner quiera excluir saldo de apertura de KPIs → migración 0016 con boolean + index parcial. No meter migración por tema cosmético.

**Veredicto completo:** `.squad/decisions/inbox/fury-old-account-review.md`

---

## 2026-07-21: Design Review — Old Account Onboarding (Slice: Fury Option C) — APPROVED

**Status:** ✅ APPROVED — No blocking defects.

**Summary:** Reviewed complete slice (Shuri backend + Vision frontend + Barton QA) against Fury's original Option C proposal. Verdict: fully implemented as designed; ready for merge.

**Review Findings:**

**Backend (Shuri):** ✅
- Atomicity: single transaction, full rollback on error
- Dedup: SHA-256 hash, ON CONFLICT DO NOTHING
- ImportRun metadata: source_filename, period, counters correct
- Guard: opening_balance=0 creates no synthetic transaction
- Semantics: 201/409/422 responses correct
- No migration required

**Frontend (Vision):** ✅
- Raw fetch justified for 409/422 error handling
- Modal pattern consistent with existing dialogs
- i18n complete (18 keys, EN/ES)
- Accessibility: aria-modal, aria-labelledby, Escape handling
- Minor (non-blocking): mock had opening_balance=0 tx_count=1 inconsistency (fixed)

**Tests (Barton):** ✅
- 669 tests all pass
- Good edge-case coverage
- No bugs detected

**Key Decision: KPI Skew Follow-up (is_system flag + migration 0016)**

Recommendation: **Defer to later task.**
- KPI skew (opening_balance appears as income) is intentional per Option C
- Owner already approved this behavior
- Backfill when needed is simple and safe
- No need to block this slice on cosmetic exclusion logic
- Future implementation: is_system boolean + partial index + WHERE NOT is_system in KPI queries (simple, explicit, safe)

**Related:** Orchestration log: .squad/orchestration-log/2026-07-21T09-23-28Z-fury.md
