## 2026-07-20T12:27:03Z: Finanzas/Extractos Rework — Orchestration Complete

**Status:** Three decision entries merged into decisions.md. Orchestration logs written. No summarization needed (Vision: 13.2 KB, Rocket: 11.4 KB, threshold: 15.4 KB).

**Scope:** Finanzas drill-down transactions table + active-filter chips + KPI deltas (equal-length preceding period). CategoryMovers + month-over-month comparison moved to Extractos. All frontend-only, committed to main (5b934c5 by DrDonoso). Production deploy succeeded.

**Process note:** Intermediate unauthorized commit (2440c60) observed and logged.

---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

---

## 2026-07-20T09:02:18+02:00: Transaction Detail / Edit Modal (mobile-only)

### Learnings

**`useIsMobile` hook** (`frontend/src/hooks/useIsMobile.ts`):
- Uses `window.matchMedia('(max-width: 600px)')` + `addEventListener('change', ...)` for live updates on resize.
- Returns a boolean that initialises synchronously on first render from `matchMedia(...).matches`.
- 600px matches the app's existing mobile breakpoint used throughout `index.css`.

**`TransactionDetailModal`** (`frontend/src/components/TransactionDetailModal.tsx`):
- Full-screen sheet (uses existing `.modal-backdrop` / `.modal` chassis; slides up from bottom on mobile via the pre-existing `@media (max-width:600px)` rule that sets `align-items: flex-end`).
- Stacked label/value field layout via `.tx-detail-field` rows. Read-only fields (date, account) at top; editable fields below.
- **Reuses inline-edit logic exactly**: same `EditData` shape, same `updateTransaction()` call, same `signedAmount` formula, same `CategorySelect` + `TagEditor` props pattern.
- `onSaved(updated)` callback received from `TransactionsTable` — parent maps the updated item into its `data.items` and calls `onEditSuccess?.()`, keeping a single source of truth.
- Escape key and backdrop click both close the modal.
- `tx.id` change in `useEffect` dep resets the form when the parent opens a new transaction.

**Mobile-only enforcement in `TransactionsTable`**:
- `useIsMobile()` hook drives a conditional: `onClick` on read-mode `<tr>` only fires `setDetailTx(tx)` when `isMobile` is true. On desktop nothing happens.
- Action buttons (`⚙+` and `✎`) call `e.stopPropagation()` so tapping them on mobile does NOT also open the detail modal.
- `tr.tr-mobile-tappable` CSS class applied only when `isMobile`; provides `cursor: pointer` + `:active` highlight at ≤600px.

---

## 2026-07-20T10:11:41+02:00: Euro decimals, Finanzas historic net, nav chevron split

### Learnings

**`fmtEur` decimals fix** (`InvestmentSnapshotCard.tsx` + `Dashboard.tsx`):
- Both files had a local euro formatter with `maximumFractionDigits: 0`. Fixed both to `minimumFractionDigits: 2, maximumFractionDigits: 2` so all euro amounts on Inicio (investment snapshot card values, accounts-table neto histórico column, Neto total KPI, average monthly expense) show cents consistently.
- `formatEur` exported from `client.ts` (line ~417) uses bare `Intl.NumberFormat` which defaults to 2 decimal places — no change needed there.

**Finanzas "neto histórico" KPI** (`FinancesOverviewPage.tsx`):
- Data source: `getByAccount()` with no params → all-time per-account summaries. Sum of `row.net` = all-time cumulative net (same computation as Dashboard.tsx `accountNetTotal`).
- Mounted once in `useEffect([], [])` — period filter changes do NOT re-fetch, keeping it period-independent.
- Displayed using `.finances-historic-net-kpi` inside `dashboard-header-actions`, with `margin-right: auto` to push the two action buttons to the right. Label reuses `t.dashboardAccountsNet` ('Neto histórico' / 'Historical net') — no new i18n keys needed.
- Colors via existing `inv-kpi-card__value--pos` / `inv-kpi-card__value--neg` classes.

**Nav chevron split** (`Layout.tsx`):
- Finanzas and Inversiones: single `<button>` replaced with `.sidebar-section-header` wrapper `<div>` containing two sibling buttons — valid HTML, no nested buttons.
- Main button (`.sidebar-section-btn`): navigates to `/finances` or `/investments` only. `flex: 1` via `.sidebar-section-header .sidebar-section-btn` selector.
- Arrow button (`.sidebar-section-arrow-btn`): toggles `financesExpanded` / `investmentsExpanded` only. Has its own `active` class for color parity when on the page.
- Ajustes section and settings sub-group toggles left unchanged (toggle-only, no navigation — was already correct).
- For Inversiones: arrow button renders only when `connectedPlugins.length > 0` (condition preserved).

---

