# Decisions Log

---

## 2026-07-14 — Investments Plugin Skeleton (Phase 1)

**Author:** Fury (Lead/Architect)  
**Status:** Approved

### Context

The owner wants a new "Investments" section in Finlytics built around a plugin architecture. Each plugin is a connector to an external investment API (Indexa Capital, brokers, crypto exchanges, etc.). Phase 1 is the SKELETON only: visualization placeholder, new menu item, "add plugin → coming soon" affordance, and the conceptual plugin model so real connectors slot in later.

### Decision

#### 1. Plugin Model

A **plugin** is a typed connector definition with this shape:

```typescript
// Frontend type (frontend/src/api/types.ts)
interface InvestmentPlugin {
  id: string              // unique slug, e.g. "indexa-capital"
  name: string            // display name, e.g. "Indexa Capital"
  description: string     // short description
  icon: string            // emoji or icon identifier
  status: 'coming_soon' | 'available' | 'connected' | 'error'
  auth_type: 'api_key' | 'oauth' | 'token' | 'none'
  supported_features: string[]  // e.g. ["holdings", "transactions", "performance"]
}
```

```python
# Backend schema (src/finlytics/api/schemas.py)
class InvestmentPluginOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    status: str   # coming_soon | available | connected | error
    auth_type: str
    supported_features: list[str]
```

#### 2. Normalized Unified Data Shape

All plugins will normalize their data into this common shape:

```typescript
interface InvestmentHolding {
  plugin_id: string
  name: string               // "Indexa Capital Cartera 10"
  ticker: string | null      // "IWDA" or null for managed portfolios
  asset_class: string        // "equity" | "fixed_income" | "mixed" | "crypto" | "cash" | "other"
  units: number | null       // share count, null for managed funds
  current_value: number      // current market value
  cost_basis: number | null  // total invested, null if unknown
  currency: string           // "EUR", "USD", etc.
  gain_loss: number | null   // unrealized P&L
  gain_loss_pct: number | null
  last_updated: string       // ISO datetime
}

interface InvestmentPortfolioSummary {
  total_value: number
  total_invested: number | null
  total_gain_loss: number | null
  total_gain_loss_pct: number | null
  currency: string
  holdings: InvestmentHolding[]
  plugins_connected: number
  last_updated: string | null
}
```

```python
class InvestmentHoldingOut(BaseModel):
    plugin_id: str
    name: str
    ticker: str | None = None
    asset_class: str
    units: float | None = None
    current_value: float
    cost_basis: float | None = None
    currency: str
    gain_loss: float | None = None
    gain_loss_pct: float | None = None
    last_updated: str

class InvestmentPortfolioOut(BaseModel):
    total_value: float
    total_invested: float | None = None
    total_gain_loss: float | None = None
    total_gain_loss_pct: float | None = None
    currency: str
    holdings: list[InvestmentHoldingOut]
    plugins_connected: int
    last_updated: str | None = None
```

#### 3. Backend vs Frontend — Recommendation

**Frontend-first skeleton + thin backend stub.**

- Add ONE backend endpoint: `GET /api/investments/plugins` → returns a static list of known plugins (all with `status: "coming_soon"` for now). This is ~20 lines of code in a new `investments.py` router.
- NO database tables in phase 1 — the plugin registry is a hardcoded list.
- NO `GET /api/investments/portfolio` in phase 1 — the frontend renders an empty/placeholder state.
- Phase 2 adds: plugin config storage (DB table), auth credential storage, actual API connectors, and the portfolio aggregation endpoint.

**Rationale:** Every other section in the app consumes a real `/api/*` endpoint. Keeping that pattern makes phase 2 a natural extension instead of a rewrite. The backend cost is minimal (~1 file, ~30 lines).

#### 4. Skeleton UI/UX Outline

The `InvestmentsPage` follows the same layout as Dashboard/Analytics:

