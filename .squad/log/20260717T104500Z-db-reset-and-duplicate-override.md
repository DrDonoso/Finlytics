# Session: DB reset and duplicate override

**Date:** 2026-07-17T10:45:00Z

## Scope

- Coordinator: Reset LOCAL database (scope=reset_total, backup=true), took pg_dump, ran alembic 0015, reseeded 20 categories
- Shuri: Backend force-import override for duplicates (ExtractedTransaction.allow_duplicate, uuid4 disambiguator in dedup_hash)
- Vision: Frontend "Not a duplicate" control in ImportPreviewTable; override survives re-checks
- All tests passing (1160 passed, 2 skipped)
- App deployed and healthy on :7777

## Outcome

Duplicate override feature complete end-to-end. Users can now mark individual flagged transactions as non-duplicates and force-import them. Database reset cleared all transient data (users, accounts, connections); owner will re-do setup/login and reconnect investment accounts.
