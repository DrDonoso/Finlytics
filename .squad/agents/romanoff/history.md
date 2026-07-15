# Project Context

- **Owner:** DrDonoso
- **Project:** Finlytics — personal bank-account expense tracking. The owner uploads a monthly bank-statement PDF (will evolve to xlsx/csv/other). An OpenAI-based information extractor pulls out transactions and categorizes them; data is persisted and shown as interactive charts in a frontend.
- **Stack:** TBD — Fury (Lead) to propose. Hard requirements from the owner: Docker, `.env`, a GitHub Actions deploy workflow, and OpenAI for extraction. Owner is stack-agnostic otherwise.
- **Created:** 2026-07-03

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

- **[2026-07-03 STACK]** Fury proposed Python 3.12 + FastAPI + PostgreSQL + React. Stack details + security boundaries in .squad/decisions.md. LiteLLM OpenAI SDK pattern + .env secrets wiring = critical surface.
- I own security + privacy. Highest-risk edge is the OpenAI boundary: no secrets in prompts, minimize PII, consider what leaves the machine. Bank statements are sensitive — data minimization, redact account numbers where possible, secrets only in `.env`/CI secret stores (never repo/image/logs), encrypt sensitive data at rest. I define policy; Rocket wires the plumbing.
- **[2026-07-03 PENDING]** Review raw-text→LLM PII boundary in extraction (Banner, Slice 2). Raw statement text sent to LLM with no pre-redaction; system prompt instructs model to omit IBANs/card numbers in description. Decide before production: accept (trust + validate) vs. pre-redact (strip sensitive fields) vs. minimize (send only transaction table pages).
- **[2026-07-03 RESOLVED]** PII boundary review COMPLETE. Implemented `redaction.py` — IBANs, card/PAN numbers, and long account numbers are now masked (last 4 preserved) before any text is sent to the third-party LLM. Redaction is applied in `extractor.py` at the LLM boundary only; local DB retains full-fidelity data. Secrets/logging verified clean. 62 tests pass. See `.squad/decisions/inbox/romanoff-pii-review.md` for full findings.
- **[2026-07-15 HEADS-UP: FIDELITY ESPP]** Feasibility probe complete for Fidelity ESPP statement-import connector. Findings: Banner's PDF extractor will require NEW PII redaction for **Participant Number** pattern: `I` + 8 digits (employee ID). Expand `redaction.py` regex. Also: full name, postal address must be masked before LLM. Flow MUST be: parse local → redact → LLM with sanitized text. PDF never stored in DB; only structured extracted data persists. Decision memo in `.squad/decisions.md` §2026-07-15T06:51:14Z. No real values or statement data in decision doc.

## Learnings (2026-07-09 Remember-Me)

- **[2026-07-09 IMPLEMENTED]** Remember-me on login. Two session modes controlled by `remember: bool` in the login body:
  - `remember=false` (default): browser-SESSION cookie (no `max_age`/`expires`, cleared on browser close) + JWT exp = `auth_token_expire_days` (default 7 days).
  - `remember=true`: PERSISTENT cookie (`max_age = auth_remember_expire_days * 86400`, default 30 days) + JWT exp = `auth_remember_expire_days` (default 30 days). Cookie survives browser close.
  - Setup endpoint (`/api/auth/setup`) uses non-remember defaults (session cookie, 7-day JWT) — no `remember` field required there.
  - All cookie security flags preserved: `httpOnly=True`, `samesite="lax"`, `secure=settings.auth_cookie_secure`, `path="/"`. No tokens or secrets are ever logged.
- **Files changed:** `src/finlytics/config.py` (added `auth_remember_expire_days: int = 30`), `src/finlytics/auth/security.py` (`create_token` now accepts optional `expire_days: int | None`), `src/finlytics/api/auth.py` (`remember` field in `LoginIn`, `_set_session_cookie` accepts `max_age: int | None`, login endpoint branches on `body.remember`). Tests: `tests/api/test_auth.py` (+4 remember-me tests). Full suite: **741 passed, 2 skipped**.

## Learnings (2026-07-03 PII Review)

- **What leaves the machine:** The user prompt sent to LiteLLM/OpenAI contains the full parsed statement text (PDF→text via pdfplumber). This includes IBANs, card numbers, account holder names, balances, and merchant details. After redaction: only last-4 of identifiers leave; amounts/dates/merchants pass through for extraction accuracy.
- **Redaction approach:** Pure-Python regex in `src/finlytics/extraction/redaction.py`. Applied in `extractor.py` line 101 (single call to `redact_pii()`) right before `build_user_prompt()`. Order: IBANs first (spaced, then compact), PAN numbers (spaced, then compact), then account numbers. Uses '•' as mask char.
- **Key design choice:** Redact only at the LLM boundary. Local PostgreSQL retains full original data because it's the owner's own machine. The `raw_line` field persisted to DB comes from the parser output before redaction — full fidelity preserved.
- **Secrets posture:** OPENAI_API_KEY loaded via pydantic-settings `.env` only; never logged, never in code. All logging in extraction pipeline logs metadata (account name, char count, run stats) — never raw text or API keys.
- **Remaining risk:** Prompt injection via crafted statement text — mitigated by structured outputs + temperature 0 + single-user. If multi-user ever added, revisit with input sanitization.

## Learnings (2026-07-14 Indexa Capital Token Security)

