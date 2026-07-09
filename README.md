# Finlytics 💰

**Self-hosted personal finance tracker — upload your bank statement, let AI categorize it, explore the dashboard.**

---

## Why Finlytics?

Every open-source personal finance tool I evaluated was either too complex, required manual entry, depended on a bank integration I don't have, or just didn't fit how I actually work. What I wanted was simple:

1. Download the monthly PDF my bank already generates.
2. Drop it in → AI parses the PDF and categorizes every transaction automatically.
3. See where my money went.

None of the available solutions fit that workflow. **Finlytics was built to be exactly that — simple, self-hosted, and tailored to a single owner's real workflow.**

---

## What It Does

### 📥 Import

- Upload a monthly bank-statement **PDF** (built and tested against BBVA; the parser is designed to extend to XLSX/CSV).
- **AI-powered extraction** via the OpenAI API or any OpenAI-compatible endpoint — structured output extracts date, amount, currency, description, merchant, category, and tags per transaction.
- **Bold-title / non-bold-detail parsing**: separates the transaction concept (e.g. *"Adeudo a su cargo"*) from its specific detail (e.g. *"Octopus Energy"* vs a community fee) so look-alike charges can be told apart.
- **Import preview**: review and edit every extracted transaction before committing to the database.
- **Idempotent import** — content-hash de-duplication means re-importing the same month never double-counts.

### ⚙️ Rules Engine

- Define rules to match transactions by title, detail, amount range, account, or currency.
- Actions: set category, set merchant, add tags, or **skip AI entirely** for known recurring charges.
- Rules run automatically on every import (before and after AI extraction).

### 📊 Dashboard

- Spending by **category**, over **time**, by **account**, and a **cashflow Sankey** diagram.
- KPI summary cards (total in/out, net balance).
- Filters: date range, account, category, tags, amount range, income/expense toggle.
- Sortable, searchable transaction table.

### 🗂️ Management

- **Categories & tags** with color swatches (name-derived colors or a custom picker).
- **Full backup** — export the entire dataset to JSON and re-import it.
- Bilingual UI: **Spanish / English**.
- **Light / dark / system** theme.
- Single-user authentication with session tokens.

---

## How It Works

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
  Interactive dashboard
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 · FastAPI · SQLAlchemy 2 (async) · Alembic · Pydantic · uvicorn |
| Database | PostgreSQL 16 |
| PDF parsing | pdfplumber |
| AI extraction | OpenAI SDK — structured outputs via any OpenAI-compatible endpoint |
| Frontend | React 18 · TypeScript · Vite · Recharts |
| Container | Multi-stage Docker (Node 20 builds the React SPA → Python 3.12-slim runtime serves both API and SPA) |
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

# Optional — set all three to enable AI-powered extraction
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=your-model-name
```

### 2. Run

**Using the published Docker Hub image (recommended):**

```bash
docker compose up -d
```

**Or build from source:**

```bash
docker compose -f docker-compose.local.yml up -d --build
```

### 3. Open

Navigate to **http://localhost:7777** and create the initial user account.

> The port can be changed by setting `FINLYTICS_PORT` in `.env` (default: `7777`).

---

## ⚙️ Configuration Reference

All configuration lives in `.env` (copy from `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password |
| `POSTGRES_USER` | `finlytics` | PostgreSQL username |
| `POSTGRES_DB` | `finlytics` | PostgreSQL database name |
| `OPENAI_API_KEY` | *(unset)* | API key for the OpenAI-compatible endpoint |
| `OPENAI_BASE_URL` | *(unset)* | Base URL of the endpoint (e.g. `https://host/v1`) |
| `OPENAI_MODEL` | *(unset)* | Model name to use for extraction |
| `FINLYTICS_PORT` | `7777` | Host port the app is exposed on |
| `TIMEZONE` | `Europe/Madrid` | Timezone used for date display |
| `AUTH_SECRET` | *(random)* | Secret for signing session tokens. If unset, a new key is generated on each startup — sessions won't survive container restarts. Generate a stable value with: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

> **AI extraction** requires all three `OPENAI_*` variables to be set. Leaving them unset disables extraction; you can still import statements and edit transactions manually.

---

## 📌 Project Status

Finlytics is a **personal project** with a single-owner focus — built for one specific workflow and not designed for multi-user deployments.

- Tested against BBVA monthly PDF statements.
- AI extraction requires an OpenAI API key (or any OpenAI-compatible endpoint).
- No license file — shared publicly as-is.
