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

**Detailed API logs and implementation history:** see `.squad/agents/shuri/history-archive.md`
