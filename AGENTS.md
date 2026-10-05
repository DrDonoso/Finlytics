# AGENTS.md — Finlytics contributor guide for AI agents

## Docker / build

**One `Dockerfile`, two targets.** There is no `Dockerfile.local` any more — it was a
workaround for an `npm 10.x` crash inside Docker ("Exit handler never called", bin-symlink
bug) that no longer reproduces on `node:26-alpine` / npm 11. Do not reintroduce a second
Dockerfile without evidence that the main one fails.

| Target | Produces | Used by |
|--------|----------|---------|
| `base` *(default)* | `node:26-alpine` compiles the SPA, `python:3.14-slim` installs `uv.lock` with uv and serves API + SPA. | CI/prod — `docker-compose.yml`, `docker-compose.local.yml` |
| `demo` | The same SPA built with `VITE_DEMO=1`, served by `nginx:alpine`. No Python, no API, no database. | Public demo — `docker-compose.demo.yml` |

```
frontend-deps  (npm ci)            ← shared layer, runs once
├── frontend-builder (npm run build)       → dist/
└── demo-builder     (npm run build:demo)  → dist-demo/
```

> **The `base` stage must stay LAST.** A bare `docker build .` builds the final stage, so moving `demo` below it would silently make the demo image the production build.

> **Never fold the demo into the `base` image.** It ships the production SPA bundle and its entrypoint runs `alembic upgrade head`, so serving the demo from it would require a live database and expose the real API (`/api/imports` bills OpenAI, the connector form asks for real broker tokens, `/api/auth/setup` reopens whenever the DB is empty).

> **`frontend/.env.demo` must stay un-ignored in `.dockerignore`.** The generic `.env.*` rule would swallow it, and Vite would then silently build the *production* bundle into the demo image. The `demo-builder` stage greps the output for the MSW worker to make that failure loud.

### Local dev workflow

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Identical to `docker-compose.yml` but builds from the working tree instead of pulling the
published image — use it to run uncommitted code. No host pre-build step: the Dockerfile
compiles the SPA itself.

### CI/prod workflow

Push to `main` → GitHub Actions runs `docker-deploy.yml` → builds `drdonoso/finlytics`
(default target) and `drdonoso/finlytics-demo` (`--target demo`) on the same CalVer tag.
The `IMAGE_TAG` / `BUILD_DATE` build args are injected there and surfaced by
`GET /api/version` (shown on the About page).

> **Rule:** Never add a "build frontend" step to the CI workflow. The `Dockerfile` handles it.

---

## Migrations

Alembic migrations live in `alembic/versions/`. The current head is `0027_add_import_summaries.py`.

- Always create a new numbered migration (`0028_...`) for schema changes.
- Verify the head before writing one — this file goes stale. `down_revision` in the
  highest-numbered file is the source of truth, not this document.
- The entrypoint runs `alembic upgrade head` automatically on container start.
- Never modify an existing migration that has been deployed.

---

## Finance assistant architecture

`src/finlytics/assistant/` is a **read-only, tool-calling agent** over the user's own
data, surfaced as a slide-out chat panel.

### Automatic import summaries

`notifications/import_summaries.py` processes opt-in jobs created by the two bank
import saving routes, not by a detector or a frontend callback. Preferences live in
Settings -> Connectors -> Notifications and reference one owned, enabled channel;
Telegram is the only supported transport. Credentials remain in `NotificationChannel`.

- Enqueue inside the import transaction, after final persistence, and wake the worker
  only after commit. Preview, manual writes, restores, Fidelity and duplicate-only
  imports must never enqueue a summary.
- Facts come through `db/queries/import_summaries.py` and the shared overview/category
  queries. Record the reviewed date bounds, not just `ImportRun.period`. Explain
  account-period totals separately from the newly inserted count; missing history is
  unknown and mixed currencies must not be silently added.
- Mortgage context uses `mortgage/service.py::build_payment_context` and the same
  `ChargeMatcher` as the mortgage screen. Retain each charge's identity and date so
  a June debit can be associated with a May due date without moving June's cash flow.
  Only the current user's linked mortgages and this account's matched charges enter
  the summary. Amount mismatches, competing claims and projected instalments are not
  certain timing explanations.
- Summary reconciliation reads cached index data only: no ECB request inside the
  import-summary transaction, and an empty cache must not become a zero interest rate.
  Bound the context and report unavailable/truncated matching explicitly to the model.
- The dedicated prompt in `notifications/import_summary_prompt.py` is not the editable
  chat prompt. It receives bounded, sanitized facts and adds commentary to a calculated
  header, followed by specific mortgage-timing notes. Lead the analysis with spending
  evolution and category changes, not a mortgage audit. `spending_change` is calculated
  from overview totals (including uncategorized expenses), never by summing a top-N list.
  A missing comparison stays null and a zero baseline has no percentage.
  Keep identifiers out without redacting
  numeric JSON values. Do not restore the generic trailing coverage sentence; explain
  a concrete limitation only when it affects the analysis.
- `ImportSummaryJob` is the durable queue. Atomic claims and expiring leases protect
  against concurrent workers. A stale worker may not overwrite a newer claim. Persist
  the generated text before sending; a transport retry must not regenerate it.
- An expired in-flight send or ambiguous Telegram timeout becomes `uncertain`, requiring
  explicit manual acknowledgement before retry. Telegram has no exactly-once send key.
  Retry only known-safe transient failures, at most three times per phase.
- Channel/settings changes cancel pending work instead of retargeting it. Already-sent
  and in-flight messages cannot be recalled. The read-only status endpoint is safe to
  poll; never poll the detector-running `/api/notifications` endpoint.
- `ImportSummaryAttempt` records each provider call's date and nullable usage, including
  failures. Deleting source data must not delete billed usage. Chat and summaries share
  `assistant/limits.py` and the database-backed monthly budget; automatic work does not
  create fake chat conversations or inflate the answer count.
- This write-capable configuration stays out of the public demo. Keep UI text bilingual
  and store the UI language when saving the preference, then snapshot it per job.

