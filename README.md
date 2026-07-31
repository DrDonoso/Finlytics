# Finlytics 💰

**Self-hosted personal finance + investments tracker — import bank statements, connect investment accounts, and see your full financial picture in one place.**

---

## Why Finlytics?

Every open-source personal finance tool I evaluated was either too complex, required manual entry, depended on a bank integration I don't have, or just didn't fit how I actually work. What I wanted was simple:

1. Download the monthly PDF my bank already generates.
2. Drop it in → AI parses the PDF and categorizes every transaction automatically.
3. See where my money went — and how my investments are doing.

None of the available solutions fit that workflow. **Finlytics was built to be exactly that — simple, self-hosted, and tailored to a single owner's real workflow.**

---

## What It Does

### 🏠 Home

The home page is a cross-domain hub that gives you the full picture at a glance:

- **Month-navigation KPIs** — income, expenses, net balance for the last completed month, with previous/next controls to browse any month with data.
- **Investment snapshot** — total portfolio value across all connected providers, with a per-provider breakdown, fetched from `/api/investments/combined-overview`.
- **Import source picker** — a data-driven list of import actions: "Bank statement PDF" is always available; any investment connector with an import flow (currently Fidelity ESPP) appears automatically.
- **ESPP purchase reminder banner** — an amber banner appears when a Fidelity ESPP upload is overdue (quarter-end schedule: last business day of March/June/September/December).

### 📥 Bank Statement Import

- Upload a monthly bank-statement **PDF** (built and tested against BBVA; the parser is designed to extend to XLSX/CSV).
- **AI-powered extraction** via the OpenAI API or any OpenAI-compatible endpoint — structured output extracts date, amount, currency, description, merchant, category, and tags per transaction.
- **Bold-title / non-bold-detail parsing**: separates the transaction concept (e.g. *"Adeudo a su cargo"*) from its specific detail (e.g. *"Octopus Energy"* vs a community fee) so look-alike charges can be told apart.
- **Import preview**: review and edit every extracted transaction before committing to the database.
- **Idempotent import** — content-hash de-duplication means re-importing the same month never double-counts.

### ⚙️ Rules Engine

- Define rules to match transactions by title, detail, amount range, account, or currency.
- Actions: set category, set merchant, add tags, or **skip AI entirely** for known recurring charges.
- Rules run automatically on every import (before and after AI extraction).

### 💳 Finances

The finances overview (`/finances`) is the day-to-day spending dashboard:

- **Global filter bar** — date range, account, category, tags, amount range, income/expense toggle.
- **KPI cards** with delta % vs the previous calendar month (income, expenses, net).
- **Spending by category** — donut chart with table; click a category to filter the whole page.
- **Top merchants** — bar chart of top spend by merchant.
- **Adaptive spending heatmap** — three rendering modes depending on the selected date range:
  - **≤ 182 days:** GitHub-calendar style (daily cells, 7-row grid).
  - **183 – 547 days:** Compact scroll view.
  - **> 547 days:** Monthly-grid (12 columns × N years, always fits).
  - **Drill-down:** click any cell to filter the entire page to that day or month; a reset button restores the previous filter state.
- **Category movers** — categories that rose or fell most vs the previous period.
- Import button (bank statement PDF).

Related pages: **Transactions** (`/transactions`, sortable/filterable full transaction list), **Analytics** (`/analytics`, spending over time, by account, Sankey cashflow), **Statements** (`/statements`, statement history).

### 💰 Investments

#### Combined Overview (`/investments`)

- Total portfolio value, total invested, total gain/loss (€ + %).
- **Allocation donuts** — by provider (Indexa Capital / Fidelity ESPP) and by asset class (equities, fixed income, cash, ESPP stock — Indexa reports these in Spanish, so its own labels are shown verbatim).
- **Provider cards** — per-provider value, gain/loss, and link to the detail view.

#### Indexa Capital connector (live-API)

Connect your Indexa Capital account with a personal API token:

- Token stored encrypted at rest (Fernet / `FINLYTICS_ENCRYPTION_KEY`); never logged, never returned to the frontend.
- **24-hour DB portfolio cache** — the first page load returns cached data instantly; a background task refreshes from the Indexa API so the next open is up-to-date. `cache_stale: true` in the response signals when data is being refreshed.
- View: portfolio value, holdings table (instrument, asset class, current value, weight), evolution line chart, allocation donut, return metrics.

#### Fidelity ESPP connector (statement-import)

Import the Fidelity "View open lots" CSV to track your MSFT ESPP holdings:

