# Fury History Archive

**Archived:** 2026-07-16

Detailed session notes and reviews before condensation.

---


**Architecture conventions discovered:**

- **Routing (frontend):** `App.tsx` — flat child routes under `<Route path="/" element={<Layout />}>`. New sections = new `<Route path="investments" element={<InvestmentsPage />} />`.
- **Sidebar menu:** `Layout.tsx` — flat `<NavLink>` entries with emoji icon (`nav-icon`) + i18n label (`nav-label`). No expandable subsections needed for investments (unlike Settings).
- **i18n:** Bilingual EN/ES. `Dict` interface in `i18n/index.ts`, implementations in `es.ts` / `en.ts`. New keys must be added to all three files.
- **API client:** `frontend/src/api/client.ts` — `apiFetch<T>()` + `buildUrl()`. New endpoints follow same `getX()` / `postX()` export pattern with mock fallback. Types in `types.ts`.
- **Page pattern:** Pages use `AsyncState<T>` (`{ loading, error, data }`) + `idle<T>()` factory. Dashboard/Analytics use `GlobalFilterBar` + `KpiCards` + chart components in `<main className="dashboard">`.
- **Backend routers:** FastAPI `APIRouter(prefix="/...", tags=["..."])` per module in `src/finlytics/api/`. Registered in `app.py` with `app.include_router(router, prefix="/api", dependencies=_auth)`.
- **Schemas:** Pydantic `BaseModel` in `schemas.py`. Amounts as `float`, responses are flat/composable.
- **Design tokens:** Single `index.css` with CSS custom properties (`--bg`, `--surface`, `--border`, `--primary`, `--radius`, `--shadow`). Light/dark theme via `[data-theme="dark"]`.
- **Settings:** `pydantic-settings` `BaseSettings` in `config.py` — env vars + `.env` file.
- **Auth:** All `/api/*` routes (except auth) require session cookie via `get_current_user` dependency.
- **Currency:** Hardcoded EUR (`formatEur()` in client, `formatCurrency(amount, lang)` in i18n). Multi-currency will matter for investments — flagged as open question.

**Key decision: Frontend-first skeleton + thin backend stub.** One `GET /api/investments/plugins` endpoint returning an empty list from a static plugin registry. This keeps phase 1 small while establishing the plugin contract for phase 2.

### 2026-07-14 — Indexa Capital Phase 2 (Architecture Plan)

**Key architecture decisions:**

- **Provider abstraction:** New `src/finlytics/investments/` package with `InvestmentProvider` ABC (3 methods: validate_token, get_portfolio, get_performance). `IndexaProvider` is the first implementation. Smallest interface that lets future plugins slot in without touching existing code.
- **Caching:** On-demand fetch with 5-min in-memory TTL. No background sync, no DB cache table. Indexa data is 1-business-day lagged — caching more aggressively adds complexity for zero user benefit.
- **Connections table:** `investment_connections` (migration 0013). One row per connected account. Token stored as Fernet ciphertext per Romanoff's approved security policy.
- **API surface:** 4 new endpoints (POST/GET/DELETE /connections, GET /portfolio) on the existing investments router. POST is for our own config, not against Indexa. GET /plugins stays but Indexa status becomes dynamic (connected vs available).
- **Schema extensions:** Added `InvestmentReturns`, `ValuePoint`, `CashInvestedSplit` to the existing `InvestmentPortfolioOut`. Holdings shape from Phase 1 maps directly to Indexa fiscal-results — no changes needed.
- **Wizard:** 4-step modal from ConnectorsPage card. Steps: intro → paste token → validate (POST /connections) → confirm/done. Single backend call at step 3.
- **Security:** Romanoff's policy is the binding constraint. Fernet encryption, fail-closed on missing key, hard-delete on disconnect, no token in any API response/log. Plan references her spec — doesn't redefine crypto.
- **MVP scope:** Connect one Indexa account + see real KPIs + holdings table. Chart, donut, cash-split, transactions are deferred post-MVP.
- **No Banner (AI) needed:** This flow is pure API → normalized data. No LLM extraction.

### 2026-07-14T11:10:33+02:00
Reviewed Phase 2 (Indexa connector). Tests and builds pass, but rejected due to UUID vs Integer PK deviation from the architectural plan and security spec. Review written to .squad/decisions/inbox/fury-indexa-phase2-review.md.
2026-07-14T14:16:54+02:00 - Reviewed investments page redesign by Wanda. Verified tests, UI matrix logic, and schemas. Approved.

