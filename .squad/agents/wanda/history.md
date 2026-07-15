# Project Context

- **Owner:** DrDonoso
- **Project:** Finlytics — personal bank-account expense tracking (PDF → transactions → PostgreSQL → React dashboard). Single-user auth. Mostly mobile-accessed.
- **Stack:** Python 3.12 + FastAPI + PostgreSQL 16 + SQLAlchemy async; React + Vite + Recharts. Theme (light/dark/system) via `ThemeContext`.
- **Joined:** 2026-07-06 — UX/UI Designer, owns visual design system, layout, proportion, responsive behavior, token consistency.

## Role & Conventions

- **Owned domain:** CSS styling, layout balance, responsive/mobile behavior, visual hierarchy, theming/token compliance.
- **Pair:** Vision (Frontend Engineer) owns React logic and data-fetching; Wanda owns the look and CSS.
- **Token discipline:** ALL color and spacing must use CSS tokens (`var(--primary)`, `var(--surface)`, etc.). No raw colour values. Both light and dark themes must be correct.
- **i18n:** Never hard-code user-facing copy; use `frontend/src/i18n/`.
- **Mobile-first approach:** Use `@media (max-width: 900px)` for tablet stacking, `@media (max-width: 600px)` or `max-width: 500px` for mobile. Test on actual mobile hardware.
- **Key CSS files:** `frontend/src/index.css` (global tokens, `.dashboard`, `.charts-row`, `.charts-row-category`, `.tx-*` sections, `.settings-*`).
- **Recharts patterns:** Explicit height on wrap container (CSS) → `ResponsiveContainer height="100%"` (JSX) for responsive donut/chart fill. `ResponsiveContainer` with just `width` alone does NOT work for height.

## Session Summary

Built all CSS styling from baseline (2026-07-06) through rules-engine UI polish (2026-07-07). **Total:** 20+ CSS modules styled, 100% token-compliant, zero raw colors. Detailed earlier sessions archived in `history-archive.md`.

## Key Learnings (CSS Patterns & Best Practices)

See `history-archive.md` for detailed CSS learnings from 2026-07-06 to 2026-07-10.