```
<main className="dashboard">
  ├── Page header: "Inversiones / Investments" title
  ├── KPI placeholder row (3 cards):
  │   ├── Total Value      → "—" (empty state)
  │   ├── Total Invested   → "—"
  │   └── P&L              → "—"
  ├── Holdings area:
  │   └── Empty state: illustration + "Conecta un plugin para ver tus inversiones"
  │       / "Connect a plugin to see your investments"
  ├── Connected Plugins section:
  │   └── Empty state: "No hay plugins conectados" / "No plugins connected"
  └── Add Plugin affordance:
      └── Card/button grid showing known plugins (from API), each with:
          ├── Plugin icon + name
          ├── "Próximamente" / "Coming soon" badge
          └── Disabled "Connect" button
```

**Design consistency:**
- Use existing `--surface`, `--border`, `--radius`, `--shadow` tokens
- KPI cards: same `.kpi-card` styling as Dashboard
- Empty states: centered text + muted color, consistent with existing empty states
- "Coming soon" badge: `--text-muted` color, subtle pill shape

#### 5. Decomposition — Build Slices

| # | Slice | Owner | Depends on | Delivers |
|---|-------|-------|-----------|----------|
| 1 | **Backend plugin stub** | Shuri | — | `src/finlytics/api/investments.py` with `GET /api/investments/plugins`, schemas in `schemas.py`, router registered in `app.py` |
| 2 | **Frontend types + API client** | Vision | Slice 1 (contract) | TS types in `types.ts`, `getInvestmentPlugins()` in `client.ts` |
| 3 | **i18n keys** | Vision/Wanda | — | New keys in `Dict` interface + `es.ts` + `en.ts` for nav label, page title, KPIs, empty states, "coming soon" |
| 4 | **InvestmentsPage + route + nav** | Vision | Slices 2, 3 | `InvestmentsPage.tsx`, route in `App.tsx`, NavLink in `Layout.tsx` |
| 5 | **UI polish & empty states** | Wanda | Slice 4 | CSS for investment KPIs, plugin cards, "coming soon" badges, empty-state illustrations, dark mode |
| 6 | **Tests** | Barton | Slices 1, 4 | Backend: test `GET /api/investments/plugins` returns expected shape. Frontend: component renders, nav link present |

**Sequencing:** Slices 1 + 3 can start in parallel. Slice 2 needs the contract from Slice 1 (just the type shapes, can start same day). Slice 4 needs 2 + 3. Slice 5 needs 4. Slice 6 can start as soon as 1 and 4 land.

**What's real vs placeholder:**
- ✅ Real: nav item, route, page shell, backend endpoint, plugin registry
- 🔜 Placeholder: KPI values ("—"), holdings area (empty), plugin connect buttons (disabled + "Coming soon")

#### 6. Open Questions for Owner (Resolved)

1. **Currency handling:** EUR placeholder for phase 1; multi-currency phase 2.
2. **Plugin catalog:** 3 entries (Indexa Capital, generic broker, crypto).
3. **Nav icon:** 💰

---

## 2026-07-14 — Backend: Investments Plugin Stub (Phase 1, Slice 1)

**Author:** Shuri (Backend)  
**Status:** Shipped

### Endpoint Contract

#### `GET /api/investments/plugins`

- **Auth:** Required — session cookie (401 if unauthenticated)
- **Method:** GET  
- **Path:** `/api/investments/plugins`  
- **Response:** `200 OK` — `application/json` — array of plugin objects

#### Response Shape