- **Two-step import wizard** — upload CSV → preview new lots (with dedup against existing lots) → confirm.
- **Tax-lot holdings** — each lot stores shares, purchase date, EUR cost basis, source type (SP purchase / DO dividend reinvestment).
- **Daily MSFT valuation** — price fetched from the Yahoo Chart API (`query1`/`query2.finance.yahoo.com`) with EUR/USD FX conversion. Intraday snapshots are settled to the official close on next read (incremental price top-up).
- **Evolution chart** — daily-resolution value + contributions series with adaptive period selector.
- **KPIs** — total shares, total invested (EUR), current value (EUR), total gain/loss (€ + %).
- **Lots table** — sortable by date, shares, cost per share, current value, gain/loss; paginated.
- **ESPP purchase reminder** — the same banner shown on the home page also appears here when an upload is overdue.

### 🔔 Notifications

- **In-app notification bell** — active reminders with unread badge, read/dismiss state stored server-side so it survives across devices.
- **Detectors** run in a background loop inside the API process (every `NOTIFICATIONS_EVAL_INTERVAL_SECONDS`, 5 min by default) and currently cover two conditions: a missing monthly statement and an overdue ESPP upload. Adding a detector is a single entry in the registry.
- **Telegram delivery** *(optional)* — connect a bot from Settings → Connectors. The bot token is encrypted at rest with the same Fernet key as the connector tokens, and it is never logged or returned to the frontend. Set `TELEGRAM_SEND_ENABLED=false` to silence all sends globally.
- In-app notifications are stored as i18n keys plus arguments, never pre-rendered strings, so their text follows the UI language. Telegram messages are rendered server-side in Spanish (`notifications/messages.py`), the owner's locale.

### 💬 Talk to your finances

A slide-out chat panel, reachable from every page, that answers natural-language questions about your own data — *"how much did I spend on groceries last quarter?"*, *"where could I cut back?"*, *"if I invest €200 a month, what would I have in 10 years?"*

- **The model never sees your database and never writes SQL.** It picks from a fixed catalogue of ten read-only tools whose executors call the same `db/queries` code that renders the dashboards, so a chat answer is structurally incapable of disagreeing with the charts next to it.
- **Read-only.** There is no tool that writes, so the assistant cannot change a category, delete a transaction or touch a connector.
- **Projections are arithmetic, not opinion.** *"What would I have in 10 years"* goes through a deterministic compound-interest tool that returns conservative / base / optimistic scenarios; the model narrates the numbers it gets back and always carries the "not financial advice" disclaimer. A model inventing *"you'd have around €40,000"* reads exactly like a model that calculated it.
- **Streamed** token by token over SSE, with a chip showing which query is running.
- **Conversations persist** per user and are recoverable after a reload. Tool results are deliberately *not* stored or replayed — a follow-up makes the assistant re-query rather than answer a new question from an old query's data.
- Reuses the `OPENAI_*` credentials. With those unset the launcher does not appear at all, rather than offering a button that can only return 503.

### 🗂️ Management

- **Categories & tags** with color swatches (name-derived colors or a custom picker).
- **Accounts** management.
- **Full backup** — export the entire dataset to JSON and re-import it.
- **Connectors** (Settings → Connectors) — connect/disconnect Indexa Capital and the Telegram bot; Fidelity status reflects CSV import state.
- Bilingual UI: **Spanish / English**.
- **Light / dark / system** theme.
- Single-user authentication with session tokens, with failed logins throttled per client IP.
- **About** page — shows the deployed Docker image tag (CalVer), build date, links to the repo / Issues / CHANGELOG, and MIT license.

---

## How It Works

### Bank statement pipeline

```
Bank statement PDF
        │
        ▼
  pdfplumber — raw text extraction
        │
        ▼
  Bold-title + non-bold-detail parsing
        │
        ├──► [Pre-match rules — skip AI if a rule matches]
        │
        ▼
  OpenAI-compatible endpoint (structured output)
  → date · amount · currency · description · merchant · category · tags
        │
        ▼
  Remaining rules applied (override category / merchant / tags)
        │
        ▼
  Content-hash de-duplication → persist to PostgreSQL
        │
        ▼
  Finanzas dashboard (spending KPIs, charts, heatmap)
```

### Investment pipeline