### 2026-07-14T19:55:43+02:00 — Investments Plugin Nav Architecture

**Owner request:** Investments should be an expandable menu with per-plugin sub-items (like Settings), not a single hardcoded page. Different plugins have different views.

**Key decisions:**
- Investments becomes expandable sidebar section (reuse Settings accordion pattern)
- Routes: `/investments` (landing hub) + `/investments/:pluginId` (per-plugin view)
- Static frontend plugin-view registry: `plugin_id → { label, icon, component }`. No plugin SDK.
- Visibility rule: sub-item appears only when plugin has both a registered view AND an active connection.
- Extract current Indexa view (~400 lines) into `IndexaView.tsx`; InvestmentsPage becomes a simple landing hub.
- Backend impact: NONE (all endpoints already exist).
- Connect/disconnect stays in Settings → Conectores; Investments is data viewing only.

**Proposal written to:** `.squad/decisions/inbox/fury-investments-plugin-nav.md` — awaiting owner sign-off.
## 2026-07-14T19:53:07+02:00 - Fury Review: Investments Nav Restructure
* Checked frontend build and typescript types: 0 errors.
* Checked backend unit tests: All passed.
* Checked App.tsx routing: Correctly set up for investments and rules routes.
* Checked Layout.tsx: Accordion behavior matches the specifications, Settings has the correct \
Datos\ grouping followed by the other sections. 
* Evaluated IndexaView.tsx and InvestmentsLandingPage.tsx: Faithfully migrated from InvestmentsPage.tsx, properly uses lazy loading and Suspense wrapper. 
* Conclusion: APPROVE.

### 2026-07-15T08:56:00+02:00 — Fidelity ESPP Connector: Feasibility & Architecture

**Key architectural insight: Statement-Import vs Live-API connectors.**

Two fundamentally different connector types must coexist under the same Provider model:
- **Type A (Live-API):** Indexa Capital. Token → API call → live data. No local holdings storage.
- **Type B (Statement-Import):** Fidelity ESPP. PDF upload → extract lots → store in DB → compute value from market price.

Both types produce `NormalizedPortfolio` / `NormalizedPerformance` — the output contract is shared. Frontend and aggregation don't care which type produced the data.

**Key decisions:**
- Provider ABC gets `provider_type` attribute + optional `parse_statement()` method.
- Service layer routes by `provider_type`: live_api vs statement_import.
- New DB tables: `investment_lots` (purchase lots), `statement_imports` (idempotency via SHA-256 hash), `market_prices` (cached daily prices).
- Market data: yfinance for MVP (free, no key), pivot to Alpha Vantage if needed.
- USD→EUR FX required (MSFT trades in USD, app is EUR-centric).
- PDF never stored — extracted in memory, PII discarded. Only financial data persists.

**Phased plan:**
1. Phase 1: PDF parser → store lots → show shares + cost basis (Banner + Shuri + Barton)
2. Phase 2: Daily MSFT price → compute live value + gain/loss in EUR (Shuri + Rocket + Vision)
3. Phase 3: Historical price series → evolution chart + multi-statement import (Shuri + Vision + Wanda)

**Open questions for owner:** Cumulative vs per-period statement? ESPP discount tracking? Sell lots ever? Daily = end-of-day sufficient?

**Skill extracted:** `.squad/skills/statement-import-connector/SKILL.md` — reusable pattern for any no-API broker/plan.

**Proposal written to:** `.squad/decisions/inbox/fury-fidelity-espp-connector-architecture.md`

### 2026-07-15T08:51:14+02:00 — Fidelity ESPP Refinement: CSV-First + Input Adapters

**Key decisions from owner input:**
- Accumulate-only (never sells MSFT) → no disposal/FIFO logic needed
- Previous day's close sufficient → no intraday price source needed
- No ESPP discount/tax tracking for now → simplifies model significantly
- Generic-ready (ticker/currency as fields) but MSFT-only live case

**CSV-first decision:**
Owner can provide a CSV of current shares instead of the quarterly PDF. This is THE smallest-thing-that-works: deterministic parse, zero LLM, zero PII, zero new dependencies. PDF+LLM extractor becomes a later optional phase (only if CSV lacks per-lot detail the owner wants).

