## 2026-07-23: Schema Versioning Cache Auto-Invalidation

**Collaborators:** Shuri (feature + happy-path), Barton (edge cases)
**Status:** ✅ APPROVED
**Tests Added:** 9 tests (TC1–TC6, split into unit + integration for TC2/TC3)

**Summary:** Shuri implemented `_PORTFOLIO_SCHEMA_VERSION = 2` in service.py. `_serialize_portfolio` embeds `_schema_version` in every payload. `_get_db_cache` detects absent/mismatched version, does `await db.delete(row)` + `await db.flush()` before returning None (delete+INSERT strategy). `get_portfolio` treats version-invalid rows as cache misses → synchronous live fetch; first load after deploy is NOT stale.

**Tests (edge cases, Barton):**
- TC1: Current version + fresh → HIT, no live call (verify serialize embeds version).
- TC2 unit: No `_schema_version` in payload → `_get_db_cache` returns None, awaits delete+flush.
- TC3 unit: Wrong `_schema_version` (e.g. 0 vs 2) → same.
- TC2/TC3 integration: Version-invalid row → sync live fetch → result is fresh (total_value from live, not stale; contribution_events present).
- TC4: delete+flush precedes INSERT → no unique-constraint error. Verified `db.delete.assert_awaited_once_with(old_row)`, `db.flush.assert_awaited_once()`, `db.add` called once with `connection_id=42` and correct `_schema_version` in payload.
- TC5: `_serialize_portfolio` embeds key; `_deserialize_portfolio` ignores it (round-trip works including `contribution_events`).
- TC6 fresh/stale regression: behavior unchanged for version-matching rows.

**Bugs Found:** None. Shuri's implementation correct in all cases.

**Key Technique — Critical Mock Gotcha:**  
SQLAlchemy 2.0 `AsyncSession.delete()` is a **coroutine** (`inspect.iscoroutinefunction(AsyncSession.delete) == True`). Mock DBs for tests involving version-invalid cache rows **must** include:
```python
db.delete = AsyncMock()   # NOT MagicMock — would raise TypeError: 'MagicMock' can't be awaited
db.flush  = AsyncMock()
```
Using `MagicMock()` for either causes `TypeError: 'MagicMock' object can't be awaited` at `await db.delete(row)`.  
Helper `_sv_mock_db(execute_side_effect)` captures this pattern for reuse.

**Re-cache strategy:** delete+INSERT (not UPDATE). `_get_db_cache` deletes the stale row and flushes within the same session; `get_portfolio` then does `db.add()` for the fresh row. Flush ensures the DELETE reaches the DB before the INSERT to avoid unique-constraint violation.

**Full Suite:** 1366 passed, 2 skipped, 0 failed.

---

## Learnings

- **SQLAlchemy 2.0 async:** `session.delete()` is a coroutine; always use `AsyncMock` in mock DBs that exercise the version-invalidation path.
- **Re-cache pattern for schema bumps:** delete+flush in `_get_db_cache` → INSERT in `get_portfolio`. This is safe and simple; avoids needing an UPSERT or a separate UPDATE path.
- **Test isolation for TC2/TC3:** split into unit (`_get_db_cache` directly) and integration (`get_portfolio` end-to-end) to get clear failure messages — the unit test tells you exactly which function is broken.
- **TC4 assertion:** don't assert `db.add` is NOT called (wrong for delete+INSERT); assert `db.delete.assert_awaited_once_with(old_row)` and verify the added row carries the new `_schema_version`.

---

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

**Cache Schema Versioning Slice (2026-07-23):**
- Shuri: orchestration-log/2026-07-23T10-48-27Z-shuri.md
- Barton: orchestration-log/2026-07-23T10-48-27Z-barton.md (self)
- Fury: orchestration-log/2026-07-23T10-48-27Z-fury.md