| Module | Role |
|--------|------|
| `tools.py` | The tool catalogue: an OpenAI function schema paired with an async executor per tool |
| `projections.py` | Deterministic compound interest. No LLM, no I/O, pure functions |
| `prompts.py` | The system prompt, version-controlled like `extraction/prompts.py` |
| `context.py` | Compact "what data exists" header (account/category ids, date coverage) injected into the prompt |
| `settings.py` | Per-user overrides resolved against the env defaults, token accounting and the budget query |
| `service.py` | The bounded agent loop, yielding `ToolStarted` / `AnswerDelta` / `Completed` / `Failed` events |

`api/assistant.py` turns those events into SSE frames. `LLMClient.stream_with_tools()`
handles the streaming call; `complete()` and `parse()` are untouched, so the extraction
pipeline is unaffected.

> **Every tool goes through `finlytics.db.queries`.** That is the whole design: the chat
> reads the same aggregation code as the dashboards, so an answer cannot disagree with the
> chart next to it. Do not add a tool that runs its own SQL — add the query to the query
> layer first and wrap it. The same holds for `context.py`, which reads
> `get_transaction_date_range` and `has_investment_connections` from there.

> **A figure an endpoint also serves comes from a shared service, never from calling the
> endpoint.** The investments tool and `GET /api/investments/combined-overview` both call
> `investments/overview.py::build_combined_overview`. Invoking a FastAPI handler from a tool
> needs a fake user and fake `BackgroundTasks`, and breaks the moment the handler grows a
> dependency.

> **There are no write tools, and adding one is not a small change.** A write needs a
> confirmation step in the UI before it executes; a model that deletes a transaction
> because it misread "remove that from the total" is not a recoverable failure. The
> registry is shaped so a write class can be added later, deliberately, not by accident.

> **Tool results are never persisted or replayed.** `AssistantMessage` stores only `user`
> and `assistant` turns; the `tool_calls` JSON column is an audit trail for the UI, not
> conversation state. Replaying old results would grow the token bill without bound *and*
> let the model answer a **new** question from a **previous** query's data. The system
> prompt tells it to re-query on follow-ups for exactly this reason — if you change that
> storage decision, change the prompt with it.

> **Never let the model estimate a return.** `project_investment` exists so *"what would I
> have in 10 years"* is arithmetic. A hallucinated figure is indistinguishable, to the
> reader, from a calculated one, and this is someone's savings.

> **Statement text is data, not instructions.** Descriptions, merchants and tags come from
> imported PDFs and are attacker-influencable in principle. The system prompt says so
> explicitly; keep that clause if you rewrite it.

Cost guards are module constants in `assistant/settings.py`: iteration cap, history window,
result-row cap, message length, conversation count and the default rate limit. They are not
decoration — each message is one to three paid LLM calls.

> **They are constants on purpose, not settings.** Anything a self-hosted owner actually wants
> to change — the rate limit, the monthly token budget, the custom instructions, the system
> prompt — is per user in the database and editable in Settings → Assistant, where it applies
> without a restart. Do not reintroduce `ASSISTANT_*` env vars: the two would then disagree and
> the UI could no longer say what is in force.

> **The rate limit and the monthly budget are not interchangeable.** The rate limit is an
> in-process sliding window: it stops a burst, and it resets on every restart. That makes it
> structurally incapable of capping a month's spend, because a redeploy hands back a full
> allowance. The monthly token budget counts `assistant_usage` and
> `import_summary_attempts` in the database,
> independently of the conversations. Deleting a chat only clears the ledger's conversation
> link; it never refunds the tokens. Migration 0026 backfills existing usage. If you move the
> limiter to Redis some day, the budget still belongs in the database.

> **A turn without an answer is billed too.** Every provider call that finished was paid for,
> so when a turn fails, hits the iteration cap or is stopped by the user,
> `_record_unanswered_usage` in `api/assistant.py` writes its summed usage to the ledger with
> `answered=false` and to the question's row for display. Successful answers write their
> ledger entry alongside the message. Otherwise the most expensive turns would be free,
> and pressing Stop would bypass the monthly cap. The write is shielded from cancellation,
> because a client disconnect cancels the very task running it.

> **The system prompt is editable from Settings → Assistant**, pre-filled with the shipped
> default and restorable in one click. Stored per user; null means "use the default", so
> clearing the box restores it rather than sending an empty system message. Store the
> override only when it *differs* from the default — the UI does this — or an untouched
> editor freezes today's prompt and the instance stops receiving improvements to it.
> Custom instructions still exist alongside it and are appended to whatever prompt is in
> force, so a small tweak does not require rewriting the whole thing.

> **`{context_block}` is mandatory in a custom prompt and the API rejects one without it.**
> Not a style rule: it is where the accounts, categories and date coverage are injected.
> Without it the model has no ids and starts inventing the ones the prompt tells it never to
> invent, so the assistant is simply broken — which is why this one is a hard 422 rather
> than a warning.

> **Substitute with `str.replace`, never `str.format`.** A user-written prompt may contain
> braces — a JSON example, a literal `{}` — and `format` raises KeyError on them, taking the
> whole assistant down over a character.

> **Dropping a safety rule is warned about, not blocked.** `SAFETY_MARKERS` in `prompts.py`
> lists the phrases that stop the model inventing figures; the API reports which a custom
> prompt no longer contains and the UI shows it beside the editor. It stays advisory because
> this is a self-hosted app and its owner is entitled to rewrite the prompt — but the
> consequence is invisible in the output, since a fabricated figure reads exactly like a
> calculated one, so it has to be visible at the moment the choice is made.

> **`stream_options.include_usage` is required to see token counts at all.** A streamed
> response carries no usage otherwise, and the usage chunk arrives with an EMPTY `choices`
> list — so it has to be read *before* the guard that skips choice-less frames. Usage must
> also be SUMMED across a turn: a tool round-trip is several provider calls, and taking only
> the last one understates the cost by roughly half.

The frontend client has **no mock fallback** on any assistant endpoint — or anywhere else
(see the frontend conventions below). A `catch { return mockGetX() }` would answer a
question about the user's money with invented figures.

---

## Investment connector architecture

Two connector types coexist under the same plugin model:

| Type | Example | Storage |
|------|---------|---------|
| **Live-API** | Indexa Capital | Token encrypted with Fernet → `investment_connections`. Portfolio fetched on demand and cached 24h in `investment_portfolio_cache`. |
| **Statement-Import** | Fidelity ESPP | Lots stored in `espp_lots`. Daily MSFT close stored in `price_history` (via Yahoo Chart API). No token required. |