- **2026-07-14:** `.btn-primary` base rule now uses `display: inline-flex; align-items: center; justify-content: center` — without this, `height: 38px` is ignored on `<a>`/`<span>` (inline elements), and text isn't vertically centred; always make shared button classes `inline-flex` so they render identically across `<button>`, `<a>`, and `<span>`.
- **2026-07-14:** Segmented-control pattern (`.inv-period-selector` / `.inv-toggle`) — sunken track: `background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 3px`. Buttons inside: `background: transparent; border: none; border-radius: 6px; height: 28px`. Active: `background: var(--primary); color: #fff`. Works identically for 2-option toggles and multi-option period selectors.
- **2026-07-14:** Ultrawide fix — add `max-width: Xpx` directly on the card element (not on `.dashboard`). This left-aligns the capped card within the parent layout, consistent with the sidebar-flush design. `min-width` on the inner table ensures horizontal scroll on narrow screens.
- **2026-07-14:** Grid `align-items: stretch` forces all children to the tallest sibling's height — when a summary card has only 4 rows but sits next to a taller donut, it gets huge empty space. Fix: `align-items: start` — each card sits at its natural height, no stretching. Add meaningful content (metrics strip) to close the perceived gap rather than forcing equal heights.
- **2026-07-14:** Metrics strip pattern (`.inv-metrics-strip` / `.inv-metric`) — flex row, no-wrap; cells divided by `border-right: 1px solid var(--border)` (last child none); each cell is `flex: 1 1 0` so they share width equally. Top separator via `border-top + padding-top` on the strip container. Safe at ≤600px with `font-size` step-down only (stays 1 row).
- **[2026-07-15 HEADS-UP: FIDELITY ESPP UPLOAD WIZARD]** Feasibility probe complete. Phase 1 scope: file upload → holdings review → confirm. Wanda to design CSS for: file-picker container (drag-drop area, button styling), holdings-review table (responsive 4-col: date, shares, price, cost-basis), action buttons (confirm/cancel, primary/secondary), and success/loading states. Invest in mobile responsiveness (responsive column widths, stacked on <600px). Reuse existing token set + button patterns from Investments skeleton. Decision memo in `.squad/decisions.md` §2026-07-15T06:51:14Z.
- **2026-07-14:** Two-donut layout — `.inv-donuts-row` (1fr/1fr, gap 12px) sits in the RIGHT cell of `.inv-top-row`, itself a 1fr/1fr grid. Donuts are each `.card` inside the row (not the row itself). `align-items: start` on the outer grid prevents either column from forcing height on the other. Stacks ≤900px same as outer grid.
- **2026-07-14:** Instrument donut compact legend (`.inv-donut-compact-legend`) — flex-col, `gap: 5px`, `max-height: 200px; overflow-y: auto` to handle ~10 items without blowing out card height. Each item: 8×8px swatch + ellipsis name (flex:1) + right-aligned pct. Better than reusing `.cat-table` which adds unnecessary column structure for 2 values.
- **2026-07-14:** Instrument colour palette — 12 hues defined as `--inv-p0`…`--inv-p11` CSS custom props on `:root` AND as a JS `INSTRUMENT_PALETTE` array constant for Recharts `Cell` fills. CSS props are for swatch `backgroundColor` fallback in SSR/legacy contexts; the JS array is the primary source in components.
- **2026-07-14 (Polish 2):** Left-column stacking pattern — use a `div.inv-left-col { display:flex; flex-direction:column; gap:20px; min-width:0 }` wrapper as the first child of a 2-col grid when you need to stack 2+ cards vertically in one grid cell. No extra media-query needed — on mobile the grid collapses to 1fr and the wrapper becomes full-width naturally.
- **2026-07-14 (Polish 2):** `ResponsiveContainer` + `cat-donut-wrap` height mismatch — always match `cat-donut-wrap` CSS `height` to the exact pixel value passed to `ResponsiveContainer`. Mismatch shifts the absolute-positioned `.cat-donut-center` (`inset: 0`) away from the visual ring centre. Prefer scoped override (`.inv-donuts-row .cat-donut-wrap { height: 220px }`) over changing the shared class to avoid breaking other donuts.
- **2026-07-14 (Polish 2):** Info-tip pattern (`.inv-info-tip` + `.inv-info-bubble`) — circular `<button>` with `position: relative`; bubble is a child `<span class="inv-info-bubble">` with `display:none` flipped to `display:block` on parent `:hover`/`:focus-visible`. `pointer-events: none` on the bubble prevents accidental mouse-leave flicker. Caret uses `::before` (border colour) + `::after` (fill colour) stacked — `::after` paints on top by default (later in DOM order). No JS needed; mobile tap sets focus → bubble appears.

---

## 2026-07-14 — Nav Reorganization Proposal (Settings + Investments accordion)

Proposal written to `.squad/decisions/inbox/wanda-nav-reorg.md`. Part A revised at 2026-07-14T20:04:24+02:00 per owner feedback. Awaiting sign-off.

**Part A — Settings (REVISED):**
- 4 groups with `.sidebar-group-label` sub-headers (same CSS, single-item groups OK).
- **DATOS** / Data: Categorías, Etiquetas, Cuentas (owner constraint: Cuentas with Categories & Tags).
- **REGLAS** / Rules: Reglas alone (owner constraint: solo section, not clustered with anything).
- **SISTEMA** / System: Copia de seguridad, Conectores (Wanda decision: both are infrastructure/external ops).
- **APLICACIÓN** / App: Apariencia (solo).
- Rules moves from top-level nav into Settings. Route: `/settings/rules` recommended.
- i18n keys: `settingsGroupData`, `settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp`.