- **[2026-07-14 DESIGN]** Security design complete for Phase 2 Indexa connector. Full spec in `.squad/decisions/inbox/romanoff-indexa-token-security.md`.
- **[2026-07-14 ENCRYPTION]** Fernet confirmed for token-at-rest. Key env var: `INDEXA_ENCRYPTION_KEY`. Fail-closed: app refuses to start if key is absent or invalid — never falls back to plaintext. Column: `connections.token_enc` (TEXT, ciphertext only). Key rotation is a future ops task requiring re-encryption of all rows.
- **[2026-07-14 STORAGE]** Connections table stores: id, user_id, plugin_id, status, account_label_masked, token_enc, created_at, last_synced_at. Nothing else. Email, document/national-ID, and plaintext token are explicitly prohibited columns.
- **[2026-07-14 MASKING]** Account identifier masking format: first 3 chars + `•••` + last 2 chars (e.g. `PBK•••Z5`). Apply immediately on receipt from Indexa; store only the masked form.
- **[2026-07-14 VALIDATION]** Token must be validated via `GET /users/me` before storage. 401/403 → reject, do not store. Error messages include only HTTP status codes — never echo the token.
- **[2026-07-14 TRANSPORT]** TLS verify=True enforced — `verify=False` is a build blocker. Timeouts: 10s connect, 30s read. No redirect token leakage.
- **[2026-07-14 LEAST-PRIVILEGE]** GET-only Indexa calls. POST /auth/authenticate must not exist. Wizard accepts token only — no email/document/password fields.
- **[2026-07-14 ENV-TOKEN]** `INDEXA_API_TOKEN` in `.env` retained as dev-only bootstrap, commented out by default in `.env.example`. DB-stored encrypted token wins. Banned from production environments.
- **[2026-07-14 DISCONNECT]** Disconnect = hard-delete of `token_enc` row + clear of any cached holdings data. User notified to also revoke in Indexa UI.
- **[2026-07-14 BLOCKERS]** 7 build blockers defined (see threat model table in design doc). Key: no plaintext storage, no token in logs/API response, TLS verify=True, no POST auth path, fail-closed on missing key, hard-delete on disconnect.

## Learnings (2026-07-15 ESPP PDF Storage Privacy Review)

- **[2026-07-15 UPLOAD BEHAVIOR — CONFIRMED]** Bank statement PDFs **are already persisted** to disk. The one-shot endpoint (`create_import`) calls `_persist_import_run(session, ..., source_pdf=file_bytes)`, which writes the PDF to `settings.upload_dir` (`/app/data/uploads/`) on the mounted volume. The preview/confirm two-step flow discards the PDF in memory (no persistence). `parser.py` is purely in-memory. `/data/` is covered by `.gitignore` (explicit comment).
- **[2026-07-15 ESPP PDF STORAGE — VERDICT]** Storing the ESPP PDF on the mounted volume is **parity with existing bank statement behavior** — not a new risk surface. For a self-hosted single-user deployment, the incremental risk vs. bank statements is moderate (adds employer/HR-linked data: address, employee ID). Recommendation: (a) store as-is on volume, consistent with bank statements. Gitignore covers `/data/`. Docker image does not include it.
- **[2026-07-15 PRE-LLM REDACTION — NON-NEGOTIABLE]** Regardless of storage decision, `redact_pii()` must be extended before any ESPP LLM call to cover: (1) participant/employee number (`\b[A-Z]\d{6,9}\b`), (2) full name (header lines page 1), (3) postal address (header lines page 1). Current `redact_pii()` only covers IBANs/PANs/account numbers. This is separable from and independent of the storage decision.
- **[2026-07-15 CSV ALTERNATIVE]** A shares-only CSV carries far less PII than the full PDF (no name, address, or employee ID). It sidesteps almost the entire privacy debate. Limitation: CSV lacks individual lot detail (purchase date, price per lot, cost basis per lot) needed for gain/loss calculations. For a "current position + value in EUR" MVP, CSV is the cleanest option.

## Learnings (2026-07-14 Indexa Phase 2 Implementation Review)

- **[2026-07-14 REVIEW VERDICT]** ✅ PASS — all 8 security invariants verified against shipped Phase 2 code. See full table in `.squad/decisions/inbox/romanoff-indexa-token-security.md §10`.
- **[2026-07-14 ENV KEY CORRECTION]** Spec said `INDEXA_ENCRYPTION_KEY`. Owner decided on `FINLYTICS_ENCRYPTION_KEY` (app-wide key for all connectors). This is the correct implementation. Design doc updated to match.
- **[2026-07-14 FAIL-CLOSED CORRECTION]** Spec said "refuse to start". Owner decided on scoped fail-closed: app starts normally; only encrypt/decrypt operations fail with HTTP 503. This is correct. Design doc updated. Scoped behavior is implemented cleanly in `crypto.py` + API layer catches `EncryptionNotConfiguredError` → 503.
- **[2026-07-14 TRANSIENT ACCOUNT NUMBER]** `/connections/validate` returns raw `account_number` transiently to the wizard. Not a security issue: server re-validates ownership on connect, it's never stored, and account numbers are internal Indexa identifiers (not IBAN/email/DNI). Documented in code.
- **[2026-07-14 TEST QUALITY]** Barton's security-invariant tests genuinely assert the invariants: token-not-in-body string checks, `add`/`flush`/`commit` not-called assertions, keyword checks in 503 detail messages, `verify=True`/`follow_redirects=False` kwargs inspection. Not just named — actually tested.

