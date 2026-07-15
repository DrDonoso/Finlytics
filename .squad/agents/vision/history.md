# Vision — Frontend Engineer

**Owner:** DrDonoso  
**Role:** Interactive React components, charting, state management, import UX, responsive design
**Created:** 2026-07-03

## Current Status (2026-07-13)

### Download original PDF feature (vision-35)
- **Status:** Shipped 2026-07-13
- **Scope:** Re-added "Download original" button (previously built, reverted, then re-implemented)
- **Components:** StatementsPage month-header button (single→direct, multiple→dropdown), ImportModal base64 capture, fetch+blob download pattern
- **Integration:** Works with Rocket's bind-mount storage and Shuri's GET /api/statements/originals + GET /api/statements/original/{id} endpoints
- **Tests:** Build clean; 0 TS errors, 0 CSS warnings
- **Caveat:** Only new imports have downloadable originals (pre-existing imports have no stored PDF)

### Investments skeleton (vision-36)
- **Status:** Shipped 2026-07-14
- **Scope:** Phase 1 investments section — types, API client, i18n, page, route, nav
- **Files changed:**
  - `frontend/src/api/types.ts` — added `InvestmentPlugin` interface (status/auth_type union types per Shuri's spec)
  - `frontend/src/api/client.ts` — added `getInvestmentPlugins(): Promise<InvestmentPlugin[]>` (authenticated GET, mock-aware)
  - `frontend/src/api/mock.ts` — added `mockGetInvestmentPlugins()` returning the 3 coming-soon plugins
  - `frontend/src/i18n/index.ts` — added 10 keys to `Dict` interface
  - `frontend/src/i18n/en.ts` — added 10 EN translations
  - `frontend/src/i18n/es.ts` — added 10 ES translations
  - `frontend/src/pages/InvestmentsPage.tsx` — new page (Wanda's exact JSX tree; loading/error/success states; "—" KPI placeholders; disabled Connect buttons)
  - `frontend/src/App.tsx` — added `<Route path="investments" element={<InvestmentsPage />} />` as child of Layout route
  - `frontend/src/components/Layout.tsx` — added 💰 NavLink to /investments between Analytics and Statements
- **[2026-07-15 HEADS-UP: FIDELITY ESPP WIZARD]** Feasibility probe complete. Phase 1 scope: upload PDF → extract holdings → review → confirm. Wanda owns UX/CSS for upload wizard. UI components needed: file picker (drag-drop or input), extracted holdings review table (date, shares, price, cost), confirm/cancel buttons, loading/success states. Vision will build React components consuming Banner's `ESPPHoldingSnapshot` schema and Shuri's endpoints. Decision memo in `.squad/decisions.md` §2026-07-15T06:51:14Z. Effort: ~3–4 days for full Phase 1 (backend + frontend + tests).
- **Integration:** Consumes `GET /api/investments/plugins` (Shuri's stub); CSS classes are Wanda's (already in index.css)
- **Tests:** `npm run build` → 0 TS errors, 0 warnings (chunk-size warning is pre-existing)


## Learnings

### 2026-07-14 — Investments page polish: ResponsiveContainer fix, metrics strip, instrument donut, retenciones/locale (vision-42)

Four targeted fixes and additions on `InvestmentsPage.tsx`.

---

**CHANGE 1 — ResponsiveContainer numeric height (critical bug fix)**
- **Root cause:** `<ResponsiveContainer width="100%" height="100%">` inside a flex item (`.inv-evolution-chart-wrap`, `.cat-donut-wrap`) resolves against an indefinite parent height → collapses to 0 px → blank chart. This is a known Recharts/CSS flex gotcha.
- **Fix:** Always use a **numeric** `height` prop (e.g. `height={360}` for the evolution line chart, `height={220}` for donuts). Never use `height="100%"` inside a flex or auto-height wrapper.
- **Pattern confirmed by:** `SpendingOverTime.tsx:57` already used `height={300}`. All investments charts now use numeric heights.

**CHANGE 2 — Compact summary + metrics strip + second donut**
- Added `INSTRUMENT_PALETTE` (12-color const array, `as const`) at module level in `InvestmentsPage.tsx`.
- Added `instrumentSlices` useMemo: filters `portfolio.holdings` by `current_value > 0`, maps to `{name, value}` using `h.name`, sorts largest-first.
- Metrics strip (`.inv-metrics-strip`): 3 cells — TWR (`returns.twr_annual`), MWR (`returns.xirr`), Volatilidad (`returns.volatility`). All values are decimals × 100 formatted with `Intl.NumberFormat(locale, {minimumFractionDigits:1,maximumFractionDigits:1})` for locale-correct comma decimals (es-ES). TWR/MWR colored pos/neg; volatility neutral.
- Two-donut layout (`.inv-donuts-row`): replaced single `.inv-chart-card--allocation` with a grid of two `.card` divs. Donut 1 = asset class (existing logic, numeric height). Donut 2 = per-instrument with `INSTRUMENT_PALETTE`, compact legend (`.inv-donut-compact-legend`) showing name + %-of-total.
- 7 new i18n keys added to `Dict` interface + ES + EN: `invMetricTwr`, `invMetricMwr`, `invMetricVolatility`, `invMetricSubAnnual`, `invMetricSubXirr`, `invDonutAssetTitle`, `invDonutInstrumentTitle`.

**CHANGE 3 — Retenciones sign + locale % formatting**
- **Retenciones:** backend may deliver `+0.01` or `-0.01`; display is always negative (tax withholding). Fix: `formatCurrency(-Math.abs(portfolio.returns.retenciones))`. CSS class is always `inv-summary-value--neg` (no conditional needed).
- **Locale %:** `(v * 100).toFixed(1)` always produces a dot regardless of locale. Replaced all new % outputs with `new Intl.NumberFormat(locale, {minimumFractionDigits:1, maximumFractionDigits:1}).format(v * 100)`. For signed values: prepend `v >= 0 ? '+' : ''` and let the Intl formatter emit the minus for negative values (no `Math.abs` needed — Intl includes the `−` sign automatically).
- Applied to: Rentabilidad % in summary row (`money_return`), all 3 metrics strip values, instrument donut legend %.

**CHANGE 4 — types.ts / mock.ts verification**
- `InvestmentReturns` already had `twr_annual`, `xirr`, `volatility`, `sharpe_ratio`, `money_return_annual` as optional nullable fields from prior sessions. No new type additions needed.
- `mockGetInvestmentPortfolio()` already had realistic values for all these fields from vision-41. No mock changes needed.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Investments page Indexa redesign (vision-41)

Full rebuild of InvestmentsPage into 3 blocks (Wanda's layout contract + Shuri's extended backend fields).

---

**Block 1 — "Valor total" summary card (`inv-summary-card` in `inv-top-row`)**
- Replaces old 5-KPI `kpi-grid`. 4 rows: Valor total (big), Rentabilidad (€+%), Aportaciones, Retenciones.
- Field mapping: `returns.pl` (rentabilidad €), `returns.money_return` (rentabilidad % decimal), `returns.aportaciones` (gross inflows), `returns.retenciones` (already negative — display with `formatCurrency`, class `--neg` when `< 0`).
- `inv-top-row` is a `1fr 1fr` grid (Wanda CSS). Allocation donut moves inside it (JSX unchanged).

**Block 2 — "Evolución de la cuenta" LineChart (`inv-evolution-card`)**
- Replaced `AreaChart+Area` with `LineChart+Line`. Two lines: "Tu cartera" (`value_series`) solid primary, "Aportaciones" (`contributions_series`) dashed step-after muted.
- **Merge strategy**: `contribMap = new Map(contributions_series.map(pt => [pt.date, pt.value]))`. For each `value_series` point, look up `contribMap.get(pt.date) ?? null`. `connectNulls` on the contributions line handles gaps — sparse contributions_series naturally produces a step chart.
- **Period filter** (`evPeriod` state, default `'Todo'`): `'1M'/'3M'/'6M'/'1A'` → `cutoff` date; 4-char string (year) → `pt.date.startsWith(year)`; `'Todo'` → all.
- **€/% toggle** (`evMode`): `'eur'` = raw values; `'pct'` = `(value/base − 1) × 100` normalized from period start (both lines). `baseC = contribMap.get(firstPoint.date) ?? 1` prevents division by zero.
- `evolutionYears` useMemo: slices `value_series[0].date.slice(0,4)` to get first year; counts up to `new Date().getFullYear()`.
- Dates are now YYYY-MM-DD (Shuri's bug fix) — use `new Date(pt.date)` directly, not `parseYYYYMMDD`.

**Block 3 — "Tabla de rentabilidades" matrix (`returns-matrix-card`)**
- Replaces old `inv-returns-card` simple list.
- Uses Shuri's `MonthlyReturnRow` shape (one object per year, `months_pct`/`months_eur` as partial string-keyed dicts `{ '8': 0.034, ... }`). Backend may omit keys for months with no data; type is `Record<string, number | null | undefined>` to allow sparse dicts.
- Access pattern: `row.months_pct[String(i+1)] ?? null` — `?? null` converts absent keys (undefined) to null for `cellCls` logic.
- `total_pct`/`total_eur`/`benchmark_pct` are pre-computed by backend — no client-side aggregation needed.
- `cellCls(v, extra)` → `returns-matrix-cell--pos/neg/empty` + optional extra (e.g. `returns-matrix-cell--total`).
- **Drawdown note**: `portfolio.drawdown` → `inv-drawdown-note` paragraph with `t.invDrawdownNote(pct, eur, start, end)`. `max_drawdown` and `max_drawdown_eur` are already negative; use `Math.abs()` + template.
- **€/% toggle** (`matrixMode` state) shared UI classes `inv-toggle`/`inv-toggle-btn`/`--active` (same as evolution chart).

**Field name reconciliation (Wanda vs Shuri):**
- Wanda's JSX used `returns.inflows`/`returns.tax_outflows`; Shuri's API uses `returns.aportaciones`/`returns.retenciones`. Used Shuri's names throughout.
- `retenciones` is already negative from Indexa API (e.g. −0.01). Wanda's comment said "positive displayed as negative" — actual value is pre-negated.
- `portfolio.contributions_series` (Shuri) vs Wanda's `net_amounts_series` — used Shuri's name.

**i18n — 30 new keys across 3 blocks:**
| Block | Keys |
|---|---|
| Block 1 | `invSummaryValorTotal`, `invSummaryRentabilidad`, `invSummaryAportaciones`, `invSummaryRetenciones` |
| Block 2 | `invEvolutionTitle`, `invPeriod1M/3M/6M/1A`, `invPeriodTodo`, `invToggleEur`, `invTogglePct`, `invLegendPortfolio`, `invLegendContributions` |
| Block 3 | `invMatrixTitle`, `invMonth{ENE…DIC}` (12), `invMatrixTotal`, `invMatrixBenchmark`, `invDrawdownNote(pct,eur,start,end)` |

**types.ts new/extended:**
- `InvestmentReturns`: added `aportaciones`, `retenciones`, `rentabilidad_eur`, `rentabilidad_pct`, `sharpe_ratio`, `money_return_annual` (all `number | null | undefined` optional)
- New `MonthlyReturnRow` interface: `year`, `months_pct`, `months_eur` (sparse dicts), `total_pct`, `total_eur`, `benchmark_pct`
- New `DrawdownOut` interface: `max_drawdown`, `max_drawdown_eur`, `start_date`, `end_date`
- `InvestmentPortfolio` extended with: `contributions_series: ValuePoint[]`, `monthly_returns: MonthlyReturnRow[] | null`, `drawdown: DrawdownOut | null`
- `ValuePoint.date` comment updated: YYYY-MM-DD (was YYYYMMDD — Shuri's date-format bug fix)

**mock.ts extended:**
- `value_series` dates fixed from YYYYMMDD to YYYY-MM-DD format
- `money_return` corrected from `1345.67` (was wrong EUR amount) to `0.1222` (proper decimal rate)
- All new returns fields added with realistic values
- `contributions_series` (5 quarterly step points over 2023–2024)
- `monthly_returns` (2 years: 2023 all 12 months, 2024 partial Jan–Mar)
- `drawdown` (mock Aug 2023 drawdown −9.12%)
- Disconnected state gets `contributions_series: [], monthly_returns: null, drawdown: null`

**Removal checklist (per Wanda):** `kpi-grid` + 5 `kpi-card`s ✓, `inv-charts-row` wrapper ✓, `inv-chart-card--value` AreaChart ✓, `inv-returns-card` simple list ✓. Kept: allocation donut (moved into `inv-top-row`), `inv-holdings-card`.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Returns table + extended InvestmentReturns (vision-40)

Built the "Tabla de Rentabilidades" returns card and wired Shuri's 6 new backend fields.

**Extended `InvestmentReturns` (types.ts):** Added 6 optional fields — `twr_total`, `twr_last_week`, `twr_last_month`, `twr_last_year`, `money_return`, `volatility` — all `number | null | undefined`. Existing `twr_annual`, `xirr`, `pl`, `invested` are non-optional (backward-compatible).

**Returns table (InvestmentsPage.tsx):**
- Placed between `inv-charts-row` and `inv-holdings-card` (renumbered 5→6).
- Rendered only when `portfolio.returns` is non-null using an IIFE `(() => { ... })()` pattern to scope `fmt`/`pctCls` helpers inline.
- `fmt(v)`: decimal → `"+1.23%"` / `"1.23%"` / `"—"` for null. `pctCls(v)`: returns `"returns-value--pos"` / `"returns-value--neg"` / `""`.
- Volatility always uses `returns-value--neutral` (risk metric, not directional).
- 7 rows: Última semana, Último mes, Último año, Acumulada (twr_total), Anualizada (twr_annual), TIR/XIRR, Volatilidad.

**i18n:** 8 new keys added to `Dict` interface + both ES and EN dicts:
| Key | ES | EN |
|-----|----|----|
| `invReturnsTitle` | Rentabilidades | Returns |
| `invReturnsWeek` | Última semana | Last week |
| `invReturnsMonth` | Último mes | Last month |
| `invReturnsYear` | Último año | Last year |
| `invReturnsTotal` | Rentabilidad acumulada | Total return (TWR) |
| `invReturnsAnnual` | Rentabilidad anualizada | Annualised return |
| `invReturnsXirr` | TIR / XIRR | IRR / XIRR |
| `invReturnsVolatility` | Volatilidad | Volatility |

**mock.ts:** Mock `returns` extended with realistic sample values: `twr_total: 0.1223`, `twr_last_week: 0.0042`, `twr_last_month: 0.0187`, `twr_last_year: 0.0831`, `money_return: 1345.67`, `volatility: 0.0614`.

**CSS:** All classes (`inv-returns-card`, `returns-table`, `returns-row`, `returns-label`, `returns-value`, `--pos`/`--neg`/`--neutral`) were already defined by Wanda in `index.css` — no CSS changes needed.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

**Verified (Shuri's fixes):** `total_value` KPI, donut center, and holdings `%weight` all reference `portfolio.total_value` which Shuri now populates correctly via the `portfolios[-1].total_amount` fallback chain. Holdings are one row per ISIN (deduped by backend). No frontend changes needed for those fixes.

---

### 2026-07-14 — Cartera / Holdings visualization plan (vision-37)

Designed (no code yet) the Phase 2 Holdings visualization for `InvestmentsPage`. Key decisions:

- **4 KPI cards:** Total value, Total invested, P&L (€ + % two-line), Plugins connected — all from `InvestmentPortfolioSummary`.
- **HoldingsAllocation donut:** group holdings by `asset_class`, 6 fixed semantic colors, reuse `SpendingByCategory` Recharts pattern (donut + side table with % weight). Click to select/dim.
- **HoldingsTable:** sortable by name/value/P&L%, per-holding P&L colored `--income`/`--expense`, native currency per row (not forced EUR), plugin source badge in Phase 2.
- **Multi-currency:** display native currency per holding via `Intl.NumberFormat(lang, { currency: holding.currency })`; KPI totals use portfolio currency (EUR). Phase 2: recommend `current_value_eur` on `InvestmentHoldingOut` for FX equivalents.
- **States:** empty (current), loading (skeletons + state-box spinner), data, error, connected-but-empty-holdings — each mapped to existing patterns.
- **Phase 1 vs Phase 2:** Phase 1 is fully placeholder ("—" KPIs, empty state). Phase 2 adds `GET /api/investments/portfolio`, `HoldingsAllocation.tsx`, `HoldingsTable.tsx`, real auth flow.
- Full plan written to `.squad/decisions/inbox/vision-cartera-viz-plan.md`.

---

### 2026-07-14 — Connectors → Settings move (vision-38)

Approved by owner (Wanda's IA recommendation). Plugin catalog moved from InvestmentsPage to a new `settings/connectors` sub-page.

**New file:**
- `frontend/src/pages/ConnectorsPage.tsx` — settings-style page (`card settings-card`, `settings-section-title`) wrapping the same plugin catalog markup (`plugin-catalog`, `plugin-card`, `coming-soon-badge`) fetched from `getInvestmentPlugins()`. Loading/error states use `.state-box` / `.state-box.error`. Reuses all existing CSS classes — no new CSS added.

**Modified files:**
- `frontend/src/pages/InvestmentsPage.tsx` — removed plugin-catalog card entirely; removed `getInvestmentPlugins`, `InvestmentPlugin`, `useState`, `useEffect` imports. Added `NavLink` import. Holdings empty state now includes a `<NavLink to="/settings/connectors" className="btn-primary">` CTA using `t.investmentsManageConnectors`.
- `frontend/src/App.tsx` — added `ConnectorsPage` import + `<Route path="connectors" element={<ConnectorsPage />} />` inside the existing settings `<Route path="settings">` block.
- `frontend/src/components/Layout.tsx` — added `<NavLink to="/settings/connectors">` with `{t.settingsSubConnectors}` inside the Ajustes accordion, after the Backup link, matching the existing sub-link markup pattern.
- `frontend/src/i18n/index.ts` — added `settingsSubConnectors: string` and `investmentsManageConnectors: string` to Dict interface.
- `frontend/src/i18n/es.ts` — added `settingsSubConnectors: 'Conectores'` and `investmentsManageConnectors: 'Gestionar conectores →'`.
- `frontend/src/i18n/en.ts` — added `settingsSubConnectors: 'Connectors'` and `investmentsManageConnectors: 'Manage connectors →'`.

**i18n reuse:** `investmentsCatalogTitle`, `investmentsComingSoon`, `investmentsConnect` (already existed) serve ConnectorsPage directly. Only 2 new keys needed.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Indexa Phase 2: wizard + real-data investments viz (vision-39)

Full frontend for Phase 2: Indexa Capital wizard, connection management, and populated InvestmentsPage.

**New files:**
- `frontend/src/components/IndexaWizard.tsx` — 4-step modal wizard (`.modal.inv-wizard`). Steps: intro → paste token → validate/accounts → success. Two-step contract: `POST /validate` then `POST /connections`. Progress dots computed from step enum (`1 | 2 | '3-loading' | '3-error' | '3-accounts' | 4`). Error state shows inline banner + token retry (dot back to 2). Accounts all pre-selected; sends raw `account_number`s on connect. Uses `useNavigate` to jump to `/investments` on "Ver inversiones".

**Modified files:**
- `frontend/src/api/types.ts` — added `InvestmentReturns`, `ValuePoint`, `CashInvestedSplit`, `InvestmentHolding`, `InvestmentPortfolio`, `InvestmentConnection`, `ValidatedAccount`, `ValidateAccountsResponse`.
- `frontend/src/api/client.ts` — added `validateIndexaToken`, `connectPlugin`, `getConnections`, `disconnectConnection`, `getInvestmentPortfolio`. Custom error handling on `validateIndexaToken` to propagate HTTP status for 400/503 branching in wizard.
- `frontend/src/api/mock.ts` — added `_mockConnected` session flag; `mockValidateIndexaToken` (rejects short tokens with status 400), `mockConnectPlugin`, `mockGetConnections`, `mockDisconnectConnection`, `mockGetInvestmentPortfolio` (returns empty portfolio when not connected, full portfolio with 3 holdings + 15-point value_series when connected). Also updated `mockGetInvestmentPlugins` to reflect dynamic status from `_mockConnected`.
- `frontend/src/i18n/index.ts` — added 44 keys to `Dict` interface: 24 wizard, 15 investments-populated, 4 connector-card-state. Note: `invAssetFixed_income` uses underscore in the key name (Wanda's convention).
- `frontend/src/i18n/es.ts` — all 44 ES translations added.
- `frontend/src/i18n/en.ts` — all 44 EN translations added.
- `frontend/src/pages/ConnectorsPage.tsx` — rewritten: fetches `getInvestmentPlugins()` + `getConnections()` in parallel. Indexa card renders in 3 states (available/connected/error) using connection status. Disconnect uses `window.confirm` + `disconnectConnection`. Wizard launched via `IndexaWizard` component; `onConnected` re-fetches both lists.
- `frontend/src/pages/InvestmentsPage.tsx` — full rewrite: on mount fetches `getInvestmentPortfolio()` + `getConnections()` in parallel. `plugins_connected === 0` → empty state + CTA. `plugins_connected > 0` → account header strip + 5 KPI cards (total value, invested, P&L€/%, TWR, XIRR; "—" when null) + `inv-charts-row` (AreaChart value-over-time + donut allocation by asset_class) + holdings table (name, ISIN, badge, value, weight%, cost, P&L€/%). `gain_loss_pct` multiplied ×100 for display. YYYYMMDD dates parsed via `parseYYYYMMDD()`. Asset class badge uses `.replace(/_/g, '-')` for CSS (equity/fixed-income/cash/other). `assetLabel()` uses direct map to avoid unsafe dynamic key access.

**Key patterns learned:**
- `WizardStep` union type with string literals for spinner/error substeps avoids extra booleans.
- `_mockConnected` mutable flag in mock.ts allows demo mode to simulate the full connect→view flow.
- `invAssetFixed_income` key name (underscore) from Wanda's spec; component uses a local `assetLabel()` map rather than template-literal key lookup to stay type-safe.
- `asset_class.replace(/_/g, '-')` converts `"fixed_income"` → `"fixed-income"` for CSS BEM modifier.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Investments Polish 2: tooltip date, Y-domain, left-col matrix, donut center, info tips (vision-43)

Five targeted changes on `InvestmentsPage.tsx` + i18n per Wanda's `wanda-investments-polish2.md` contract.

---

**CHANGE 1 — Evolution chart tooltip shows full dd/mm/yyyy date**
- **Problem:** `evolutionData` was storing the date as a pre-formatted `toLocaleDateString` string (e.g. "jul 26"), so the tooltip label showed the same compact string — no way to recover the full date.
- **Fix:** `evolutionData` now stores `date: pt.date` (the raw ISO YYYY-MM-DD string). `XAxis` keeps compact axis labels via `tickFormatter={(isoDate) => new Date(isoDate).toLocaleDateString(locale, { month: 'short', year: '2-digit' })}`. Tooltip uses `labelFormatter={(isoDate) => formatDDMMYYYY(isoDate)}`.
- **`formatDDMMYYYY`** is a module-level helper: splits on `-` → `${d}/${m}/${y}`. Safe for edge cases (partial ISO strings fall back to returning the raw value).
- Removed `locale` from the `evolutionData` useMemo dependency array (it's no longer used inside the memo).

**CHANGE 2 — Y-axis auto-scales with padded domain**
- **Problem:** YAxis had no `domain` prop, defaulting Recharts to `[0, 'auto']` — always anchored at 0, so 1-month or 1-year views never zoomed in.
- **Fix:** New `evolutionDomain` useMemo (deps: `evolutionData`, `evMode`) computes min/max across ALL plotted values (both `value` and `contributions` lines). Pads by 8% of range; edge case: if all values are equal, pads by 10% of value (or 500/1 fallback).
- **"Nice" rounding:** `niceStep(range, isEur)` returns a step size proportional to the data range (5000/1000/500/200/100/50 for EUR; 0.5 for %). `niceFloor` / `niceCeil` round to the nearest step so axis ticks land on clean numbers.
- `YAxis domain={evolutionDomain}` — recomputes whenever period or mode changes (since those drive `evolutionData`).

**CHANGE 3 — Returns matrix moved to left column (`.inv-left-col`)**
- Per Wanda's layout spec: `inv-top-row` left cell now wraps summary card + matrix together; right cell stays `inv-donuts-row`.
- **Refactor:** extracted the matrix IIFE into a `const returnsMatrixCard = (() => { ... })()` variable (computed before `return`). Guard: `if (!portfolio?.monthly_returns || portfolio.monthly_returns.length === 0) return null`. Inside the IIFE, all `portfolio!.` non-null assertions replaced with `portfolio.` since the guard already ensures it's non-null.
- JSX structure: `<div className="inv-left-col">` wraps `<div className="card inv-summary-card">` + `{returnsMatrixCard}`. The old standalone Block 5 IIFE removed from below the evolution chart.
- Horizontal scroll on narrow screens is handled by Wanda's pre-existing `.returns-matrix-wrap { overflow-x: auto }` on the `<table>` — no JSX change needed.

**CHANGE 4 — Donut center label alignment (CSS-only, verified)**
- Wanda added `.inv-donuts-row .cat-donut-wrap { height: 220px; max-width: 220px; }` to `index.css` to match the RC's `height={220}` prop. Both donuts already use `.cat-donut-wrap` + `.cat-donut-center` (position: absolute; inset: 0). No JSX change was needed — confirmed.

**CHANGE 5 — Info tooltip buttons on TWR / MWR / Volatilidad**
- Added `.inv-metric-header` wrapper div inside each `.inv-metric`, containing the existing `.inv-metric-label` + a new `<button className="inv-info-tip" type="button" aria-label={t.invMetric*Info}>` with an `.inv-info-bubble` span inside.
- Keyboard-focusable via `tabIndex` default on `<button>`. Wanda's CSS shows the bubble on `:hover` / `:focus-visible`.
- **3 new i18n keys** added to `Dict` interface + `es.ts` + `en.ts`:

| Key | ES | EN |
|-----|----|----|
| `invMetricTwrInfo` | "Rentabilidad ponderada por tiempo (TWR)…" | "Time-Weighted Return (TWR)…" |
| `invMetricMwrInfo` | "Rentabilidad ponderada por dinero (MWR / TIR)…" | "Money-Weighted Return (MWR / IRR)…" |
| `invMetricVolInfo` | "Volatilidad anualizada…" | "Annualised volatility…" |

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Holdings table: sorting, units column, header tooltips (vision-44)

Three targeted changes on the Cartera / `inv-holdings-table` in `InvestmentsPage.tsx`.

---

**CHANGE 1 — Full column sorting**
- Added `type HoldingsSortCol = 'name'|'isin'|'class'|'units'|'value'|'weight'|'cost'|'pnl'|'pnlpct'` as a local type inside the component (before the state declarations).
- State: `const [sortCol, setSortCol] = useState<HoldingsSortCol>('value')` and `const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc')`. Default is Value descending (matches backend order).
- `sortedHoldings` useMemo: spreads `portfolio.holdings` into a new array, sorts via a `switch` on `sortCol`. Text columns (`name`/`isin`/`class`) use `localeCompare(…, locale)`. `class` sorts by the translated label via `assetLabel(h.asset_class, t)`. `weight` sorts identical to `value` (proportional). Numeric columns use simple subtraction. `void totalVal` is used to acknowledge the unused-but-computed variable without triggering a lint warning.
- `handleSortClick(col)`: if same column → toggle `sortDir`; if new column → set it + default dir to `'asc'` for text cols, `'desc'` for all numeric.
- `SortArrow` inner component (defined after the useMemo, before the return): renders `null` if column is not active, else `▲`/`▼` in a `<span aria-hidden="true">`. This pattern avoids a ternary inside JSX header cells.
- All 9 `<th>` cells are made clickable: `onClick`, `onKeyDown` (Enter/Space), `tabIndex={0}`, `role="columnheader"`, `aria-sort`. Classes dynamically include `inv-th-sort-active` when the column matches `sortCol`. No new CSS needed — Wanda's `inv-th-sortable`/`inv-th-sort-active` classes already handle the active style.

**CHANGE 2 — "Participaciones" (units) column**
- Inserted new column at position 4 (after Class, before Value): `t.invColUnits` header with `.inv-th-num.inv-th-sortable`.
- Row cell: `new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(h.units)` for locale-aware decimal formatting (es-ES uses comma). Class `.inv-td-num`.
- **3 new i18n keys** added to `Dict` interface + `es.ts` + `en.ts`:

| Key | ES | EN |
|-----|----|----|
| `invColUnits` | `'Participaciones'` | `'Units'` |

**CHANGE 3 — Info tooltips on G/P and G/P% headers**
- Same `.inv-info-tip` / `.inv-info-bubble` pattern as the metrics strip (vision-43). Each `<th>` for G/P and G/P% includes the sort arrow + a `<button className="inv-info-tip">?<span className="inv-info-bubble">…</span></button>`.
- `onClick={e => e.stopPropagation()}` on the button prevents the `<th>` click handler from triggering a re-sort when the user clicks the tooltip icon. The `<th>` retains its own `onClick` for sorting.
- **4 new i18n keys** added to `Dict` interface + `es.ts` + `en.ts`:

| Key | ES | EN |
|-----|----|----|
| `invColPnLInfo` | "Ganancia o pérdida latente (no realizada) de cada fondo en euros: valor actual menos coste." | "Unrealized gain/loss of each fund in euros: current value minus cost." |
| `invColPnLPctInfo` | "Ganancia o pérdida latente en porcentaje sobre el coste invertido en ese fondo." | "Unrealized gain/loss as a percentage of the amount invested in that fund." |

**Data loop change:** `portfolio!.holdings.map(…)` replaced with `sortedHoldings.map(…)`. The `units` formatter (`fmtUnits`) is computed inline per row.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

---

### 2026-07-14 — G/P and G/P% header tooltips escape overflow clip (vision-45)

**Root cause:** `.inv-holdings-table-wrap` has `overflow-x: auto` (index.css:4504). Per CSS spec, `overflow-x: auto` forces the computed `overflow-y` to `auto` too, so the absolutely-positioned `.inv-info-bubble` (which renders ABOVE the header via CSS `bottom: calc(100% + 8px)`) was being clipped by the scroll container's overflow boundary and never appeared.

The metrics-strip tooltips (vision-43) worked because they are NOT inside any overflow container.

**Fix — `position: fixed` + `getBoundingClientRect()` (mirrors TagTypeahead pattern):**
- Added `const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)` near the other state declarations.
- Both `<button className="inv-info-tip">` elements (G/P and G/P% headers) now handle `onMouseEnter`/`onFocus` → `rect = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: ..., x: rect.left + rect.width/2, y: rect.top })`, and `onMouseLeave`/`onBlur` → `setOpenTip(null)`. The existing `onClick={e => e.stopPropagation()}` is kept. The old `<span className="inv-info-bubble">` child was removed from inside these buttons (the old CSS-hover approach no longer needed).
- A single shared bubble is rendered once before `</main>`: `{openTip && <span className="inv-info-bubble" style={{ position: 'fixed', left: openTip.x, top: openTip.y - 8, transform: 'translate(-50%, -100%)', zIndex: 1000, pointerEvents: 'none' }}>{openTip.text}</span>}`.
- `position: fixed` escapes the overflow container entirely; `transform: translate(-50%, -100%)` centers horizontally and places the bubble above the icon; `pointerEvents: none` avoids mouse-leave flicker. No index.css changes required — `.inv-info-bubble` visual styles (background, border, padding, etc.) already exist and are reused.
- Works for keyboard focus (focus "?" → shows), mouse hover, horizontal table scroll (viewport-fixed, not clipped by scroll).

**Pattern reference:** `TagTypeahead.tsx` uses the same `getBoundingClientRect()` + `position: fixed` injection to escape overflow for its suggestions dropdown.

**Build:** `npm run build` → 0 TS errors. Chunk-size warning is pre-existing.

---

### 2026-07-14 — Investments plugin-nav restructure + Settings regroup + Rules move (vision-46)

Owner-signed navigation restructure. All changes are frontend-only. Build: `npm run build` → 0 TS errors, IndexaView lazy-split as a separate 35.69 kB chunk.

---

**PART 1 — Investments as an expandable section with per-plugin views**

**New files:**
- `frontend/src/investments/registry.ts` — static `PLUGIN_VIEW_REGISTRY: Record<string, PluginViewEntry>` map. `PluginViewEntry = { icon, name, component: LazyExoticComponent<ComponentType<any>> }`. Current entry: `'indexa-capital'` → `{ icon: '🏦', name: 'Indexa Capital', component: React.lazy(() => import('./views/IndexaView')) }`. Adding future plugins = one import + one entry.
- `frontend/src/investments/views/IndexaView.tsx` — extracted from `InvestmentsPage.tsx`. Identical behavior: fetches `getInvestmentPortfolio()` + `getConnections()`, shows loading/error/empty/connected states. Import paths adjusted for new depth (`../../api/*`, `../../i18n`). Function renamed `InvestmentsPage` → `IndexaView`.
- `frontend/src/investments/PluginViewWrapper.tsx` — reads `:pluginId` from `useParams`. Looks up in `PLUGIN_VIEW_REGISTRY`. If not found: renders "not available" state with link to `/settings/connectors`. If found: wraps component in `<Suspense>` fallback spinner and renders it.
- `frontend/src/pages/InvestmentsLandingPage.tsx` — `/investments` hub. Fetches `getConnections()` + `getInvestmentPlugins()` in parallel. Filters for `status === 'active'` + in registry. Renders plugin-card links (`.plugin-card.connector-card--connected`) to `/investments/{plugin_id}`. Empty state: empty icon + `invLandingEmpty` text + "Gestionar conectores →" CTA to `/settings/connectors`.

**Modified files:**
- `frontend/src/App.tsx` — imports replaced (`InvestmentsPage` → `InvestmentsLandingPage` + `PluginViewWrapper`). Single `investments` route replaced with nested: `<Route path="investments"><Route index element={<InvestmentsLandingPage />} /><Route path=":pluginId" element={<PluginViewWrapper />} /></Route>`. Added `/settings/rules` route for `RulesPage`. Added `/rules` → `<Navigate to="/settings/rules" replace />` redirect (old bookmarks preserved).
- `frontend/src/components/Layout.tsx` — added imports: `useNavigate`, `getConnections`, `InvestmentConnection`, `PLUGIN_VIEW_REGISTRY`. Added `isOnInvestments`, `investmentsExpanded` state + `useEffect` (auto-expand on /investments/* route). Added `connections`/`connectionsLoaded` state + `useEffect` fetching `getConnections()` on mount (fail gracefully). Added `connectedPlugins` derived array. Replaced flat 💰 NavLink with `sidebar-section` accordion (same DOM structure as Settings). Investments button: `onClick` → toggles expanded + navigates to `/investments`.

**PART 2 — Settings FINAL regrouping (owner override)**

The task specified FINAL structure overriding the docs' earlier multi-group proposal:
```
⚙️ Ajustes ▾
  [DATOS group label]    ← only ONE group header
  Categorías → /settings/categories
  Etiquetas  → /settings/tags
  Cuentas    → /settings/accounts
  Reglas     → /settings/rules       (LOOSE — no header)
  Conectores → /settings/connectors  (LOOSE)
  Copia de seguridad → /settings/backup  (LOOSE)
  Apariencia → /settings/appearance  (LOOSE)
```
Implemented in `Layout.tsx` settings accordion. Group label uses `.sidebar-group-label` CSS class (Wanda's class, already in index.css). `navRules` key reused for the Rules sub-link.

**PART 3 — Rules moved from top-level to Settings**

- Removed top-level `📏 Rules` `<NavLink to="/rules">` from `Layout.tsx`.
- Added `<NavLink to="/settings/rules">` inside Settings accordion (LOOSE, no group header).
- `App.tsx`: `<Route path="rules" element={<Navigate to="/settings/rules" replace />}` added to preserve old `/rules` links.
- `<Route path="rules" element={<RulesPage />}` added inside the Settings nested routes.

**i18n — 6 new keys added to Dict interface + es.ts + en.ts:**

| Key | ES | EN | Notes |
|-----|----|----|-------|
| `navInvestmentsOverview` | `"Resumen"` | `"Overview"` | Sidebar sub-item; landing page CTA button |
| `invNoPluginsHint` | `"Conecta un plugin →"` | `"Connect a plugin →"` | Shown in accordion when no connected plugins |
| `invLandingTitle` | `"Inversiones"` | `"Investments"` | Landing page `<h1>` |
| `invLandingEmpty` | `"Conecta un plugin para ver tus inversiones"` | `"Connect a plugin to view your investments"` | Landing empty state |
| `invPluginNotAvailable` | `"Plugin no disponible. Conecta este plugin en Ajustes → Conectores."` | `"Plugin unavailable. Connect this plugin in Settings → Connectors."` | PluginViewWrapper unknown-plugin state |
| `settingsGroupData` | `"Datos"` | `"Data"` | DATOS group header in Settings accordion |

**Key patterns:**
- `React.lazy()` call in `registry.ts` defers the actual dynamic import. TypeScript types: `LazyExoticComponent<ComponentType<any>>` — the `any` generic avoids complex variance issues with the registry's mixed-type value.
- Layout fetches connections on mount for the sidebar (separate from page-level data fetches). Fail gracefully: `connectionsLoaded` flag controls the empty-state hint vs. spinner absence.
- `useNavigate` in Layout for the Investments accordion button click → navigate to /investments + toggle. Settings button stays toggle-only (no navigation).
- Investments accordion mirrors Settings accordion exactly: same CSS classes, same `useEffect` auto-expand pattern, same state shape.

---

## Key Patterns

- **Responsive-first:** mobile priority (360–430px), drawer nav, 40px touch targets
- **Mock data strategy:** VITE_USE_MOCK=1 env flag; graceful error fallback
- **Fetch+blob pattern:** Authenticated downloads respect session cookies; not bare <a href>
- **CSS custom properties:** --expense, --income, --surface, --border; no external UI lib
- **Plugin-view registry:** `frontend/src/investments/registry.ts` — static map `plugin_id → {icon, name, component}`. Adding a new plugin = one lazy import + one entry. No plugin SDK needed.

## Key Files
- frontend/src/pages/{Dashboard,TransactionsPage,StatementsPage,AnalyticsPage}.tsx
- frontend/src/components/{ImportModal,TransactionsTable,RuleFormModal}.tsx
- frontend/src/api/{client,types,mock}.ts
- frontend/src/investments/registry.ts
- frontend/src/investments/views/IndexaView.tsx
- frontend/src/investments/PluginViewWrapper.tsx

## For Full History
See history-archive/ — archived entries from prior waves.

---

## 2026-07-15 — Fidelity ESPP Phase 1 UI: Pending Owner Preference

**From Fury architecture & Banner findings:**

**CSV-first MVP confirmed.** Fury has identified 3 key UI questions pending owner input:

1. **Display preference:** How should Phase 1 UI present Fidelity ESPP?
   - Option A: KPI cards (estilo Indexa) — valor actual, gain/loss %, total cost basis
   - Option B: Table view — per-lot detail (date acquired, shares, cost basis)
   - Option C: Both

2. **Currency:** EUR-only display (cost basis in EUR, values in EUR when Phase 2 live pricing arrives) or EUR + USD side-by-side?

3. **Revaluation frequency:** On-demand (fetch live price when user navigates to page), hourly refresh, or daily?

**No production UI work until owner sign-off.** Design phase ready; await decision gate.

---

*For earlier sessions and learning archive, see history-archive.md.*