**Part B — Investments accordion:** unchanged from original proposal (owner approved).
- Exact reuse of `.sidebar-section` / `.sidebar-section-btn` / `.sidebar-subnav` / `.sidebar-arrow` pattern.
- Sub-items: "Resumen" → `/investments` (always) + per-plugin NavLinks → `/investments/{plugin_id}`.
- Empty case: `.sidebar-plugin-hint` hint below "Resumen".
- New CSS: `.sidebar-plugin-hint` only (~6 lines). New i18n: `navInvestmentsOverview`, `invNoPluginsHint`.

---

## 2026-07-08 Cross-Agent Context — Feature Proposals Awaiting Owner Decision

Fury has generated a 7-item feature shortlist and it's awaiting owner green-light on 2–3 features:

- **#1 Period Comparison** (M, High) → Shuri (backend) + Vision (UI)
- **#2 Recurring Detection** (M, High) → Shuri (backend) + Vision (UI)
- **#3 CSV/XLSX Import** (S, High) → Banner (parser) + Barton (tests)
- **#4 Budgets** (M, Medium) → Shuri (API) + Vision (UI) + Wanda (design)
- **#5 Export CSV/XLSX** (S, Medium) → Shuri (endpoint) + Vision (button)
- **#6 Forecast** (M, Nice-to-have) → Shuri (algorithm) + Vision (chart)
- **#7 Multi-Currency** (L, Nice-to-have) → Shuri (aggregation) + Vision (display)

**Phase 1 Recommendation:** #1 (Period Comparison) + #3 (CSV/XLSX Import)

Check .squad/decisions.md → "2026-07-08: Feature Proposals Shortlist" for full details. **Owner decision → team decomposition → your next slices.**

---

## 2026-07-14 — Investments Polish 2 (3 Visual Changes)

CSS appended to `frontend/src/index.css`. Vision contract written to `.squad/decisions/inbox/wanda-investments-polish2.md`. Build verified: `npm run build` passes, 0 errors.

**Change 1 — Returns matrix moved into left column:**
Added `.inv-left-col` (flex-col wrapper, gap 20px). Vision wraps `.inv-summary-card` + `.returns-matrix-card` in this new div as the first child of `.inv-top-row`. The matrix fills the empty gap below the summary card on wide screens; its existing `overflow-x: auto` in `.returns-matrix-wrap` handles horizontal scroll when the column (~490–560px) is narrower than `min-width: 720px`. Standalone `returns-matrix-card` below the evolution card is removed.

**Change 2 — Donut center label fix:**
Scoped override `.inv-donuts-row .cat-donut-wrap { height: 220px; max-width: 220px }` matches the wrapper to the explicit `ResponsiveContainer height={220}` used in `InvestmentsPage.tsx`. No JSX change needed. The shared `.cat-donut-wrap { height: 280px }` is preserved for `SpendingByCategory` / `TopMerchants`.

**Change 3 — Info-tip tooltips:**
New classes: `.inv-metric-header` (flex row: label + tip), `.inv-info-tip` (14px circle button, position:relative), `.inv-info-bubble` (absolute bubble, 240px max-width, hidden → shown on `:hover`/`:focus-visible`). Caret uses `::before` (border) + `::after` (fill) double-triangle trick. Mobile tap works via CSS `:focus-visible` — no JS required. 3 new i18n keys: `invMetricTwrInfo`, `invMetricMwrInfo`, `invMetricVolInfo` (ES + EN copy in contract).

---

## 2026-07-14 — Investments Page — Indexa-Style Redesign (Blocks 1–3)

Redesigned the populated Investments page as 3 Indexa-mirroring blocks. CSS appended to `frontend/src/index.css`. Full Vision contract written to `.squad/decisions/inbox/wanda-investments-redesign.md`.

