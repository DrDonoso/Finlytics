## Learnings (2026-07-17 Telegram Notification Channel Audit)

- **[2026-07-17 TELEGRAM CREDENTIAL MODEL]** `bot_token` + `chat_id` are stored as a single Fernet-encrypted JSON blob in `notification_channels.config_enc` (TEXT). The same `FINLYTICS_ENCRYPTION_KEY` / `crypto.py` Fernet helpers used by Indexa. Same fail-closed 503 pattern on missing key. `NotificationChannelOut` never returns `config_enc`, token, or chat_id. Label is `"Telegram · ••••{last4 of chat_id}"`.
- **[2026-07-17 AUDIT VERDICT]** ⚠️ FIX-FIRST — No Critical or High findings. Two Medium findings require fixes before next deploy. Full report in `.squad/decisions/inbox/romanoff-telegram-audit.md`.
- **[2026-07-17 M1 — MISSING UNIQUE CONSTRAINT]** `notification_channels` has no `UNIQUE(user_id, channel)`. Concurrent upserts can create duplicate rows. The `UNIQUE(notification_id, channel)` on `notification_deliveries` prevents double-sends (second attempt gets IntegrityError → caught by generic handler → "failed" in audit log), but stale encrypted configs linger. Fix: new migration adding the constraint.
- **[2026-07-17 M2 — config_enc NULLABLE]** Column is `nullable=True` at DB level. A NULL `config_enc` row causes `AttributeError` caught silently by the generic exception handler — no crash, no token leak, but silent failure on every future delivery. Fix: `NOT NULL` in migration + explicit null guard before decrypt in `deliver_new` and the test path.
- **[2026-07-17 LOW — httpx FLAGS]** `telegram.py` doesn't explicitly set `verify=True, follow_redirects=False` in its `httpx.AsyncClient` instantiation — relies on correct httpx defaults. Inconsistent with `indexa.py` which is explicit. Should be made explicit for all outbound httpx clients (house style).
- **[2026-07-17 LOW — THIRD-PARTY ERROR PASSTHROUGH]** Telegram API `description` field is included verbatim in `TelegramError` and stored in `delivery.error` + returned from test endpoint. Telegram's documented descriptions don't include tokens; risk is very low but worth sanitizing.
- **[2026-07-17 CONFIRMED CLEAN]** Auth-gating, ownership scoping (user_id filter on all channel operations), no token in logs, no token in responses, HTTPS enforced, 10s timeout, no SSRF (fixed host + chat_id in JSON body), delivery idempotency via DB UNIQUE constraint, templating uses trusted args only. All 8 threat checklist items pass (with the caveats above).

## Learnings (2026-07-14 Indexa Phase 2 Implementation Review)

- **[2026-07-14 REVIEW VERDICT]** ✅ PASS — all 8 security invariants verified against shipped Phase 2 code. See full table in `.squad/decisions/inbox/romanoff-indexa-token-security.md §10`.
- **[2026-07-14 ENV KEY CORRECTION]** Spec said `INDEXA_ENCRYPTION_KEY`. Owner decided on `FINLYTICS_ENCRYPTION_KEY` (app-wide key for all connectors). This is the correct implementation. Design doc updated to match.
- **[2026-07-14 FAIL-CLOSED CORRECTION]** Spec said "refuse to start". Owner decided on scoped fail-closed: app starts normally; only encrypt/decrypt operations fail with HTTP 503. This is correct. Design doc updated. Scoped behavior is implemented cleanly in `crypto.py` + API layer catches `EncryptionNotConfiguredError` → 503.
- **[2026-07-14 TRANSIENT ACCOUNT NUMBER]** `/connections/validate` returns raw `account_number` transiently to the wizard. Not a security issue: server re-validates ownership on connect, it's never stored, and account numbers are internal Indexa identifiers (not IBAN/email/DNI). Documented in code.
- **[2026-07-14 TEST QUALITY]** Barton's security-invariant tests genuinely assert the invariants: token-not-in-body string checks, `add`/`flush`/`commit` not-called assertions, keyword checks in 503 detail messages, `verify=True`/`follow_redirects=False` kwargs inspection. Not just named — actually tested.


---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