Both produce data consumed by `GET /api/investments/combined-overview`, which
`investments/overview.py::build_combined_overview` builds for the API and the assistant alike.

> **An unreadable provider is "unavailable", never 0 €.** A connection in
> `HOLDING_STATUSES` (`active` or `error`, in `db/queries/investments.py`) still holds money.
> An `error` connection, or an account whose fetch fails, is counted in the portfolio's
> `accounts_unavailable`, and the combined overview sets `partial`. The Dashboard, the
> investments page, the snapshot card and the assistant then say the total is incomplete.
> Valuing it at zero silently takes the whole portfolio out of net worth.

> **Rates are never summed across accounts.** Euro amounts add up, and `_add_optional` keeps
> an unknown one unknown rather than zero. A percentage does not add up: with more than one
> Indexa account, `money_return` and `money_return_annual` are `null` and `monthly_returns` is
> `[]`, and the UI hides them. A legitimate `0` stays `0`, so never coalesce it with `or None`.

> **Repeated holdings are merged, not concatenated.** `investments/service.py::_merge_holdings`
> keys instruments on `(plugin_id, ticker or name)` across accounts, sums their values, and
> recomputes the return from the combined gain and cost basis. An unknown quantity, cost or
> gain stays unknown through `_sum_known`; treating it as zero would understate the position.
> Asset-class labels go through the bilingual `investments/assetClass.ts` helper.

### Token encryption

All connector API tokens are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).

- Key: `FINLYTICS_ENCRYPTION_KEY` env var (must be a valid Fernet key).
- Fail-closed: any encrypt/decrypt operation raises `EncryptionNotConfiguredError` → HTTP 503 when the key is absent or invalid.
- Tokens NEVER appear in logs, API responses, or any non-encrypted DB column.

---

## Mortgage module

The only **liability** in the app. Lives in `src/finlytics/mortgage/` and is deliberately
independent from the investment plugin model.

| File | Responsibility |
|------|----------------|
| `schedule.py` | Pure French-system amortization engine. No DB, no I/O — takes an immutable `MortgageSpec` and returns the full instalment table. |
| `euribor.py` | Fetches the 12-month Euribor monthly average from the ECB Data Portal and caches it in `euribor_rates`. |
| `simulator.py` | Builds two schedules (with/without a hypothetical prepayment) and reports the delta. Persists nothing. |
| `service.py` | Bridges ORM models ↔ engine specs; derives the KPI, chart and reconciliation payloads. |

### Rate model

Fixed, variable and mixed mortgages all use the same structure — a list of
`mortgage_rate_periods` tranches — so the engine has no per-type branching:

- **fixed** → one `kind='fixed'` tranche
- **variable** → one `kind='variable'` tranche
- **mixed** → a `fixed` tranche followed by a `variable` one

The instalment is recomputed when a tranche starts, when a variable tranche hits a
review, when a bonus window opens or closes, and after a `reduce_payment` prepayment.
A `reduce_term` prepayment deliberately keeps the instalment and shortens the loan.

### Conventions and constraints

- **Decimal everywhere.** A `float` accumulated over 360 instalments drifts the closing
  balance by several euros. The final instalment absorbs the rounding residue so the
  balance closes at exactly zero.
- **Euribor source:** `https://data-api.ecb.europa.eu/service/data/FM/M.U2.EUR.RT.MM.EURIBOR1YD_.HSTA`
  — public, no API key. Network failures degrade to the cached series.
- **Projection honesty:** future variable instalments hold the last published index flat
  and are flagged `projected=true` so the UI can render them as estimates.
- **Review lag:** Spanish deeds usually apply the index published 2 months before the
  review date. Configurable per tranche via `review_lag_months`.
- **Optional linking:** `linked_account_id` / `linked_category_id` are nullable. Without
  them the module is a pure calculator; with them `/reconciliation` compares the expected
  instalment against real transactions.
- **Term entry accepts months, not just whole years.** A loan signed mid-month usually
  amortizes capital over 359 instalments because the first charge covers interest alone,
  and a year-only field silently understates the instalment by a couple of euros.