**Layout change:**
Old: `[account-header] [kpi-grid 5 cards] [inv-charts-row 3fr+2fr] [inv-returns-card simple list] [holdings]`  
New: `[account-header] [inv-top-row 1fr+1fr: summary + donut] [inv-evolution-card full-width] [returns-matrix-card capped] [holdings]`

**New class names defined:**

_Block 1 — Summary card:_
- `.inv-top-row` — `1fr 1fr` grid wrapping summary + donut; stacks ≤900px
- `.inv-summary-card` — flex-column card shell
- `.inv-summary-row` — flex row label/value pair; `border-bottom: 1px solid var(--border)`
- `.inv-summary-row--total` — extra padding below hero row
- `.inv-summary-label` — 13px muted
- `.inv-summary-value` — 15px/600 tabular-nums; default text color
- `.inv-summary-value--big` — 26px/800 hero number (Valor total)
- `.inv-summary-value--pos` / `--neg` — `var(--income)` / `var(--expense)`

_Shared controls (period selector + toggle):_
- `.inv-period-selector` — sunken track: `var(--bg)` bg, border, 8px radius, 3px padding, `flex-wrap: wrap`
- `.inv-period-btn` — 28px/12px/transparent inside the track; 32px at ≤600px
- `.inv-period-btn--active` — `var(--primary)` bg + white text
- `.inv-toggle` — identical to `.inv-period-selector` (just 2 options)
- `.inv-toggle-btn` / `--active` — same as period btn

_Block 2 — Evolution chart:_
- `.inv-evolution-card` — flex-column full-width card
- `.inv-evolution-header` — flex space-between: title + controls; wraps mobile
- `.inv-evolution-controls` — groups period selector + toggle
- `.inv-evolution-chart-wrap` — 360px height → `ResponsiveContainer height="100%"`
- `.inv-chart-legend` — centered flex row below chart
- `.inv-chart-legend-item` — flex, swatch + label
- `.inv-chart-legend-swatch` — 24×3px line-style swatch

_Block 3 — Monthly returns matrix:_
- `.returns-matrix-card` — **`max-width: 1100px`** ultrawide fix
- `.returns-matrix-header` — flex space-between: title + toggle
- `.returns-matrix-wrap` — `overflow-x: auto` horizontal scroll
- `.returns-matrix` — `<table>`, `min-width: 720px`, `border-collapse: collapse`
- `.returns-matrix-year` — left-aligned bold year column
- `.returns-matrix-cell` — base (no extra rules)
- `.returns-matrix-cell--pos` — `var(--income)` + `rgba(34,197,94,0.10)` bg tint (dark: 0.12)
- `.returns-matrix-cell--neg` — `var(--expense)` + `rgba(239,68,68,0.10)` bg tint (dark: 0.12)
- `.returns-matrix-cell--empty` — `var(--text-muted)`
- `.returns-matrix-cell--total` — bold + `border-left`
- `.returns-matrix-cell--bench` — muted
- `.inv-drawdown-note` — 12px muted text, `border-top`

**i18n keys (Vision to add to ES + EN + Dict interface):**
`invSummaryValorTotal`, `invSummaryRentabilidad`, `invSummaryAportaciones`, `invSummaryRetenciones`,
`invEvolutionTitle`, `invPeriod1M`, `invPeriod3M`, `invPeriod6M`, `invPeriod1A`, `invPeriodTodo`,
`invToggleEur`, `invTogglePct`, `invLegendPortfolio`, `invLegendContributions`,
`invMatrixTitle`, `invMonthENE`…`invMonthDIC` (12 keys), `invMatrixTotal`, `invMatrixBenchmark`,
`invDrawdownNote` (function: `(pct, eur, start, end) => string`)

