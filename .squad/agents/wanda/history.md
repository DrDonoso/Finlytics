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

## 2026-07-15 — Nav Restructure + Overview Pages Design Spec

### Learnings

- **Nav restructure:** Grouped Transacciones + Tendencias + Extractos under new "Finanzas" (💳) expandable parent at `/finances`. Inversiones converted from expandable accordion to direct NavLink (no more "Resumen" sub-item). Sub-plugin links removed from sidebar — navigation to Indexa/Fidelity via provider cards on `/investments`.
- **Finances overview page (`/finances`):** Proposed 4 components: GlobalFilterBar + KpiCards + SpendingByCategory + TopMerchants. Omitted SpendingHeatmap (low info density for daily operational view) and CategoryMovers (redundant with KPI deltas). Reuses `.dashboard` + `.charts-row-category` CSS — zero new CSS needed.
- **Investments combined overview (`/investments`):** Designed consolidated view with KPI strip (total value, invested, gain/loss), two donuts (by provider + by asset class using existing `.inv-donuts-row` pattern), and provider cards with mini-metrics + link to detail. Defined `GET /api/investments/combined-overview` response shape for Shuri.
- **Settings 4-group mapping re-applied:** Datos (Categorías, Etiquetas, Cuentas) → Reglas (Reglas) → Sistema (Conectores, Backup) → Aplicación (Apariencia). Three i18n keys missing (`settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp`) — spec'd for Vision to add.
- **Tendencias title fix:** `.analytics-page-title` uses 18px/600 vs standard `tx-page-title` 22px/700. Fix: change `<h1>` class to `tx-page-title`. Orphan CSS rule can be removed.
- **Spec delivered to:** `.squad/decisions/inbox/wanda-nav-restructure-overviews.md` — contract for Vision to implement.