- **`signature_date` models the opening interest stub.** When it precedes the first
  payment date, the engine emits an interest-only row (accrued on actual days over a
  365-day year, which is what reproduces the lender's figure) and starts amortizing with
  the following instalment. Without it the schedule repays capital that never was and
  finishes a month early.
- **`/payment-candidates` checks the terms against the ledger** at setup time: it looks
  for a recurring charge and reports the deviation from the computed instalment. It only
  suggests — nothing is linked or modified server-side.
- **Net worth:** only mortgages with `include_in_net_worth = true` reach
  `GET /api/mortgages/net-worth`, which the Dashboard adds to its KPI. An unused module
  answers zeros; a *failed* read marks the KPI as partial rather than counting as zero,
  which would overstate net worth by the whole outstanding debt.
- **Demo:** the demo scenario includes a fixed-rate mortgage, and `demo/handlers.ts`
  serves the same read payloads the API would (the prepayment simulation included).
  Writes stay unhandled: the demo is read-only.

---

## Auth sessions

The session is a JWT in an HttpOnly cookie, and it is revocable. Each token carries a `jti`
and the `ver` (`users.token_version`) it was minted under; `load_session_user` in
`api/deps.py` checks both in one query.

- `POST /api/auth/logout` records the `jti` in `revoked_tokens` until the token's own
  expiry (expired rows are purged on each logout), so a copied cookie dies with the logout.
- `POST /api/auth/logout-others` and `POST /api/auth/password` bump `token_version`, which
  ends every session at once, then re-issue the cookie so the calling device stays in.
- A token without `ver`/`jti` — anything issued before migration 0023 — is refused, so
  every user signs in once after that deploy.

> **A wrong current password answers 400, not 401.** The SPA treats any 401 from a
> protected call as "the session has ended" and signs out, so a typo would log the user
> out. `sessionPost()` in `client.ts` routes only a real 401 to that handler.

> **The password change shares the login rate limiter.** Without it, a stolen session
> becomes an unthrottled oracle for guessing the current password.

> **bcrypt accepts at most 72 UTF-8 bytes, not 72 characters.** `auth/security.py` rejects
> longer passwords before hashing or verification. Setup and password-change forms use
> `utils/password.ts` to enforce the same cap; never truncate a password to make it fit.

> **`/settings/security` stays out of the demo.** It writes credentials.

---

## Transaction dedup key

`transactions.dedup_hash` is what makes re-importing a statement a no-op.
`compute_dedup_hash()` in `db/repository.py` is its only definition: a SHA-256 over the
`account_id`, the date, the amount quantized to cents, the description and — only when
non-empty — the detail line.

> **Key on the account id, never its name.** Renaming an account would otherwise re-import
> a whole statement as new rows, and two accounts differing only by case would share one
> dedup space.

> **Quantize the amount before hashing.** `str(Decimal)` spells one value as `-42.1` or
> `-42.10` depending on whether it came from a JSON body or a `Numeric(14,2)` column, so the
> import path and the edit path would disagree about the same row.

> **Changing the payload is a data migration.** Every stored hash has to be recomputed, as
> `0024_rekey_dedup_hash_on_account_id.py` does, or the next import inserts everything
> again. Rows that collide under a new key are duplicates the old key let through: keep
> them under a `legacy:<id>` disambiguator and report the count, never delete them.

> **`update_transaction` re-keys a row only when its natural key moves.** The edit form
> resends every field, so it compares the hash of the old and new values rather than the
> fields themselves; re-keying an untouched forced duplicate would collide with the row it
> duplicates.

> **A backup round-trips everything the key depends on.** `api/backup.py` exports `detail`
> and `is_system`, and, when the stored hash cannot be re-derived from the row's fields,
> `duplicate_key`. That covers a forced duplicate and a `legacy:<id>` collision. The restore
> uses that key or re-hashes against the *target's* account ids. Drop any of those fields
> and a restored opening balance counts as income, rows that differ only in their detail
> merge into one, and re-importing the original PDF duplicates rows.

---

## Backend conventions

- **Routers:** `APIRouter(prefix="/...", tags=["..."])` per module in `src/finlytics/api/`. Registered in `app.py` with `app.include_router(router, prefix="/api", dependencies=_auth)`.
- **Schemas:** Pydantic `BaseModel` in `api/schemas.py`. Amounts as `float`, percentages as raw numbers (e.g. `12.5` = 12.5%).
- **Auth:** All `/api/*` routes (except `/api/auth/*`) are auth-gated via the `get_current_user` dependency.
- **Response headers:** `api/middleware.py` supplies CSP, nosniff, frame denial, referrer and permissions policies. `FinlyticsApp.build_middleware_stack` wraps the complete Starlette stack, including its 500 responder. Keep these wrappers pure ASGI so assistant SSE is not buffered. Interactive API docs skip only CSP. The demo mirrors the policy in `vite.config.ts` (`DEMO_CSP`, emitted into `_headers`) and `nginx.demo.conf`; update all three together.
- **Request ids and logging:** `X-Request-ID` is reused only when it matches `[A-Za-z0-9._-]{1,64}`; otherwise generate a UUID. The same id tags responses and logs. Unexpected errors use `log.exception`; caught warning-level failures use `exc_info=True`. A broad exception handler without logging needs a specific `BLE001` exemption and reason. Never expose statement text, connector tokens or internal exception details in an API error.
- **Import failures:** unsupported files and malformed Fidelity CSVs are client errors. Unexpected extraction/import failures return generic details and retain diagnostics in `log.exception`, not in the response.
- **API contract:** `scripts/export_openapi.py` writes `frontend/src/api/openapi.json`; `npm run gen:api` generates `schema.gen.ts`, and `contract.ts` checks the handwritten client types against it. Both generators have a `--check` mode that CI runs. Regenerate both outputs after schema changes, never edit the generated types. The small schema generator avoids a dependency on TypeScript's JavaScript compiler API, which the Go-native TypeScript 7 no longer supplies.
- **Config:** `pydantic-settings` `BaseSettings` in `config.py` — env vars + `.env` file.
- **Dependencies:** `uv.lock` is the source of truth. The image and CI install with `uv sync --locked`, which fails when the lock is out of date with `pyproject.toml` — after editing dependencies, run `uv lock` and commit both files. Local setup: `uv sync --extra test`, then `uv run pytest` and `uv run mypy`. Dependabot's `uv` ecosystem moves the lock; the uv binary itself is pinned once, in the Dockerfile's `uv` stage, and CI reads it from there.
- **Lockfile:** every `registry` in `uv.lock` must be `https://pypi.org/simple` and every artefact `url` must be on `https://files.pythonhosted.org/`; CI rejects anything else, for the same reason as `package-lock.json` below. A lock resolved through a private mirror (`UV_DEFAULT_INDEX`, `UV_INDEX_URL` or a user-level `uv.toml`) records the mirror's URLs — re-lock against PyPI instead of committing it.
- **Types:** mypy covers the whole package and CI gates it. Handlers declare the query layer's TypedDicts (`db/queries/types.py`) as their return type and let `response_model` validate them. Do not annotate a handler with a Pydantic model it never constructs: the checker then trusts a type the function does not return.
- **Lint:** Ruff's default rule set, run as `uv run ruff check src tests alembic`, and CI gates it. Every exception in `pyproject.toml` is a convention with its reason beside it. FastAPI's `Depends()`-style markers are declared immutable calls rather than silencing `B008`, and deployed migrations are excluded because they are never edited.
- **Rules:** `api/rules.py` pre-filters candidate transactions in SQL, loads only those columns, and leaves `_matches` in Python as the final word. That is also the only place a regex is evaluated. The SQL has to be a *superset* of what `_matches` accepts, never narrower. It folds case with `translate()` rather than `lower()`, whose result depends on the database collation. `tests/pg/test_rules_prefilter.py` holds it to that.
- **PostgreSQL tests:** the rest of the suite runs on SQLite and mocks, which cannot execute `INSERT ... ON CONFLICT`, `to_char` or the migration chain. Those paths are tested in `tests/pg/`, against the server named by `TEST_DATABASE_URL` (a role allowed to `CREATE DATABASE`). The chain is migrated once into a template database and every test gets its own clone, so the code under test begins and commits transactions exactly as in production. Without the variable the tier skips; under CI it fails instead, and the `tests` job runs a `postgres` service for it. Locally, use a throwaway server rather than the compose `db`, which holds real data: `docker run --rm -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:18-alpine` with `TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`. An upsert, a dialect-specific function or a migration that rewrites data gets its test there, not a mock.

## Frontend conventions

- **Routing:** `App.tsx` — nested routes under `<Route path="/" element={<Layout />}>`. Every page is a `lazy()` import, so each screen (and recharts, which only chart pages pull in) is its own chunk; `Layout`, `SettingsLayout`, `LoginPage` and `SetupPage` stay eager because they render before or around every route.
  - `Layout` owns the **only** `<Suspense>` and a `RouteErrorBoundary` around `<Outlet />`. React Router runs navigations in a transition, so after the first paint the previous page stays on screen while the next chunk loads — a per-route boundary would flash a spinner instead.
  - A chunk that fails to load (typically a tab opened before a deploy, whose hashed file no longer exists) shows a reload prompt inside the shell. React caches the rejected import, so only a reload recovers — do not replace this with a silent `vite:preloadError` auto-reload, which would throw away an in-flight assistant answer or a half-filled form.
  - **Prefetch:** `routePrefetch.ts` holds every page's loader in `pageChunks`, and `App.tsx` builds its `lazy()` components from it. `Layout` fetches a page's chunk when the pointer or focus reaches an in-app link (or a `data-prefetch` element). In production it also fetches `LIKELY_NEXT`, one chunk at a time while the browser is idle, and skips that under Save-Data. A new page goes into `pageChunks`, or it is simply never prefetched.
- **Local dates:** build a `YYYY-MM-DD` with `todayIso()` / `isoDate(d)` from `utils/dates.ts`. Never use `toISOString().slice(0, 10)`: it converts to UTC first, so in Spain it returns yesterday between midnight and 02:00, and a local midnight comes out as the previous day. Vitest pins `TZ=Europe/Madrid` because CI runs in UTC, where that bug cannot show.
- **i18n:** Bilingual EN/ES. `Dict` interface in `i18n/index.ts`, implementations in `es.ts` / `en.ts`. All three files must be updated for every new string.
  - **Locale and money:** a UI language becomes an `Intl` locale tag only in `i18n/index.ts`. Format amounts with `formatCurrency` (from `useT()` in a component, or the module export with a `lang` argument in a pure helper), and hand `useT().locale` / `langLocale(lang)` to any other `Intl` or `toLocale*` call. Never inline `'es-ES'` or pass the bare `lang` (`'en'` resolves to `en-US`): the English UI used to print `1.234,56 €` beside `€1,234.56`. `test/locale.test.ts` fails on an inline tag.
  - **Percentages and plain numbers:** `formatPercent` / `formatNumber`, or `<Percent>` in JSX — never `toFixed()` plus `'%'`, which printed `12.5%` in the Spanish UI and `-0.0 %` for a value that rounds to zero. Pass `unit: 'fraction'` for the API values that are fractions (see the units note under *Public demo*). `formatCurrency` never prints `-0,00 €` either: anything under half a cent is zero. `test/format.test.ts` pins these cases.
  - **Chart axes:** use `formatCompactCurrency` with `width="auto"` on monetary Y axes. Full currency strings clip or squeeze the plot at large balances; tooltips still show the full amount.
- **API client:** `frontend/src/api/client.ts` — typed `apiFetch<T>()`. New endpoints follow the `getX()` / `postX()` pattern.
  - **JSON writes:** explicitly set `Content-Type: application/json` when sending a JSON body. `apiFetch` does not add it, so the browser otherwise sends text and FastAPI rejects the model with 422. MSW's `request.json()` accepts text bodies too; mutation tests must verify the header as well as the payload. Do not set it on `FormData` uploads.
  - **Mock layer:** `frontend/src/api/mock.ts`, activated build-time by `VITE_USE_MOCK=1`. Coverage is **partial** — roughly 40 of 68 client functions have a mock branch. Rules, backup, statements, all Fidelity endpoints and `combined-overview` have none.
  - ⚠️ **Never fall back to the mock on an error** (`catch { return mockGetX() }`). Thirteen reads used to, so in production a 500 or a network drop rendered **fake data as if it were the user's** — and the unconditional reference also shipped the whole mock dataset in the production bundle. The mock is reachable only behind `if (USE_MOCK)`, which the bundler drops; `api/client.test.ts` asserts that a failed read rejects. The same goes for "degrade to zeros": a figure that feeds a total (the mortgage's net-worth contribution, say) must throw, so the page can mark the total as partial instead of silently omitting a line of it.