**Design decisions:**
- Summary card sits LEFT of donut in `inv-top-row` (1fr/1fr) — balanced heights; both cards fill the row height via `align-items: stretch`
- Evolution chart is NOW full-width (not 3fr of a 3fr+2fr split) — more room for the time axis and two lines
- Chart uses `LineChart + 2 × Line` (not AreaChart) — portfolio solid primary; contributions dashed muted step-line (`type="stepAfter"`, `strokeDasharray="5 3"`)
- Dynamic year buttons (2024, 2025, 2026…) generated from data range — no hardcoding
- Matrix `max-width: 1100px` caps the card; `min-width: 720px` on the table forces horizontal scroll below that — correct behaviour on both ultrawide (capped) and mobile (scrollable)
- Benchmark column shows % only (no EUR benchmark data); displays `—` in EUR mode

Designed and implemented all CSS for the Phase 1 Investments page skeleton. CSS appended to `frontend/src/index.css`. Design spec + Vision contract written to `.squad/decisions/inbox/wanda-investments-skeleton-design.md`.

**Class names defined (new):**
- `.investments-header` — flex row, `align-items: center; justify-content: space-between` for title + future actions
- `.investments-page-title` — 22px/700, `var(--text)`, `letter-spacing: -0.3px`; 18px at ≤600px
- `.investments-holdings-card` — `min-height: 200px` CLS guard on the holdings `.card`
- `.investments-empty` — flex-column, centered, 40px pad, `var(--text-muted)`, `min-height: 140px`
- `.investments-empty__icon` — 36px emoji, opacity 0.8
- `.investments-empty__text` — max-width 280px, line-height 1.5
- `.investments-catalog-card` — hook class only (no rules); scopes future catalog tweaks
- `.plugin-catalog` — `repeat(auto-fill, minmax(220px, 1fr))`, gap 16px; 200px breakpoint at ≤900px; 1fr at ≤600px
- `.plugin-card` — `var(--bg)` bg (inset contrast inside parent `.card`), flex-column, gap 8px
- `.plugin-card__icon` — 32px emoji, margin-bottom 4px
- `.plugin-card__name` — 15px/600, `var(--text)`
- `.plugin-card__description` — 13px muted, `flex: 1 1 auto` (pushes badge+button to card bottom)
- `.coming-soon-badge` — pill: `rgba(100,116,139,0.10)` bg, `var(--text-muted)` text, `border-radius: 999px`; explicit dark override for `rgba(148,163,184,0.12)` bg + border

**Reused existing classes (no duplication):**
- `.kpi-grid` + `.kpi-card` + `.kpi-label` + `.kpi-value` — full KPI row reuse
- `.card` + `.card-title` — holdings and catalog card shells
- `.btn-primary:disabled` — existing opacity 0.45 rule covers disabled Connect buttons
- `.state-box` + `.state-box.error` — loading/error states for plugin fetch

**Token choices:**
- Card bg: `var(--bg)` for plugin-card nested inside `var(--surface)` parent card → creates visible inset hierarchy in both themes
- Badge: raw rgba (not token-based) because CSS can't do `rgba(var(--token))`. Added dual dark-mode override (`[data-theme="dark"]` + `@media prefers-color-scheme`).

**Mobile/dark decisions:**
- Grid degrades from 3-col → 2-col → 1-col via auto-fill breakpoints, no JS
- Holdings empty state reduces padding at ≤600px; title font shrinks from 22px → 18px
- All token-driven colors resolve correctly in both themes; only `.coming-soon-badge` needed raw rgba overrides

---

## 2026-07-14 — Indexa Phase 2 Design (Wizard + Viz + Connector states)

Designed and implemented all CSS for Phase 2: Indexa wizard, populated investments page, connector card states. CSS appended to `frontend/src/index.css`. Design spec + Vision contract written to `.squad/decisions/inbox/wanda-indexa-phase2-design.md`. Build verified: `npm run build` passes, 0 errors.

**New class names defined:**

