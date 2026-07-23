# Fury — Code Reviewer & Technical Lead

**Owner:** DrDonoso  
**Role:** Design review, architecture validation, proposal authoring  
**Created:** 2026-07-14  

---

## Session Summary (Condensed)

**Total sessions reviewed:** 7 major feature slices  
**Approval rate:** 100% (7/7 APPROVED)  
**Total tests reviewed:** 1356+ passed

---

## Architecture Decisions Locked

| Component | Status | Date |
|-----------|--------|------|
| Investments plugin system | ✅ APPROVED | 2026-07-14 |
| Indexa Capital Phase 2 (encryption, cache) | ✅ APPROVED | 2026-07-14 |
| Fidelity ESPP statement-import connector | ✅ APPROVED | 2026-07-15 |
| Merchant normalization (Slice 1) | ✅ APPROVED | 2026-07-16 |
| Notifications + Telegram (hybrid model, backend-owned) | ✅ APPROVED | 2026-07-17 |
| Old Account Onboarding (Slice: Option C) | ✅ APPROVED | 2026-07-21 |
| Import-time Opening Balance | ✅ APPROVED | 2026-07-21 |
| is_system / KPI exclusion (OPTION B) | ✅ APPROVED | 2026-07-21 |
| Indexa Contributions Table (derive from net_amounts deltas; multi-account aggregation) | ✅ APPROVED | 2026-07-23 |

---

## Key Technical Insights

**Plugin Architecture Pattern (Indexa, Fidelity coexistence):**
- `InvestmentProvider` ABC with `provider_type` (live_api|statement_import)
- Registry-driven: backend `_PLUGIN_REGISTRY`, frontend `PLUGIN_VIEW_REGISTRY`
- Token encryption with Fernet; fail-closed (503) if key absent
- Combined-overview endpoint merges both connector types seamlessly

**Flow vs. Balance Model:**
- Finlytics measures **flows** (transactions, income/expense by period), not balance/equity
- KPI queries sum `Transaction.amount`; no account-level balance aggregation
- Opening balance as synthetic transaction (not Account field) respects this model
- `is_system=True` flag excludes these rows from all aggregations, preserving KPI semantics

**Backend Infrastructure Implications:**
- No scheduler; single-worker uvicorn
- `BackgroundTasks` for async operations (Indexa refresh, market data topup)
- Lifespan hooks can be added; currently unnecessary
- `session.begin()` atomicity critical for multi-step operations

**Frontend Patterns:**
- `AsyncState<T>` for loading/error/data states
- Plugin views via registry + conditional render
- Token handling via password field (never logged)
- i18n: 3 files (Dict interface, en.ts, es.ts) — all must be updated together

**Notification Model Decision:**
- Backend-owned state (not localStorage) from Slice 1
- Hybrid: detectors upsert with stable `dedup_key` (identity+idempotency in one)
- Telegram: opt-in per channel, token encrypted, delivery async

---

## Review Sessions (Condensed)

### 2026-07-14: Investments Architecture
✅ Plugin skeleton approved. Indexa Phase 2 schema locked. Fidelity connector paths validated.

### 2026-07-15–16: Merchant Normalization
✅ Slice 1 (deterministic resolver, schema) locked. Slice 2 (palette-aware UI) approved. Soft-delete semantics confirmed.

### 2026-07-17: Notifications + Telegram
✅ Hybrid model approved. Backend-owned dedup_key. Fernet encryption (fail-closed). Telegram channel integration design finalized.

### 2026-07-21a: Old Account Onboarding
✅ Option C approved. Atomic transaction, SHA-256 dedup, ImportRun metadata correct. No migration needed. 41 tests pass. Follow-up `is_system` deferred (future optimization).

### 2026-07-21b: Import-time Opening Balance
✅ Approved. `was_created` detection both paths correct. Date inference sound. Atomic within import. 11 edge-case tests pass. DRY helper refactor validated.

### 2026-07-21c: is_system / KPI Exclusion (OPTION B)
✅ Approved. Migration 0017 chain correct. 7 KPIs exclude is_system; ledger includes with badge. 15 dedicated tests + 1290 suite all pass. No defects.

---

## Learnings

### 2026-07-23: Portfolio Cache Schema Versioning (Option B) — ✅ APPROVED
- **Invalidación sin migración**: `_schema_version` embebido en el JSON del payload; filas existentes (sin key) → `None != 2` → auto-invalidación. Elegante y zero-downtime.
- **MISS sincrónico, no STALE**: retornar `None` desde `_get_db_cache` garantiza el path MISS (fetch en vivo inmediato), no el STALE (que devolvería datos viejos + background). Crítico para que la primera carga post-deploy ya muestre contribution_events.
- **flush() antes del INSERT**: `delete+flush` en la misma sesión asegura que el DELETE llega al motor SQL dentro de la transacción antes del posterior `db.add()`. Sin esto, `uq_portfolio_cache_connection_id` violaría en el commit.
- **Fail-safe en fetch fallido**: si el live fetch falla tras el delete+flush, `commit()` nunca se llama → el DELETE se revierte con la sesión → la fila stale sobrevive para reintentar. No hay pérdida de datos.
- **Self-heal producción**: deploy → primera request → fila vieja invalidada → fetch sincrónico → tabla de contributions visible inmediatamente. No requiere intervención manual.