## 2026-07-20T10:11:41+02:00: Inicio UI Polish — Euro decimals, all-time net, nav split

**Euro decimals:** Fixed InvestmentSnapshotCard.tsx and Dashboard.tsx local formatters to display 2 decimals (was 0). All Inicio amounts now consistent EUR formatting.

**Finanzas "Neto histórico":** Added all-time account net fetch (getByAccount() no params) in FinancesOverviewPage.tsx. Displayed in dashboard-header-actions with margin-right: auto spacing. Reuses existing i18n key.

**Nav chevron split:** Replaced single nav+toggle button in Finanzas/Inversiones headers with .sidebar-section-header wrapper + two sibling buttons (.sidebar-section-btn nav-only, .sidebar-section-arrow-btn toggle-only). Valid HTML, preserved active state.

**Validation:** 
pm run build passes.

**Merged to:** decisions.md (Vision — Inicio euro decimals, all-time net, nav chevron split).

---

## 2026-07-20T10:50:46+02:00: Finanzas Drill-Down Transactions Table + Active-Filter Chips

### Learnings

**Drill-down table wiring** (`FinancesOverviewPage.tsx`):
- Added `<TransactionsTable globalFilters={filters} categories={categories} allTags={allTags} merchant={filters.merchant} hideInternalFilters onEditSuccess={() => setRefreshKey(k => k + 1)} />` at the bottom of `<main className="dashboard">`, inside a `.charts-row-full` wrapper.
- `merchant={filters.merchant}` must be passed explicitly — `TransactionsTable.fetchData` uses the `merchant` PROP (not `globalFilters.merchant`) in its `getTransactions` call. Omitting it would cause merchant drill-downs to silently not filter the table.
- `onEditSuccess` bumps `refreshKey`, which re-fetches all KPIs/donuts/heatmap on the page (they depend on `[filters, refreshKey]`).
- `hideInternalFilters` suppresses the table's own category dropdown since the page donuts/heatmap drive the filtering.

**Three drill-down paths:**
1. **Category donut** → `filters.category_id`. Fixed `onCategoryClick` to TOGGLE (re-clicking the same category clears it): `(id) => setFilters(f => ({ ...f, category_id: f.category_id === id ? undefined : id }))`. Merchant already toggled the same way.
2. **Merchant donut** → `filters.merchant` (already toggled — unchanged).
3. **Heatmap** → calls `onSelectPeriod(date, date)` for a day or `onSelectPeriod(firstDay, lastDay)` for a month. This updates `filters.from/to` (NOT `filters.day`). `handleSelectPeriod` saves `preZoomFilters` and clears `day`. The table reflects the zoomed `from/to` automatically.

**`day` param addition to `TransactionsTable`**:
- Added `day?: string` to `TransactionsParams` (types.ts).
- TransactionsTable now passes `day: globalFilters.day || undefined` to `getTransactions`, and `globalFilters.day` to both the page-reset `useEffect` deps and `fetchData` callback deps.
- Currently `filters.day` is always `undefined` on the Finances page (heatmap always uses `from/to`), but the wiring is correct for future use.

**Active-filter chips row** (above the table):
- Rendered only when at least one drill-down is active: `filters.category_id || filters.merchant || filters.day || preZoomFilters`.
- Wrapped in `.charts-row-full` to match page layout.
- CSS: added `.drill-down-chips` (flex row, gap 6px) and `.drill-down-label` (muted 12px label) to `index.css`. "Limpiar todo" button reuses existing `.btn-clear-filters` class.
- Category chip: looks up category name from the `categories` array via `categoryLabel()`, using a local `dynamicEs` memo.
- Heatmap zoom chip: shows `Día: 15 ene` when `from === to`, or `1 ene – 31 ene` date range otherwise. ✕ calls `handleResetPeriod`.
- `filters.day` chip (future-proofed): shown only when `preZoomFilters` is absent.
- `handleClearDrillDowns`: clears `category_id`, `merchant`, `day`; if `preZoomFilters` exists, restores original `from/to` from it (not the full old state) and clears `preZoomFilters`.

**i18n additions:**
- `drillDownActiveFilters`: "Filtros activos" / "Active filters"
- `drillDownClearAll`: "Limpiar todo" / "Clear all"
- Reused existing keys: `tableColCategory`, `colMerchant`, `filterChipDay`, `filterClearChip`, `filterChipMerchant`.

**Validation:** `npm run build` passes (tsc --noEmit + vite build, zero TS errors, pre-existing chunk warning only).

---

## 2026-07-20T11:34:19+02:00: CategoryMovers → Extractos + Finanzas KPI comparison fix

### Learnings

