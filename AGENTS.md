# AGENTS.md — Finlytics contributor guide for AI agents

## Docker / build

**One `Dockerfile`, two targets.** There is no `Dockerfile.local` any more — it was a
workaround for an `npm 10.x` crash inside Docker ("Exit handler never called", bin-symlink
bug) that no longer reproduces on `node:26-alpine` / npm 11. Do not reintroduce a second
Dockerfile without evidence that the main one fails.

| Target | Produces | Used by |
|--------|----------|---------|
| `base` *(default)* | `node:26-alpine` compiles the SPA, `python:3.14-slim` serves API + SPA. | CI/prod — `docker-compose.yml`, `docker-compose.local.yml` |
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

Alembic migrations live in `alembic/versions/`. The current head is `0020_add_assistant_system_prompt.py`.

- Always create a new numbered migration (`0021_...`) for schema changes.
- Verify the head before writing one — this file goes stale. `down_revision` in the
  highest-numbered file is the source of truth, not this document.
- The entrypoint runs `alembic upgrade head` automatically on container start.
- Never modify an existing migration that has been deployed.

---

## Finance assistant architecture

`src/finlytics/assistant/` is a **read-only, tool-calling agent** over the user's own
data, surfaced as a slide-out chat panel.

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
> layer first and wrap it.

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
> allowance. The monthly token budget is counted from `assistant_messages` in the database,
> which is the only reason it works. If you move the limiter to Redis some day, that does not
> change — the budget still belongs in the database.

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

The frontend client has **no mock fallback** on any assistant endpoint. The
`catch { return mockGetX() }` pattern documented below would answer a question about the
user's money with invented figures.

---

## Investment connector architecture

Two connector types coexist under the same plugin model:

| Type | Example | Storage |
|------|---------|---------|
| **Live-API** | Indexa Capital | Token encrypted with Fernet → `investment_connections`. Portfolio fetched on demand and cached 24h in `investment_portfolio_cache`. |
| **Statement-Import** | Fidelity ESPP | Lots stored in `espp_lots`. Daily MSFT close stored in `price_history` (via Yahoo Chart API). No token required. |

Both produce data consumed by `GET /api/investments/combined-overview`.

### Token encryption

All connector API tokens are encrypted at rest using Fernet (AES-128-CBC + HMAC-SHA256).

- Key: `FINLYTICS_ENCRYPTION_KEY` env var (must be a valid Fernet key).
- Fail-closed: any encrypt/decrypt operation raises `EncryptionNotConfiguredError` → HTTP 503 when the key is absent or invalid.
- Tokens NEVER appear in logs, API responses, or any non-encrypted DB column.

---

## Backend conventions

- **Routers:** `APIRouter(prefix="/...", tags=["..."])` per module in `src/finlytics/api/`. Registered in `app.py` with `app.include_router(router, prefix="/api", dependencies=_auth)`.
- **Schemas:** Pydantic `BaseModel` in `schemas.py`. Amounts as `float`, percentages as raw numbers (e.g. `12.5` = 12.5%).
- **Auth:** All `/api/*` routes (except `/api/auth/*`) are auth-gated via the `get_current_user` dependency.
- **Config:** `pydantic-settings` `BaseSettings` in `config.py` — env vars + `.env` file.

## Frontend conventions

- **Routing:** `App.tsx` — nested routes under `<Route path="/" element={<Layout />}>`.
- **i18n:** Bilingual EN/ES. `Dict` interface in `i18n/index.ts`, implementations in `es.ts` / `en.ts`. All three files must be updated for every new string.
- **API client:** `frontend/src/api/client.ts` — typed `apiFetch<T>()`. New endpoints follow the `getX()` / `postX()` pattern.
  - **Mock layer:** `frontend/src/api/mock.ts`, activated build-time by `VITE_USE_MOCK=1`. Coverage is **partial** — roughly 40 of 68 client functions have a mock branch. Rules, backup, statements, all Fidelity endpoints and `combined-overview` have none.
  - ⚠️ **Gotcha:** 13 functions also fall back to the mock on *any* thrown error (`catch { return mockGetX() }`), not just when `USE_MOCK` is set. In production a 500 or a network drop therefore renders **fake data as if it were the user's**. Do not copy this pattern into new endpoints; prefer letting the error surface.
- **Tests:** Vitest + Testing Library + MSW. `npm test` runs them once, `npm run test:watch` in watch mode, `npm run test:coverage` with coverage. `npm run lint` is oxlint, and `npm run build` runs `tsc --noEmit` first. CI gates all three (`lint` → `test` → `build`), so all three must pass.
- **Plugin view registry:** `frontend/src/investments/registry.ts` — maps `plugin_id → { icon, name, component }`. Add an entry here for any new investment connector view.
- **Design tokens:** Single `index.css` with CSS custom properties (`--bg`, `--surface`, `--border`, `--primary`, `--radius`, `--shadow`). Light/dark via `[data-theme="dark"]`.

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
| `scenario.ts` | Seeded generator — accounts, transactions, Indexa portfolio and Fidelity ESPP lots. **Dates are relative to today** because `defaultRange()` opens on the previous calendar month; hardcoded dates would go stale. ESPP purchases land on the last weekday of Mar/Jun/Sep/Dec, mirroring `api/fidelity.py`. |
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
  silently loses that screen. The catch-all's console error is the signal.
- Demo mode intentionally exposes a reduced surface (`DemoRoutes` in `App.tsx`). Anything that
  writes, uploads or asks for third-party credentials stays out.
- Keep the demo free of MSW leakage into production: the dynamic import in `main.tsx` is guarded
  by a literal `import.meta.env.VITE_DEMO` check so the bundler can drop it.
- **The README screenshots in `docs/screenshots/` are captures of this demo build** (`npm run dev:demo`,
  logged in as `demo`/`demo`), which is the only source they may come from — a real instance would put
  someone's actual balances in a public repo. Regenerate them from the demo when a screen changes, and
  keep the "this is demo data" note under them. `docs/` is in `.dockerignore`: it never reaches an image.