_Wizard (`.inv-wizard*`):_
- `.modal.inv-wizard` — 480px narrow modal variant (full-width bottom-sheet ≤600px)
- `.inv-wizard__progress` — flex container for step dots + connectors
- `.inv-wizard__step-dot` / `--active` / `--done` — 8px dots; active: scale 1.4×, primary; done: income green
- `.inv-wizard__step-sep` / `--done` — 2px connector lines between dots
- `.inv-wizard__body` — flex-col, centered, step content container (inside `.modal-body`)
- `.inv-wizard__logo` — 56px emoji, step 1
- `.inv-wizard__title` — 18px/700
- `.inv-wizard__desc` — 14px/muted, max-width 340px
- `.inv-wizard__link` — styled external link (primary tinted pill)
- `.inv-wizard__security-note` / `__security-note-icon` — "token cifrado" note block
- `.inv-wizard__token-field` / `__token-label` / `__token-input` — monospace 44px password input
- `.inv-wizard__account-list` / `__account-item` / `--checked` / `__account-checkbox` / `__account-info` / `__account-label` / `__account-type` — discovered accounts step
- `.inv-wizard__success` / `__success-icon` / `__success-title` / `__success-desc` / `__success-accounts` / `__success-account` / `__success-account-check` — step 4 success
- `.inv-wizard__error-banner` / `__error-banner-icon` — inline error (step 3 failure)

_Investments populated:_
- `.inv-account-header` / `__left` / `__icon` / `__label` / `__updated` — connected account strip
- `.inv-charts-row` — 3fr/2fr grid (stacks ≤900px): value chart + allocation donut
- `.inv-chart-card` / `--value` / `--allocation` — chart cards with CLS guards (`.state-box min-height: 280px`)
- `.inv-value-chart-wrap` — 260px height wrapper → `ResponsiveContainer height="100%"`
- `.inv-holdings-card` — min-height 200px CLS guard
- `.inv-holdings-table-wrap` / `.inv-holdings-table` — scrollable holdings table (min-width 720px)
- `.inv-th-num` / `.inv-th-sortable` / `.inv-th-sort-active` — table header variants
- `.inv-td-name` / `.inv-td-isin` / `.inv-td-num` / `.inv-td-weight` — table data cells
- `.inv-pnl--pos` / `.inv-pnl--neg` — income/expense coloring for P&L cells
- `.inv-asset-class-badge` / `--equity` / `--fixed-income` / `--cash` / `--other` — asset class pills (dark mode dual-overrides for equity/fixed-income/other)

_Connector cards:_
- `.connector-card--connected` — green border modifier on `.plugin-card`
- `.connected-badge` — green "Conectado" pill (mirrors `.coming-soon-badge`, dark override)
- `.connector-card--error` — red border modifier
- `.error-badge` — red "Error" pill
- `.btn-disconnect` — 28px muted button, red hover (36px mobile touch target)

**Reused (no duplication):**
- Wizard shell: `.modal-backdrop` `.modal` `.modal-header` `.modal-body` `.modal-footer`
- KPI row: `.kpi-grid` `.kpi-card` `.kpi-label` `.kpi-value` `.kpi-sub`
- Allocation donut: `.cat-chart-layout` `.cat-donut-wrap` `.cat-donut-center` `.cat-table-wrap` `.cat-table`
- States: `.state-box` `.state-box.error` `.spinner-wrap` `.spinner`

**Key design decisions:**
- Wizard is 480px max-width (vs 980px for import modal) — focused single-task flow
- Token input is `type="password"` + monospace for security perception
- Wizard step dots use `--income` (green) for done state — consistent with app's "success = green"
- Value chart: `AreaChart` with SVG gradient fill (22%→2% primary opacity) — matches app's blue primary
- Allocation donut: identical to SpendingByCategory pattern — zero new CSS, full visual consistency
- Asset class badges: 5-color fixed palette (equity=primary blue, fixed-income=income green, cash=slate, other=purple) + dark mode overrides
- `inv-charts-row` uses 3fr/2fr (not equal halves) because the value chart has a time axis and needs width to read

---

## 2026-07-14 — IA Recommendation: Connector Catalog → Settings

