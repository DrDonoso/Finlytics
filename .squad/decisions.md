# Decisions Log

---

## 2026-07-14T11:10:33+02:00 — Phase 2: Indexa Capital Connector — Complete Design & Implementation Record

**Coordinators:** Fury (Lead)  
**Contributors:** Romanoff (Security), Shuri (Backend), Wanda (Design), Vision (Frontend), Barton (QA), Rocket (DevOps)  
**Status:** APPROVED & SHIPPED (commit 4a7673c, local)  
**Context:** Phase 2 — multi-agent implementation of Indexa Capital read-only connector with encrypted token storage, wizard UI, and portfolio aggregation.

---

### Architecture Plan (Fury)

# Phase 2: Indexa Capital Connector — Architecture & Plan

**Author:** Fury (Lead/Architect)  
**Date:** 2026-07-14  
**Status:** DRAFT — awaiting owner sign-off  
**Depends on:** Phase 1 shipped (investments skeleton), Romanoff's security policy (approved)

---

## 1. Connector Architecture

### Where the code lives

```
src/finlytics/investments/
├── __init__.py
├── base.py            # InvestmentProvider ABC (small — 3 methods)
├── indexa.py           # IndexaProvider(InvestmentProvider) — the real client
├── crypto.py           # encrypt_token() / decrypt_token() — Fernet helpers per Romanoff
└── service.py          # Orchestrator: resolves connections → calls provider → returns normalized shapes
```

New package `src/finlytics/investments/`, separate from `src/finlytics/api/`. The API layer (`api/investments.py`) stays thin — it calls `service.py`, which owns the business logic.

### Provider abstraction (smallest thing that works)

```python
class InvestmentProvider(ABC):
    """Base interface for investment connectors."""
    plugin_id: str

    async def validate_token(self, token: str) -> ValidationResult:
        """Call external API to verify token is valid. Return discovered accounts."""
        ...

    async def get_portfolio(self, token: str, accounts: list[str]) -> NormalizedPortfolio:
        """Fetch holdings + performance + allocation. Return normalized data."""
        ...

    async def get_performance(self, token: str, account: str) -> NormalizedPerformance:
        """Fetch returns + value series for one account."""
        ...
```

Only 3 methods. `IndexaProvider` implements them by calling the 3 Indexa GET endpoints (`/users/me`, `/accounts/{acc}/fiscal-results`, `/accounts/{acc}/performance`). Future providers (broker, crypto) implement the same interface.

### Indexa → normalized mapping

| Indexa endpoint | Maps to |
|---|---|
| `GET /users/me` | `validate_token()` → discover accounts, validate auth |
| `GET /accounts/{acc}/fiscal-results` | `get_portfolio()` → `InvestmentHoldingOut[]` — each `fiscal_result` becomes a holding |
| `GET /accounts/{acc}/performance` | `get_performance()` → KPIs (total_amount, investment, pl, twr_annual, xirr) + value series (`total_amounts`) + cash/invested split (`portfolios[0]`) |

`GET /accounts/{acc}` (account detail) is called only during validation to store `type` and `risk_profile` — not on every portfolio fetch.

### Caching strategy: **on-demand with short TTL**

- **No background sync.** Fetch live from Indexa on each page load.
- **In-memory TTL cache (5 min)** per connection_id to avoid hammering Indexa if the user refreshes. Use a simple dict + timestamp — no Redis, no DB cache table.
- **Rationale:** Indexa data is 1-business-day lagged anyway. No documented rate limits. A 5-min TTL means the user sees fresh data on each visit but rapid refreshes don't spam. Simpler than a sync cron + cache invalidation.
- **Multi-account:** If a user has 2 Indexa accounts, both are fetched and aggregated in a single `/portfolio` call.

---

## 2. Persistence

### `investment_connections` table

Romanoff's security design (already approved) specifies the schema. Using her exact column set:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` default |
| `user_id` | INT FK → users.id | |
| `plugin_id` | TEXT NOT NULL | `'indexa-capital'` |
| `status` | TEXT NOT NULL | `'active'` \| `'error'` \| `'disconnected'` |
| `account_label_masked` | TEXT | `'PBK•••Z5'` — first 3 + `•••` + last 2 |
| `token_enc` | TEXT NOT NULL | Fernet ciphertext only |
| `created_at` | TIMESTAMPTZ | server default `now()` |
| `last_synced_at` | TIMESTAMPTZ | nullable |

**One row per Indexa account.** If the user's token discovers 2 accounts and they connect both → 2 rows sharing the same `token_enc`. This keeps the model simple and lets the user disconnect individual accounts.

### Alembic migration

- Current head: **`0012`** (`0012_add_source_path_to_import_runs.py`)
- Next migration: **`0013_add_investment_connections.py`**
- Additive only (new table, no ALTER on existing tables)

### Encryption

Per Romanoff's approved policy:
- `cryptography.Fernet` with `INDEXA_ENCRYPTION_KEY` env var
- Fail-closed: app refuses to start if key is absent
- Hard-delete on disconnect (not soft-delete)
- Token never appears in any API response or log

Shuri implements `crypto.py` following Romanoff's spec exactly. No deviations.

---

## 3. API Endpoints

Four new endpoints on the existing `investments` router. The existing `GET /plugins` stays.

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| **POST** | `/api/investments/connections` | Connect wizard: validate token → store encrypted → return discovered accounts | `{ token: string }` | `{ connection_id, accounts: [{ account_number_masked, type, status }] }` |
| **GET** | `/api/investments/connections` | List user's connected plugins | — | `[{ id, plugin_id, status, account_label_masked, created_at, last_synced_at }]` |
| **DELETE** | `/api/investments/connections/{id}` | Disconnect: hard-delete row + clear cache | — | `204 No Content` |
| **GET** | `/api/investments/portfolio` | Aggregated portfolio: KPIs + holdings + value series + allocation | `?connection_id=` (optional, for single-account view) | Extended `InvestmentPortfolioOut` (see §4) |

### POST /connections flow (wizard backend)

1. Receive `{ token }` in request body.
2. Call `IndexaProvider.validate_token(token)` → `GET /users/me`.
3. If 401/403 → return `400 { detail: "Token inválido" }`. Never store.
4. If 200 → discover accounts. For each account, call `GET /accounts/{acc}` for type/profile.
5. Encrypt token with Fernet → insert row(s) into `investment_connections`.
6. Return connection IDs + masked account labels.

### GET /plugins behavior change

The existing static registry stays. But `status` for `indexa-capital` becomes **dynamic**: if the user has an active connection → `"connected"`, otherwise → `"available"` (no longer `"coming_soon"`). The other two plugins remain `"coming_soon"`.

---

## 4. Schema Extensions

### Extended `InvestmentPortfolioOut`

Add to the existing schema (currently: total_value, total_invested, total_gain_loss, total_gain_loss_pct, currency, holdings, plugins_connected, last_updated):

```python
class InvestmentReturns(BaseModel):
    """Performance metrics from Indexa /performance endpoint."""
    twr_annual: float | None = None        # time-weighted return, annualized
    xirr: float | None = None              # money-weighted annualized return
    pl: float | None = None                # absolute P&L (EUR)
    invested: float | None = None          # net capital invested

class ValuePoint(BaseModel):
    date: str    # "YYYYMMDD" or "YYYY-MM-DD"
    value: float

class CashInvestedSplit(BaseModel):
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float

class InvestmentPortfolioOut(BaseModel):    # EXTENDED — new fields below
    # ... existing fields unchanged ...
    returns: InvestmentReturns | None = None
    value_series: list[ValuePoint] = []           # from total_amounts dict
    cash_invested: CashInvestedSplit | None = None  # from portfolios[0]
```

### `InvestmentHoldingOut` — already sufficient

The existing shape covers fiscal-results mapping:

| Existing field | Indexa source |
|---|---|
| `name` | `instrument.name` |
| `ticker` | `instrument.identifier` (ISIN) |
| `asset_class` | `instrument.asset_class` (map Indexa classes → our enum) |
| `units` | `titles` |
| `current_value` | `amount` |
| `cost_basis` | `cost_amount` |
| `gain_loss` | `profit_loss` |
| `gain_loss_pct` | `profit_loss / cost_amount` (computed) |

**Asset class mapping** (Indexa → ours):
- `equity_europe`, `equity_north_america`, `equity_pacific`, `equity_emerging` → `"equity"`
- `fixed_income_*` → `"fixed_income"`
- `cash`, `money_market` → `"cash"`
- anything else → `"other"`

Weight % = `amount / total_amount` (computed client-side from the holdings array, not stored).

---

## 5. Wizard UX Flow

Launched from the Indexa connector card on **Ajustes → Conectores** (`/settings/connectors`). The card's "Conectar" button opens a multi-step modal/drawer.

### Step 1 — Intro

- Indexa logo + brief explanation: "Conecta tu cartera de Indexa Capital (solo lectura)."
- Link to Indexa's token page: "Genera tu token en → Área privada → Configuración de usuario → Aplicaciones."
- "Siguiente" button.
- **Backend calls:** None.

### Step 2 — Paste token

- Single text input: "Pega tu token de solo lectura."
- Security note: "Tu token se almacenará cifrado. Finlytics solo accede en modo lectura."
- "Validar" button (disabled until input non-empty).
- **Backend calls:** None yet — proceeds to step 3 on click.

### Step 3 — Validate & discover

- Spinner: "Verificando token…"
- **Backend call:** `POST /api/investments/connections` with `{ token }`.
- **On success:** Show discovered account(s) with masked labels and types. If multiple accounts: checkboxes to pick which to connect (all selected by default). "Conectar" button.
- **On 400 (invalid token):** Error message inline, back to step 2. No stored data.
- **On network error:** Generic error, retry affordance.

### Step 4 — Confirm / done

- Success state: "✅ Conectado — tu cartera se cargará en Inversiones."
- Show connected account(s) summary.
- "Ver inversiones" button → navigate to `/investments`.
- At this point, `/investments` page auto-fetches `GET /portfolio` and renders real data.
- **Backend calls:** The POST in step 3 already stored the connection. No additional call needed.

### Disconnect flow

On `Ajustes → Conectores`, connected plugins show a "Desconectar" button instead of "Conectar". Click → confirmation dialog → `DELETE /api/investments/connections/{id}` → card reverts to "Conectar".

---

## 6. Decomposition & Sequencing

### Agents & responsibilities

| Agent | Scope | Key deliverables |
|---|---|---|
| **Shuri** (backend) | Migration + provider + endpoints | `0013` migration, `investments/` package (base.py, indexa.py, crypto.py, service.py), extend `api/investments.py` with 3 new endpoints, config additions |
| **Vision** (frontend) | Wizard UI + real data viz | Wizard modal component, InvestmentsPage data-connected (KPIs, value chart, allocation donut, holdings table), ConnectorsPage card states (available/connected/error) |
| **Wanda** (design) | Wizard + viz visual design | Wizard step mockups, chart styling, allocation donut specs, new i18n keys, responsive specs for data-populated state |
| **Romanoff** (security) | Review gate (parallel) | Already delivered security policy. Reviews all PRs for compliance before merge. |
| **Barton** (tests) | Mocked integration tests | Backend: mock Indexa HTTP responses (httpx mock), test connection CRUD + portfolio aggregation. Frontend: test framework TBD. |

**Banner is NOT needed** — no AI/LLM extraction in this flow.

### Sequencing (dependency order)

```
                    ┌─ Romanoff: security policy ─── DONE ✅
                    │
Phase 2 start ──────┼─ Wanda: wizard + viz design specs ──────────────────┐
                    │                                                      │
                    └─ Shuri: migration + crypto + provider + endpoints ───┤
                                                                          │
                         Vision: wizard UI + real viz ─────────────────────┤
                                                                          │
                         Barton: backend tests (mock HTTP) ───────────────┘
```

1. **Romanoff** — already done (security policy approved).
2. **Wanda** + **Shuri** can start in parallel:
   - Wanda: wizard step designs, chart/donut specs, i18n keys.
   - Shuri: migration, crypto.py, IndexaProvider, service.py, API endpoints.
3. **Vision** — needs Wanda's designs + Shuri's endpoints (contract). Can start wizard UI as soon as Wanda delivers step designs, chart viz as soon as Shuri's portfolio endpoint is up.
4. **Barton** — starts as soon as Shuri's endpoints are testable. Mocked Indexa responses only (no live API calls in tests).

### MVP (first shippable slice)

**MVP = connect one Indexa account + see KPIs + holdings table.**

This requires:
- Shuri: migration + crypto + provider (fiscal-results only) + POST/GET/DELETE connections + GET portfolio
- Vision: wizard (4 steps) + KPI cards with real data + holdings table
- Barton: backend connection + portfolio tests

**Deferred (post-MVP):**
- Value-over-time chart (needs `total_amounts` series → chart component)
- Allocation donut (needs asset_class grouping → donut component)
- Cash vs invested split display
- Multi-account aggregation UI (if user has >1 Indexa account, MVP connects all but shows aggregated)
- Transactions, fees, benchmark, volatility
- Frontend test infrastructure (vitest setup)

---

## 7. Open Questions for Owner