```
Indexa Capital API token          Fidelity "open lots" CSV
        │                                   │
        ▼                                   ▼
  POST /api/investments/connections   Preview + confirm wizard
  Token encrypted (Fernet) → DB      New lots persisted to DB
        │                                   │
        ▼                                   ▼
  GET /api/investments/portfolio      Yahoo Chart API (MSFT + EUR/USD FX)
  24h DB cache + background refresh   Intraday → settled to close daily
        │                                   │
        └──────────────┬────────────────────┘
                       ▼
         /api/investments/combined-overview
         Total value · gain/loss · allocation by provider + asset class
                       │
                       ▼
         Investments dashboard (overview + per-provider detail)
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12+ · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic · uvicorn |
| Database | PostgreSQL 18 |
| PDF parsing | pdfplumber |
| AI extraction | OpenAI SDK — structured outputs via any OpenAI-compatible endpoint |
| Token encryption | `cryptography` Fernet (AES-128-CBC + HMAC-SHA256) |
| Market data | Yahoo Chart API (`query1`/`query2.finance.yahoo.com`) — MSFT price + EUR/USD FX |
| Investment connectors | Plugin architecture: live-API (Indexa) + statement-import (Fidelity ESPP) |
| Frontend | React 19 · TypeScript · Vite · React Router · TanStack Query · Recharts |
| Frontend tests | Vitest · Testing Library · MSW |
| Container | Multi-stage Docker (`node:26-alpine` builds the React SPA → `python:3.14-slim` runtime serves both API and SPA) |
| CI/CD | GitHub Actions — CalVer tags, Docker Hub push, auto-generated categorized changelog |

---

## 🚀 Self-Hosting

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/)
- An OpenAI-compatible endpoint for AI extraction *(optional but strongly recommended — without it, extraction is disabled)*

### 1. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
# Required
POSTGRES_PASSWORD=a-strong-password

# Strongly recommended — signs session cookies. If unset, a new key is
# generated on every restart and all sessions are invalidated.
# Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
AUTH_SECRET=your-own-generated-secret

# Optional — set all three to enable AI-powered extraction
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-model-name

# Required to use the Indexa Capital connector (token encryption)
# Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FINLYTICS_ENCRYPTION_KEY=your-fernet-key
```

> ⚠️ Generate your own values. Placeholders copied from `.env.example` are public;
> the app refuses to start if `AUTH_SECRET` is left at a known placeholder.

### 2. Run

**Using the published Docker Hub image (recommended for production):**

```bash
docker compose up -d
```

This pulls `drdonoso/finlytics:latest` from Docker Hub and starts the full stack (app + PostgreSQL). No local build required.

**Build from source (CI / full multi-stage):**

```bash
docker compose up -d --build
```

Uses the main `Dockerfile` — `node:26-alpine` compiles the React SPA inside Docker, then `python:3.14-slim` serves both the API and the SPA. This is what GitHub Actions runs on every push to `main`.

**Local dev (build from your working tree):**

```bash
docker compose -f docker-compose.local.yml up -d --build
```

Same stack, but built from the current checkout instead of the published image — use it to run uncommitted code.

### 3. Open

Navigate to **http://localhost:7777** and create the initial user account.

> The port can be changed by setting `FINLYTICS_PORT` in `.env` (default: `7777`).

### Optional: the public demo

There is a second, backend-less build for showing the app off without exposing any
real data. MSW intercepts every `/api/*` call in the browser and answers from a
synthetic dataset generated at page load, so there is no API container, no
database and nothing to reset — a reload restores everything.

```bash
docker compose -f docker-compose.demo.yml up -d      # drdonoso/finlytics-demo, nginx only
```

Log in with `demo` / `demo`. The same bundle (`npm run build:demo`) also deploys
to a static CDN; `frontend/wrangler.jsonc` carries the Cloudflare settings.

> ⚠️ The demo **only works over HTTPS** (or `localhost`). Its API layer is a
> Service Worker, and browsers refuse to register those outside a secure
> context. On plain HTTP nothing loads.

---

## ⚙️ Configuration Reference

