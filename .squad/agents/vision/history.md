# Vision — Frontend Engineer

**Owner:** DrDonoso  
**Role:** React components, charting, state management, UX flows, responsive design  
**Created:** 2026-07-03

---

## ⚠️ Merchant Management UI (Slice 2) — REVERTED

**Date:** 2026-07-16  
**Reason:** Owner rejected feature ("no me convence esta parte de los comercios"). No fault; product decision.

Merchant Management UI was fully implemented and shipping cleanly but removed per owner request. Slice 2 work was technically sound but feature not needed at this time. Backend Slice 1 (Shuri) also reverted in coordination.

---

## Key Features — 2026-07-13 to 2026-07-16

| Feature | Status | Key Components |
|---------|--------|------------------|
| **Statements redesign** | ✅ | PDF download, month selector, statement list |
| **Investments skeleton** | ✅ | Phase 1: types, client, i18n, page, routing, nav |
| **Fidelity ESPP wizard** | ✅ | PDF upload, holdings review, confirm flow |
| **InvestmentSnapshotCard** | ✅ | Cross-domain summary for Dashboard |
| **Inicio/Finanzas split** | ✅ | Widget reorganization (analysis → Finanzas) |
| **Palette-aware charts** | ✅ | 5 accent palettes, semantic color semantics |
| **Merchant UI Slice 2** | ⏭️ REVERTED | CRUD, alias management, unmatched queue |

---

## Frontend Conventions

- **Routing:** Flat child routes under `<Route path="/" element={<Layout />}>` in `App.tsx`
- **i18n:** Bilingual EN/ES; `Dict` interface in `i18n/index.ts`, implementations in `es.ts` / `en.ts`
- **API client:** `apiFetch<T>()` in `client.ts`; endpoints follow `getX()` / `postX()` pattern with mock fallback
- **Pages:** `AsyncState<T>` (`{ loading, error, data }`) pattern
- **CSS tokens:** Single `index.css`; palette via `data-palette` attribute; theme via `data-theme`

---

**Detailed component logs and implementation history:** see `.squad/agents/vision/history-archive.md`