**Input Adapter → Normalized Positions design:**
Both CSV and PDF (and future Manual Entry) are "input adapters" producing a common `NormalizedLot` (ticker, shares, purchase_date, purchase_price, cost_basis, currency, source_type). All feed the same `holding_lots` table. Valuation layer (shares × price × FX) doesn't care about source.

**Generic-now vs defer line:**
- NOW (cheap, field-level): ticker, currency, source_type as DB columns; price_cache keyed by ticker; FX pair derived from lot currency.
- DEFER (YAGNI): multi-broker parser registry, sell/disposal logic, dividend tracking, background scheduler, multi-user routing.

**Reuse of imports.py pattern:**
Reusar el PATRÓN (preview → confirm + dedup_hash + import_run tracking), pero NO las funciones exactas (output es NormalizedLot, no ExtractedTransaction). New endpoints under `/api/investments/fidelity/import/` following same two-step discipline.

**Schema change:** `espp_lots` → `holding_lots` (or add ticker/currency/source_type columns to generalize). Minimal delta from Shuri's original sketch.

**Proposal written to:** `.squad/decisions/inbox/fury-fidelity-espp-refinement.md`

### 2026-07-15T09:55:00+02:00 — Fidelity ESPP: Closing Design Round (Currency + Flow + Phasing)

**Currency-of-record decision: EUR export, EUR storage.**

Rationale (3 arguments):
1. Owner thinks in EUR — "¿cuánto tengo?" is an EUR question. Cost basis in EUR = "what left my paycheck" converted at acquisition FX by Fidelity. That IS his fiscal and mental truth.
2. USD cost basis is a dead end — to display EUR cost, you'd need either today's FX (cost "changes" daily = confusing) or original FX per lot (= exactly what Fidelity already computed for us in the EUR CSV).
3. Stock-vs-FX separation wasn't requested — academic nice-to-have. Trivially derivable later from price_cache data without schema change.

Fallback: if only USD available, detect from footer, store USD, flag for FX lookup at display time. But we actively recommend EUR.

**Finalized end-to-end flow:**
1. Owner exports "View open lots.csv" from Fidelity (EUR, ~61 lots, cumulative)
2. Upload in app → wizard (3 steps)
3. Preview: sha256 dedup (file level) + parse + dedup_hash per lot (ordinal for duplicate DO lots) → show new lots
4. Confirm: persist to holding_lots + import_run tracking
5. Daily value (Phase 2): on-request price_cache check → Stooq/yfinance → value = Σshares × MSFT_USD × FX
6. Evolution (Phase 3): backfill MSFT+FX from min(purchase_date), compute value(date) step function + invested step, chart with period selector

**Phasing:**
- Phase 1: CSV→lots→static display (Value from CSV snapshot). Demoable: "subo CSV, veo lotes + KPIs."
- Phase 2: Daily MSFT+FX → live EUR value + gain/loss. Demoable: "entro y veo valor actualizado sin reimportar."
- Phase 3: Historical backfill + evolution chart (Indexa-style). Demoable: "gráfico desde 2019."

**6 final open questions** sent to owner: EUR gain vs USD% pure, chart periods, daily granularity, SP/DO visual distinction, free price source SLA acceptance, EUR CSV confirmation.

**Proposal written to:** `.squad/decisions/inbox/fury-fidelity-espp-currency-and-flow.md`

### 2026-07-15T10:34:28+02:00 — Review Gate: Fidelity ESPP Full Implementation

**Verdict: REJECT** — 4 blocking contract mismatches between backend and frontend.

**Blocking issues found:**
1. `gain_loss_pct` double-multiply: backend sends already-×100 (12.5 for 12.5%), frontend multiplies again → shows 1250%. Affects both KPIs and lot table.
2. Preview lot field names diverge: backend sends `cost_basis_per_share` / `cost_basis`, frontend expects `_eur` suffix variants.
3. `FidelityImportPreview.new_count` doesn't exist in backend response — frontend should use `new_lots.length`.
4. Confirm result: backend sends `skipped`, frontend expects `duplicates`.

**What passed:** Money math (FX direction correct), idempotency (dedup_hash + file_hash), provider abstraction, evolution series logic, migration pattern, graceful degradation, Indexa untouched, plugin_id consistent, CSV parser solid.