- **Data layer:** every read goes through a hook in `api/queries.ts`, keyed from `queryKeys`. A component never calls a `getX()` from a `useEffect`: that pattern let a slow response for the previous filter overwrite the current one, and every screen refetched what another had just loaded. After a write, invalidate by key prefix (`['summary']`, `['investments']`, `queryKeys.transactionsAll`) rather than threading a `refreshKey` prop through the tree.
  - **Deliberate exceptions**, all of them either writes or wizard state rather than cacheable reads: the auth bootstrap in `AuthContext`, the streamed conversation in `AssistantContext`, the import previews (`previewImport` / `checkDuplicates` in `ImportModal`, `fidelityImportPreview` in `FidelityView`) and the on-demand `simulateMortgagePrepayment`. Anything else fetched by hand is a bug.
  - **The cache belongs to a session.** `AuthContext` clears it when `authenticated` goes from true to false, which covers logout and a 401 alike; otherwise the next user to sign in on the same tab would briefly see the previous one's figures.
  - **Never poll `GET /api/notifications`:** it runs every detector and writes. `useNotificationChangePoll` polls `/unread-count` and invalidates the list only when the two disagree, and the badge is derived from the list, so it cannot contradict the dropdown under it.
  - **A form seeded from a query mounts only once the data exists** (see `AssistantSettingsPage`). Rendering it with empty defaults first flashes validation errors about values nobody typed, and `useState` initialisers do not re-run when the data arrives.
