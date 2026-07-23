## 2026-07-23: Indexa Contribution Events — 30 Tests Comprehensive

**Collaborators:** Shuri, Vision, Barton, Fury  
**Status:** ✅ APPROVED  
**Session Log:** .squad/log/2026-07-23T10-09-14Z-indexa-contributions.md

**Summary:** Comprehensive test suite for contribution event derivation. 30 tests covering delta derivation, withdrawal semantics, multi-account aggregation, edge cases, schema validation, cache round-trip, and end-to-end integration. Full suite: 1356 passed, 2 skipped, 0 failed.

**Test Categories:** Delta derivation (6), withdrawals (3), edge cases (5), multi-account (8), schema/cache (4), integration (4). All tests pass independently and collectively.

**Key Techniques:**
- `async def` tests with pytest-asyncio (no `run_until_complete` inside async test).
- Multi-account aggregation testing via `_aggregate(fetched: list[tuple[conn, portfolio]], total_connections)`.
- Schema validation for `ContributionEventOut` and `InvestmentPortfolioOut`.
- Cache round-trip via `dataclasses.asdict()` serialization.

**Bugs Found:** None. Shuri's implementation correct in all cases.

**Related:** orchestration-log/2026-07-23T10-09-14Z-barton.md

---

## 2026-07-22: FX-Decouple (Model A) Regression Tests

**Context:** Shuri refactored ESPP pipeline: store MSFT close_usd for all market days, no FX daily intersection, single FX rate at read time.

**Bugs Verified Fixed:** EURUSD=X no Friday rows; null FX values; today-00:00-UTC exclusion.

**Tests Added:** 30 regression tests covering Friday presence, null FX handling, today inclusion, FX consistency, backfill/topup counts, KPI regression. Technique: `pg_insert(...).values(...)._multi_values[0]` length verification; parameter capture of `_yahoo_get`. Infrastructure fix: added `.first.return_value` to mock.

**Result:** 1325 passed, 2 skipped, 0 failed.

---

## 2026-07-21: is_system KPI Exclusion (3 sessions)

**Sessions:**
1. **Option B decision:** Ledger-visible, KPI-excluded (15 integration tests, BigInteger PRIMARY KEY shim for SQLite, to_char custom function).
2. **Documentation updates:** Test names/comments corrected to reflect Option B.
3. **POST /api/accounts edge cases:** 11 tests for negative balance, ImportRun proxy mocking, dedup determinism, zero-balance guard. Helpers: `_pg_insert_ok()`, `_track_session_adds()`.

**Result:** 1290 passed, 2 skipped, 0 failed. No bugs found.

**Related:** orchestration-log/2026-07-21T16-59-22Z-barton.md

---

## 2026-07-21: confirm_import opening_balance (TDD)

**Context:** Early edge-case tests (11 tests) before Shuri's implementation. ImportRun mock strategy with side_effect differentiated by source_filename. Guard requirement for empty transactions list.

**Result:** 11/11 PASS. Suite: 683 tests, 0 failures.

---

## 2026-07-17: Notifications + Telegram

**Summary:** Hybrid notifications + Telegram with Fernet encryption. Backend-owned state. 1239 passed, 2 skipped. Docker E2E PASS. No defects.

---

## Cross-Agent References

**Scribe Orchestration Logs (2026-07-23):**
- Shuri: orchestration-log/2026-07-23T10-09-14Z-shuri.md
- Vision: orchestration-log/2026-07-23T10-09-14Z-vision.md
- Barton: orchestration-log/2026-07-23T10-09-14Z-barton.md (self)
- Fury: orchestration-log/2026-07-23T10-09-14Z-fury.md

