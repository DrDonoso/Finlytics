# Finlytics — Frontend

Personal finance + investments dashboard. Stack: **Vite + React + TypeScript + Recharts**.

> For the full app documentation see the [root README](../README.md).

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
│   └── mock.ts               # Realistic demo data (BBVA + Indexa + Fidelity, May–June 2026)
├── components/
│   ├── Layout.tsx            # Main app shell (nav, sidebar — Inicio/Finanzas/Inversiones/Ajustes)
│   ├── SettingsLayout.tsx    # Shared layout for settings sub-pages
│   ├── GlobalFilterBar.tsx   # Global filters: date range, account, category, tags, amount
│   ├── KpiCards.tsx          # KPI summary cards (in, out, net, top category)
│   ├── SpendingByCategory.tsx # Donut chart by category (Recharts)
│   ├── SpendingOverTime.tsx  # Monthly bar chart: spending vs income (Recharts)
│   ├── SpendingByAccount.tsx # Bar chart by account (Recharts)
│   ├── SpendingHeatmap.tsx   # Adaptive heatmap: 3 modes (GitHub-calendar / compact / monthly-grid)
│   ├── CategoryMovers.tsx    # Categories with highest rise/fall vs previous period
│   ├── CashflowSankey.tsx    # Cashflow Sankey diagram (Recharts)
│   ├── TransactionsTable.tsx # Paginated, sortable transaction table
│   ├── ImportModal.tsx       # PDF import flow (upload → preview → confirm)
│   ├── ImportLauncher.tsx    # Trigger button/handle for ImportModal
│   ├── ImportSourcePicker.tsx # Data-driven import source list (bank PDF + connectors with import_route)
│   ├── InvestmentSnapshotCard.tsx # Investments summary card shown on Inicio
│   ├── TopMerchants.tsx      # Top merchants bar chart
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
│   └── index.ts              # i18n helper + Dict interface
├── investments/
│   ├── registry.ts           # Plugin view registry: plugin_id → { icon, name, component }
│   ├── PluginViewWrapper.tsx # Route wrapper that lazy-loads the plugin view
│   └── views/
│       ├── IndexaView.tsx    # Indexa Capital: portfolio KPIs, holdings, evolution, allocation
│       └── FidelityView.tsx  # Fidelity ESPP: KPIs, evolution, lots table, import wizard, reminder
├── pages/
│   ├── LoginPage.tsx         # Login screen
│   ├── SetupPage.tsx         # Initial user setup
│   ├── Dashboard.tsx         # Inicio (Home): month KPIs + investments snapshot + import picker
│   ├── FinancesOverviewPage.tsx # Finanzas: filters + KPIs + spending charts + heatmap
│   ├── TransactionsPage.tsx  # Full transaction list with filters
│   ├── AnalyticsPage.tsx     # Tendencias: spending over time, by account, Sankey
│   ├── StatementsPage.tsx    # Extractos: statement import history
│   ├── InvestmentsLandingPage.tsx # /investments: combined overview (KPIs + donuts + provider cards)
│   ├── RulesPage.tsx         # Rules management
│   ├── CategoriesPage.tsx    # Categories management
│   ├── AccountsPage.tsx      # Accounts management
│   ├── SettingsPage.tsx      # Tags management (settings index redirects here)
│   ├── ConnectorsPage.tsx    # Investment connectors (connect/disconnect Indexa; Fidelity status)
│   ├── AppearancePage.tsx    # Theme & language preferences
│   ├── BackupPage.tsx        # Export/import backup
│   └── AboutPage.tsx         # App version (CalVer), build date, repo/issues/changelog, MIT license
└── utils/
    ├── utils.ts              # Date range helpers (defaultRange, currentMonthRange)
    └── comparison.ts         # previousCalendarMonth helper
```

## Environment variables

| Variable | Values | Description |
|----------|--------|-------------|
| `VITE_USE_MOCK` | `1` / *(empty)* | Forces mock data without calling the backend |