- **Filters live in the URL.** Transactions, Finances and Analytics read theirs through `useUrlFilters` (`hooks/useUrlFilters.ts`), so a reload, the back button or a shared link restores the view. Keys: `from`, `to`, `account_id`, `category_id`, `tag` (repeatable), `flow`, `merchant`, `q`, `min`, `max`, `day`. A missing `from`/`to` means the page default and an empty one an open end; a customised range always writes both ends, so a shared link keeps its period as the default moves. Malformed values are dropped, unknown params are preserved, and navigation uses `replace` so typing does not flood the history.
  - Updates compose on the **last written** value, not the rendered URL: navigations commit in a transition, so two updates in one tick would both start from the same URL and the second would silently drop the first.
  - A free-text box binds through `useDebouncedFilter` (300 ms), which also writes a change made elsewhere — a chip, *Clear*, the back button — back into the box. A plain `useState` leaves stale text above a filter that is no longer applied.
- **Shared building blocks** — use them rather than re-deriving the markup:
  - `CardHeader` is the one card heading. It renders an `h2`, because every page has exactly one `h1` (visible, or `sr-only` on the Dashboard, Finances and Statements); an optional `action` wraps under the title on narrow cards. Settings pages render neither `<main>` nor an `h1`: `SettingsLayout` owns both.
  - `CategoryBadge`: the category colour marks a dot and the label keeps the body text colour — user-picked hues cannot all clear 4.5:1 as text.
  - `SortableTh`: a button inside the `th` takes the pointer and the keyboard, and the `th` carries `aria-sort`. Trailing controls (an info tip) sit beside the button, never inside it.
  - `splitTopSlices` (`utils/categorySlices.ts`): a donut draws the six largest slices and folds the rest into one neutral slice. A tail of one is never folded.
  - `computeDelta` (`utils/comparison.ts`) divides by the **absolute** baseline, so a negative figure that improves reads as a rise rather than a fall.
  - `Modal` (`components/Modal.tsx`) opens a native `<dialog>` with `showModal()`: the browser makes the background inert and restores focus on close. Mount/unmount it to open/close it, pass `labelledBy` or `label`, and set `disabled` while saving, including on the site's close buttons. Escape dismisses unless an inner picker claimed it; backdrop dismissal requires both the press and release outside the box, so dragging a text selection cannot discard a form. Nested dialogs stack naturally. Content portaled to `document.body` is beneath the dialog and inert: render its tooltips inside `Modal` instead. The assistant panel and non-modal pickers keep their own widget behavior.
  - `ToastProvider` (`contexts/ToastContext.tsx`) is mounted once in the authenticated app, inside the language provider. `useToast()` replaces the current message, announces it through a persistent status region and starts a six-second timer, cleaned up on replacement, dismissal and unmount. Dialogs register in opening order so the toast portal stays inside the active one; a manual popover lifts it above the dialog without making its controls inert. Logging out unmounts the provider and clears its messages. Do not add local toast states or timeouts.
- **Forms:** use `NumericInput` for money and keep its text unchanged until submit, never `type="number"` or parsing on every keystroke. `utils/parseNumber.ts` supplies `parseAmount` for money and `parseDecimal` for rates/counts, accepting English and Spanish separators. A single separator before three digits means grouping for amounts (`1.234` is 1234), but a decimal for rates (`2,125` is 2.125). Malformed or empty required values must block saving, not become zero. `parseOr` defaults only a blank field; pair optional parsing with `isMalformed` validation. This preserves trailing separators and lets a field be emptied.
- **Effects:** never call a state setter synchronously in an effect to follow a prop, the route or a query result; oxlint's `react/set-state-in-effect` fails the build. That pattern paints the stale value first and renders a second time to correct it.
  - To follow a value, adjust during render against the previous one, kept in state: `DateInput` resyncing its text, the `Layout` drawer and accordions, `StatementsPage` landing on the newest month.
  - To start over for a new record, remount it with a `key`, as `TransactionsTable` does for `TransactionDetailModal` (`key={detailTx.id}`).
  - A "latest value" ref that a timer or a listener reads is written in `useLayoutEffect`, never during render (`react/refs`). The import modal's duplicate re-check is one.
  - Anything derived from a query result must keep its identity when the result is absent. Otherwise an error renders a fresh `[]` each time and the adjustment loops forever. `StatementsPage` falls back to a memoised `EMPTY` for this.
  - `react/exhaustive-effect-dependencies` is off in `.oxlintrc.json`. `react-hooks/exhaustive-deps` already fails on a missing dependency, and the compiler rule also flags extra ones, which is how an effect says "run again when X changes".
- **Category palette:** the base-category colours in `seed.py` are chosen to stay distinguishable under protanopia and deuteranopia. Changing them takes a migration that recolours only rows still on the old seeded value (see `0025_recolor_base_category_palette.py`), and `tests/test_seed.py` asserts that the seed equals the palette that migration installs — a new palette moves that test to the new migration. `demo/scenario.ts` and `api/mock.ts` mirror the same hexes.
- **Accessibility:** `@axe-core/playwright` enforces zero axe violations on every demo route, with the assistant open and in the native prepayment dialog at desktop and mobile widths. Failures report rule ids and element targets; fix the markup rather than excluding a rule.
  - One focus ring for the whole app — `:focus-visible` in `tokens.css`. Text fields get a halo instead, because they match `:focus-visible` on a mouse click too. Never remove an outline without a replacement.
  - A header cell with no visible text (an actions column) needs `sr-only` text, and every `<label>` needs `htmlFor` pointing at its control's `id`.
  - A clickable row gets a real `<button>` inside a cell. Never put `onClick` or `role="button"` on a `tr`: that breaks the table semantics and is unreachable by keyboard.
  - A region that scrolls horizontally is `<section tabIndex={0} aria-label={…}>` behind a `jsx-a11y/no-noninteractive-tabindex` disable directive that states the reason — keyboard users have to focus it to scroll it. oxlint rejects both `section role="region"` (redundant) and `div role="region"` (prefer the tag).
  - The typeaheads (`TagTypeahead`, `PreviewTypeahead`, `TagFilterSelect`) follow the ARIA combobox pattern: `role="combobox"` on the input, `aria-activedescendant` on the highlighted `role="option"`, `role="listbox"` for the popup. A chip's remove button is labelled `tagChipRemoveNamed(name)`, never a bare "×".
