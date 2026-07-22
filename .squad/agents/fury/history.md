# Fury — Code Reviewer & Technical Lead

**Owner:** DrDonoso  
**Role:** Design review, architecture validation, proposal authoring  
**Created:** 2026-07-14  

---

## Session Summary (Condensed)

**Total sessions reviewed:** 6 major feature slices  
**Approval rate:** 100% (6/6 APPROVED)  
**Total tests reviewed:** 1290+ passed

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

