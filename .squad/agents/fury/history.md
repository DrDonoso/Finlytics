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

## For detailed reviews and session notes, see `history-archive.md`