- **Responsive layout:** below 768px (`COMPACT_NAV_QUERY` in `hooks/useMediaQuery.ts`, which must match the CSS breakpoint) the sidebar becomes a drawer and a bottom nav appears; fixed elements along the bottom edge clear it through `--chrome-bottom`. At 600px and below a transaction row reads as a card instead of a scrolled table. The Indexa view is intrinsic — auto-fit grids plus `flex-wrap`, no viewport breakpoints — because its width depends on the sidebar, not the viewport.
- **Tests:** Vitest + Testing Library + MSW. `npm test` runs them once, `npm run test:watch` in watch mode, `npm run test:coverage` with coverage. `npm run lint` is oxlint, and `npm run build` runs `tsc --noEmit` first. CI gates all three (`lint` → `test` → `build`), so all three must pass.
  - **Lint warnings fail too:** the script is `oxlint --deny-warnings src e2e`, configured in `.oxlintrc.json`. A disable directive names its rule and gives the reason after `--`. List keys are stable ids, never the index of a list that can be filtered or reordered.
  - **Smoke test:** `npm run e2e` runs Playwright (`e2e/demo-smoke.spec.ts`). It builds the demo, serves it on port 4173, signs in and opens every route in `ROUTES`, then asks the assistant a question. It also exercises the simulator's background inertness, focus restoration, bottom sheet and drag-safe backdrop dismissal. Each test fails on axe violations, a page error, a console error or any response ≥ 400, the demo's 501 catch-all included. It runs in CI as the `e2e` job. A new demo screen goes into `ROUTES`. Where the Playwright browser download is blocked, a local config that extends `playwright.config.ts` with `channel: 'msedge'` or `'chrome'` runs it on an installed browser. Do not commit that config. The spec and `playwright.config.ts` are in `.dockerignore`; `tsconfig.json` still lists them, and tsc accepts a missing include, so the image's build keeps type-checking.
- **Lockfile:** every `resolved` URL in `package-lock.json` must point at `https://registry.npmjs.org/`, and CI rejects anything else. An install behind a private mirror (check `npm config get registry`) records the mirror's URLs, and Dependabot then fails on every package they cover — security updates included — without opening a PR. Rewrite the prefix before committing; the tarballs are the same, so the integrity hashes still match.
- **Plugin view registry:** `frontend/src/investments/registry.ts` — maps `plugin_id → { icon, name, load, component }`, built with `lazyView()` so the view's chunk can be prefetched. Add an entry here for any new investment connector view.
- **Design tokens:** CSS custom properties in `styles/tokens.css`, imported first by `index.css` (`--bg`, `--surface`, `--border`, `--primary`, `--radius`, `--shadow`, plus the `--text-*` type scale and `--space-*` 4px grid that new rules use instead of raw pixels). Light/dark via `[data-theme="dark"]`. `--income` / `--expense` colour text and must clear 4.5:1; chart marks use `--income-fill` / `--expense-fill`, which only need 3:1.

### Privacy mode

An eye button in the topbar blurs every monetary value so the app can be opened
next to someone else. `PrivacyContext` persists the choice under
`finlytics_privacy` and sets `data-privacy="on"` on `<html>`; `styles/privacy.css`
blurs anything carrying the `private` class.

> **Render amounts through `components/Money.tsx`.** `<Money value={n} />` for a
> plain figure, `<Private>` for one an existing formatter already produced, or
> append `private` to the enclosing element when it contains only the amount.
> A new amount that skips all three is simply not covered — and nothing throws.

> **`privacy.test.tsx` mounts the money-bearing routes against the demo dataset
> and fails on any euro text without a `.private` ancestor.** That test is the
> reason a missed call site surfaces at all, since a leak is invisible in a
> passing build. Add a route there when you add a screen that shows money.

> **A native `title` tooltip cannot be blurred by CSS.** The heatmap and the
> amortization table therefore read `usePrivacy()` and drop the figure from the
> tooltip text instead. Any new `title` carrying an amount needs the same.

> **Blur is a visual guard, not redaction.** The text stays in the DOM, so it is
> selectable and readable by assistive tech — it defends against a glance over
> the shoulder or a screen share, not against someone at the keyboard. Public
> market data (a share price, an FX rate) is deliberately left sharp; it says
> nothing about the user. Percentages, dates and counts stay readable too, so
> the app remains usable with the toggle on.

### Home-screen install (PWA)

`frontend/public/` holds `manifest.webmanifest` plus the icon set. Both builds copy
`public/` verbatim, so the demo and the production image get them for free — FastAPI's
SPA catch-all and `nginx.demo.conf` already serve any real file at the root.

> **`logo.svg` and `icon.svg` are two different marks, deliberately.** The favicon is a
> transparent gradient mark so it reads on a light or dark tab strip. A home-screen tile is
> composited over the wallpaper and iOS flattens transparency onto black, where thin navy
> strokes vanish — so `icon.svg` is full-bleed instead: gradient tile, white mark. Do not
> "unify" them.

> **iOS cannot use an SVG icon at all**, which is the only reason the PNGs exist. Without
> `apple-touch-icon.png`, "Add to Home Screen" falls back to a generated letter tile. The
> PNGs are rasterised from `icon.svg` at 180 (Apple), 192 and 512, plus a `maskable` 512
> whose mark is scaled to 0.72 so Android's mask cannot clip it. Regenerate all four with
> any rasteriser when the mark changes — there is no build step for it, and no npm
> dependency is carried for a once-a-year task.

> **`theme-color` is media-less on purpose.** The theme is a stored user choice, so a
> `prefers-color-scheme` media query would get it wrong whenever the two disagree. The
> FOUC-prevention script in `public/theme-init.js`, loaded by `index.html`, sets it on first
> paint and `ThemeContext.applyTheme` keeps it in step; both mirror `--bg` from `tokens.css`.
> Keep the bootstrap external: the CSP deliberately forbids inline scripts.

> **`app.py` registers the `.webmanifest` MIME type.** Python's `mimetypes` table has no
> entry for it, so `FileResponse` would serve the manifest as `text/plain`. nginx has
> shipped the mapping since 1.21.4, so the demo needs nothing.