```json
[
  {
    "id": "indexa-capital",
    "name": "Indexa Capital",
    "description": "Automated index-fund portfolio management",
    "icon": "🏦",
    "status": "coming_soon",
    "auth_type": "token",
    "supported_features": ["holdings", "transactions", "performance"]
  },
  {
    "id": "generic-broker",
    "name": "Broker (Stocks & ETFs)",
    "description": "Connect a stock/ETF broker account",
    "icon": "📈",
    "status": "coming_soon",
    "auth_type": "api_key",
    "supported_features": ["holdings", "transactions"]
  },
  {
    "id": "crypto-exchange",
    "name": "Crypto Exchange",
    "description": "Track crypto holdings from an exchange",
    "icon": "🪙",
    "status": "coming_soon",
    "auth_type": "api_key",
    "supported_features": ["holdings"]
  }
]
```

### Pydantic Schemas Available (for phase 2 reference)

`InvestmentHoldingOut` and `InvestmentPortfolioOut` are already defined in `src/finlytics/api/schemas.py` — Vision can use them to type the portfolio endpoint when phase 2 lands, without any backend schema changes.

### What's NOT included in phase 1

- No `GET /api/investments/portfolio` — frontend should render empty/placeholder state
- No DB tables, no migrations

### Files Changed

- `src/finlytics/api/schemas.py` — 3 new schemas (InvestmentPluginOut, InvestmentHoldingOut, InvestmentPortfolioOut)
- `src/finlytics/api/investments.py` — new router (created)
- `src/finlytics/app.py` — router registered

---

## 2026-07-14 — Design: InvestmentsPage Skeleton (Phase 1)

**Author:** Wanda (UX/UI Designer)  
**Status:** Implemented

### Layout Principles

- InvestmentsPage uses `<main className="dashboard">` (existing shell) — inherits the `24px 40px` padding, `flex-column`, `20px gap`.
- Visual hierarchy: title → KPI row → holdings state → plugin catalog.
- Mobile-first. The sidebar collapses at `≤767px`; content padding reduces at `≤600px` via existing `.dashboard` rules.
- All dark-mode support is baked into the CSS tokens and the new rules — no inline style overrides needed.
- **Do not** add inline color/spacing — use class names defined.

### Exact DOM Structure (JSX contract)

```tsx
<main className="dashboard">

  {/* ── 1. Page header ── */}
  <div className="investments-header">
    <h1 className="investments-page-title">{t.investmentsTitle}</h1>
  </div>

  {/* ── 2. KPI placeholder row — REUSE existing .kpi-grid + .kpi-card ── */}
  <div className="kpi-grid">
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
      <div className="kpi-value">—</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
      <div className="kpi-value">—</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiPnL}</div>
      <div className="kpi-value">—</div>
    </div>
  </div>

  {/* ── 3. Holdings empty state ── */}
  <div className="card investments-holdings-card">
    <div className="card-title">{t.investmentsHoldingsTitle}</div>
    <div className="investments-empty">
      <span className="investments-empty__icon" aria-hidden="true">📊</span>
      <p className="investments-empty__text">{t.investmentsEmptyHoldings}</p>
    </div>
  </div>

  {/* ── 4. Plugin catalog ── */}
  <div className="card investments-catalog-card">
    <div className="card-title">{t.investmentsCatalogTitle}</div>
    <div className="plugin-catalog">
      {plugins.map(plugin => (
        <div className="plugin-card" key={plugin.id}>
          <span className="plugin-card__icon" aria-hidden="true">{plugin.icon}</span>
          <span className="plugin-card__name">{plugin.name}</span>
          <p className="plugin-card__description">{plugin.description}</p>
          <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
          <button
            className="btn-primary"
            disabled
            aria-disabled="true"
          >
            {t.investmentsConnect}
          </button>
        </div>
      ))}
    </div>
  </div>

</main>
```

### Class-Name Reference

#### Existing classes (no new CSS needed)
| Class | Where defined | Notes |
|---|---|---|
| `.dashboard` | index.css | Page shell — `flex-column`, gap 20px, padding 24px 40px |
| `.card` | index.css | Surface + border + radius + shadow |
| `.card-title` | index.css | UPPERCASE label, 13px, muted |
| `.kpi-grid` | index.css | `repeat(auto-fill, minmax(180px, 1fr))` — handles 3 KPIs cleanly |
| `.kpi-card` | index.css | Surface + border + radius + shadow + 20px padding |
| `.kpi-label` | index.css | 12px, uppercase, muted |
| `.kpi-value` | index.css | 26px, 700 weight — shows "—" as placeholder |
| `.btn-primary` | index.css | Primary button. `:disabled` → opacity 0.45, cursor default |