All configuration lives in `.env` (copy from `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password |
| `POSTGRES_USER` | `finlytics` | PostgreSQL username |
| `POSTGRES_DB` | `finlytics` | PostgreSQL database name |
| `POSTGRES_HOST` | `db` | Only needed when running the API outside docker-compose |
| `POSTGRES_PORT` | `5432` | Only needed when running the API outside docker-compose |
| `OPENAI_API_KEY` | *(unset)* | API key for the OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | *(unset)* | Base URL of the endpoint (e.g. `https://host/v1`) |
| `OPENAI_MODEL` | *(unset)* | Model name to use for extraction |
| `FINLYTICS_ENCRYPTION_KEY` | *(unset)* | Fernet key for encrypting connector API tokens and the Telegram bot token at rest. Required to use the Indexa Capital connector. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `FINLYTICS_PORT` | `7777` | Host port the app is exposed on |
| `FINLYTICS_DATA_DIR` | `./data` | Host directory mounted at `/app/data`; original statement PDFs land in `<dir>/uploads/`. On Linux it must be writable by uid 1000 |
| `TIMEZONE` | `Europe/Madrid` | Calendar day the reminders reason about, and the process clock inside the container. The image runs in UTC, so without it a reminder is evaluated against the wrong day whenever UTC and local time disagree |
| `AUTH_SECRET` | *(random)* | Secret for signing session tokens. If unset, a new key is generated on each startup — sessions won't survive container restarts. Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `AUTH_COOKIE_SECURE` | `false` | Set to `true` when serving over HTTPS so the session cookie gets the `Secure` flag |
| `AUTH_TOKEN_EXPIRE_DAYS` | `7` | Session lifetime |
| `AUTH_REMEMBER_EXPIRE_DAYS` | `30` | Session lifetime when "remember me" is used |
| `AUTH_LOGIN_MAX_ATTEMPTS` | `10` | Failed logins allowed per client IP inside the window. `0` disables the limit |
| `AUTH_LOGIN_WINDOW_SECONDS` | `300` | Width of the failed-login window |
| `NOTIFICATIONS_LOOP_ENABLED` | `true` | Background detector loop. Set `false` on all but one instance if you ever run several workers |
| `NOTIFICATIONS_EVAL_INTERVAL_SECONDS` | `300` | Seconds between detector evaluation cycles |
| `TELEGRAM_SEND_ENABLED` | `true` | Global kill switch for Telegram delivery |
| `ASSISTANT_ENABLED` | `true` | Kill switch for the finance chat assistant |
| `ASSISTANT_MAX_TOOL_ITERATIONS` | `5` | Hard stop on the tool-call loop. Each iteration is a paid LLM round-trip |
| `ASSISTANT_HISTORY_MESSAGES` | `20` | Past turns replayed as context; older ones are dropped |
| `ASSISTANT_MAX_MESSAGE_CHARS` | `4000` | Longest user message accepted |
| `ASSISTANT_MAX_TOOL_RESULT_ROWS` | `100` | Rows any single query may feed back to the model |
| `ASSISTANT_MAX_CONVERSATIONS` | `100` | Threads kept per user |
| `ASSISTANT_RATE_LIMIT_MESSAGES` | `30` | Messages allowed per user inside the window |
| `ASSISTANT_RATE_LIMIT_WINDOW_SECONDS` | `3600` | Width of the assistant rate-limit window |
| `ASSISTANT_PROJECTION_RATES` | `2,5,8` | Annual real-return assumptions (%) for the projection tool, as conservative,base,optimistic |

> **AI extraction** requires all three `OPENAI_*` variables to be set. Leaving them unset disables extraction; you can still import statements and edit transactions manually.
>
> **The finance assistant** reuses those same `OPENAI_*` variables — there is no separate key. With them unset it reports itself disabled and the UI hides its launcher.
>
> **Investments / Indexa Capital** requires `FINLYTICS_ENCRYPTION_KEY`. Without it the app starts normally but connecting a provider returns HTTP 503.
>
> **Behind HTTPS**, set `AUTH_COOKIE_SECURE=true` and a fixed `AUTH_SECRET`. The session cookie is already `HttpOnly` + `SameSite=Lax`; without a fixed secret every restart logs everyone out. Also run uvicorn with `--proxy-headers` so the login throttle sees the real client IP instead of the proxy's.
>
> **Behind a reverse proxy**, make sure it does not buffer responses, or the assistant's answer arrives in one lump at the end instead of streaming. The app already sends `X-Accel-Buffering: no`, which nginx honours; other proxies may need `proxy_buffering off` or their equivalent.

---

## 📌 Project Status

Finlytics is a **personal project** with a single-owner focus — built for one specific workflow and not designed for multi-user deployments.

- Bank import tested against BBVA monthly PDF statements.
- AI extraction requires an OpenAI API key (or any OpenAI-compatible endpoint).
- Investment connectors: Indexa Capital (live API) and Fidelity ESPP (CSV import).

---

## 📄 License

[MIT](./LICENSE) — © 2026 DrDonoso.

All runtime dependencies are permissively licensed
(MIT / BSD-3-Clause / Apache-2.0); none are copyleft.

## 🔐 Security

Found a vulnerability? Please report it privately — see
[SECURITY.md](./SECURITY.md). That file also lists the deployment settings you
must get right (`AUTH_SECRET`, `FINLYTICS_ENCRYPTION_KEY`, TLS, network
exposure).

## ⚖️ Disclaimer

Finlytics is an independent, unofficial project. It is **not affiliated with,
endorsed by, or sponsored by** BBVA, Indexa Capital, Fidelity Investments,
Microsoft, Yahoo, or OpenAI. All product names, logos and brands are the
property of their respective owners and are used here for identification
purposes only.

The connectors read data you already have access to — your own accounts. Indexa
Capital is accessed with a read-only personal API token you provide; market
prices come from publicly reachable Yahoo Finance endpoints, whose terms of use
are your responsibility to observe. No affiliation or data-access agreement with
any of these providers is implied.

Nothing here is financial advice. The software is provided "as is", without
warranty of any kind, as stated in the [LICENSE](./LICENSE) — verify any figure
against your bank or broker before acting on it.
