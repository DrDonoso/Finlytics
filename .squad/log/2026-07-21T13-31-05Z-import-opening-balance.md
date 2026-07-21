# Session Log — Import-time Opening Balance

**Timestamp:** 2026-07-21T13:31:05Z  
**Coordinator:** Scribe  
**Slice:** Import-time opening balance — capture saldo anterior when importing statement for NEW account  
**Status:** ✅ COMPLETED + APPROVED  

---

## Summary

Four-agent squad successfully implemented and validated capture of opening balance (saldo anterior) during statement import. Feature allows users to optionally provide an opening balance when a new account is detected, creating a synthetic "Saldo inicial" transaction dated one day before the first transaction in the statement.

**Result:** Full suite 1275 passed, 2 skipped, 0 failed. Frontend build green. Approved for merge.

---

## Agents & Deliverables

| Agent | Role | Status | Files Modified |
|-------|------|--------|-----------------|
| Shuri | Backend | ✅ Complete | repository.py (helper), imports.py, accounts.py, schemas.py, test_imports.py, test_accounts.py |
| Vision | Frontend | ✅ Complete | ImportModal.tsx, types.ts, i18n (index/es/en) |
| Barton | QA | ✅ Complete | test_import_opening_balance.py (11 TCs) |
| Fury | Review | ✅ APPROVED | — (review gate passed) |

---

## Key Decisions

1. **Helper location:** repository.py (shared by POST /accounts and confirm_import)
2. **Opening date:** Auto-inferred as min(transaction_date) − 1 day (not user input)
3. **Existing accounts:** Opening balance silently ignored (was_created detection)
4. **Idempotence:** Dual-layer (call-level flag + DB-level ON CONFLICT)
5. **KPI skew:** Deferred (is_system flag + migration 0016 pending owner decision)

---

## Known Issues

**RuntimeWarning (test_statements_originals.py):** Test noise, optional ~2-line cleanup in Vision scope.

**is_system follow-up:** Owner pending. Opening balances currently count as "income" in their month (by design).

---

## Next Steps

Owner decision pending on is_system flag + migration 0016 (separate ticket). Code ready to merge now.

---