**Trigger:** Owner asked "¿Los conectores disponibles no estarían mejor en Settings?"

**Recommendation: YES — move the catalog to a new `settings/connectors` sub-page. Starting Phase 1, not deferred.**

**Rationale:**
- Connecting a plugin (credentials, OAuth, API keys) is a configuration action — same category as Accounts, Categories, Backup already in Settings.
- Settings already has an expandable sidebar sub-nav; adding "Conectores" as a 6th link is zero structural change.
- InvestmentsPage should be a *view* (portfolio data), not a wizard. When empty, it needs one CTA pointing to where setup happens — not a full catalog section.
- On mobile: KPIs → empty state → one CTA is cleaner than KPIs → empty state → 3 disabled plugin cards.
- Building the connect flow in Settings from the start avoids a Phase-2 migration.

**Proposed Investments page after change:**  
`title → KPI row (—) → holdings empty state + single "Gestionar conectores →" NavLink to /settings/connectors`

**New Settings/Connectors page:**  
Reuses existing `.plugin-catalog` / `.plugin-card` CSS verbatim — no new CSS needed.

**Scope:** Small — mostly a file reorganization. No new backend, no new CSS. ~5 small frontend changes (new route, new sub-nav link, new ConnectorsPage, CTA on InvestmentsPage, 2–3 i18n keys).

Full proposal: `.squad/decisions/inbox/wanda-connectors-placement.md`

---

## 2026-07-10 — Home Dashboard Restructure (Implementation Outcome)

Vision-29 has implemented the home restructure based on Wanda-3's assessment and Fury-6's product recommendations:

**What was built:**
- ✅ **Part A:** Removed embedded TransactionsTable (eliminated the double-filter confusion and mobile visibility issue). Added RecentTransactions widget (5 rows, read-only, "View all →" deep-link).
- ✅ **Part B:** New TopMerchants panel (top-8 by expense) powered by Shuri's new `/api/summary/by-merchant` endpoint.
- ✅ **Part C:** Moved all three trend charts (SpendingByAccount, SpendingOverTime, CashflowSankey) off home to new `/analytics` route (Tendencias nav). Each has own GlobalFilterBar + filter state.
- ✅ **Part D:** CLS fixes — all chart cards have explicit min-heights to prevent spinner→chart reflow. Per-component class modifiers: `.cat-card`, `.movers-card`, `.overtime-card`, `.byaccount-card`, `.cashflow-card`, `.recent-tx-card`, `.merchants-card`.

**CSS Changes:**
- 6 new i18n keys added (recentActivityTitle, recentViewAll, topMerchantsTitle, topMerchantsEmpty, navAnalytics, analyticsTitle).
- New component-scoped CSS for min-heights and spacing; no token breakage or theme regressions expected.
- Build: 0 TS errors, 784 KB bundle.

**Status:** ✅ Implemented, **awaiting user review** — NOT YET committed. Live on :7777 for preview.


**No action needed from Wanda** — this was Vision's implementation using existing design tokens and patterns. Ready for user feedback before merge to main.


---

## 2026-07-14 — Returns Table Design (Tabla de Rentabilidades)

Designed and implemented CSS for the returns table card. Evolution chart height bumped 260→300px. CSS appended to `frontend/src/index.css`. Vision contract: `.squad/decisions/inbox/wanda-returns-table-design.md`.

**New class names:**
- `.inv-returns-card` — hook class on the `.card` shell (no extra rules; placement: between `inv-charts-row` and holdings)
- `.returns-table` — `flex-direction: column` row container
- `.returns-row` — `flex; space-between; border-bottom: 1px solid var(--border)`; first-child: no top pad; last-child: no border/bottom-pad
- `.returns-label` — 13px/muted left cell; 12px ≤600px
- `.returns-value` — 14px/700/tabular-nums right cell; default `var(--text)`; 13px ≤600px
- `.returns-value--pos` — `var(--income)` green (positive return)
- `.returns-value--neg` — `var(--expense)` red (negative return)
- `.returns-value--neutral` — `var(--text-muted)` (volatility — risk metric, not directional)