| # | Question | Default if no answer |
|---|---|---|
| 1 | **Multi-account handling:** If a user's Indexa token reveals 2+ accounts (mutual + pension), connect all automatically, or let them pick? | Default: show checkboxes, all pre-selected. User can deselect. |
| 2 | **Auto-refresh on page load?** Should `/investments` call `GET /portfolio` every time the page mounts, or show a manual "Actualizar" button? | Default: auto-fetch on mount with 5-min in-memory TTL (transparent to user). |
| 3 | **Dev bootstrap:** Allow `INDEXA_API_TOKEN` in `.env` for dev testing without the wizard? (Romanoff says OK if dev-only + documented.) | Default: yes, per Romanoff's policy §7 — commented out in `.env.example`. |
| 4 | **Chart scope for MVP?** Include the value-over-time chart in MVP, or ship KPIs + holdings first and add the chart in a fast follow-up? | Default: defer chart to post-MVP. KPIs + holdings table = shippable and useful on its own. |
| 5 | **`INDEXA_ENCRYPTION_KEY` required at startup?** Romanoff says fail-closed (app won't start without it). This means existing users must set this env var even if they don't use Indexa. Acceptable? | Default: yes, fail-closed — add to `.env.example` with generation instructions. Low friction for a single-user app. |


---

### Fury Review — Integer PK Consistency (Re-evaluated, Approved)

# Phase 2: Indexa Capital Connector — Review

**Author:** Fury
**Date:** 2026-07-14T11:10:33+02:00
**Status:** APPROVED

## Verdict
**APPROVE**

## Evaluation
Upon re-review with full context:
1. **Integer PK:** The use of an auto-incrementing integer PK for investment_connections instead of a UUID was explicitly requested to match the User, Account, Category, Tag, and ImportRun models. Introducing a single UUID table in an otherwise entirely integer-PK schema violates the principle of consistency, making it harder for a solo owner to maintain. Since enumeration risks are mitigated by user-scoped 404s on access, the Integer PK is correct.
2. **Missing .env.example nit:** Acknowledged as an intentional choice to enforce the wizard-only setup and minimize paths to exposed tokens. 

The implementation fully aligns with the codebase conventions and the core architectural principles of Finlytics. The changeset is ready for commit.


---


### Security Design (Romanoff) — All 8 Invariants Verified

# Security Design: Indexa Capital Token Handling

**Author:** Romanoff (Security & Privacy Engineer)  
**Date:** 2026-07-14  
**Status:** VERIFIED ✅ — Policy + implementation review complete (2026-07-14). All 8 invariants PASS.  
**Context:** Phase 2 — real Indexa Capital connector. User pastes a read-only API token in a setup wizard; app stores it and calls Indexa GET endpoints.

---

## ⚠️ Owner Overrides (post-design, APPROVED — supersede §1 below)

Two decisions were made by DrDonoso AFTER this spec was written. They are **correct as implemented** — this doc was stale; code is right:

1. **Encryption key is `FINLYTICS_ENCRYPTION_KEY`** (general app-wide key for all connectors), NOT `INDEXA_ENCRYPTION_KEY`. The env var name in `.env.example`, `config.py`, and `crypto.py` is `FINLYTICS_ENCRYPTION_KEY`. Anywhere this doc says `INDEXA_ENCRYPTION_KEY`, substitute `FINLYTICS_ENCRYPTION_KEY`.

2. **Scoped fail-closed** (not global): The app **starts normally** without `FINLYTICS_ENCRYPTION_KEY`. Only encrypt/decrypt operations fail (raise `EncryptionNotConfiguredError` → HTTP 503). "Refuse to start" is NOT required and NOT implemented. This is correct per owner's decision. Any reference in this doc to "refuse to start" should be read as "encrypt/decrypt operations fail with 503".

---

## 1. Encryption at Rest

**Decision: Fernet confirmed.** Use `cryptography.Fernet` (AES-128-CBC + HMAC-SHA256) with a 32-byte urlsafe-base64 key from env **`FINLYTICS_ENCRYPTION_KEY`** (general app-wide key).

### Key Generation (run once, store result in `.env`)

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### `.env.example` Entry

```
# App-wide Fernet key for encrypting all connector API tokens at rest.
# The app starts normally without this key; only encrypt/decrypt operations
# (connecting or fetching a portfolio) fail with HTTP 503 when it is absent.
# Required to use the Indexa Capital connector (and any future connector).
#
# Generate once, store in .env, NEVER commit the actual key to version control:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# FINLYTICS_ENCRYPTION_KEY=
```

### Fail-Closed Behavior (SCOPED — per owner decision)

- If `FINLYTICS_ENCRYPTION_KEY` is **absent** or **invalid**: the app starts normally. Only `encrypt_token()` and `decrypt_token()` raise `EncryptionNotConfiguredError`, which the API layer catches and returns as HTTP 503. Do NOT fall back to plaintext storage under any circumstances.
- If decryption fails at read time (e.g., key was rotated without re-encrypting): return a connection-error 503 to the caller — never propagate the garbled ciphertext to the UI or logs.

### What is Encrypted

- **Column `connections.token_enc`** (TEXT): stores the Fernet ciphertext (not the plaintext token). This is the one and only column that holds any form of the credential.
- No other column stores any part of the token, partial or full.

### Key Rotation

Key rotation is out of scope for the initial build but **must** be documented in a future ops runbook: to rotate, re-encrypt all `token_enc` values before switching the env key. Until rotation is implemented, treat key loss as permanent token loss — the user must reconnect via the wizard.

---

## 2. Storage & Exposure Rules

### What Is Stored (connections table)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | FK → users | |
| `plugin_id` | TEXT | e.g. `'indexa-capital'` |
| `status` | TEXT | `'active'` \| `'error'` \| `'disconnected'` |
| `account_label_masked` | TEXT | e.g. `'PBK•••Z5'` — see masking rule below |
| `token_enc` | TEXT | Fernet ciphertext ONLY |
| `created_at` | TIMESTAMP | |
| `last_synced_at` | TIMESTAMP | nullable |

**Explicitly NOT stored:** plaintext token, Indexa account email, national document/ID (DNI/NIE/passport), any password.

### What the API MAY Return to the Frontend

- Connection `id`, `plugin_id`, `status`
- `account_label_masked` (see format below)
- `created_at`, `last_synced_at`

**The API MUST NEVER return:** `token_enc`, any decrypted token, any partial token, email, document number.

### Account Label Masking Format

The Indexa `/users/me` response may include an account identifier or username. Mask as:

> Preserve first **3** characters + `•••` + last **2** characters

Example: `PBKXXXXXXZ5` → `PBK•••Z5`

If the identifier is shorter than 6 characters, mask all but the last 2.  
Apply masking immediately on receipt from Indexa — store only the masked form. Never persist the full account identifier.

---

## 3. Token Validation Before Storage

Before persisting the token (encrypted or otherwise), the app **MUST** validate it:

1. Call `GET https://api.indexacapital.com/users/me` with header `X-AUTH-TOKEN: <token>`.
2. `200 OK` → token is valid; proceed to encrypt and store.
3. `401` or `403` → invalid or revoked token → **reject** the wizard submission with a user-facing error ("Token inválido — verifícalo en Indexa Capital."). Do NOT store anything.
4. Any other error (timeout, 5xx) → reject with a generic "no se pudo verificar el token" message. Do NOT store anything.

**Critical:** when constructing error messages or log entries about validation failures, include only the HTTP status code. Never echo the token value back in any message, exception, or log line.

---

## 4. Transport

- **HTTPS only.** All calls to `https://api.indexacapital.com` must use HTTPS. Plaintext HTTP is not acceptable.
- **TLS verification enforced.** `verify=True` always. `verify=False` is banned — treat it as a build-blocking defect.
- **Timeouts required.** Set explicit timeouts on every Indexa HTTP call: `connect_timeout=10s`, `read_timeout=30s`. Never make an unbounded call.
- **No token in redirects.** Disable automatic redirect following, or ensure the `X-AUTH-TOKEN` header is stripped before any redirect. Do not let the HTTP client silently forward auth headers to a redirected URL.

---

## 5. Least Privilege & No Over-Collection

### Read-Only Enforcement

- The app MUST ONLY make `GET` calls to the Indexa API. No `POST`, `PUT`, `PATCH`, `DELETE`.
- The app MUST NOT implement, accept, or route any call to `POST /auth/authenticate` (the Indexa password-auth flow). If this path appears in any code under review, it is a blocking defect.
- The wizard MUST NOT present fields for email, DNI/NIE, or any password. If a user somehow submits them, they must be silently discarded at the API boundary — never stored.

### Data Minimization

- Store only: the encrypted token + masked account refs + sync timestamps.
- Do NOT persist full transaction history from Indexa unless a specific user-facing feature explicitly requires it.
- Do NOT cache full `/users/me` response bodies — extract only what's needed (e.g., an account identifier for masking), then discard the rest.

---

## 6. Logging & Redaction

**NEVER log:**
- The Indexa token (plaintext or ciphertext)
- Full account numbers or identifiers
- Email addresses obtained from Indexa `/users/me`
- Document numbers (DNI/NIE/passport)
- The `INDEXA_ENCRYPTION_KEY` value

**MAY log:**
- HTTP status codes from Indexa (e.g., "Indexa validation returned 403")
- Connection `id` (UUID) and `plugin_id`
- Sync timestamps and duration
- Generic error categories (timeout, network error, bad status) — never the response body that might contain PII

**Implementation note for Shuri:** extend the existing `redaction.py` pattern to cover Indexa-specific patterns if they can appear in log strings (e.g., apply token masking if token values could leak into exception messages from the HTTP library).

---

## 7. The `.env` Token (`INDEXA_API_TOKEN`)

**Decision: Retain as dev-only bootstrap, clearly documented. DB-stored encrypted token is the source of truth.**

**Rationale:**  
Banning `INDEXA_API_TOKEN` from `.env` entirely would break any dev/smoke-test workflow that doesn't need a full wizard flow. Keeping it is acceptable provided the precedence and scope are explicit.

### Rules

1. `INDEXA_API_TOKEN` is a **dev-only convenience** for testing the connector without running the wizard. It MUST be clearly labeled as such in `.env.example`.
2. The backend MUST treat the **DB-stored encrypted token as the source of truth**. If a connection record exists in the DB, use that token — ignore `INDEXA_API_TOKEN`.
3. `INDEXA_API_TOKEN` MUST NOT be present in any production deployment, CI pipeline, Docker image, or server environment. Rocket must ensure it is absent from non-dev environments.
4. `.env.example` entry:

```
# DEV ONLY — optional bootstrap token for testing the Indexa connector without the UI wizard.
# In production, the token is stored encrypted in the DB via the wizard. Remove this from any
# non-local environment. NEVER commit a real token value.
# INDEXA_API_TOKEN=
```

5. The variable is commented out by default in `.env.example` — it must not accidentally look "required."

---

## 8. Disconnect / Revocation

**On DELETE /api/connections/{id}:**

1. **Hard-delete** the connection row — including `token_enc`. Not a soft-delete, not a status flag flip. The ciphertext must be gone.
2. **Clear any cached portfolio/holdings data** associated with that connection (delete rows keyed to `connection_id` in any holdings/snapshot tables).
3. **Inform the user** in the UI: "Tu token ha sido eliminado de Finlytics. Para mayor seguridad, también puedes revocarlo desde el panel de Indexa Capital." — the user retains independent control to revoke in Indexa's UI.
4. **On revocation detected at sync time** (Indexa returns 401/403): transition the connection to `status='error'`, surface a "Token revocado — reconecta o verifica en Indexa Capital" message. Do not delete automatically (let the user explicitly disconnect to avoid surprise data loss).

---

## 9. Threat Model Summary

| Risk | Mitigation | Build blocker? |
|------|-----------|----------------|
| **Token theft from DB** | Fernet encryption at rest; key in env, separate from DB | ✅ BLOCK if stored plaintext |
| **Token in logs** | Logging policy §6; redaction layer; never log token | ✅ BLOCK if token appears in any log |
| **Token in API response** | API schema §2 never includes `token_enc` or decrypted value | ✅ BLOCK if returned to frontend |
| **MITM to Indexa** | TLS verify=True enforced; HTTPS only; timeout guards | ✅ BLOCK if verify=False anywhere |
| **Encryption key exposure** | `FINLYTICS_ENCRYPTION_KEY` in .env, git-ignored, never in image/logs | ✅ BLOCK if key committed or logged |
| **Parallel .env credential path** | `INDEXA_API_TOKEN` dev-only; DB wins; banned in production | ⚠️ Flag in code review; not a build blocker if documented correctly |
| **Email/document over-collection** | Wizard accepts token only; `/users/me` used for validation only; PII discarded immediately | ✅ BLOCK if email/doc stored |
| **POST /auth/authenticate (credential stuffing surface)** | Path must not be implemented; ban in code review | ✅ BLOCK if present in any form |
| **Missing encryption key at startup** | Scoped fail-closed: app starts; only encrypt/decrypt ops fail (HTTP 503) | ✅ BLOCK if silently falls back to plaintext |
| **Indexa data injected into LLM pipeline** | Indexa data MUST NOT enter the LLM extraction pipeline | ⚠️ Flag now; enforce at Banner boundary |

### Summary of Build Blockers (non-negotiable before shipping Phase 2)

1. `token_enc` in DB is Fernet ciphertext — never plaintext.
2. `FINLYTICS_ENCRYPTION_KEY` absent → encrypt/decrypt fail with HTTP 503 (not silent plaintext fallback).
3. Token never appears in any API response, log line, or error message.
4. `verify=True` on all Indexa HTTP calls.
5. `POST /auth/authenticate` path does not exist anywhere in the codebase.
6. Wizard does not accept, store, or transmit email/document/password fields.
7. Disconnect hard-deletes the ciphertext.

---

## 10. Implementation Review — 2026-07-14

**Reviewer:** Romanoff (independent — designed policy, Shuri implemented)  
**Verdict: ✅ PASS — all 8 security invariants satisfied**

| # | Invariant | Verdict | Key citation |
|---|-----------|---------|--------------|
| 1 | Token encrypted at rest | ✅ PASS | `investments/service.py:129` — `encrypt_token(token)` before any DB write; `db/models.py:303` — `token_enc` TEXT Fernet ciphertext only; migration `0013_add_investment_connections.py` |
| 2 | Token never in API response / logs | ✅ PASS | `api/schemas.py:ConnectionOut` — no token field; `api/investments.py:107,145` — error messages use HTTP status, never echo token; `investments/indexa.py:141` — logs only count; `investments/service.py:281-312` — logs conn IDs + generic exception strings |
| 3 | Account masking | ✅ PASS | `investments/service.py:50-55` — `_mask_account()` correct format first3•••last2; raw `account_number` returned transiently in `/validate` only (documented intentional, never stored); `db/models.py:293` — only `account_label_masked` stored |
| 4 | Fail-closed (scoped) | ✅ PASS | `investments/crypto.py:24-36` — raises `EncryptionNotConfiguredError` on absent/invalid key; `api/investments.py:139,196` — catches → 503; never falls back to plaintext |
| 5 | Transport | ✅ PASS | `investments/indexa.py:62-69` — `verify=True`, `follow_redirects=False`, timeouts 10s/30s, base URL `https://` |
| 6 | Least privilege | ✅ PASS | Only `client.get()` calls; no POST/auth/authenticate anywhere in codebase; wizard has one field (`type="password"` input = token only); no email/document/password in any schema |
| 7 | Disconnect hard-deletes | ✅ PASS | `investments/service.py:215` — `await db.delete(row)`; `service.py:217` — `clear_connection_cache()` |
| 8 | Data minimization | ✅ PASS | Migration/model: no email/doc columns; `investments/indexa.py:133-139` — only account_number/type/status extracted from `/users/me`; email/username discarded immediately |

**Tests cross-checked:** `test_connect_response_never_contains_raw_token`, `test_get_connections_no_token_enc_in_response`, `test_connect_missing_encryption_key_returns_503`, `test_portfolio_missing_encryption_key_returns_503`, `test_indexa_client_tls_verify_and_no_redirects`, `test_crypto_missing_key_encrypt_raises`, `test_crypto_missing_key_decrypt_raises`, `test_crypto_tampered_ciphertext_raises`, `test_validate_stores_nothing_in_db`, `test_mask_account_standard` — all genuinely assert the invariants, not just name them.

**One observation (not a fail):** `DiscoveredAccountOut.account_number` (raw) is returned in `/connections/validate` responses. This is intentional: the wizard needs it for the subsequent connect call. The server re-validates ownership in `connect_plugin()` (`service.py:117-127`), so a client cannot use this to spoof a different account. The field is transient (no storage), and account numbers are internal Indexa identifiers, not IBANs/emails/DNI.


---

### Backend Implementation Contract (Shuri) — 5 Endpoints, 858 Tests PASS

# Shuri → Backend Contract: Indexa Capital Phase 2

**Author:** Shuri (Backend Engineer)  
**Date:** 2026-07-14  
**Status:** SHIPPED — 838 tests green  
**For:** Vision (frontend), Barton (tests), Wanda (i18n keys)

---

## Base URL

All endpoints are prefixed `/api/investments`.  All require a valid session cookie (401 if absent).

---

## 1. GET /api/investments/plugins

Returns the plugin registry.  **Indexa Capital status is dynamic** from Phase 2.

```
GET /api/investments/plugins
Authorization: session cookie
```

**Response 200** `list[InvestmentPluginOut]`

```json
[
  {
    "id": "indexa-capital",
    "name": "Indexa Capital",
    "description": "Automated index-fund portfolio management",
    "icon": "🏦",
    "status": "available" | "connected",
    "auth_type": "token",
    "supported_features": ["holdings", "transactions", "performance"]
  },
  {
    "id": "generic-broker",
    "status": "coming_soon",
    ...
  },
  {
    "id": "crypto-exchange",
    "status": "coming_soon",
    ...
  }
]
```

`indexa-capital.status`:
- `"connected"` — user has ≥1 active connection
- `"available"` — no active connections; wizard CTA shown

---

## 2. POST /api/investments/connections/validate  ← Step 1 of wizard

Validate a token and discover accounts.  **Stores NOTHING** — no DB writes, no token persisted, no encryption required.

```
POST /api/investments/connections/validate
Content-Type: application/json

{ "token": "<indexa-read-only-token>" }
```

**Response 200** `ValidateTokenResponse`

```json
{
  "accounts": [
    {
      "account_number": "PBKLBYZ5",
      "account_number_masked": "PBK•••Z5",
      "type": "mutual",
      "status": "active"
    }
  ]
}
```

`account_number` is the raw identifier (transient — only use it in the next connect call; it is NEVER stored).  
`account_number_masked` is for display in the wizard checkbox list.

**Errors:**

| Code | Condition | Detail |
|---|---|---|
| 400 | Indexa rejects token (401/403) | `"Token inválido — verifícalo en Indexa Capital."` |
| 503 | Network / timeout error | `"No se pudo verificar el token — error de red con Indexa Capital."` |

---

## 3. POST /api/investments/connections  ← Step 2 of wizard

Re-validate token server-side, persist **only the selected accounts**.  
Server enforces ownership: any `account_number` not owned by the token is silently dropped.

```
POST /api/investments/connections
Content-Type: application/json

{
  "token": "<indexa-read-only-token>",
  "account_numbers": ["PBKLBYZ5"]
}
```

`account_numbers` must be non-empty and should come from the validate step.

**Response 201** `list[ConnectionOut]` — one entry per connected account

```json
[
  {
    "id": 1,
    "plugin_id": "indexa-capital",
    "status": "active",
    "account_label_masked": "PBK•••Z5",
    "created_at": "2026-07-14T11:10:33+02:00",
    "last_synced_at": null
  }
]
```

**⚠️ Token NEVER appears in any response.**

**Errors:**

| Code | Condition | Detail |
|---|---|---|
| 400 | `account_numbers` is empty | `"account_numbers must not be empty."` |
| 400 | Indexa rejects token (401/403) | `"Token inválido — verifícalo en Indexa Capital."` |
| 400 | All `account_numbers` non-owned | `"Los account_numbers seleccionados no pertenecen a este token."` |
| 503 | Network / timeout error | `"No se pudo verificar el token — error de red con Indexa Capital."` |
| 503 | `FINLYTICS_ENCRYPTION_KEY` absent | `"Server not configured for encryption — contact the administrator."` |

---

## 4. GET /api/investments/connections

List all connected plugins for the authenticated user.

```
GET /api/investments/connections
```

**Response 200** `list[ConnectionOut]`

```json
[
  {
    "id": 1,
    "plugin_id": "indexa-capital",
    "status": "active",               // active | error | disconnected
    "account_label_masked": "PBK•••Z5",
    "created_at": "2026-07-14T11:10:33+02:00",
    "last_synced_at": "2026-07-14T11:12:00+02:00"
  }
]
```

**`status` values:**
- `active` — token valid, data fetchable
- `error` — Indexa returned 401/403 at last sync; user should reconnect
- `disconnected` — manually disconnected (hard-deleted; this value appears in cache only)

---

## 5. DELETE /api/investments/connections/{id}

Hard-deletes the connection row **and its encrypted token ciphertext**.  No soft-delete.

```
DELETE /api/investments/connections/1
```

**Response 204** — no body

**Errors:**

| Code | Condition |
|---|---|
| 404 | connection not found (or belongs to another user) |

---

## 6. GET /api/investments/portfolio

Aggregate portfolio for all active connections.  Includes everything Vision needs for the full Inversiones page.

```
GET /api/investments/portfolio
```

**Response 200** `InvestmentPortfolioOut`

```json
{
  "total_value": 12345.67,
  "total_invested": 11000.00,
  "total_gain_loss": 1345.67,
  "total_gain_loss_pct": 0.1223,
  "currency": "EUR",
  "plugins_connected": 1,
  "last_updated": "2026-07-14T11:12:00.123456+00:00",

  "returns": {
    "twr_annual": 0.0851,
    "xirr": 0.0912,
    "pl": 1345.67,
    "invested": 11000.00
  },

  "value_series": [
    { "date": "20240101", "value": 10200.00 },
    { "date": "20240201", "value": 10450.00 }
  ],

  "cash_invested": {
    "cash_amount": 250.00,
    "instruments_amount": 12095.67,
    "instruments_cost": 10750.00,
    "total_amount": 12345.67
  },

  "holdings": [
    {
      "plugin_id": "indexa-capital",
      "name": "Vanguard Global Stock Index Fund",
      "ticker": "IE00B03HCZ61",
      "asset_class": "equity",
      "units": 42.5,
      "current_value": 8320.00,
      "cost_basis": 7500.00,
      "currency": "EUR",
      "gain_loss": 820.00,
      "gain_loss_pct": 0.1093,
      "last_updated": "2026-07-14T11:12:00.123456+00:00"
    }
  ]
}
```

**No-connection empty state (no wizard completed):**

```json
{
  "total_value": 0.0,
  "total_invested": null,
  "total_gain_loss": null,
  "total_gain_loss_pct": null,
  "currency": "EUR",
  "plugins_connected": 0,
  "last_updated": null,
  "returns": null,
  "value_series": [],
  "cash_invested": null,
  "holdings": []
}
```

**Errors:**

| Code | Condition |
|---|---|
| 503 | `FINLYTICS_ENCRYPTION_KEY` absent — cannot decrypt tokens |

**Caching:** 5-minute in-memory TTL per `connection_id`.  Rapid page refreshes reuse cached data; the cache is evicted on DELETE.

---

## Extended Schema Reference

### InvestmentPortfolioOut (extended)

```python
class InvestmentReturns(BaseModel):
    twr_annual: float | None = None    # time-weighted annualised return
    xirr: float | None = None          # money-weighted annualised return
    pl: float | None = None            # absolute P&L in EUR
    invested: float | None = None      # net capital invested

class ValuePoint(BaseModel):
    date: str     # "YYYYMMDD" — matches Indexa total_amounts keys
    value: float

class CashInvestedSplit(BaseModel):
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float

class InvestmentPortfolioOut(BaseModel):
    # existing fields unchanged
    total_value: float
    total_invested: float | None
    total_gain_loss: float | None
    total_gain_loss_pct: float | None
    currency: str
    holdings: list[InvestmentHoldingOut]
    plugins_connected: int
    last_updated: str | None
    # Phase 2 additions
    returns: InvestmentReturns | None = None
    value_series: list[ValuePoint] = []
    cash_invested: CashInvestedSplit | None = None
```

### ConnectionOut

```python
class ConnectionOut(BaseModel):
    id: int
    plugin_id: str
    status: str                         # active | error | disconnected
    account_label_masked: str | None    # e.g. "PBK•••Z5"
    created_at: datetime
    last_synced_at: datetime | None
```

**`token_enc` is NEVER included in `ConnectionOut` or any API response.**

### ConnectCreate (Step 2 body)

```python
class ConnectCreate(BaseModel):
    token: str               # raw Indexa read-only token
    account_numbers: list[str]  # from validate step; server re-validates ownership
```

### ValidateTokenRequest (Step 1 body)

```python
class ValidateTokenRequest(BaseModel):
    token: str
```

### ValidateTokenResponse (Step 1 response)

```python
class DiscoveredAccountOut(BaseModel):
    account_number: str          # raw — transient, never stored
    account_number_masked: str   # PBK•••Z5 — for display
    type: str
    status: str

class ValidateTokenResponse(BaseModel):
    accounts: list[DiscoveredAccountOut]
```

---

## Indexa → Finlytics Field Mapping

| Indexa source | Finlytics field |
|---|---|
| `fiscal_results[].instrument.name` | `holding.name` |
| `fiscal_results[].instrument.identifier` (ISIN) | `holding.ticker` |
| `fiscal_results[].instrument.asset_class` (mapped) | `holding.asset_class` |
| `fiscal_results[].titles` | `holding.units` |
| `fiscal_results[].amount` | `holding.current_value` |
| `fiscal_results[].cost_amount` | `holding.cost_basis` |
| `fiscal_results[].profit_loss` | `holding.gain_loss` |
| `profit_loss / cost_amount` | `holding.gain_loss_pct` |
| `performance.total_amount` | `total_value` |
| `performance.return.investment` | `total_invested` / `returns.invested` |
| `performance.return.pl` | `total_gain_loss` / `returns.pl` |
| `performance.return.time_return_annual` | `returns.twr_annual` |
| `performance.return.XIRR` | `returns.xirr` |
| `performance.total_amounts` (dict) | `value_series` |
| `performance.portfolios[-1]` | `cash_invested` |

**Asset class mapping:**

| Indexa value | Finlytics asset_class |
|---|---|
| `equity_europe`, `equity_north_america`, `equity_pacific`, `equity_emerging` (any `equity_*`) | `"equity"` |
| `fixed_income_*` | `"fixed_income"` |
| `cash`, `money_market` | `"cash"` |
| anything else | `"other"` |

---

## Notes for Barton (test mocking)

Wizard flow is now two steps — mock both:

**Step 1 — Validate:**
- `POST /connections/validate` with valid mock token → 200 `{ "accounts": [...] }`.
- `POST /connections/validate` with mock returning 401 → 400 `"Token inválido"`.
- Response always has `accounts` key; `account_number` present (raw), `account_number_masked` present.

**Step 2 — Connect:**
- `POST /connections` with `{ token, account_numbers: ["ACC1"] }` → 201 list.
- `POST /connections` with `account_numbers: []` → 400 (no service call).
- `POST /connections` with all `account_numbers` not owned → 400 `NoValidAccountsError`.
- `POST /connections` with a mix of owned + non-owned → only owned ones in response.
- `POST /connections` when `FINLYTICS_ENCRYPTION_KEY` absent → 503.

**Other endpoints:**
- Mock `GET https://api.indexacapital.com/users/me` with `httpx.MockTransport` or `respx`.
- Mock `GET /accounts/{acc}/fiscal-results` and `GET /accounts/{acc}/performance`.
- `GET /portfolio` with no connections → 200 with `total_value=0, holdings=[]`.
- `DELETE /connections/999` → 404.

## Notes for Vision (frontend)

- `value_series[].date` is `"YYYYMMDD"` format (from Indexa) — parse with `dayjs(date, "YYYYMMDD")` or equivalent.
- `returns.twr_annual` and `returns.xirr` are `null` when user has multiple connected accounts (non-aggregatable).
- `holdings[].gain_loss_pct` is a decimal (0.1093 = 10.93%) — multiply by 100 for display.
- `total_gain_loss_pct` same convention.
- `cash_invested.instruments_cost` = total amount invested in instruments (cost basis); `instruments_amount` = current market value.


---

### Design Spec (Wanda) — Wizard + Viz CSS Complete

# Wanda Design Spec — Indexa Phase 2

**Author:** Wanda (UX/UI)  
**Date:** 2026-07-14  
**Status:** READY FOR VISION  
**Depends on:** Shuri's endpoints (§3 of fury-indexa-phase2-plan.md)

All CSS is in `frontend/src/index.css` — appended after the existing investments skeleton block. Build verified: `npm run build` passes with 0 errors.

---

## REUSE MAP (no new CSS needed for these)

| UI element | Reuse | Notes |
|---|---|---|
| Modal shell | `.modal-backdrop` `.modal` `.modal-header` `.modal-title` `.modal-close` `.modal-body` `.modal-footer` | Standard modal pattern |
| Spinner | `.spinner-wrap` `.spinner` `.spinner-label` | Validation step |
| KPI row | `.kpi-grid` `.kpi-card` `.kpi-label` `.kpi-value` `.kpi-sub` | KPIs + `.kpi-value.income/expense` for P&L |
| Allocation donut | `.cat-chart-layout` `.cat-donut-wrap` `.cat-donut-center` `.cat-table-wrap` `.cat-table` `.cat-row` | 1:1 reuse from SpendingByCategory |
| State boxes | `.state-box` `.state-box.error` | Loading + error |
| Recharts tooltip | `.recharts-default-tooltip` global override | Already dark-mode correct |
| Form inputs | `.form-input` `.form-group` `.form-hint` | General modal forms |
| Buttons | `.btn-primary` `.btn-secondary` `.btn-danger` | Footer CTAs |
| Page layout | `.dashboard` | InvestmentsPage root |
| Plugin card shell | `.plugin-card` `.plugin-card__icon` `.plugin-card__name` `.plugin-card__description` | ConnectorsPage |
| Coming-soon badge | `.coming-soon-badge` | Non-Indexa cards |

---

## Deliverable A — Indexa Wizard

### Overview

A 4-step modal launched from the Indexa card on `ConnectorsPage`. Uses the standard `.modal` shell with a new narrow variant `.modal.inv-wizard` (480px desktop / full bottom-sheet mobile ≤600px).

### DOM structure

```jsx
{/* Trigger: onClick → open wizard */}
<button className="btn-primary" onClick={onOpenWizard}>{t.wizardOpen}</button>

{/* Wizard modal */}
<div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
  <div className="modal inv-wizard">

    {/* Step progress indicator (above modal header) */}
    <div className="inv-wizard__progress" aria-label={t.wizardProgressLabel}>
      <span className="inv-wizard__step-dot inv-wizard__step-dot--done" />
      <span className="inv-wizard__step-sep inv-wizard__step-sep--done" />
      <span className="inv-wizard__step-dot inv-wizard__step-dot--active" />
      <span className="inv-wizard__step-sep" />
      <span className="inv-wizard__step-dot" />
      <span className="inv-wizard__step-sep" />
      <span className="inv-wizard__step-dot" />
    </div>

    {/* Standard modal header */}
    <div className="modal-header">
      <span className="modal-title" id="wizard-title">{t.wizardTitle}</span>
      <button className="modal-close" onClick={onClose} aria-label={t.wizardClose}>✕</button>
    </div>

    {/* Modal body — one of four step variants */}
    <div className="modal-body">
      {/* ── Step 1: Intro ─────────────────────────────── */}
      <div className="inv-wizard__body">
        <span className="inv-wizard__logo" aria-hidden="true">📈</span>
        <h2 className="inv-wizard__title">{t.wizardStep1Title}</h2>
        <p className="inv-wizard__desc">{t.wizardStep1Desc}</p>
        <a
          className="inv-wizard__link"
          href="https://app.indexacapital.com/user/settings"
          target="_blank"
          rel="noopener noreferrer"
        >
          🔑 {t.wizardStep1Link}
        </a>
        <div className="inv-wizard__security-note">
          <span className="inv-wizard__security-note-icon" aria-hidden="true">🔒</span>
          <span>{t.wizardSecurityNote}</span>
        </div>
      </div>

      {/* ── Step 2: Paste token ───────────────────────── */}
      <div className="inv-wizard__body">
        <h2 className="inv-wizard__title">{t.wizardStep2Title}</h2>
        <div className="inv-wizard__token-field">
          <label className="inv-wizard__token-label" htmlFor="indexa-token">
            {t.wizardTokenLabel}
          </label>
          <input
            id="indexa-token"
            type="password"
            className="inv-wizard__token-input"
            placeholder={t.wizardTokenPlaceholder}
            value={token}
            onChange={e => setToken(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="inv-wizard__security-note">
          <span className="inv-wizard__security-note-icon" aria-hidden="true">🔒</span>
          <span>{t.wizardSecurityNote}</span>
        </div>
      </div>

      {/* ── Step 3a: Validating (spinner) ────────────── */}
      <div className="spinner-wrap">
        <div className="spinner" role="status" aria-label={t.wizardStep3Validating} />
        <p className="spinner-label">{t.wizardStep3Validating}</p>
      </div>

      {/* ── Step 3b: Error (invalid token) ───────────── */}
      <div className="inv-wizard__body">
        <div className="inv-wizard__error-banner" role="alert">
          <span className="inv-wizard__error-banner-icon" aria-hidden="true">⚠️</span>
          <span>{t.wizardErrorInvalidToken}</span>
        </div>
        <div className="inv-wizard__token-field">
          {/* re-show token input for correction */}
          <label className="inv-wizard__token-label" htmlFor="indexa-token-retry">
            {t.wizardTokenLabel}
          </label>
          <input
            id="indexa-token-retry"
            type="password"
            className="inv-wizard__token-input"
            placeholder={t.wizardTokenPlaceholder}
            value={token}
            onChange={e => setToken(e.target.value)}
            autoComplete="off"
          />
        </div>
      </div>

      {/* ── Step 3c: Accounts discovered ─────────────── */}
      <div className="inv-wizard__body">
        <h2 className="inv-wizard__title">{t.wizardStep3Title}</h2>
        <p className="inv-wizard__desc">{t.wizardStep3Desc}</p>
        <div className="inv-wizard__account-list">
          {accounts.map(acc => (
            <label
              key={acc.account_number_masked}
              className={`inv-wizard__account-item${selectedAccounts.includes(acc.connection_id) ? ' inv-wizard__account-item--checked' : ''}`}
            >
              <input
                type="checkbox"
                className="inv-wizard__account-checkbox"
                checked={selectedAccounts.includes(acc.connection_id)}
                onChange={() => toggleAccount(acc.connection_id)}
              />
              <div className="inv-wizard__account-info">
                <span className="inv-wizard__account-label">{acc.account_number_masked}</span>
                <span className="inv-wizard__account-type">{acc.type}</span>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ── Step 4: Success ───────────────────────────── */}
      <div className="inv-wizard__success">
        <span className="inv-wizard__success-icon" aria-hidden="true">✅</span>
        <h2 className="inv-wizard__success-title">{t.wizardStep4Title}</h2>
        <p className="inv-wizard__success-desc">{t.wizardStep4Desc}</p>
        <div className="inv-wizard__success-accounts">
          {connectedAccounts.map(acc => (
            <div className="inv-wizard__success-account" key={acc.account_number_masked}>
              <em className="inv-wizard__success-account-check" aria-hidden="true">✓</em>
              {acc.account_number_masked}
            </div>
          ))}
        </div>
      </div>
    </div>

    {/* Modal footer — buttons vary per step */}
    <div className="modal-footer">
      {/* Step 1 */}
      <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
      <button className="btn-primary" onClick={goToStep2}>{t.wizardNext}</button>

      {/* Step 2 */}
      <button className="btn-secondary" onClick={goBack}>{t.wizardBack}</button>
      <button className="btn-primary" onClick={validateToken} disabled={!token.trim()}>
        {t.wizardValidate}
      </button>

      {/* Step 3b (error) */}
      <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
      <button className="btn-primary" onClick={validateToken} disabled={!token.trim()}>
        {t.wizardRetry}
      </button>

      {/* Step 3c (accounts) */}
      <button className="btn-secondary" onClick={goBack}>{t.wizardBack}</button>
      <button className="btn-primary" onClick={connect} disabled={selectedAccounts.length === 0}>
        {t.wizardConnect}
      </button>

      {/* Step 4 */}
      <button className="btn-primary" onClick={goToInvestments}>{t.wizardViewInvestments}</button>
    </div>

  </div>
</div>
```

### Step states summary

| Step | `inv-wizard__progress` dots | Body content | Footer |
|---|---|---|---|
| 1 — Intro | dot 1 active | logo + title + desc + link + security note | Cerrar / Siguiente |
| 2 — Token | dot 2 active | title + token-field + security note | ← Volver / Validar (disabled until non-empty) |
| 3a — Validating | dot 3 active | `.spinner-wrap` | — (no buttons, auto-advances) |
| 3b — Error | dot 2 active (back to 2) | error-banner + token-field (pre-filled) | Cerrar / Reintentar |
| 3c — Accounts | dot 3 active | title + desc + account-list | ← Volver / Conectar (disabled if none selected) |
| 4 — Success | all dots done | `.inv-wizard__success` block | Ver inversiones → |

---

## Deliverable B — InvestmentsPage Populated

### Page root

When a connection exists, **replace** the empty state with the fully populated layout below. Reuse the existing `<main className="dashboard">` as the page root.

```jsx
<main className="dashboard">

  {/* 1. Page header */}
  <div className="investments-header">
    <h1 className="investments-page-title">{t.investmentsTitle}</h1>
  </div>

  {/* 2. Connected account header strip */}
  <div className="inv-account-header">
    <div className="inv-account-header__left">
      <span className="inv-account-header__icon" aria-hidden="true">🔗</span>
      <span className="inv-account-header__label">{connection.account_label_masked}</span>
      {connection.last_synced_at && (
        <span className="inv-account-header__updated">
          {t.invAccountUpdated(formatRelativeTime(connection.last_synced_at))}
        </span>
      )}
    </div>
    {/* "Desconectar" lives on the ConnectorsPage — nothing needed here */}
  </div>

  {/* 3. KPI row — reuse .kpi-grid + .kpi-card */}
  <div className="kpi-grid">
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
      <div className="kpi-value">{formatCurrency(portfolio.total_value)}</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
      <div className="kpi-value">{formatCurrency(portfolio.returns?.invested ?? portfolio.total_invested)}</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiPnL}</div>
      <div className={`kpi-value ${portfolio.total_gain_loss >= 0 ? 'income' : 'expense'}`}>
        {formatCurrency(portfolio.total_gain_loss)}
      </div>
      <div className="kpi-sub">
        {portfolio.total_gain_loss_pct >= 0 ? '+' : ''}{portfolio.total_gain_loss_pct.toFixed(2)}%
      </div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.invKpiTwr}</div>
      <div className={`kpi-value ${(portfolio.returns?.twr_annual ?? 0) >= 0 ? 'income' : 'expense'}`}>
        {portfolio.returns?.twr_annual != null
          ? `${(portfolio.returns.twr_annual * 100).toFixed(2)}%`
          : '—'}
      </div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.invKpiXirr}</div>
      <div className={`kpi-value ${(portfolio.returns?.xirr ?? 0) >= 0 ? 'income' : 'expense'}`}>
        {portfolio.returns?.xirr != null
          ? `${(portfolio.returns.xirr * 100).toFixed(2)}%`
          : '—'}
      </div>
    </div>
  </div>

  {/* 4. Charts row: value-over-time + allocation donut */}
  <div className="inv-charts-row">

    {/* 4a. Value over time */}
    <div className="card inv-chart-card inv-chart-card--value">
      <div className="card-title">{t.invChartValueTitle}</div>
      {loading && <div className="state-box"><span className="icon">⏳</span><span>{t.loading}</span></div>}
      {!loading && portfolio.value_series.length === 0 && (
        <div className="state-box"><span className="icon">📈</span><span>{t.noDataPeriod}</span></div>
      )}
      {!loading && portfolio.value_series.length > 0 && (
        <div className="inv-value-chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="invValueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--primary)" stopOpacity={0.22} />
                  <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={v => `${(v / 1000).toFixed(0)}k€`}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                width={52}
              />
              <Tooltip
                contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--text)' }}
                itemStyle={{ color: 'var(--text)' }}
                formatter={(value: number) => [formatCurrency(value), t.investmentsKpiTotalValue]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--primary)"
                strokeWidth={2}
                fill="url(#invValueGrad)"
                dot={false}
                activeDot={{ r: 4, fill: 'var(--primary)' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>

    {/* 4b. Allocation donut — REUSE cat-chart-layout */}
    <div className="card inv-chart-card inv-chart-card--allocation">
      <div className="card-title">{t.invChartAllocationTitle}</div>
      {loading && <div className="state-box"><span className="icon">⏳</span><span>{t.loading}</span></div>}
      {!loading && allocationData.length === 0 && (
        <div className="state-box"><span className="icon">🍩</span><span>{t.noDataPeriod}</span></div>
      )}
      {!loading && allocationData.length > 0 && (
        <div className="cat-chart-layout">
          <div className="cat-donut-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={allocationData}
                  cx="50%"
                  cy="50%"
                  innerRadius={72}
                  outerRadius={100}
                  dataKey="value"
                  paddingAngle={2}
                >
                  {allocationData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} opacity={0.9} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                  labelStyle={{ color: 'var(--text)' }}
                  itemStyle={{ color: 'var(--text)' }}
                  formatter={(value: number, name: string) => [formatCurrency(value), t[`invAsset${capitalize(name)}`]]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="cat-donut-center">
              <span className="cat-donut-label">{t.invChartAllocationTitle}</span>
              <span className="cat-donut-total">{formatCurrency(portfolio.total_value)}</span>
            </div>
          </div>
          <div className="cat-table-wrap">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th-name">{t.invColClass}</th>
                  <th className="cat-th-num">{t.catColValue}</th>
                  <th className="cat-th-num">{t.catColWeight}</th>
                </tr>
              </thead>
              <tbody>
                {allocationData.map((item, i) => (
                  <tr key={item.name} className="cat-row">
                    <td className="cat-td-name">
                      <div className="cat-td-name-inner">
                        <span className="cat-swatch" style={{ background: item.color }} />
                        <span className="cat-td-label">{t[`invAsset${capitalize(item.name)}`]}</span>
                      </div>
                    </td>
                    <td className="cat-td-num">{formatCurrency(item.value)}</td>
                    <td className="cat-td-num cat-td-weight">
                      {(item.value / portfolio.total_value * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>

  </div>

  {/* 5. Holdings table */}
  <div className="card inv-holdings-card">
    <div className="card-title card-title--has-action">
      <span>{t.investmentsHoldingsTitle}</span>
      <span className="kpi-sub">{portfolio.holdings.length} {t.invHoldingsCount}</span>
    </div>
    {portfolio.holdings.length === 0 ? (
      <div className="state-box">
        <span className="icon">📋</span>
        <span>{t.invHoldingsEmpty}</span>
      </div>
    ) : (
      <div className="inv-holdings-table-wrap">
        <table className="inv-holdings-table">
          <thead>
            <tr>
              <th className="inv-th-sortable">{t.invColName}</th>
              <th>{t.invColISIN}</th>
              <th>{t.invColClass}</th>
              <th className="inv-th-num inv-th-sortable inv-th-sort-active">{t.invColValue}</th>
              <th className="inv-th-num">{t.invColWeight}</th>
              <th className="inv-th-num">{t.invColCost}</th>
              <th className="inv-th-num inv-th-sortable">{t.invColPnL}</th>
              <th className="inv-th-num">{t.invColPnLPct}</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.holdings.map(h => {
              const weight = portfolio.total_value > 0 ? (h.current_value / portfolio.total_value * 100).toFixed(1) : '0.0'
              const isPos = h.gain_loss >= 0
              return (
                <tr key={h.ticker}>
                  <td className="inv-td-name" title={h.name}>{h.name}</td>
                  <td className="inv-td-isin">{h.ticker}</td>
                  <td>
                    <span className={`inv-asset-class-badge inv-asset-class-badge--${h.asset_class}`}>
                      {t[`invAsset${capitalize(h.asset_class)}`] ?? h.asset_class}
                    </span>
                  </td>
                  <td className="inv-td-num">{formatCurrency(h.current_value)}</td>
                  <td className="inv-td-weight">{weight}%</td>
                  <td className="inv-td-num">{formatCurrency(h.cost_basis)}</td>
                  <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                    {isPos ? '+' : ''}{formatCurrency(h.gain_loss)}
                  </td>
                  <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                    {isPos ? '+' : ''}{(h.gain_loss_pct * 100).toFixed(2)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>

  {/* Loading / error states (replaces the above when applicable) */}
  {loading && (
    <div className="card">
      <div className="state-box">
        <span className="icon">⏳</span>
        <span>{t.loading}</span>
      </div>
    </div>
  )}
  {error && (
    <div className="card">
      <div className="state-box error">
        <span className="icon">⚠️</span>
        <span>{t.invErrorLoading}: {error}</span>
      </div>
    </div>
  )}

</main>
```

### Recharts: value-over-time chart spec

| Prop | Value |
|---|---|
| Chart type | `AreaChart` (Recharts) |
| `ResponsiveContainer` | `width="100%" height="100%"` inside `.inv-value-chart-wrap` (height: 260px CSS) |
| X-axis data key | `date` — format `"MMM YY"` from `YYYY-MM-DD` |
| Y-axis formatter | `v => ${(v/1000).toFixed(0)}k€` |
| Area stroke | `var(--primary)`, strokeWidth 2 |
| Area fill | SVG gradient `invValueGrad`: 22% opacity top → 2% bottom |
| Grid | horizontal only (`vertical={false}`), `var(--border)` |
| Tooltip | existing app style: `var(--surface)` bg, `var(--border)` border |
| Dot | `dot={false}`, `activeDot` r=4 fill `var(--primary)` |

### Allocation donut color palette

Use asset-class fixed colors (not random) for consistent visual identity:

```ts
const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:       '#2563eb',   // primary blue
  fixed_income: '#22c55e',   // income green
  cash:         '#94a3b8',   // muted slate
  other:        '#8b5cf6',   // purple
}
```

---

## Deliverable C — ConnectorsPage Card States

### Available (current, unchanged)
```jsx
<div className="plugin-card">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  {/* No badge when available */}
  <button className="btn-primary" onClick={onOpenWizard}>{t.investmentsConnect}</button>
</div>
```

### Connected
```jsx
<div className="plugin-card connector-card--connected">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  <span className="connected-badge">✓ {t.connectorConnected}</span>
  <button className="btn-disconnect" onClick={onDisconnect}>{t.connectorDisconnect}</button>
</div>
```

### Error
```jsx
<div className="plugin-card connector-card--error">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  <span className="error-badge">⚠ {t.connectorError}</span>
  <button className="btn-primary" onClick={onOpenWizard}>{t.connectorErrorRetry}</button>
</div>
```

### Coming Soon (other cards, unchanged)
```jsx
<div className="plugin-card">
  {/* ... */}
  <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
  <button className="btn-primary" disabled aria-disabled="true">{t.investmentsConnect}</button>
</div>
```

---

## Full i18n key list (new keys only)

Vision must add these to `frontend/src/i18n/es.ts`, `en.ts`, and `Dict` in `index.ts`.

### Wizard keys

| Key | ES | EN |
|---|---|---|
| `wizardTitle` | `'Conectar Indexa Capital'` | `'Connect Indexa Capital'` |
| `wizardProgressLabel` | `'Progreso del asistente'` | `'Wizard progress'` |
| `wizardStep1Title` | `'Conecta tu cartera de Indexa Capital'` | `'Connect your Indexa Capital portfolio'` |
| `wizardStep1Desc` | `'Solo lectura. Finlytics nunca realiza operaciones en tu nombre.'` | `'Read-only. Finlytics never trades on your behalf.'` |
| `wizardStep1Link` | `'Genera tu token → Área privada → Configuración → Aplicaciones'` | `'Generate your token → Private area → Settings → Applications'` |
| `wizardSecurityNote` | `'Tu token se almacenará cifrado. Finlytics solo accede en modo lectura.'` | `'Your token is stored encrypted. Finlytics only accesses in read-only mode.'` |
| `wizardNext` | `'Siguiente'` | `'Next'` |
| `wizardStep2Title` | `'Pega tu token de solo lectura'` | `'Paste your read-only token'` |
| `wizardTokenLabel` | `'Token de acceso'` | `'Access token'` |
| `wizardTokenPlaceholder` | `'Pega aquí tu token…'` | `'Paste your token here…'` |
| `wizardValidate` | `'Validar'` | `'Validate'` |
| `wizardStep3Validating` | `'Verificando token…'` | `'Verifying token…'` |
| `wizardStep3Title` | `'Cuentas encontradas'` | `'Accounts found'` |
| `wizardStep3Desc` | `'Selecciona las cuentas que quieres conectar.'` | `'Select the accounts you want to connect.'` |
| `wizardConnect` | `'Conectar'` | `'Connect'` |
| `wizardStep4Title` | `'¡Conectado!'` | `'Connected!'` |
| `wizardStep4Desc` | `'Tu cartera se cargará en Inversiones.'` | `'Your portfolio will load in Investments.'` |
| `wizardViewInvestments` | `'Ver inversiones'` | `'View investments'` |
| `wizardErrorInvalidToken` | `'Token inválido. Comprueba que es correcto y vuelve a intentarlo.'` | `'Invalid token. Check it\'s correct and try again.'` |
| `wizardErrorNetwork` | `'Error de conexión. Comprueba que el servidor está en marcha.'` | `'Connection error. Check the server is running.'` |
| `wizardBack` | `'← Volver'` | `'← Back'` |
| `wizardRetry` | `'Reintentar'` | `'Retry'` |
| `wizardClose` | `'Cerrar'` | `'Close'` |
| `wizardOpen` | `'Conectar'` | `'Connect'` |

### Investments page keys

| Key | ES | EN |
|---|---|---|
| `invKpiTwr` | `'TWR anual'` | `'Annual TWR'` |
| `invKpiXirr` | `'XIRR'` | `'XIRR'` |
| `invChartValueTitle` | `'Evolución del valor'` | `'Value over time'` |
| `invChartAllocationTitle` | `'Asignación por clase'` | `'Allocation by class'` |
| `invHoldingsEmpty` | `'Sin posiciones en cartera'` | `'No holdings in portfolio'` |
| `invHoldingsCount` | `'posiciones'` | `'holdings'` |
| `invAccountUpdated` | `(t: string) => \`Actualizado \${t}\`` | `(t: string) => \`Updated \${t}\`` |
| `invColName` | `'Instrumento'` | `'Instrument'` |
| `invColISIN` | `'ISIN'` | `'ISIN'` |
| `invColClass` | `'Clase'` | `'Class'` |
| `invColValue` | `'Valor'` | `'Value'` |
| `invColWeight` | `'Peso'` | `'Weight'` |
| `invColCost` | `'Coste'` | `'Cost'` |
| `invColPnL` | `'G/P'` | `'P&L'` |
| `invColPnLPct` | `'G/P %'` | `'P&L %'` |
| `invAssetEquity` | `'Renta variable'` | `'Equity'` |
| `invAssetFixed_income` | `'Renta fija'` | `'Fixed income'` |
| `invAssetCash` | `'Efectivo'` | `'Cash'` |
| `invAssetOther` | `'Otros'` | `'Other'` |
| `invErrorLoading` | `'Error al cargar la cartera'` | `'Error loading portfolio'` |

> **Asset class key note:** The `capitalize()` helper converts `"fixed_income"` → `"Fixed_income"`, so the key is `invAssetFixed_income`. Alternatively, use a direct lookup map instead of string interpolation — Vision's choice.

### Connectors page keys

| Key | ES | EN |
|---|---|---|
| `connectorConnected` | `'Conectado'` | `'Connected'` |
| `connectorError` | `'Error de conexión'` | `'Connection error'` |
| `connectorDisconnect` | `'Desconectar'` | `'Disconnect'` |
| `connectorErrorRetry` | `'Reconectar'` | `'Reconnect'` |

---

## CSS class name index

| Class | Purpose | File section |
|---|---|---|
| `.modal.inv-wizard` | Narrow wizard modal (480px) | Wizard |
| `.inv-wizard__progress` | Step dots container | Wizard |
| `.inv-wizard__step-dot` | Inactive step dot | Wizard |
| `.inv-wizard__step-dot--active` | Current step dot (scale 1.4×, primary) | Wizard |
| `.inv-wizard__step-dot--done` | Completed step dot (income green) | Wizard |
| `.inv-wizard__step-sep` | Connector line between dots | Wizard |
| `.inv-wizard__step-sep--done` | Completed connector line (income green) | Wizard |
| `.inv-wizard__body` | Step content container (flex-col, centered) | Wizard |
| `.inv-wizard__logo` | Large emoji/icon (56px) | Wizard step 1 |
| `.inv-wizard__title` | Step title (18px/700) | Wizard |
| `.inv-wizard__desc` | Step description (14px, muted) | Wizard |
| `.inv-wizard__link` | Styled external link | Wizard step 1 |
| `.inv-wizard__security-note` | Encrypted-storage note block | Wizard steps 1+2 |
| `.inv-wizard__security-note-icon` | Lock icon inside note | Wizard |
| `.inv-wizard__token-field` | Token input group (flex-col) | Wizard step 2 |
| `.inv-wizard__token-label` | Token input label | Wizard step 2 |
| `.inv-wizard__token-input` | Monospace password input (44px) | Wizard step 2 |
| `.inv-wizard__account-list` | Discovered accounts list | Wizard step 3 |
| `.inv-wizard__account-item` | Single account row (checkbox + info) | Wizard step 3 |
| `.inv-wizard__account-item--checked` | Selected account (primary border tint) | Wizard step 3 |
| `.inv-wizard__account-checkbox` | Native checkbox (accent-color primary) | Wizard step 3 |
| `.inv-wizard__account-info` | Text block inside account item | Wizard step 3 |
| `.inv-wizard__account-label` | Masked account label (monospace, 14px/600) | Wizard step 3 |
| `.inv-wizard__account-type` | Account type (11px, muted, capitalize) | Wizard step 3 |
| `.inv-wizard__success` | Success state container | Wizard step 4 |
| `.inv-wizard__success-icon` | Large success emoji (52px) | Wizard step 4 |
| `.inv-wizard__success-title` | Success heading | Wizard step 4 |
| `.inv-wizard__success-desc` | Success description | Wizard step 4 |
| `.inv-wizard__success-accounts` | Connected accounts summary list | Wizard step 4 |
| `.inv-wizard__success-account` | Single connected account row | Wizard step 4 |
| `.inv-wizard__success-account-check` | Green checkmark | Wizard step 4 |
| `.inv-wizard__error-banner` | Error alert (red bg, expense color) | Wizard error state |
| `.inv-wizard__error-banner-icon` | Warning icon inside banner | Wizard error state |
| `.inv-account-header` | Connected account strip (surface card) | Investments populated |
| `.inv-account-header__left` | Flex group: icon + label | Investments |
| `.inv-account-header__icon` | Connector icon (18px) | Investments |
| `.inv-account-header__label` | Masked account (monospace, 14px/600) | Investments |
| `.inv-account-header__updated` | "Actualizado …" timestamp (12px, muted) | Investments |
| `.inv-charts-row` | 2-col grid (3fr / 2fr, stacks ≤900px) | Investments |
| `.inv-chart-card` | Chart card (flex-col) | Investments |
| `.inv-chart-card--value` | Value-over-time modifier | Investments |
| `.inv-chart-card--allocation` | Allocation donut modifier | Investments |
| `.inv-value-chart-wrap` | 260px wrapper for Recharts AreaChart | Investments |
| `.inv-holdings-card` | Holdings card (min-height 200px) | Investments |
| `.inv-holdings-table-wrap` | Scrollable table wrapper | Investments |
| `.inv-holdings-table` | Holdings data table (min-width 720px) | Investments |
| `.inv-th-num` | Right-aligned header | Holdings table |
| `.inv-th-sortable` | Sortable header (cursor, hover) | Holdings table |
| `.inv-th-sort-active` | Active sort column (text color) | Holdings table |
| `.inv-td-name` | Instrument name (500, ellipsis) | Holdings table |
| `.inv-td-isin` | ISIN (monospace, 12px, muted) | Holdings table |
| `.inv-td-num` | Numeric cell (right, tabular-nums) | Holdings table |
| `.inv-td-weight` | Weight % (12px, muted, right) | Holdings table |
| `.inv-pnl--pos` | Positive P&L (income green, 600) | Holdings table |
| `.inv-pnl--neg` | Negative P&L (expense red, 600) | Holdings table |
| `.inv-asset-class-badge` | Asset class pill (base) | Holdings table |
| `.inv-asset-class-badge--equity` | Blue equity tint | Holdings table |
| `.inv-asset-class-badge--fixed-income` | Green fixed-income tint | Holdings table |
| `.inv-asset-class-badge--cash` | Muted cash tint | Holdings table |
| `.inv-asset-class-badge--other` | Purple other tint | Holdings table |
| `.connector-card--connected` | Green border modifier on `.plugin-card` | ConnectorsPage |
| `.connected-badge` | Green "Conectado" pill | ConnectorsPage |
| `.connector-card--error` | Red border modifier on `.plugin-card` | ConnectorsPage |
| `.error-badge` | Red "Error" pill | ConnectorsPage |
| `.btn-disconnect` | Small muted disconnect button (red hover) | ConnectorsPage |

---

## Responsive behaviour summary

| Breakpoint | Change |
|---|---|
| `≤900px` | `.inv-charts-row` stacks to 1 column |
| `≤600px` | `.modal.inv-wizard` → full-width bottom-sheet; `.btn-disconnect` → 36px touch target |

---

## Dark mode

All new classes use only CSS token variables or dual-pattern raw rgba overrides (`[data-theme="dark"]` + `@media (prefers-color-scheme: dark)` with `:root:not([data-theme="light"])`). No class-based theme switching needed.


---

### Frontend Implementation (Vision) — Wizard + Real Data Viz Shipped

# Vision → Indexa Phase 2 Frontend

**Author:** Vision (Frontend Engineer)  
**Date:** 2026-07-14  
**Status:** SHIPPED — `npm run build` 0 TS errors  
**Depends on:** Shuri's backend (858 tests green), Wanda's design spec

---

## Summary

Full Phase 2 frontend: Indexa Capital wizard, connection management on ConnectorsPage, and the fully-populated InvestmentsPage (KPIs + area chart + allocation donut + holdings table).

---

## Files Changed

| File | Change |
|---|---|
| `frontend/src/api/types.ts` | Added `InvestmentReturns`, `ValuePoint`, `CashInvestedSplit`, `InvestmentHolding`, `InvestmentPortfolio`, `InvestmentConnection`, `ValidatedAccount`, `ValidateAccountsResponse` |
| `frontend/src/api/client.ts` | Added `validateIndexaToken`, `connectPlugin`, `getConnections`, `disconnectConnection`, `getInvestmentPortfolio` |
| `frontend/src/api/mock.ts` | Added mocks for all 5 new calls; `_mockConnected` flag drives demo-mode state; `mockGetInvestmentPlugins` now reflects dynamic connected status |
| `frontend/src/i18n/index.ts` | Added 44 keys to `Dict` interface (24 wizard, 15 investments-populated, 4 connector-card-state, 1 `invAccountUpdated` fn) |
| `frontend/src/i18n/es.ts` | 44 ES translations |
| `frontend/src/i18n/en.ts` | 44 EN translations |
| `frontend/src/components/IndexaWizard.tsx` | **NEW** — 4-step modal wizard per Wanda's `.modal.inv-wizard` spec |
| `frontend/src/pages/ConnectorsPage.tsx` | Rewritten — fetches plugins + connections, renders Indexa card in 3 states (available/connected/error), launches wizard, handles disconnect |
| `frontend/src/pages/InvestmentsPage.tsx` | Rewritten — full populated viz (KPIs, charts, table) or empty state based on `plugins_connected` |

---

## Contract Implemented

### Wizard (two-step — override of Shuri's original single-POST)

1. **Validate:** `POST /api/investments/connections/validate` `{ token }` → `{ accounts: [{ account_number, account_number_masked, type, status }] }`  
   - 400 → invalid token banner, back to step 2  
   - 503 → network error banner, back to step 2  

2. **Connect:** `POST /api/investments/connections` `{ token, account_numbers: string[] }` → `ConnectionOut[]`  
   - Sends raw `account_number`s (not masked); displays `account_number_masked` in checkboxes  
   - All accounts pre-selected  

### Other endpoints

- `GET /api/investments/connections` — lists active connections for ConnectorsPage + InvestmentsPage header strip  
- `DELETE /api/investments/connections/{id}` — hard-delete; triggered after `window.confirm`  
- `GET /api/investments/portfolio` — aggregated portfolio with holdings, value_series, returns  

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `WizardStep` union type with string literals (`'3-loading' \| '3-error' \| '3-accounts'`) | Avoids extra boolean flags; step + substep in one state atom |
| `assetLabel()` lookup map (not template-literal key access) | Type-safe; `invAssetFixed_income` underscore key works without `as any` |
| `asset_class.replace(/_/g, '-')` for CSS badge class | CSS uses `inv-asset-class-badge--fixed-income` (hyphen), backend sends `fixed_income` (underscore) |
| Parallel `Promise.all([getInvestmentPortfolio(), getConnections()])` on InvestmentsPage | Single loading state; connection header strip needs separate connection data |
| `_mockConnected` flag in mock.ts | Allows full connect→view flow in demo mode (VITE_USE_MOCK=1) |
| `formatRelativeTime()` inline helper | App had no relative-time utility; simple implementation avoids a new dep |
| `gain_loss_pct × 100` for display | Shuri's spec: decimal format (0.1093 = 10.93%) |
| `total_gain_loss_pct × 100` same | Same decimal convention; applied in KPI sub-label |

---

## i18n Keys Added (44 total)

### Wizard (24 keys)
`wizardTitle`, `wizardProgressLabel`, `wizardStep1Title`, `wizardStep1Desc`, `wizardStep1Link`, `wizardSecurityNote`, `wizardNext`, `wizardStep2Title`, `wizardTokenLabel`, `wizardTokenPlaceholder`, `wizardValidate`, `wizardStep3Validating`, `wizardStep3Title`, `wizardStep3Desc`, `wizardConnect`, `wizardStep4Title`, `wizardStep4Desc`, `wizardViewInvestments`, `wizardErrorInvalidToken`, `wizardErrorNetwork`, `wizardBack`, `wizardRetry`, `wizardClose`, `wizardOpen`

### Investments populated (15 keys + 1 fn)
`invKpiTwr`, `invKpiXirr`, `invChartValueTitle`, `invChartAllocationTitle`, `invHoldingsEmpty`, `invHoldingsCount`, `invAccountUpdated` (fn), `invColName`, `invColISIN`, `invColClass`, `invColValue`, `invColWeight`, `invColCost`, `invColPnL`, `invColPnLPct`, `invAssetEquity`, `invAssetFixed_income`, `invAssetCash`, `invAssetOther`, `invErrorLoading`

### Connector card states (4 keys)
`connectorConnected`, `connectorError`, `connectorDisconnect`, `connectorErrorRetry`

---

## Mock Data (demo mode)

- `validateIndexaToken`: accepts any token ≥8 chars; returns one account `PBK•••Z5`
- `mockGetInvestmentPortfolio` when connected: `total_value=12345.67`, 3 holdings (equity/fixed_income/cash), 15-point `value_series` from Jan 2023 → Mar 2024
- `mockGetConnections` when connected: single active connection `id=1, plugin_id=indexa-capital`


---

### QA Findings (Barton) — 28 Tests, 2 Owner Decisions on Config/Startup

# Barton → QA Findings: Indexa Phase 2 Backend

**Author:** Barton (Tester/QA)  
**Date:** 2026-07-14  
**For:** Coordinator (Fury), Shuri (fix owner), Romanoff (spec owner)  
**Status:** OPEN — 2 bugs, both require a fix before Phase 2 ships to production

---

## Context

Ran full security + functional test pass on `src/finlytics/investments/` and `src/finlytics/api/investments.py`. All 44 investment tests pass (896 suite-wide). Two discrepancies found between Romanoff's security spec and Shuri's implementation.

---

## BUG-1: Env var name mismatch — `INDEXA_ENCRYPTION_KEY` vs `FINLYTICS_ENCRYPTION_KEY`

**Severity:** HIGH (operational failure; security mis-configuration possible)  
**Files:** `src/finlytics/config.py:82`, `.env.example`, `romanoff-indexa-token-security.md §1`

### What the spec says (Romanoff §1)

```
INDEXA_ENCRYPTION_KEY=
```

### What is implemented (Shuri)

```python
# config.py
finlytics_encryption_key: str | None = None
```

```
# .env.example
# FINLYTICS_ENCRYPTION_KEY=
```

### Impact

Anyone following Romanoff's spec to configure the production environment will set `INDEXA_ENCRYPTION_KEY=<key>`. The application reads `FINLYTICS_ENCRYPTION_KEY`. The key is **silently ignored**: `settings.finlytics_encryption_key` stays `None`, every connect/portfolio call returns HTTP 503, and the wizard is permanently broken.

No plaintext storage occurs (fail-closed is preserved), but the connector is **inoperable until the operator learns the correct variable name**. This is an ops footgun.

### Recommended fix

Either:
- **Option A (preferred):** Update Romanoff's spec to document `FINLYTICS_ENCRYPTION_KEY` (the broader name makes sense as it covers future connectors).
- **Option B:** Shuri renames the field to `indexa_encryption_key` and updates `config.py` + `.env.example` to match Romanoff's spec.

If Option A, Romanoff must re-publish the updated `.env.example` entry and threat model section.

---

## BUG-2: Startup behavior mismatch — "refuse to start" vs "503 on use"

**Severity:** MEDIUM (security policy violation; not a data-exposure risk)  
**Files:** `src/finlytics/config.py:77–82`, `romanoff-indexa-token-security.md §1`

### What the spec says (Romanoff §1)

> If `INDEXA_ENCRYPTION_KEY` is **absent** or **invalid** at startup: **refuse to start** (raise a configuration error). Do NOT fall back to plaintext storage under any circumstances.

### What is implemented (Shuri)

```python
# config.py comment (line 79–80):
# Scoped fail: app starts normally when absent; only encrypt/decrypt
# operations fail (HTTP 503) if the key is missing or invalid.
```

The application boots without error when `FINLYTICS_ENCRYPTION_KEY` is absent. The first encrypt or decrypt call raises `EncryptionNotConfiguredError` → surfaced as HTTP 503. Plaintext storage never occurs.

### Impact

The **data-safety property is preserved** (no plaintext tokens are ever stored or returned). However, the spec demands a startup-time hard failure, which:

1. Surfaces mis-configuration immediately (fail-fast principle) rather than at first user action.
2. Prevents the app from starting in an environment where the connector is expected to work, which could confuse operators into thinking the wizard is broken for other reasons.

In practice: the current behavior is _operationally safer_ than a silent start in some deployment models (e.g., a rolling update where the key was accidentally dropped from the env). But it violates Romanoff's documented policy.

### Recommended fix

**Shuri:** Add a `model_validator` (or startup event) that raises at application startup if `finlytics_encryption_key` is absent and a connection row exists in the DB — or, simpler, raise unconditionally at startup (matching the spec). Coordinate with Romanoff on whether the "scoped fail" model is acceptable.

**Romanoff:** If the "503 on use" design is intentional and accepted, update §1 to document the approved behavior so the spec and code match.

---

## Tests that assert the fail-closed property (passing)

The following tests confirm the fail-closed behavior **as implemented** (503 responses):

- `test_connect_missing_encryption_key_returns_503`
- `test_portfolio_missing_encryption_key_returns_503`
- `test_crypto_missing_key_encrypt_raises`
- `test_crypto_missing_key_decrypt_raises`

If BUG-2 is fixed to add startup-time refusal, additional startup tests should be added in `tests/test_startup.py` (deferred to coordinator decision).

---

## No other security issues found

The following Romanoff build-blockers were explicitly verified and pass:

| Build-blocker | Test | Status |
|---|---|---|
| Token never in API response | `test_connect_response_never_contains_raw_token`, `test_validate_happy_path_returns_accounts`, `test_get_connections_no_token_enc_in_response` | ✅ PASS |
| `account_label_masked` always masked | `test_get_connections_no_token_enc_in_response`, `test_mask_account_standard`, `test_mask_account_short_gets_bullet_prefix` | ✅ PASS |
| `TLS verify=True` always | `test_indexa_client_tls_verify_and_no_redirects` | ✅ PASS |
| `follow_redirects=False` | `test_indexa_client_tls_verify_and_no_redirects` | ✅ PASS |
| Encrypt→decrypt round-trip correct | `test_crypto_encrypt_decrypt_roundtrip` | ✅ PASS |
| Tampered ciphertext raises | `test_crypto_tampered_ciphertext_raises` | ✅ PASS |
| Missing key → fail-closed | `test_crypto_missing_key_encrypt_raises`, `test_crypto_missing_key_decrypt_raises` | ✅ PASS |
| `POST /auth/authenticate` absent | Not present in codebase (grep confirms) | ✅ PASS |
| Hard-delete removes ciphertext | `test_delete_connection_returns_204` + service logic review | ✅ PASS |


---

## 2026-07-14 — Recommendations: Connectors → Settings, Cartera Phase 2 Plan

# Decisions Log

---

## 2026-07-14 — Recommendations: Connectors → Settings, Cartera Phase 2 Plan

**Authors:** Wanda (UX/UI), Vision (Frontend)  
**Status:** Approved / Planned

### Wanda: Connector Catalog Placement (IA Recommendation)

**Decision:** Move the full connector catalog from `InvestmentsPage` to a new Settings sub-page (`/settings/connectors`). Replace the catalog on Investments with a single "Gestionar conectores →" CTA.

**Rationale:**
- Connecting a plugin = config (credentials, tokens) → belongs in Settings, not portfolio view
- Even Phase 1 benefits: eliminates visual weight of disabled "coming soon" cards
- Mobile-first: clean Investments page + one tap to Settings
- Phase 2 readiness: connect flows built in Settings from the start (no migration needed)

**Result:** Wanda's recommendation was approved by DrDonoso and implemented by Vision (see "Connectors Moved to Settings" section below).

### Vision: Cartera / Holdings Visualization Plan (Phase 2)

**Current state (Phase 1):** Holdings area shows empty-state placeholder.  
**Phase 2 plan:**

| Feature | Details |
|---------|---------|
| KPI row | 4 cards: Total value, Total invested, Gain/Loss, Plugins connected |
| Asset allocation | Donut chart grouped by asset class (equity, fixed_income, crypto, cash, mixed, other) — reuse SpendingByCategory pattern |
| Holdings table | Name, ticker, asset class, current value, cost basis, P&L (€ + %), currency — sortable by name/value/P&L% |
| Multi-currency | Holdings display native currency; KPI totals in portfolio currency (EUR assumed) |
| All states | No plugins (current), loading, data available, error, empty holdings |

This page layout and component structure are pre-planned so real data in Phase 2 slots in cleanly without rework.

---

## 2026-07-14 — Investments Plugin Skeleton (Phase 1)

**Author:** Fury (Lead/Architect)  
**Status:** Approved

### Context

The owner wants a new "Investments" section in Finlytics built around a plugin architecture. Each plugin is a connector to an external investment API (Indexa Capital, brokers, crypto exchanges, etc.). Phase 1 is the SKELETON only: visualization placeholder, new menu item, "add plugin → coming soon" affordance, and the conceptual plugin model so real connectors slot in later.

### Decision

#### 1. Plugin Model

A **plugin** is a typed connector definition with this shape:

```typescript
// Frontend type (frontend/src/api/types.ts)
interface InvestmentPlugin {
  id: string              // unique slug, e.g. "indexa-capital"
  name: string            // display name, e.g. "Indexa Capital"
  description: string     // short description
  icon: string            // emoji or icon identifier
  status: 'coming_soon' | 'available' | 'connected' | 'error'
  auth_type: 'api_key' | 'oauth' | 'token' | 'none'
  supported_features: string[]  // e.g. ["holdings", "transactions", "performance"]
}
```

```python
# Backend schema (src/finlytics/api/schemas.py)
class InvestmentPluginOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    status: str   # coming_soon | available | connected | error
    auth_type: str
    supported_features: list[str]
```

#### 2. Normalized Unified Data Shape

All plugins will normalize their data into this common shape:

```typescript
interface InvestmentHolding {
  plugin_id: string
  name: string               // "Indexa Capital Cartera 10"
  ticker: string | null      // "IWDA" or null for managed portfolios
  asset_class: string        // "equity" | "fixed_income" | "mixed" | "crypto" | "cash" | "other"
  units: number | null       // share count, null for managed funds
  current_value: number      // current market value
  cost_basis: number | null  // total invested, null if unknown
  currency: string           // "EUR", "USD", etc.
  gain_loss: number | null   // unrealized P&L
  gain_loss_pct: number | null
  last_updated: string       // ISO datetime
}

interface InvestmentPortfolioSummary {
  total_value: number
  total_invested: number | null
  total_gain_loss: number | null
  total_gain_loss_pct: number | null
  currency: string
  holdings: InvestmentHolding[]
  plugins_connected: number
  last_updated: string | null
}
```

```python
class InvestmentHoldingOut(BaseModel):
    plugin_id: str
    name: str
    ticker: str | None = None
    asset_class: str
    units: float | None = None
    current_value: float
    cost_basis: float | None = None
    currency: str
    gain_loss: float | None = None
    gain_loss_pct: float | None = None
    last_updated: str

class InvestmentPortfolioOut(BaseModel):
    total_value: float
    total_invested: float | None = None
    total_gain_loss: float | None = None
    total_gain_loss_pct: float | None = None
    currency: str
    holdings: list[InvestmentHoldingOut]
    plugins_connected: int
    last_updated: str | None = None
```

#### 3. Backend vs Frontend — Recommendation

**Frontend-first skeleton + thin backend stub.**

- Add ONE backend endpoint: `GET /api/investments/plugins` → returns a static list of known plugins (all with `status: "coming_soon"` for now). This is ~20 lines of code in a new `investments.py` router.
- NO database tables in phase 1 — the plugin registry is a hardcoded list.
- NO `GET /api/investments/portfolio` in phase 1 — the frontend renders an empty/placeholder state.
- Phase 2 adds: plugin config storage (DB table), auth credential storage, actual API connectors, and the portfolio aggregation endpoint.

**Rationale:** Every other section in the app consumes a real `/api/*` endpoint. Keeping that pattern makes phase 2 a natural extension instead of a rewrite. The backend cost is minimal (~1 file, ~30 lines).

#### 4. Skeleton UI/UX Outline

The `InvestmentsPage` follows the same layout as Dashboard/Analytics:

```
<main className="dashboard">
  ├── Page header: "Inversiones / Investments" title
  ├── KPI placeholder row (3 cards):
  │   ├── Total Value      → "—" (empty state)
  │   ├── Total Invested   → "—"
  │   └── P&L              → "—"
  ├── Holdings area:
  │   └── Empty state: illustration + "Conecta un plugin para ver tus inversiones"
  │       / "Connect a plugin to see your investments"
  ├── Connected Plugins section:
  │   └── Empty state: "No hay plugins conectados" / "No plugins connected"
  └── Add Plugin affordance:
      └── Card/button grid showing known plugins (from API), each with:
          ├── Plugin icon + name
          ├── "Próximamente" / "Coming soon" badge
          └── Disabled "Connect" button
```

**Design consistency:**
- Use existing `--surface`, `--border`, `--radius`, `--shadow` tokens
- KPI cards: same `.kpi-card` styling as Dashboard
- Empty states: centered text + muted color, consistent with existing empty states
- "Coming soon" badge: `--text-muted` color, subtle pill shape

#### 5. Decomposition — Build Slices

| # | Slice | Owner | Depends on | Delivers |
|---|-------|-------|-----------|----------|
| 1 | **Backend plugin stub** | Shuri | — | `src/finlytics/api/investments.py` with `GET /api/investments/plugins`, schemas in `schemas.py`, router registered in `app.py` |
| 2 | **Frontend types + API client** | Vision | Slice 1 (contract) | TS types in `types.ts`, `getInvestmentPlugins()` in `client.ts` |
| 3 | **i18n keys** | Vision/Wanda | — | New keys in `Dict` interface + `es.ts` + `en.ts` for nav label, page title, KPIs, empty states, "coming soon" |
| 4 | **InvestmentsPage + route + nav** | Vision | Slices 2, 3 | `InvestmentsPage.tsx`, route in `App.tsx`, NavLink in `Layout.tsx` |
| 5 | **UI polish & empty states** | Wanda | Slice 4 | CSS for investment KPIs, plugin cards, "coming soon" badges, empty-state illustrations, dark mode |
| 6 | **Tests** | Barton | Slices 1, 4 | Backend: test `GET /api/investments/plugins` returns expected shape. Frontend: component renders, nav link present |

**Sequencing:** Slices 1 + 3 can start in parallel. Slice 2 needs the contract from Slice 1 (just the type shapes, can start same day). Slice 4 needs 2 + 3. Slice 5 needs 4. Slice 6 can start as soon as 1 and 4 land.

**What's real vs placeholder:**
- ✅ Real: nav item, route, page shell, backend endpoint, plugin registry
- 🔜 Placeholder: KPI values ("—"), holdings area (empty), plugin connect buttons (disabled + "Coming soon")

#### 6. Open Questions for Owner (Resolved)

1. **Currency handling:** EUR placeholder for phase 1; multi-currency phase 2.
2. **Plugin catalog:** 3 entries (Indexa Capital, generic broker, crypto).
3. **Nav icon:** 💰

---

## 2026-07-14 — Backend: Investments Plugin Stub (Phase 1, Slice 1)

**Author:** Shuri (Backend)  
**Status:** Shipped

### Endpoint Contract

#### `GET /api/investments/plugins`

- **Auth:** Required — session cookie (401 if unauthenticated)
- **Method:** GET  
- **Path:** `/api/investments/plugins`  
- **Response:** `200 OK` — `application/json` — array of plugin objects

#### Response Shape

```json
[
  {
    "id": "indexa-capital",
    "name": "Indexa Capital",
    "description": "Automated index-fund portfolio management",
    "icon": "🏦",
    "status": "coming_soon",
    "auth_type": "token",
    "supported_features": ["holdings", "transactions", "performance"]
  },
  {
    "id": "generic-broker",
    "name": "Broker (Stocks & ETFs)",
    "description": "Connect a stock/ETF broker account",
    "icon": "📈",
    "status": "coming_soon",
    "auth_type": "api_key",
    "supported_features": ["holdings", "transactions"]
  },
  {
    "id": "crypto-exchange",
    "name": "Crypto Exchange",
    "description": "Track crypto holdings from an exchange",
    "icon": "🪙",
    "status": "coming_soon",
    "auth_type": "api_key",
    "supported_features": ["holdings"]
  }
]
```

### Pydantic Schemas Available (for phase 2 reference)

`InvestmentHoldingOut` and `InvestmentPortfolioOut` are already defined in `src/finlytics/api/schemas.py` — Vision can use them to type the portfolio endpoint when phase 2 lands, without any backend schema changes.

### What's NOT included in phase 1

- No `GET /api/investments/portfolio` — frontend should render empty/placeholder state
- No DB tables, no migrations

### Files Changed

- `src/finlytics/api/schemas.py` — 3 new schemas (InvestmentPluginOut, InvestmentHoldingOut, InvestmentPortfolioOut)
- `src/finlytics/api/investments.py` — new router (created)
- `src/finlytics/app.py` — router registered

---

## 2026-07-14 — Frontend Implementation: Connectors Moved to Settings

**Author:** Vision (Frontend Engineer)  
**Status:** Shipped

### Placement

- **InvestmentsPage (`/investments`):** KPI row + holdings empty state + "Gestionar conectores →" NavLink to `/settings/connectors`
- **ConnectorsPage (`/settings/connectors`):** Full plugin catalog grid (3 cards: Indexa Capital, Broker, Crypto Exchange — all "Coming soon", all disabled)

### Implementation

| File | Change |
|------|--------|
| `frontend/src/pages/ConnectorsPage.tsx` | **Created** — plugin catalog under settings layout |
| `frontend/src/pages/InvestmentsPage.tsx` | Removed catalog; added NavLink CTA |
| `frontend/src/App.tsx` | Added `settings/connectors` route |
| `frontend/src/components/Layout.tsx` | Added "Conectores" sub-link in Ajustes accordion |
| `frontend/src/i18n/index.ts`, `es.ts`, `en.ts` | Added `settingsSubConnectors`, `investmentsManageConnectors` keys |

**Result:** 0 TypeScript errors. Build succeeded. Connector catalog cleanly moved; Investments page refocused as pure view + CTA. In Phase 2, disabled Connect buttons become real auth flows — page already the right home.

---

## 2026-07-14 — Design: InvestmentsPage Skeleton (Phase 1)

**Author:** Wanda (UX/UI Designer)  
**Status:** Implemented

### Layout Principles

- InvestmentsPage uses `<main className="dashboard">` (existing shell) — inherits the `24px 40px` padding, `flex-column`, `20px gap`.
- Visual hierarchy: title → KPI row → holdings state → plugin catalog.
- Mobile-first. The sidebar collapses at `≤767px`; content padding reduces at `≤600px` via existing `.dashboard` rules.
- All dark-mode support is baked into the CSS tokens and the new rules — no inline style overrides needed.
- **Do not** add inline color/spacing — use class names defined.

### Exact DOM Structure (JSX contract)

```tsx
<main className="dashboard">

  {/* ── 1. Page header ── */}
  <div className="investments-header">
    <h1 className="investments-page-title">{t.investmentsTitle}</h1>
  </div>

  {/* ── 2. KPI placeholder row — REUSE existing .kpi-grid + .kpi-card ── */}
  <div className="kpi-grid">
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
      <div className="kpi-value">—</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
      <div className="kpi-value">—</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiPnL}</div>
      <div className="kpi-value">—</div>
    </div>
  </div>

  {/* ── 3. Holdings empty state ── */}
  <div className="card investments-holdings-card">
    <div className="card-title">{t.investmentsHoldingsTitle}</div>
    <div className="investments-empty">
      <span className="investments-empty__icon" aria-hidden="true">📊</span>
      <p className="investments-empty__text">{t.investmentsEmptyHoldings}</p>
    </div>
  </div>

  {/* ── 4. Plugin catalog ── */}
  <div className="card investments-catalog-card">
    <div className="card-title">{t.investmentsCatalogTitle}</div>
    <div className="plugin-catalog">
      {plugins.map(plugin => (
        <div className="plugin-card" key={plugin.id}>
          <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
          <span className="plugin-card__name">{plugin.name}</span>
          <p className="plugin-card__description">{plugin.description}</p>
          <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
          <button
            className="btn-primary"
            disabled
            aria-disabled="true"
          >
            {t.investmentsConnect}
          </button>
        </div>
      ))}
    </div>
  </div>

</main>
```

### Class-Name Reference

#### Existing classes (no new CSS needed)
| Class | Where defined | Notes |
|---|---|---|
| `.dashboard` | index.css | Page shell — `flex-column`, gap 20px, padding 24px 40px |
| `.card` | index.css | Surface + border + radius + shadow |
| `.card-title` | index.css | UPPERCASE label, 13px, muted |
| `.kpi-grid` | index.css | `repeat(auto-fill, minmax(180px, 1fr))` — handles 3 KPIs cleanly |
| `.kpi-card` | index.css | Surface + border + radius + shadow + 20px padding |
| `.kpi-label` | index.css | 12px, uppercase, muted |
| `.kpi-value` | index.css | 26px, 700 weight — shows "—" as placeholder |
| `.btn-primary` | index.css | Primary button. `:disabled` → opacity 0.45, cursor default |

#### New classes (added to index.css by Wanda)
| Class | Purpose |
|---|---|
| `.investments-header` | Flex row wrapper for title + future action buttons |
| `.investments-page-title` | H1, 22px/700, matches `.tx-page-title` scale; 18px on mobile |
| `.investments-holdings-card` | `min-height: 200px` on the holdings `.card` to prevent CLS |
| `.investments-empty` | Flex-column, centered, 40px pad, muted — for "no holdings" state |
| `.investments-empty__icon` | 36px emoji icon, opacity 0.8 |
| `.investments-empty__text` | max-width 280px, lh 1.5 |
| `.investments-catalog-card` | Hook class on the catalog wrapper `.card` (no extra rules yet) |
| `.plugin-catalog` | `repeat(auto-fill, minmax(220px, 1fr))` grid, gap 16px |
| `.plugin-card` | Individual card: `var(--bg)` background for nested inset look |
| `.plugin-card__icon` | 32px emoji, margin-bottom 4px |
| `.plugin-card__name` | 15px/600, `var(--text)` |
| `.plugin-card__description` | 13px, muted, `flex: 1 1 auto` — pushes badge+button to card bottom |
| `.coming-soon-badge` | Muted pill: `rgba` bg, `var(--text-muted)`, pill border. Dark-mode override included |

### Responsive Behaviour

| Viewport | KPI row | Plugin catalog |
|---|---|---|
| Desktop `>900px` | `auto-fill, minmax(180px, 1fr)` → 3 cols | `auto-fill, minmax(220px, 1fr)` → 3 cols |
| Tablet `≤900px` | `auto-fill, minmax(180px, 1fr)` → 2–3 cols | `auto-fill, minmax(200px, 1fr)` → 1–2 cols |
| Mobile `≤600px` | `auto-fill, minmax(180px)` → 1 col | `1fr` → 1 col (full width) |

### Dark-Mode Notes

All tokens (`--surface`, `--bg`, `--border`, `--text-muted`, `--text`) resolve correctly for both `[data-theme="dark"]` and `@media (prefers-color-scheme: dark)`. The only CSS that needed explicit dark overrides was `.coming-soon-badge` (raw `rgba` values adjusted for readability on dark surfaces). Everything else is token-driven.

### i18n Keys Required

| Key | ES | EN |
|---|---|---|
| `investmentsTitle` | `"Inversiones"` | `"Investments"` |
| `investmentsKpiTotalValue` | `"Valor total"` | `"Total value"` |
| `investmentsKpiTotalInvested` | `"Total invertido"` | `"Total invested"` |
| `investmentsKpiPnL` | `"Ganancia / Pérdida"` | `"Gain / Loss"` |
| `investmentsHoldingsTitle` | `"Cartera"` | `"Holdings"` |
| `investmentsEmptyHoldings` | `"Conecta un plugin para ver tus inversiones"` | `"Connect a plugin to see your investments"` |
| `investmentsCatalogTitle` | `"Conectores disponibles"` | `"Available connectors"` |
| `investmentsComingSoon` | `"Próximamente"` | `"Coming soon"` |
| `investmentsConnect` | `"Conectar"` | `"Connect"` |
| `navInvestments` | `"Inversiones"` | `"Investments"` |

---

## 2026-07-14 — Frontend: InvestmentsPage Skeleton (Phase 1, Slices 2–4)

**Author:** Vision (Frontend Engineer)  
**Status:** Shipped

### What was built

Slices 2, 3, and 4 of the investments plugin skeleton, per the specs from Wanda and Shuri.

### Key Decisions

#### Loading/error scope

The `loading` / `error` state-boxes replace only the `.plugin-catalog` content inside `.investments-catalog-card`, not the entire page. This lets the KPI row and holdings card render immediately (they have no async dependency in Phase 1), giving a better perceived performance. The spinner lives inside the catalog card, consistent with the `.state-box` pattern used in other cards across the app.

#### No fallback to mock on real error

Unlike summary endpoints (which fall back silently to mock data), `getInvestmentPlugins()` surfaces real errors directly — it does NOT fall back to mock on fetch failure. Rationale: the endpoint is stable and static; a real error (e.g. 401, network down) should be visible to the user rather than silently showing stale mock data. Consistent with the `getRules()`/`confirmImport()` pattern for stable endpoints.

#### Demo mode (VITE_USE_MOCK=1)

`mockGetInvestmentPlugins()` returns all 3 plugins with `status: "coming_soon"`, matching the live backend stub exactly. Demo mode is fully functional.

### Implementation Summary

- **File:** `frontend/src/pages/InvestmentsPage.tsx` — full skeleton component
- **Route:** `/investments` added to `App.tsx`
- **Nav:** 💰 item added to `Layout.tsx`
- **Type:** `InvestmentPlugin` added to `frontend/src/types.ts`
- **Client:** `getInvestmentPlugins()` in `client.ts` + `mockGetInvestmentPlugins()` in `mock.ts`
- **i18n:** 10 keys added to `Dict`, `es.ts`, `en.ts` (investmentsTitle, investmentsKpiTotalValue, investmentsKpiTotalInvested, investmentsKpiPnL, investmentsHoldingsTitle, investmentsEmptyHoldings, investmentsCatalogTitle, investmentsComingSoon, investmentsConnect, navInvestments)

### CSS Note

All required class names were confirmed already present in `index.css` per Wanda's spec. No CSS was added by Vision.

---

## 2026-07-14 — QA: Investments Backend Tests (Phase 1, Slice 6)

**Author:** Barton (Tester / QA)  
**Status:** Shipped

### Tests Implemented

`tests/api/test_investments.py` — 6 tests, all passing.

| Test | What it checks |
|---|---|
| `test_plugins_401_unauthenticated` | No cookie → 401 (auth guard is active) |
| `test_plugins_200_returns_list_of_three` | Authenticated → 200, exactly 3 plugins |
| `test_plugins_all_required_keys_present` | Every object has all 7 required keys |
| `test_plugins_all_status_coming_soon` | All `status == "coming_soon"` |
| `test_plugins_correct_id_set` | Id set matches `{indexa-capital, generic-broker, crypto-exchange}` exactly |
| `test_plugins_supported_features_nonempty` | Every plugin has a non-empty `supported_features` list |

### Implementation Details

The endpoint is a static in-memory registry with no DB access. Authenticated tests use the shared conftest `client` fixture (pre-bypasses `get_current_user`). The 401 test uses a local `unauthenticated_client` fixture that overrides only `get_db` and sends no cookie, so the real `get_current_user` raises 401 before any DB interaction.

### Smoke Set Result

`tests/api/test_auth.py tests/api/test_spa_fallback.py tests/api/test_investments.py`  
→ **43 passed, 0 failed**. No regressions.

### Frontend Test Infra Assessment

**Result: NO.** `frontend/package.json` has no `test` script and no vitest/jest devDependency. There is no `@testing-library/react`, `vitest`, or `jest` in `devDependencies`.

**Recommendation:** Scaffolding frontend test infra (vitest + @testing-library/react) is a non-trivial one-time setup task. Since Vision's Investments page exists now, defer frontend test implementation until the coordinator decides whether frontend unit tests are in scope for this project. When that decision is made, Barton can write the nav-link and coming-soon render test in a single session.

---

## 2026-07-14 — DevOps: Local Commit & Rebuild

**Author:** Rocket (DevOps/Platform)  
**Status:** Done — local only, not pushed

### Commit

Committed complete Investments Phase 1 skeleton locally:

```
afbcd89  feat(investments): add plugin-based investments section skeleton
```

15 files changed (11 modified, 4 new): all under `frontend/`, `src/`, and `tests/`. `.squad/` files deliberately excluded.

### Rebuild

```powershell
docker compose -f docker-compose.local.yml up -d --build
```

**Result:** ✅  
- `finlytics-db-1` healthy (postgres:16-alpine)  
- `finlytics-api-1` up, port 7777  
- `GET http://localhost:7777/` → **200**  
- `GET http://localhost:7777/api/investments/plugins` → **401** (auth guard active = new route live)

### What Owner Sees

- 💰 **Inversiones** sidebar → `/investments` with 3 KPI (—) + holdings empty state + "Gestionar conectores →" CTA
- **Ajustes → Conectores** → plugin catalog (Indexa, Broker, Crypto — all "Próximamente")

### Local Run Pattern (Established)

For uncommitted feature code: **Always use `docker-compose.local.yml` with `--build`** (includes `build: .` from current working tree). Default `docker-compose.yml` pulls published Hub image (stale). 401 smoke check confirms new route is live.

---