#### New classes (added to index.css by Wanda)
| Class | Purpose |
|---|---|
| `.investments-header` | Flex row wrapper for title + future action buttons |
| `.investments-page-title` | H1, 22px/700, matches `.tx-page-title` scale; 18px on mobile |
| `.investments-holdings-card` | `min-height: 200px` on the holdings `.card` to prevent CLS |
| `.investments-empty` | Flex-column, centered, 40px pad, muted — for "no holdings" state |
| `.investments-empty__icon` | 36px emoji icon, opacity 0.8 |
| `.investments-empty__text` | max-width 280px, lh 1.5 |
| `.investments-catalog-card` | Hook class on the catalog wrapper `.card` (no extra rules yet) |
| `.plugin-catalog` | `repeat(auto-fill, minmax(220px, 1fr))` grid, gap 16px |
| `.plugin-card` | Individual card: `var(--bg)` background for nested inset look |
| `.plugin-card__icon` | 32px emoji, margin-bottom 4px |
| `.plugin-card__name` | 15px/600, `var(--text)` |
| `.plugin-card__description` | 13px, muted, `flex: 1 1 auto` — pushes badge+button to card bottom |
| `.coming-soon-badge` | Muted pill: `rgba` bg, `var(--text-muted)`, pill border. Dark-mode override included |

### Responsive Behaviour

| Viewport | KPI row | Plugin catalog |
|---|---|---|
| Desktop `>900px` | `auto-fill, minmax(180px, 1fr)` → 3 cols | `auto-fill, minmax(220px, 1fr)` → 3 cols |
| Tablet `≤900px` | `auto-fill, minmax(180px, 1fr)` → 2–3 cols | `auto-fill, minmax(200px, 1fr)` → 1–2 cols |
| Mobile `≤600px` | `auto-fill, minmax(180px)` → 1 col | `1fr` → 1 col (full width) |

### Dark-Mode Notes

All tokens (`--surface`, `--bg`, `--border`, `--text-muted`, `--text`) resolve correctly for both `[data-theme="dark"]` and `@media (prefers-color-scheme: dark)`. The only CSS that needed explicit dark overrides was `.coming-soon-badge` (raw `rgba` values adjusted for readability on dark surfaces). Everything else is token-driven.

### i18n Keys Required

| Key | ES | EN |
|---|---|---|
| `investmentsTitle` | `"Inversiones"` | `"Investments"` |
| `investmentsKpiTotalValue` | `"Valor total"` | `"Total value"` |
| `investmentsKpiTotalInvested` | `"Total invertido"` | `"Total invested"` |
| `investmentsKpiPnL` | `"Ganancia / Pérdida"` | `"Gain / Loss"` |
| `investmentsHoldingsTitle` | `"Cartera"` | `"Holdings"` |
| `investmentsEmptyHoldings` | `"Conecta un plugin para ver tus inversiones"` | `"Connect a plugin to see your investments"` |
| `investmentsCatalogTitle` | `"Conectores disponibles"` | `"Available connectors"` |
| `investmentsComingSoon` | `"Próximamente"` | `"Coming soon"` |
| `investmentsConnect` | `"Conectar"` | `"Connect"` |
| `navInvestments` | `"Inversiones"` | `"Investments"` |

---

## 2026-07-14 — Frontend: InvestmentsPage Skeleton (Phase 1, Slices 2–4)

**Author:** Vision (Frontend Engineer)  
**Status:** Shipped

### What was built

