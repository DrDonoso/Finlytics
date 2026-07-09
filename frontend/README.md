# Finlytics — Frontend

Personal expense dashboard. Stack: **Vite + React + TypeScript + Recharts**.

## Development

```bash
npm install
npm run dev        # http://localhost:5173
```

Requires the backend (FastAPI) to be running at `http://localhost:7777`.

### Mock mode (no backend)

```bash
VITE_USE_MOCK=1 npm run dev
```

With `VITE_USE_MOCK=1` the dashboard loads demo data (BBVA + Indexa Capital, May–June 2026) without calling the API.

## Production build

```bash
npm run build      # output: frontend/dist/
npm run preview    # serves the build locally at :4173
```

In production, FastAPI serves `frontend/dist/` as a static SPA (`/` → `index.html`, `/api/*` → API).

## Structure

```
src/
├── api/
│   ├── types.ts              # TypeScript interfaces for all API contracts
│   ├── client.ts             # Typed fetch client; falls back to mock on error or VITE_USE_MOCK=1
│   └── mock.ts               # Realistic demo data (BBVA + Indexa, May–June 2026)
├── components/
│   ├── Layout.tsx            # Main app shell (nav, sidebar)
│   ├── SettingsLayout.tsx    # Shared layout for settings sub-pages
│   ├── GlobalFilterBar.tsx   # Global filters: date range, account, category, tags, amount
│   ├── KpiCards.tsx          # KPI summary cards (in, out, net, top category)
│   ├── SpendingByCategory.tsx # Donut chart by category (Recharts)
│   ├── SpendingOverTime.tsx  # Monthly bar chart: spending vs income (Recharts)
│   ├── SpendingByAccount.tsx # Bar chart by account (Recharts)
│   ├── CashflowSankey.tsx    # Cashflow Sankey diagram (Recharts)
│   ├── TransactionsTable.tsx # Paginated, sortable transaction table
│   ├── ImportModal.tsx       # PDF import flow (upload → preview → confirm)
│   ├── RuleFormModal.tsx     # Create/edit rule modal
│   ├── CategorySelect.tsx    # Category picker dropdown
│   ├── TagEditor.tsx         # Inline tag editor
│   ├── TagFilterSelect.tsx   # Multi-tag filter selector
│   ├── TagTypeahead.tsx      # Tag typeahead input
│   ├── ColorSwatchPicker.tsx # Color swatch picker for categories/tags
│   └── DateInput.tsx         # Controlled date input
├── contexts/
│   ├── AuthContext.tsx       # Authentication state
│   └── ThemeContext.tsx      # Light/dark/system theme
├── i18n/
│   ├── en.ts                 # English strings
│   ├── es.ts                 # Spanish strings
│   └── index.ts              # i18n helper
└── pages/
    ├── LoginPage.tsx         # Login screen
    ├── SetupPage.tsx         # Initial user setup
    ├── Dashboard.tsx         # Main dashboard (charts + KPIs)
    ├── TransactionsPage.tsx  # Full transaction list with filters
    ├── RulesPage.tsx         # Rules management
    ├── CategoriesPage.tsx    # Categories & tags management
    ├── SettingsPage.tsx      # Settings index
    ├── AppearancePage.tsx    # Theme & language preferences
    └── BackupPage.tsx        # Export/import backup
```

## Environment variables

| Variable | Values | Description |
|----------|--------|-------------|
| `VITE_USE_MOCK` | `1` / *(empty)* | Forces mock data without calling the backend |