## Public demo (`frontend/src/demo/`)

`npm run build:demo` (flag `VITE_DEMO=1`, via `.env.demo`) emits a backend-less build to
`frontend/dist-demo/`: [MSW](https://mswjs.io) intercepts `/api/*` in the browser and answers
from a synthetic dataset.

CI publishes it as `drdonoso/finlytics-demo` (`docker build --target demo`). It is deployed
from `docker-compose.demo.yml` — a single nginx container, no API, no database, no volumes.
That file's header carries the operational notes; the one that bites is:

> **The demo only works over HTTPS** (or `localhost`). Its whole API layer is a Service
> Worker, and browsers refuse to register those outside a secure context. On plain HTTP the
> worker never starts and every screen fails to load — `main.tsx` catches this and renders an
> explicit message rather than a broken app.

The same `dist-demo/` also deploys to a static CDN, which is the better home for a public
demo — it needs no inbound access to your own network and gets HTTPS for free. Three files
exist for that path and must stay in sync with `nginx.demo.conf`:

| File | Platform | Purpose |
|------|----------|---------|
| `frontend/wrangler.jsonc` | Cloudflare Workers | Pure static (no `main`); `not_found_handling: single-page-application` is the SPA fallback. Its header records the dashboard build settings — `Path` must be `/frontend`, since there is no `package.json` at the repo root. |
| `dist-demo/_headers` | Cloudflare | `no-cache` on the worker, immutable `/assets/*`, security headers |

`_headers` is emitted by a `vite.config.ts` plugin in demo mode rather than committed
under `public/`, because everything in `public/` is also copied into the **production**
bundle, where FastAPI serves the SPA and it would be dead weight.

> **Do not add a `_redirects` file with `/*  /index.html  200`.** Cloudflare rejects the
> deploy with *"Infinite loop detected in this rule"* — it normalises `/index.html` back
> to `/`, which re-matches the wildcard. The SPA fallback belongs in `wrangler.jsonc`
> (`not_found_handling`), which is also stricter: a missing *asset* still 404s.

| File | Role |
|------|------|
| `config.ts` | `IS_DEMO` flag, the `demo`/`demo` credentials, and the connector allowlist |
| `scenario.ts` | Seeded generator — accounts, transactions, Indexa portfolio, Fidelity ESPP lots and a fixed-rate mortgage. **Dates are relative to today** because `defaultRange()` opens on the previous calendar month; hardcoded dates would go stale. ESPP purchases land on the last weekday of Mar/Jun/Sep/Dec, mirroring `api/fidelity.py`. |
| `store.ts` | Single source of truth: the ledger AND every aggregate derive from one transaction list, so an edit is reflected in the KPIs. Filter semantics mirror `db/queries.py::_apply_filters`. |
| `handlers.ts` | MSW routes, plus a catch-all that answers 501 and logs `[demo] Unhandled API request:` |
| `assistantAnswers.ts` | Scripted chat answers. There is no model in the demo, so replies are keyword-matched against the suggested prompts — but every figure is read from `store.ts` at answer time, so the assistant never contradicts the charts beside it. The fallback says plainly that the public demo has no live model. |
| `browser.ts` | Worker startup — awaited in `main.tsx` **before** React mounts (AuthProvider fetches on its first effect) |
| `DemoLoginNotice.tsx` | The demo disclaimer, shown **only** on the login card |
| `nginx.demo.conf` | Serves the demo image. SPA fallback for deep links; `mockServiceWorker.js` must never be cached. Only the demo uses nginx — in production FastAPI serves the SPA itself. |

The demo keeps a real login screen: `/api/auth/status` starts unauthenticated and
`/api/auth/login` only accepts `demo`/`demo` (anything else 401s), so the sign-in flow
demoes itself. Session state is a module variable in `handlers.ts`, so a reload logs the
visitor back out — the same reset that restores the dataset.

> **Keep the disclaimer on the login screen only.** It is there to set expectations once,
> before the visitor is inside. A persistent banner would cover the UI on every page,
> which is the thing the demo exists to show.

> **Percentage units are not uniform across the API** — mirror the backend, don't guess.
> `combined-overview` (`total_gain_loss_pct`, `providers[].gain_loss_pct`, every `pct`),
> `fidelity/kpis.gain_loss_pct` and `fidelity/lots[].gain_loss_pct` are **percentages**
> (25.4 = 25.4%). Everything under `InvestmentPortfolio` is the opposite — decimal
> **fractions** — because `IndexaView` renders those with `* 100`: `total_gain_loss_pct`,
> all of `returns.*` (including `money_return`, which is a money-weighted *rate*, not
> euros), `drawdown.max_drawdown`, `holdings[].gain_loss_pct`, and `monthly_returns`
> (`months_pct`, `total_pct`, `benchmark_pct`). The UI prints most of them with a bare
> `.toFixed()`, so getting this wrong renders "+0.3 %" or "+342773.0 %" and nothing throws.

> **`monthly_returns` month keys are unpadded**: `"1"`…`"12"`, not `"01"`. The backend keys
> them by int and the matrix looks them up with `String(i + 1)`. Zero-padding silently
> blanks January–September — only 10/11/12 match — which reads as "the current year has
> no data" until October.

Rules when touching the frontend:

- **A new `/api` endpoint reached by a demo route needs a handler in `handlers.ts`**, or the demo
  silently loses that screen. The catch-all answers 501 and logs a console error, and the
  Playwright smoke test fails on either, provided the route is listed in `e2e/demo-smoke.spec.ts`.
- Demo mode intentionally exposes a reduced surface (`DemoRoutes` in `App.tsx`). Anything that
  writes, uploads or asks for third-party credentials stays out.
- Keep the demo free of MSW leakage into production: the dynamic import in `main.tsx` is guarded
  by a literal `import.meta.env.VITE_DEMO` check so the bundler can drop it.
- **The README screenshots in `docs/screenshots/` are captures of this demo build** (`npm run dev:demo`,
  logged in as `demo`/`demo`), which is the only source they may come from — a real instance would put
  someone's actual balances in a public repo. Regenerate them from the demo when a screen changes, and
  keep the "this is demo data" note under them. `docs/` is in `.dockerignore`: it never reaches an image.