**i18n keys (Vision to add to ES + EN):**
`invReturnsTitle`, `invReturnsWeek`, `invReturnsMonth`, `invReturnsYear`, `invReturnsTotal`, `invReturnsAnnual`, `invReturnsXirr`, `invReturnsVolatility`

**Evolution chart:** `.inv-value-chart-wrap` bumped 260px → 300px for more visual weight. No JSX change needed (`ResponsiveContainer height="100%"` fills wrapper).

**Null handling:** Vision renders `—` for null values; no special CSS required (default `var(--text)` color).

---

## 2026-07-14 — Investments Page Polish (3 visual changes)

Owner feedback on redesigned page. Three CSS-only changes applied to `frontend/src/index.css`. Build verified: `npm run build` passes (exit 0). Vision contract: `.squad/decisions/inbox/wanda-investments-polish.md`.

### Change 1 — Compact summary card (remove stretch)

**Problem:** `align-items: stretch` on `.inv-top-row` was forcing the 4-row summary card to match the taller donut card height, creating large empty space.  
**Fix:** Changed to `align-items: start` — each card sits at its natural content height. No JSX change needed.

### Change 2 — Metrics strip: TWR / MWR / Volatility

Added below the 4 summary rows inside `.inv-summary-card`, separated by a top border.

**New classes:**
- `.inv-metrics-strip` — `display: flex; flex-wrap: nowrap; border-top + padding-top` separator; fills remaining space below summary rows
- `.inv-metric` — `flex: 1 1 0; flex-direction: column; align-items: center; border-right` divider (last-child none)
- `.inv-metric-label` — 10px/700/uppercase (e.g. "TWR")
- `.inv-metric-sublabel` — 9px/muted caption (e.g. "anualizada")
- `.inv-metric-value` — 15px/700/tabular-nums
- `.inv-metric-value--pos` — `var(--income)` · `.inv-metric-value--neg` — `var(--expense)` · `.inv-metric-value--neutral` — `var(--text-muted)` (volatility)

**Data fields:** `returns.twr_annual`, `returns.xirr`, `returns.volatility`

**New i18n keys:**
`invMetricTwr`, `invMetricMwr`, `invMetricVolatility`, `invMetricSubAnnual`, `invMetricSubXirr`

### Change 3 — Second donut: allocation by instrument

Replaced single donut slot in `inv-top-row` right cell with `.inv-donuts-row` (two cards side by side).

**New classes:**
- `.inv-donuts-row` — `display: grid; grid-template-columns: 1fr 1fr; gap: 12px; stacks ≤900px`
- `.inv-donut-compact-legend` — `flex-col; max-height: 200px; overflow-y: auto` — compact per-fund list
- `.inv-donut-legend-item` — flex row: swatch + name (truncate) + pct
- `.inv-donut-legend-swatch` — 8×8px `border-radius: 2px` colored square
- `.inv-donut-legend-name` — `flex:1; text-overflow: ellipsis; color: var(--text-muted)`
- `.inv-donut-legend-pct` — 11px/600/tabular-nums/right-aligned

**Instrument colour palette (CSS + JS):**
CSS: `--inv-p0` … `--inv-p11` on `:root`  
JS constant: `INSTRUMENT_PALETTE` array (Vision adds to InvestmentsPage.tsx or shared file)  
`['#3b82f6','#22c55e','#f59e0b','#ec4899','#8b5cf6','#06b6d4','#f97316','#64748b','#84cc16','#e11d48','#0ea5e9','#d946ef']`

**Data:** `instrumentSlices` derived from `portfolio.holdings` (fund_name + current_value, sorted desc)

**New i18n keys:** `invDonutAssetTitle` (Por clase de activo / By asset class), `invDonutInstrumentTitle` (Por instrumento / By instrument)
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