### 2026-07-23: Indexa Contribution Events (Option A) — ✅ APPROVED
- **Derivación de deltas correcta**: `_derive_contribution_events` computa diferencias entre entries consecutivas de `net_amounts`; skip de 0.0 inicial; skip de deltas cero; type por signo. Sin posibilidad de doble-conteo.
- **Multi-cuenta: el truco es sumar deltas (no cumulativos)**: tanto en `get_portfolio` (IndexaProvider) como en `_aggregate` (service), se suman amounts por fecha y se recalcula el cumulative como running total del stream combinado. Esto es correcto: cumulative = integral de flujos, no suma de integrales parciales con orígenes distintos.
- **Cache backward-compatible**: `contribution_events: list = []` en schema + `get("contribution_events") or []` en deserialización → cachés antiguas sin el campo no rompen.
- **Retiradas confirmadas**: delta negativo → amount negativo → type="withdrawal". Tests TC-3 (5 variantes) + TC-11 withdrawal lo verifican.
- **No-regresión**: `contributions_series` (chart) intacta; field nuevo es ortogonal.

### 2026-07-22: FX Decouple Review (Model A) — ✅ APPROVED
- **Single-FX model coherence**: value_series usa `close_usd × live_fx`, contributions es EUR nativo del CSV Fidelity → comparación gain/loss coherente sin reconversión.
- **KPIs/lots usan daily-bar FX** (vía `get_latest_price().fx_eur_usd`), evolution usa live-snapshot FX (`get_current_fx_rate()`). Diferencia es ruido intraday (<0.3%), no inconsistencia real — son vistas distintas con requisitos distintos.
- **close_eur almacenado es campo muerto**: ningún código activo lo lee para cálculos EUR (todos computan `close_usd × fx_eur_usd` en runtime).
- **Gap recovery bounded**: máximo 1 intento backfill/request, self-heals al rellenar viernes, `len >= 30` protege fixtures.
- **Forward-fill FX es el patrón correcto** para series que cruzan días sin bar FX (viernes, nulls): usar el FX más reciente disponible.

---

## Deferred Follow-ups

- **Merchant Slice 3 (soft-delete recovery UI):** Awaiting owner prioritization
- **Notifications Slice 2 (panel + dismiss UI):** Approved concept; Vision/Wanda own visual delivery
- **Account balance history (multi-currency):** Research phase (owner query: support multiple base currencies)

---

## For Detailed Session Notes

See `history-archive.md` (moved 2026-07-16).  
See `.squad/orchestration-log/2026-07-21T*-fury.md` for latest cross-agent refs.

---

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

---

## Session: 2026-07-23 — Indexa Contributions Table (slice complete)

**Collaborators:** Shuri, Vision, Barton, Fury  
**Status:** ✅ IMPLEMENTED + APPROVED  
**Decisions:** .squad/decisions.md (merged from inbox), .squad/orchestration-log/  
**Session Log:** .squad/log/2026-07-23T10-09-14Z-indexa-contributions.md

**Summary:** Full squad execution: derivation of contribution events from net_amounts deltas (Shuri), frontend table with i18n (Vision), 30 comprehensive tests (Barton), architecture review (Fury). Multi-account aggregation verified. 1356 tests pass. No defects. Ready for merge.

**Key Decision (OPTION A):** Derive contribution events from net_amounts deltas at runtime; aggregate multi-account by summing deltas per date; withdrawals semantically represent negative deltas; same-day netting accepted limitation.

**Cross-agent refs:**
- Shuri: orchestration-log/2026-07-23T10-09-14Z-shuri.md
- Vision: orchestration-log/2026-07-23T10-09-14Z-vision.md
- Barton: orchestration-log/2026-07-23T10-09-14Z-barton.md
- Fury: orchestration-log/2026-07-23T10-09-14Z-fury.md


## Session: 2026-07-23 — Cache Schema Versioning (slice complete)

**Collaborators:** Shuri, Barton, Fury  
**Status:** ✅ IMPLEMENTED + APPROVED  
**Decisions:** .squad/decisions.md (merged inbox + archived 9 pre-7d entries), .squad/decisions-archive.md  
**Session Log:** .squad/log/2026-07-23T10-48-27Z-cache-versioning.md

**Summary:** Root cause analysis and fix for stale portfolio cache serving pre-deploy JSON (missing contribution_events). Solution: version-based cache invalidation. Embed `_PORTFOLIO_SCHEMA_VERSION=2` in all new rows; detect mismatches on read; auto-invalidate via delete+flush → first-load-fresh synchronous refetch → self-heals production on first request post-deploy. No migration, no frontend changes. 1366 tests pass. No defects.

**Decision (OPTION B):** Delete+flush invalidation in `_get_db_cache` (not UPDATE/upsert in write path). Centralizes logic, maintains simple write pattern, guarantees MISS path taken on version mismatch.

**Cross-agent refs:**
- Shuri: orchestration-log/2026-07-23T10-48-27Z-shuri.md
- Barton: orchestration-log/2026-07-23T10-48-27Z-barton.md
- Fury: orchestration-log/2026-07-23T10-48-27Z-fury.md