**CategoryMovers moved to Extractos (`StatementsPage.tsx`)**:
- Removed from `FinancesOverviewPage.tsx` entirely (import + render block + `prevByCategory` state + its `getByCategory` fetch).
- Added to `StatementsPage.tsx` with proper month-over-month comparison: `getByCategory` for selected month (`from`/`to`) AND for `previousCalendarMonth(from)`. Both fetches pass `account_id: selAccountId` so the movers respect the active account filter.
- State: `selByCat`, `prevByCat`, `selByCatLoading`, `prevByCatLoading`, `byCatError` — all independent from the overview state, re-fetched on the same deps as overview (`from`, `to`, `currentMonthHasData`, `refreshKey`, `overviewRefKey`, `selAccountId`).
- Rendered between the month summary header and the `TransactionsTable`, wrapped in `.charts-row-full.stmts-movers-wrap`.
- `t.moversTitle` ("Mayores cambios · vs mes anterior") is now literally correct in Extractos because the comparison IS the previous calendar month.

**`previousEqualRange` helper (`frontend/src/utils/comparison.ts`)**:
- New export: `previousEqualRange(from: string, to: string): { from: string; to: string } | null`.
- Computes preceding period of equal length: `diffDays = (to - from) + 1`; `prevTo = from − 1 day`; `prevFrom = prevTo − (diffDays − 1) days`.
- Parses dates as local Date objects (year/month/day constructor — avoids UTC midnight offset issues).
- Returns `null` when `diffDays <= 0` or input is invalid.
- Used in `FinancesOverviewPage.tsx` to correctly compare the KPI deltas against a preceding equal-length period (e.g., a 6-month range compared to the 6 months before it, not just December).

**Finanzas KPI comparison fix + label**:
- `FinancesOverviewPage.tsx` now calls `previousEqualRange(filters.from, filters.to)` instead of `previousCalendarMonth(filters.from)` for the `prevOverview` fetch that feeds `KpiCards`.
- The `prevByCategory` state + fetch was removed entirely (CategoryMovers is no longer in Finanzas).
- Added `<div className="kpi-prev-period-bar">{t.kpisPrevPeriodLabel}</div>` as the last child of `.dashboard-header` (full-width bottom bar via `flex: 0 0 100%` CSS, with a top border and right-aligned muted 11px text).
- New i18n key `kpisPrevPeriodLabel`: "vs. periodo anterior" (ES) / "vs. previous period" (EN) — added to all three i18n files (`index.ts` Dict interface, `es.ts`, `en.ts`).

**CSS additions (`frontend/src/index.css`)**:
- `.kpi-prev-period-bar`: `flex: 0 0 100%; font-size: 11px; color: var(--text-muted); text-align: right; padding: 5px 20px 7px; border-top: 1px solid var(--border)`.
- `.stmts-movers-wrap`: `margin-top: 4px` (minimal spacing above CategoryMovers in Extractos).

**Validation:** `npm run build` passes (tsc --noEmit + vite build, zero TS errors, pre-existing chunk warning + pre-existing CSS orphan warning only).

---

## 2026-07-20T12:06:38+02:00: Finanzas variation removed; Extractos KPI month-over-month deltas added

### Learnings

**Finanzas KPI variation removed (`FinancesOverviewPage.tsx`)**:
- Removed `previousOverview` prop from `<KpiCards>` — deltas/arrows no longer render in Finanzas.
- Removed `prevOverview` state and its `getOverview` fetch (the `previousEqualRange` block).
- Removed `previousEqualRange` import from the page.
- Removed `<div className="kpi-prev-period-bar">` and its `kpisPrevPeriodLabel` i18n key from all 3 i18n files and the `Dict` interface.
- Removed the `.kpi-prev-period-bar` CSS rule from `index.css`.
- Removed `previousEqualRange` export from `comparison.ts` entirely (no other consumers).

**Extractos KPI month-over-month deltas (`StatementsPage.tsx`)**:
- Added `prevOverview: Overview | null` state; fetched in the same `useEffect` as `overview` via `previousCalendarMonth(from)` + `getOverview(prevRange, ...)`.
- Added local `TxDeltaBadge` component (module-level, uses same `header-kpi-delta*` CSS classes as KpiCards DeltaBadge).
- Rendered `<TxDeltaBadge>` inside each `.tx-total` card (below the value span):
  - **Transacciones** → `neutral` (no good/bad coloring).
  - **Ingresos totales** → ↑ = good (default, no invert).
  - **Gastos totales** → ↑ = bad (`invert` prop).
  - **Neto** → ↑ = good (default).
- Graceful degradation: `computeDelta` returns `null` when `prevOverview` is null → badge renders nothing.
- No new CSS or i18n keys needed (reused existing delta classes and comparison helpers).
---

*2026-07-21T08:31:35Z:* Fury proposal on old account onboarding awaits owner validation — may require UX for 'create account with initial balance' flow (\decisions.md\ PROPOSAL section).