**Review written to:** `.squad/decisions/inbox/fury-fidelity-review.md`

### 2026-07-15T10:34:28+02:00 — Re-Review Gate: Fidelity ESPP Contract Fixes (Banner)

**Verdict: ✅ APPROVE** — All 4 blocking contract mismatches resolved. BUG #KPI-1 also fixed.

**Verified:**
1. `gain_loss_pct` — frontend no longer multiplies by 100 (FidelityView.tsx:355, 536). Comment in types.ts:489 updated to `// percentage: 12.5 = 12.5%`.
2. Preview lot fields — backend schemas.py + fidelity.py renamed to `cost_basis_per_share_eur` / `cost_basis_total_eur`. Frontend types match.
3. `new_count` removed from frontend type; view uses `new_lots.length` (FidelityView.tsx:608).
4. `skipped` → `duplicates` in backend schema (schemas.py:594) and endpoint (fidelity.py:312). Frontend reads `duplicates`.
5. BUG #KPI-1: `get_latest_price` wrapped in try/except in both `fidelity_kpis` (L324) and `fidelity_lots` (L446), degrading to null price + HTTP 200.
6. Full 5-endpoint contract cross-check: every field name and nullability in types.ts matches schemas.py. Zero remaining mismatches.

**Learning:** Non-author fix agent (Banner) pattern worked cleanly — 7 files touched, tests updated to match, both suites green. The authoritative field list in Banner's fix summary was accurate and complete.

**Re-review written to:** `.squad/decisions/inbox/fury-fidelity-rereview.md`

## Learnings

### 2026-07-16 — Full documentation rewrite (README, DEPLOY, AGENTS, frontend/README)

**Scope:** Comprehensive documentation update covering everything the app now does. Verified all features against the actual code before documenting.

**Key things now documented:**

- **Investments — two connector types:** Live-API (Indexa Capital: Fernet-encrypted token, 24h DB cache + async background refresh) vs Statement-Import (Fidelity ESPP: CSV upload, `espp_lots` table, Yahoo Chart API for MSFT + EUR/USD FX, incremental price top-up).
- **Combined investments overview (`/investments`):** KPI strip + allocation donuts (by provider + by asset class) + provider cards. Powered by `GET /api/investments/combined-overview`.
- **ESPP purchase reminder:** `GET /api/investments/fidelity/reminder` → banner on Dashboard (Inicio) and FidelityView. Quarter-end schedule (last business day of Mar/Jun/Sep/Dec).
- **Navigation restructure:** Inicio (cross-domain hub) / Finanzas (expandable: Transacciones, Tendencias, Extractos) / Inversiones (direct NavLink) / Ajustes (4 groups: Datos, Reglas, Sistema, Aplicación).
- **Finanzas overview (`/finances`):** GlobalFilterBar + KPIs + SpendingByCategory + TopMerchants + SpendingHeatmap (3-mode adaptive) + CategoryMovers + import. Heatmap drill-down confirmed: `handleSelectPeriod` updates filters; `preZoomFilters` enables reset.
- **Inicio (`/`):** Month-nav KPIs (from `/api/summary/months`) + InvestmentSnapshotCard + ImportSourcePicker (data-driven from `/api/investments/plugins`).
- **AboutPage:** Docker image tag (CalVer via `GET /api/version`), build date, repo/issues/changelog links, MIT license.
- **Two-Dockerfile convention:** `Dockerfile` = full multi-stage (CI/prod); `Dockerfile.local` = host-prebuilt frontend (local dev). Documented in all four docs.
- **FINLYTICS_ENCRYPTION_KEY** added to config reference in README and DEPLOY.
- **License:** Updated from "No license" to MIT.
- **Migrations:** Current head = `0015_add_portfolio_cache`.

**Convention confirmed:** `frontend/src/investments/registry.ts` is the plugin-view registry; new connectors must add an entry there. `AGENTS.md` now documents this pattern.

**frontend/README.md:** Was already non-boilerplate (Rocket/Vision had updated it with mock mode docs). Updated to reflect new pages, new components (SpendingHeatmap, CategoryMovers, InvestmentSnapshotCard, ImportSourcePicker, etc.), investments/ subtree, and the full page list.