Slices 2, 3, and 4 of the investments plugin skeleton, per the specs from Wanda and Shuri.

### Key Decisions

#### Loading/error scope

The `loading` / `error` state-boxes replace only the `.plugin-catalog` content inside `.investments-catalog-card`, not the entire page. This lets the KPI row and holdings card render immediately (they have no async dependency in Phase 1), giving a better perceived performance. The spinner lives inside the catalog card, consistent with the `.state-box` pattern used in other cards across the app.

#### No fallback to mock on real error

Unlike summary endpoints (which fall back silently to mock data), `getInvestmentPlugins()` surfaces real errors directly — it does NOT fall back to mock on fetch failure. Rationale: the endpoint is stable and static; a real error (e.g. 401, network down) should be visible to the user rather than silently showing stale mock data. Consistent with the `getRules()`/`confirmImport()` pattern for stable endpoints.

#### Demo mode (VITE_USE_MOCK=1)

`mockGetInvestmentPlugins()` returns all 3 plugins with `status: "coming_soon"`, matching the live backend stub exactly. Demo mode is fully functional.

### Implementation Summary

- **File:** `frontend/src/pages/InvestmentsPage.tsx` — full skeleton component
- **Route:** `/investments` added to `App.tsx`
- **Nav:** 💰 item added to `Layout.tsx`
- **Type:** `InvestmentPlugin` added to `frontend/src/types.ts`
- **Client:** `getInvestmentPlugins()` in `client.ts` + `mockGetInvestmentPlugins()` in `mock.ts`
- **i18n:** 10 keys added to `Dict`, `es.ts`, `en.ts` (investmentsTitle, investmentsKpiTotalValue, investmentsKpiTotalInvested, investmentsKpiPnL, investmentsHoldingsTitle, investmentsEmptyHoldings, investmentsCatalogTitle, investmentsComingSoon, investmentsConnect, navInvestments)

### CSS Note

All required class names were confirmed already present in `index.css` per Wanda's spec. No CSS was added by Vision.

---

## 2026-07-14 — QA: Investments Backend Tests (Phase 1, Slice 6)

**Author:** Barton (Tester / QA)  
**Status:** Shipped

### Tests Implemented

`tests/api/test_investments.py` — 6 tests, all passing.

| Test | What it checks |
|---|---|
| `test_plugins_401_unauthenticated` | No cookie → 401 (auth guard is active) |
| `test_plugins_200_returns_list_of_three` | Authenticated → 200, exactly 3 plugins |
| `test_plugins_all_required_keys_present` | Every object has all 7 required keys |
| `test_plugins_all_status_coming_soon` | All `status == "coming_soon"` |
| `test_plugins_correct_id_set` | Id set matches `{indexa-capital, generic-broker, crypto-exchange}` exactly |
| `test_plugins_supported_features_nonempty` | Every plugin has a non-empty `supported_features` list |

### Implementation Details

The endpoint is a static in-memory registry with no DB access. Authenticated tests use the shared conftest `client` fixture (pre-bypasses `get_current_user`). The 401 test uses a local `unauthenticated_client` fixture that overrides only `get_db` and sends no cookie, so the real `get_current_user` raises 401 before any DB interaction.

### Smoke Set Result

`tests/api/test_auth.py tests/api/test_spa_fallback.py tests/api/test_investments.py`  
→ **43 passed, 0 failed**. No regressions.

### Frontend Test Infra Assessment

**Result: NO.** `frontend/package.json` has no `test` script and no vitest/jest devDependency. There is no `@testing-library/react`, `vitest`, or `jest` in `devDependencies`.

**Recommendation:** Scaffolding frontend test infra (vitest + @testing-library/react) is a non-trivial one-time setup task. Since Vision's Investments page exists now, defer frontend test implementation until the coordinator decides whether frontend unit tests are in scope for this project. When that decision is made, Barton can write the nav-link and coming-soon render test in a single session.

---
