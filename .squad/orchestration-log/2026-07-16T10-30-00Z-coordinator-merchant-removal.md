# Orchestration Log — Coordinator: Merchant Feature Removal

**Timestamp:** 2026-07-16T10:30:00Z (UTC)  
**Orchestrator:** Coordinator  
**Event:** Merchant Normalization feature (Slice 1 backend + Slice 2 UI) removed per owner rejection

## Context

Owner (DrDonoso) rejected the merchant-normalization feature after review ("no me convence esta parte de los comercios"). Coordinator instructed full removal while retaining the palette work (Wanda).

## Actions Completed

1. **Database rollback:** Migration 0016 dropped; head downgraded to 0015_add_portfolio_cache.py
   - Dropped tables: merchants, merchant_aliases
   - Dropped transaction columns: canonical_merchant_id, merchant_resolution_source
   - Transaction data preserved

2. **Code cleanup:** Deleted 6 implementation files
   - Alembic migration (0016)
   - Backend API (merchants.py)
   - DB logic (merchant_normalization.py)
   - Frontend page (MerchantsPage.tsx)
   - Test suites (2 files)

3. **Source reversion:** Reverted 12 files to HEAD state (merchant-only changes removed)

4. **i18n surgery:** Removed 38-line "Merchant normalization management" block; kept pre-existing merchant keys (TopMerchants, rules, columns)

5. **Docker rebuild:** Redeployed; verified alembic_version=0015, no merchants table, 0 merchant routes in OpenAPI

## Verification

- ✅ Container health: :7777 responsive
- ✅ Palette bootstrap served
- ✅ Auth routes secured (401 on unauthed /api/categories)
- ✅ No merchant-related tables in schema
- ✅ Wanda palette work remains intact

## Status

**COMPLETE** — Feature fully removed. App source uncommitted (owner in local loop).
