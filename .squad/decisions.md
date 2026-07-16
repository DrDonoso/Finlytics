# Merchant Normalization Feature — REMOVED/REVERTED

**Date:** 2026-07-16T12:30:00+02:00  
**Owner request:** DrDonoso rejected the merchant-normalization feature ("no me convence esta parte de los comercios"). Coordinator removed it entirely and retained only the palette work (Wanda).

## Decision

Merchant Normalization (Slice 1 backend + Slice 2 UI) is REVERTED to HEAD state:
- DB migration 0016 removed; downgraded to 0015 (`alembic upgrade head` → head is now 0015_add_portfolio_cache.py)
- Dropped `merchants`, `merchant_aliases` tables
- Dropped `transactions.canonical_merchant_id` and `transactions.merchant_resolution_source` columns
- Transaction data intact; no data loss

## Files removed

- `alembic/versions/0016_add_merchant_normalization.py`
- `src/finlytics/api/merchants.py` (Slice 1 endpoints)
- `src/finlytics/db/merchant_normalization.py` (deterministic resolver)
- `frontend/src/pages/MerchantsPage.tsx` (Slice 2 UI)
- `tests/api/test_merchants.py`
- `tests/test_merchant_normalization.py`
- 38-line "Merchant normalization management" i18n block from `frontend/src/i18n/{index,es,en}.ts` (kept pre-existing merchant keys for TopMerchants panel, rules, columns)

## Reverted to HEAD

- `src/finlytics/api/schemas.py`
- `src/finlytics/app.py`
- `src/finlytics/db/models.py`
- `src/finlytics/db/queries.py`
- `src/finlytics/db/repository.py`
- `frontend/src/App.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/mock.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/CategorySelect.tsx`
- `frontend/src/components/Layout.tsx`

## Retained

Color palettes (Wanda) and palette-aware charts remain deployed. This decision supersedes the earlier merchant-normalization decision entries from Shuri and Vision (both marked reverted).

## Verification

- Docker rebuild: alembic_version column = 0015 ✓
- merchants table: gone ✓
- OpenAPI schema: 0 /merchants routes ✓
- /api/categories returns 401 (auth-gated correctly) ✓
- Palette bootstrap served ✓
- Container healthy on :7777 ✓

---

# Wanda — Palette-aware finance semantic colors

**Date:** 2026-07-16
**Owner request:** DrDonoso wanted analytics charts and the rest of the app to feel cohesive across accent palettes instead of always using the exact same red/green tones.

## Decision

`--income` and `--expense` are now palette-aware tonal variants for all non-classic palettes, with matching `--income-rgb`, `--expense-rgb`, `--income-bright`, and `--expense-bright` derived tokens. Classic keeps the previous defaults exactly (`#22c55e` income, `#ef4444` expense).

Meaning is preserved: income/positive remains unmistakably green, and expense/negative remains unmistakably red. Light and dark palette overrides are defined in `frontend/src/index.css`.

## Applied scope

- Chart semantics: cashflow Sankey ribbons now use `rgba(var(--income-rgb), …)` / `rgba(var(--expense-rgb), …)`.
- Heatmap expense intensity now derives from `--expense*`, so it follows the selected palette.
- Existing tokenized CSS for KPIs, transaction totals, import/error states, investment P&L, provider gains, and returns matrix now inherits the palette-aware semantic tokens.

## Guardrail

Category identity colors remain untouched: backend `category.color`, categorical fallback arrays, merchant/category slice colors, provider colors, asset-class colors, and instrument palettes are not reinterpreted as income/expense semantics.

---

# Vision decision — Merchant management UI Slice 2

**Date:** 2026-07-16T11:59:01+02:00  
**Owner:** Vision  
**Scope:** Frontend UI on top of Shuri's deployed merchant-normalization Slice 1 backend.

## Decisions implemented

1. **Placement:** The page lives at `/settings/merchants`, nested under `SettingsLayout`, and appears in sidebar under `Ajustes → Datos → Comercios` beside Categories/Tags/Accounts.
2. **Client contract:** Added typed client methods for the existing backend endpoints: list/create/update merchants, add/delete aliases, backfill, and unmatched queue. Mock equivalents are available for `VITE_USE_MOCK=1`.
3. **Defaults language:** The UI explicitly explains merchant default category/tags as "fill if missing" only, matching the locked Slice 1 product decision.
4. **Soft delete:** No hard-delete UI exists for canonical merchants. The action is "Deactivate", implemented as `PATCH active:false`.
5. **Alias behavior:** Alias add/delete is presented as deterministic and applying to all matching transactions (past + future). Regex is hidden behind an advanced toggle; exact/normalized/contains/prefix are the default modes.
6. **Unmatched queue:** Unknown merchants are not auto-created. The "Sin mapear" section lets the owner map raw text to an existing merchant or create a new merchant and immediately add a normalized alias for that raw text.

## Known backend seam

`GET /api/merchants` currently returns canonical merchants with `alias_count`, but Slice 1 does not expose a read endpoint for existing aliases. The page therefore shows alias counts and any aliases added during the current session. A future `GET /api/merchants/{id}/aliases` (or aliases embedded in `MerchantOut`) would allow complete alias listing.

## Files touched

- `frontend/src/pages/MerchantsPage.tsx`
- `frontend/src/api/client.ts`
- `frontend/src/api/types.ts`
- `frontend/src/api/mock.ts`
- `frontend/src/components/CategorySelect.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/App.tsx`
- `frontend/src/i18n/index.ts`
- `frontend/src/i18n/es.ts`
- `frontend/src/i18n/en.ts`
- `.squad/agents/vision/history.md`
- `.squad/decisions/inbox/vision-merchant-ui-slice2.md`

## Validation

`cd frontend && npm run build` passed with zero TypeScript errors. The existing Vite chunk-size warning remains expected.

---

## BATCH STATUS: Finlytics Feedback Batch 5 (2026-07-15)

**Summary:** 2 feature items completed + verified in Docker. Heatmap scaling problem solved + ESPP upload reminder shipped.

1. **Wanda:** SpendingHeatmap redesign spec — 3 adaptive modes (Daily ≤182d GitHub-calendar / Compact 183–547d in-card scroll / Monthly-Grid >547d 12×year always-fits). Root-cause CSS fix (.heatmap-card overflow:hidden + .heatmap-outer width:100%) + full CSS rewrite + 3-mode logic + monthGrid aggregation. Spec: `.squad/decisions/inbox/wanda-heatmap-redesign.md`.

2. **Shuri:** ESPP purchase-reminder endpoint — GET /api/investments/fidelity/reminder → {overdue, expected_date, period_label, last_lot_date}. Backend functions: _last_weekday_of_month + _expected_espp_dates + compute_espp_reminder (pure, fully testable). 5-day grace window. 4 test cases, all passing. Spec: `.squad/decisions/inbox/shuri-espp-reminder.md`.

3. **Vision:** Implemented both — SpendingHeatmap.tsx (3-mode detection, monthGrid useMemo, Intl date labels, render branching) + index.css (complete rewrite, heatmap tokens, overflow fix, monthly-grid CSS). ESPP banner on Inicio (Dashboard) + Fidelity view (via /reminder endpoint) — amber badge with i18n + Link to import. Frontend types + client method + i18n keys added. Build: 0 errors TS. Implementation spec: `.squad/decisions/inbox/vision-heatmap-espp-reminder.md`.

4. **Rocket:** Rebuilt docker-compose.local.yml; no new migrations (head 0015); /api/investments/fidelity/reminder verified 401 (auth-gated); heatmap overflow fixed in DevTools; ESPP banner displays correctly when overdue; running :7777.

5. **Coordinator:** Cadence analysis — ESPP purchases (SP) are consistent year-round at quarter-end (last business day Mar/Jun/Sep/Dec, 4/yr); dividend reinvestments (DO) irregular per MSFT calendar. Owner's question answered: "quarterly, plus unexpected dividends".

**Outcome:** ✅ Heatmap scaling fixed (3-mode + adaptive cellsize) | ✅ ESPP import reminder endpoint shipped + banner integrated | ✅ Cadence analysis delivered | ⏳ Pending: owner acceptance + checkpoint commit of feature code.

---

# Decisions Log

## INTEGRATION STATUS: Fidelity ESPP Connector — Full Implementation + Refinements Complete (2026-07-15)

**Fidelity ESPP:**  
Connector implemented (all phases: foundation + parser + endpoints), Fury APPROVED, running in Docker at http://localhost:7777; repo code uncommitted pending owner test; Dockerfile npm-in-Docker workaround flagged for CI deploy follow-up.

**Fidelity Refinements (Daily Evolution + Price Top-Up):**  
Shuri delivered two post-integration refinements:
1. **Daily market-day chart resolution** — evolution series now emits one point per MSFT trading day (vs weekly) for ranges up to ~6 years. 1089 tests passed.
2. **Incremental price top-up** — `topup_recent_prices()` fetches Yahoo history and UPSERTs to settle intraday snapshots to official closes daily. Last stored day is corrected on next read. 1104 tests passed.

**Overall status:** Fidelity ESPP fully integrated. Daily chart + sortable/paginated lots table with tooltips. Price refresh on-demand (≤1 fetch/business day, settled-daily model).

---


## INTEGRATION STATUS: Finlytics UX Batch — Nav Restructure + Investment Overview + Indexa Cache (2026-07-15)

**UX Batch Scope:** Navigation restructure with new "Finanzas" 💳 group consolidating Transacciones/Tendencias/Extractos + FinancesOverviewPage; Inversiones converted to direct NavLink with combined-overview landing page; Indexa 24h portfolio cache with async refresh; Fidelity combined-overview endpoint; Settings 4-group mapping (Datos/Reglas/Sistema/Aplicación); Tendencias title fix.

**Status:** All 5 owner points implemented + verified in Docker. Repo feature code UNCOMMITTED pending owner sign-off. All agent deliverables merged into this log.

**Key Artifacts:**
- Nav restructure spec + FinancesOverviewPage proposal (Wanda)
- Indexa portfolio cache migration (Shuri) — 1112 tests passed
- Combined-overview endpoint (Shuri) — 8 tests, 1120 total
- Frontend implementation (Vision) — nav restructure, 2 overview pages, i18n, CSS — build 0 errors
- Nullability contract fix (Coordinator) — combined-overview fields typed number|null, guarded usages

---

## BATCH STATUS: Finlytics Feedback Batch 4 (2026-07-15)

**Summary:** 3 feature items completed + verified in Docker.

1. **Shuri:** New GET /api/summary/months endpoint — {months: ["YYYY-MM"...ASC], latest: "YYYY-MM"|null}. Reuses get_statement_months over Transaction. Tests: 1130 passed.

2. **Vision:** (1) Connector descriptions localized via frontend i18n (PLUGIN_DESC_KEYS) instead of backend English. (2) Inicio KPIs default to LAST month with transaction data + Mes/Año label + prev/next month nav (consumes /api/summary/months). (3) "Ver transacciones" button added to Finanzas → /transactions. Build: 0 errors TS.

3. **Coordinator:** Caught + corrected endpoint contract mismatch before rebuild (vision assumed /api/overview/months bare array; actual is /api/summary/months {months, latest}).

4. **Rocket:** Rebuilt docker-compose.local.yml; no new migrations (head 0015); /api/summary/months verified 401 (route wired); new frontend chunk served; running :7777.

**Outcome:** ✅ 3 items implemented + verified | ⏳ Pending owner decisions: heatmap scaling proposal (GitHub-calendar + in-card scroll + weekly for long ranges) + checkpoint commit of uncommitted feature code.

---

## Vision: Inicio/Finanzas Split + InvestmentSnapshotCard + ImportSourcePicker (2026-07-15)

**Fecha:** 2026-07-15T16:20:19+02:00  
**Autor:** Vision (Frontend Engineer)  
**Solicitado por:** DrDonoso (David)  
**Estado:** SHIPPED — build limpio, 0 errores TS

### Contexto

Batch de 5 items de feedback del owner implementa la propuesta MOVE+REPLACE de Wanda (`.squad/decisions.md` § "PROPOSAL: Recomendación: Inicio vs Finanzas") — esta decisión estaba marcada como pendiente.

### Decisiones implementadas

**1. Connectors — Eliminar botón "Resumen" de Fidelity ESPP cuando conectado**  
Card connected muestra solo: badge ✓ + botón Desconectar. Archivo: `ConnectorsPage.tsx` — `renderFidelityEsppCard`.

**2. Settings groups collapsed por defecto**  
Los 4 grupos colapsables (Datos/Reglas/Sistema/Aplicación) usan `useState(false)`. Archivo: `Layout.tsx` líneas ~57-60.

**3. Split Inicio vs Finanzas — MOVE + REPLACE** (Principio: cada widget tiene UN único hogar. Sin duplicación.)

| Componente | Antes | Ahora |
|---|---|---|
| `GlobalFilterBar` | ✅ | ❌ |
| `SpendingByCategory` | ✅ | ❌ |
| `TopMerchants` | ✅ | ❌ |
| `SpendingHeatmap` | ✅ | ❌ |
| `CategoryMovers` | ✅ | ❌ |
| `KpiCards` | ✅ Filtrable | ✅ Mes actual fijo |
| `InvestmentSnapshotCard` | ❌ | ✅ Nuevo |
| Botón Importar | File picker | `ImportSourcePicker` |

**Nota:** `defaultRange()` devuelve mes anterior; Dashboard usa `currentMonthRange()` inline para mes en curso.

**Finanzas:** Hereda GlobalFilterBar, KpiCards (con previousOverview), SpendingByCategory, TopMerchants; AÑADE SpendingHeatmap, CategoryMovers, ImportLauncher + ImportModal.

**4. Botón Importar en Finanzas**  
`ImportLauncher` + `ImportModal` + `refreshKey` + `toast` en `FinancesOverviewPage.tsx`. Tras importar, `refreshKey` dispara re-fetch de todos los datos.

**5. Inicio: Importar → ImportSourcePicker (data-driven)**  
Nuevo componente `ImportSourcePicker.tsx`:
- Siempre lista "Extractos bancarios" (file picker).
- Fetches `GET /api/investments/plugins` y filtra `import_route !== null`.
- Fidelity ESPP → `import_route: '/investments/fidelity-espp'` (Shuri backend).
- Extensible: futuros plugins aparecen automáticamente.

Tipo actualizado: `InvestmentPlugin.import_route: string | null` en `api/types.ts`.

**6. Nuevo componente: InvestmentSnapshotCard**  
`frontend/src/components/InvestmentSnapshotCard.tsx`:
- Fetches `GET /api/investments/combined-overview`.
- Loading → spinner. Error → error box. Vacío → mensaje + link "Ver inversiones →".
- Populated → total_value_eur grande + desglose por provider (icon + name + value_eur).
- `fmtEur(null)` → "—".
- Header siempre muestra link a `/investments`. CSS: clases `inv-snapshot-*` en `index.css`.

### Archivos modificados/creados

| Archivo | Cambio |
|---|---|
| `frontend/src/api/types.ts` | `InvestmentPlugin.import_route: string \| null` |
| `frontend/src/api/mock.ts` | `import_route` en todos plugins; fidelity-espp entry |
| `frontend/src/i18n/index.ts` | 7 nuevas claves (invSnapshot*, importPicker*) |
| `frontend/src/i18n/es.ts` | 7 traducciones ES |
| `frontend/src/i18n/en.ts` | 7 traducciones EN |
| `frontend/src/components/Layout.tsx` | sg* collapsed por defecto |
| `frontend/src/pages/ConnectorsPage.tsx` | Eliminado Link "Resumen" en Fidelity connected |
| `frontend/src/pages/Dashboard.tsx` | Reescrito como hub cross-domain |
| `frontend/src/pages/FinancesOverviewPage.tsx` | Heatmap + Movers + Import añadidos |
| `frontend/src/index.css` | CSS para inv-snapshot-* e import-picker-* |
| `frontend/src/components/InvestmentSnapshotCard.tsx` | **Nuevo** |
| `frontend/src/components/ImportSourcePicker.tsx` | **Nuevo** |

**Build:** `tsc --noEmit && vite build` → 0 TypeScript errors, built in 6.48s ✓

---

# DESIGN SPEC + PROPOSAL: Reestructuración de navegación y páginas overview

**Autora:** Wanda (UX/UI Designer)  
**Fecha:** 2026-07-15  
**Implementador:** Vision (Frontend Engineer)  
**Estado:** Spec lista para implementación

---

## A) Reestructuración del nav

### Nombre del nuevo grupo: **"Finanzas"** 💳

**Justificación:** "Finanzas" es el término paraguas que engloba naturalmente Transacciones, Tendencias y Extractos — son tres vistas sobre la misma realidad financiera (gastos/ingresos). "Movimientos" suena demasiado operacional; "Cuentas" se confunde con el sub-ajuste de cuentas bancarias. "Finanzas" es breve, claro, y no colisiona con ningún concepto existente.

**Icono:** 💳 (tarjeta de crédito — representa dinero en movimiento, distinto de 💰 Inversiones y 🏠 Inicio).

### Árbol de nav resultante

```
🏠 Inicio                    /                    NavLink directo
💳 Finanzas (expandible)      /finances            sidebar-section-btn → overview
   ├── 📋 Transacciones       /transactions        NavLink sub-item
   ├── 📈 Tendencias          /analytics           NavLink sub-item
   └── 📄 Extractos           /statements          NavLink sub-item
💰 Inversiones (directo)      /investments         NavLink directo (NO expandible)
⚙️ Ajustes (expandible)       (sin ruta propia)    sidebar-section-btn → toggle
   ├── DATOS
   │   ├── Categorías         /settings/categories
   │   ├── Etiquetas          /settings/tags
   │   └── Cuentas            /settings/accounts
   ├── REGLAS
   │   └── Reglas             /settings/rules
   ├── SISTEMA
   │   ├── Conectores         /settings/connectors
   │   └── Copia de seguridad /settings/backup
   └── APLICACIÓN
       └── Apariencia         /settings/appearance
```

### Comportamiento expandir/colapsar — Finanzas

Patrón **idéntico** al acordeón de Ajustes, con una diferencia clave: **al hacer clic en el botón `sidebar-section-btn`, ADEMÁS de toggle expand/collapse, navega a `/finances`** (como hace Inversiones actualmente).

```tsx
// Layout.tsx — nuevo estado
const isOnFinances = ['/finances', '/transactions', '/analytics', '/statements']
  .some(p => location.pathname.startsWith(p))
const [financesExpanded, setFinancesExpanded] = useState(isOnFinances)

useEffect(() => {
  if (isOnFinances && !financesExpanded) setFinancesExpanded(true)
}, [isOnFinances])
```

**Click del botón:**
```tsx
onClick={() => {
  setFinancesExpanded(v => !v)
  navigate('/finances')
}}
```

### Inversiones: de expandible a directo

**Eliminar:** el bloque `sidebar-section` + accordion + `navInvestmentsOverview` sub-link.  
**Reemplazar con:** un `NavLink` directo, igual que Inicio o el antiguo Transacciones:

```tsx
<NavLink to="/investments" className={navLinkClass}>
  <span className="nav-icon">💰</span>
  <span className="nav-label">{t.navInvestments}</span>
</NavLink>
```

Los sub-links de plugins conectados (Indexa, Fidelity) **se eliminan de la nav**. La navegación a cada plugin se hace desde la propia página `/investments` (cards clicables). Esto simplifica el sidebar y reduce carga cognitiva en mobile.

### Comportamiento mobile

- El sidebar overlay funciona exactamente igual (hamburger → overlay → cierre al navegar).
- El acordeón de Finanzas en mobile: al tocar "Finanzas" → navega a `/finances` + expande sub-items. Si ya está expandido y toca de nuevo → colapsa (pero NO navega, ya estás ahí).
- Inversiones: tap directo → `/investments` → cierra sidebar.

### Claves i18n nuevas necesarias

| Clave | ES | EN | Tipo |
|---|---|---|---|
| `navFinances` | `'Finanzas'` | `'Finances'` | `string` |
| `financesOverviewTitle` | `'Finanzas'` | `'Finances'` | `string` |
| `settingsGroupRules` | `'Reglas'` | `'Rules'` | `string` |
| `settingsGroupSystem` | `'Sistema'` | `'System'` | `string` |
| `settingsGroupApp` | `'Aplicación'` | `'App'` | `string` |
| `invCombinedTitle` | `'Inversiones'` | `'Investments'` | `string` |
| `invCombinedTotalValue` | `'Valor total'` | `'Total value'` | `string` |
| `invCombinedTotalGain` | `'Ganancia total'` | `'Total gain'` | `string` |
| `invCombinedByProvider` | `'Por proveedor'` | `'By provider'` | `string` |
| `invCombinedByAssetClass` | `'Por tipo de activo'` | `'By asset class'` | `string` |

**Clave eliminable:** `navInvestmentsOverview` (ya no hay sub-link "Resumen").

### Archivos que Vision debe modificar

| Archivo | Cambio |
|---|---|
| `frontend/src/components/Layout.tsx` | Reestructurar nav: añadir Finanzas expandible, convertir Inversiones a directo, reagrupar Ajustes |
| `frontend/src/App.tsx` | Añadir ruta `/finances` → `FinancesOverviewPage` |
| `frontend/src/pages/FinancesOverviewPage.tsx` | **CREAR** — nueva página overview (ver sección C) |
| `frontend/src/i18n/index.ts` | Añadir tipos para claves nuevas |
| `frontend/src/i18n/es.ts` | Añadir valores ES |
| `frontend/src/i18n/en.ts` | Añadir valores EN |

---

## B) Overview combinado de Inversiones (`/investments`)

### Concepto

La página `/investments` deja de ser un catálogo de plugins conectados y se convierte en un **overview consolidado** que muestra el patrimonio total across proveedores (actualmente Indexa Capital + Fidelity ESPP).

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  h1: "Inversiones"                                       │
├──────────────────────────────────────────────────────────┤
│  KPI strip (3 cards, estilo .inv-kpi-card existente)     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Valor    │  │ Invertido│  │ Ganancia  │               │
│  │ total    │  │ total    │  │ / Pérdida │               │
│  │ €XX,XXX  │  │ €XX,XXX  │  │ +€X,XXX  │               │
│  │          │  │          │  │ (+X.X%)   │               │
│  └──────────┘  └──────────┘  └──────────┘               │
├──────────────────────────────────────────────────────────┤
│  Donuts row (2-col grid, reutiliza .inv-donuts-row)      │
│  ┌─────────────────────┐  ┌─────────────────────────┐   │
│  │  🍩 Por proveedor    │  │  🍩 Por tipo de activo   │   │
│  │  (Indexa / Fidelity)│  │  (RV / RF / Cash / ESPP)│   │
│  │  + leyenda compacta │  │  + leyenda compacta     │   │
│  └─────────────────────┘  └─────────────────────────┘   │
├──────────────────────────────────────────────────────────┤
│  Provider cards (links a detalle)                        │
│  ┌────────────────────────────┐  ┌──────────────────┐   │
│  │ 🏦 Indexa Capital          │  │ 📊 Fidelity ESPP │   │
│  │ €XX,XXX · +X.X%           │  │ €XX,XXX · +X.X%  │   │
│  │ → Ver detalle              │  │ → Ver detalle     │   │
│  └────────────────────────────┘  └──────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

### Mobile stacking (≤900px)

- KPI strip: se mantiene en row (flex-wrap si es necesario; 3 cards caben en 360px con el sizing existente de `.inv-kpi-card`).
- Donuts row: `.inv-donuts-row` ya tiene `grid-template-columns: 1fr` a ≤900px → stacks automáticamente.
- Provider cards: 1 columna, full-width.

### API: shape de respuesta que Shuri debe construir

**Endpoint:** `GET /api/investments/combined-overview`

```json
{
  "total_value_eur": 45230.50,
  "total_invested_eur": 38000.00,
  "total_gain_loss_eur": 7230.50,
  "total_gain_loss_pct": 19.03,
  "by_provider": [
    { "provider": "indexa", "label": "Indexa Capital", "value_eur": 32000.00, "pct": 70.7 },
    { "provider": "fidelity", "label": "Fidelity ESPP", "value_eur": 13230.50, "pct": 29.3 }
  ],
  "by_asset_class": [
    { "asset_class": "equity", "label": "Renta Variable", "value_eur": 28000.00, "pct": 61.9 },
    { "asset_class": "fixed_income", "label": "Renta Fija", "value_eur": 4000.00, "pct": 8.8 },
    { "asset_class": "espp_stock", "label": "ESPP Stock", "value_eur": 13230.50, "pct": 29.3 }
  ],
  "providers": [
    {
      "id": "indexa",
      "name": "Indexa Capital",
      "icon": "🏦",
      "value_eur": 32000.00,
      "gain_loss_eur": 5200.00,
      "gain_loss_pct": 19.4,
      "route": "/investments/indexa"
    },
    {
      "id": "fidelity",
      "name": "Fidelity ESPP",
      "icon": "📊",
      "value_eur": 13230.50,
      "gain_loss_eur": 2030.50,
      "gain_loss_pct": 18.1,
      "route": "/investments/fidelity"
    }
  ]
}
```

**Notas para Shuri:**
- `by_asset_class`: Indexa ya tiene `asset_type` por instrumento (equity, fixed_income, cash); Fidelity ESPP es todo equity (MSFT stock), asignar `espp_stock` como clase propia para visibilidad.
- Valores en EUR (Fidelity hace conversión USD→EUR con el rate almacenado).
- Si un provider no tiene conexión activa, omitirlo del response (no incluir con valor 0).
- Los `label` son para el donut; i18n los localiza en frontend.

### CSS guidance (para que Vision aplique)

- Reutilizar `.inv-kpi-card` existente para los 3 KPIs.
- Reutilizar `.inv-donuts-row` (grid 1fr 1fr, gap 12px) para los donuts.
- Reutilizar `.cat-chart-layout` + `.cat-donut-wrap` + `.cat-donut-center` para cada donut (patrón Recharts PieChart).
- Los provider cards: usar clase `.inv-provider-card` nueva, estilo similar a `.plugin-card.connector-card--connected` pero con métricas inline. CSS sugerido:

```css
.inv-provider-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.inv-provider-card {
  /* hereda .card base */
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.inv-provider-card:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.inv-provider-card__value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}
.inv-provider-card__gain {
  font-size: 13px;
  font-weight: 500;
}
.inv-provider-card__gain--positive { color: var(--income); }
.inv-provider-card__gain--negative { color: var(--expense); }
```

### Fallback: sin providers conectados

Mantener el estado vacío actual (`investments-empty` con CTA → Conectores). Mostrar solo si `providers.length === 0` (o 404 del endpoint).

---

## C) PROPUESTA: Página overview de grupo Finanzas — `/finances`

> **⚠️ Esta sección es una PROPUESTA para el owner. Wanda recomienda; David decide.**

### Principio rector

La página de Finanzas NO es un duplicado de Inicio. Es un **panel de control operativo del gasto**: responde "¿cómo está mi dinero este mes?" sin ruido. Inicio es el dashboard de bienvenida (más completo, con acciones rápidas de importación). Finanzas es la vista de análisis a la que vuelves a diario.

### Selección de componentes y justificación

| # | Componente | ¿Incluir? | Justificación |
|---|---|---|---|
| 1 | **GlobalFilterBar** | ✅ SÍ | **Imprescindible.** Es la herramienta de segmentación (rango, cuenta, categoría, tags). Sin ella, la página sería estática. Va arriba, primer elemento — es el "control" de todo lo que hay debajo. |
| 2 | **KpiCards** | ✅ SÍ | **Core.** Los 4 KPIs (ingresos, gastos, neto, saldo) son el resumen ejecutivo. Es lo primero que el ojo debe ver después de los filtros. Incluir con variantes `previousOverview` para comparativa mes anterior — el delta % es la métrica más valiosa de una vista financiera. |
| 3 | **SpendingByCategory** | ✅ SÍ | **Core.** El donut de categorías + tabla responde "¿en qué gasto?" — la pregunta más frecuente. Es el componente más interactivo (clic en categoría filtra todo lo demás). Va justo después de KPIs: jerarquía natural. |
| 4 | **TopMerchants** | ✅ SÍ | **Valioso.** Complementa SpendingByCategory: la categoría dice el "qué", el merchant dice el "dónde". Útil para detectar suscripciones olvidadas o gastos recurrentes. Va en row compartida con SpendingByCategory (patrón `.charts-row-category` existente). |
| 5 | **SpendingHeatmap** | ❌ NO | **Omitir.** El heatmap es valioso en Inicio como curiosidad ("¿qué día gasto más?") pero en un panel operativo es ruido visual. Es el componente más grande (365 celdas), con menor densidad informativa por pixel. No responde preguntas accionables del día a día. **Dejar exclusivo de Inicio** — es su diferenciador visual. |
| 6 | **CategoryMovers** | ❌ NO | **Omitir.** Los "movers" (categorías que más subieron/bajaron vs mes anterior) son interesantes pero redundantes cuando ya tienes KpiCards con delta % y SpendingByCategory. Aporta insight comparativo que es más apropiado para Tendencias (`/analytics`), donde ya convive con SpendingOverTime. **Dejar exclusivo de Inicio.** |

### Rationale condensado (para el owner)

> **David:** La página de Finanzas es tu "vista rápida de gasto". Propongo 4 componentes: filtros + KPIs + donut de categorías + top merchants. Son los que respondes las 3 preguntas clave: "¿cuánto?" (KPIs), "¿en qué?" (categorías), "¿dónde?" (merchants). Omito el heatmap y los movers porque son más "exploratorios" que "operativos" — se quedan en Inicio donde tienen más contexto. Si quieres, puedo añadir cualquiera de los dos, pero mi recomendación es mantener Finanzas enfocada y sin scroll innecesario en mobile.

### Layout propuesto

**Desktop (>900px):**
```
┌──────────────────────────────────────────────────────────┐
│  GlobalFilterBar (full-width)                            │
│  ┌──────────────────────────────────────────────────────┐│
│  │ KpiCards (row de 4 cards)                            ││
│  └──────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────┤
│  .charts-row-category (grid 1fr 1fr)                     │
│  ┌────────────────────┐  ┌──────────────────────────┐   │
│  │ SpendingByCategory │  │ TopMerchants             │   │
│  │ (donut + tabla)    │  │ (donut + lista)          │   │
│  └────────────────────┘  └──────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

**Mobile (≤600px):**
```
┌──────────────────────┐
│ GlobalFilterBar      │
│ (stacked/scrollable) │
├──────────────────────┤
│ KpiCards (2x2 grid)  │
├──────────────────────┤
│ SpendingByCategory   │
│ (full-width, donut   │
│  encima de tabla)    │
├──────────────────────┤
│ TopMerchants         │
│ (full-width)         │
└──────────────────────┘
```

Todo el CSS de layout ya existe (`.dashboard`, `.dashboard-header`, `.charts-row-category`). Vision solo necesita montar el JSX — **cero CSS nuevo** para esta página.

### Implementación para Vision

- **Archivo:** `frontend/src/pages/FinancesOverviewPage.tsx`
- **Estructura:** Clonar la lógica de data-fetching de `Dashboard.tsx` (filtros, overview, byCategory) pero **sin**: ImportModal, ImportLauncher, heatmap data, categoryMovers data, globalOverview (unfiltered), toast.
- **Ruta:** `/finances` en `App.tsx`.
- **Título de página:** usar `<h1 className="tx-page-title">{t.financesOverviewTitle}</h1>` (misma clase que Transacciones, consistencia visual).

---

## D) Reagrupación de Ajustes — 4 grupos

### Decisión original (de decisions.md, línea ~735)

La estructura acordada usa 4 etiquetas de grupo con i18n keys `settingsGroupData` / `settingsGroupRules` / `settingsGroupSystem` / `settingsGroupApp`.

### Estado actual (Layout.tsx)

Solo existe UN grupo label (`settingsGroupData`) y los 7 sub-links están TODOS bajo él, sin separación.

### Mapping correcto a aplicar

```
⚙️ Ajustes
 ├── settingsGroupData ("Datos" / "Data")
 │   ├── Categorías     /settings/categories   settingsSubCategories
 │   ├── Etiquetas      /settings/tags         settingsSubTags
 │   └── Cuentas        /settings/accounts     settingsSubAccounts
 ├── settingsGroupRules ("Reglas" / "Rules")
 │   └── Reglas         /settings/rules        navRules
 ├── settingsGroupSystem ("Sistema" / "System")
 │   ├── Conectores     /settings/connectors   settingsSubConnectors
 │   └── Copia de seg.  /settings/backup       settingsSubBackup
 └── settingsGroupApp ("Aplicación" / "App")
     └── Apariencia     /settings/appearance   settingsSubAppearance
```

**Este mapping es 100% fiel a la decisión original** (decisions.md §Structure, líneas 736-749). No hay ambigüedad.

### Implementación para Vision

Reemplazar el bloque `{settingsExpanded && (...)}` en Layout.tsx con:

```tsx
{settingsExpanded && (
  <div className="sidebar-subnav">
    {/* DATOS */}
    <span className="sidebar-group-label">{t.settingsGroupData}</span>
    <NavLink to="/settings/categories" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubCategories}</span>
    </NavLink>
    <NavLink to="/settings/tags" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubTags}</span>
    </NavLink>
    <NavLink to="/settings/accounts" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubAccounts}</span>
    </NavLink>

    {/* REGLAS */}
    <span className="sidebar-group-label">{t.settingsGroupRules}</span>
    <NavLink to="/settings/rules" className={navLinkClass}>
      <span className="nav-label">{t.navRules}</span>
    </NavLink>

    {/* SISTEMA */}
    <span className="sidebar-group-label">{t.settingsGroupSystem}</span>
    <NavLink to="/settings/connectors" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubConnectors}</span>
    </NavLink>
    <NavLink to="/settings/backup" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubBackup}</span>
    </NavLink>

    {/* APLICACIÓN */}
    <span className="sidebar-group-label">{t.settingsGroupApp}</span>
    <NavLink to="/settings/appearance" className={navLinkClass}>
      <span className="nav-label">{t.settingsSubAppearance}</span>
    </NavLink>
  </div>
)}
```

### i18n keys a añadir (3 faltan)

Las keys `settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp` **no existen** en el código actual (solo `settingsGroupData` fue creada). Vision debe añadir en `index.ts`, `es.ts`, `en.ts`:

```ts
// index.ts — añadir al tipo
settingsGroupRules: string
settingsGroupSystem: string
settingsGroupApp: string

// es.ts
settingsGroupRules: 'Reglas',
settingsGroupSystem: 'Sistema',
settingsGroupApp: 'Aplicación',

// en.ts
settingsGroupRules: 'Rules',
settingsGroupSystem: 'System',
settingsGroupApp: 'App',
```

---

## E) Fix del título de Tendencias (AnalyticsPage)

### Problema

`AnalyticsPage.tsx` usa:
```tsx
<h1 className="analytics-page-title">{t.analyticsTitle}</h1>
```

CSS de `.analytics-page-title` (index.css:942):
```css
.analytics-page-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
  margin: 0;
}
```

Mientras que `TransactionsPage.tsx` usa:
```tsx
<h1 className="tx-page-title">{t.txTitle}</h1>
```

CSS de `.tx-page-title` (index.css:2330):
```css
.tx-page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}
```

**Diferencia:** `analytics-page-title` es `18px / 600` vs `tx-page-title` es `22px / 700`. El estándar es `22px / 700` (también usado por `.investments-page-title`).

### Fix exacto

**Opción recomendada:** Cambiar AnalyticsPage.tsx para usar la misma clase `tx-page-title`:

```tsx
// AnalyticsPage.tsx, línea 89 — CAMBIAR:
<h1 className="analytics-page-title">{t.analyticsTitle}</h1>
// POR:
<h1 className="tx-page-title">{t.analyticsTitle}</h1>
```

Adicionalmente, el `<h1>` en AnalyticsPage está **dentro** de `.dashboard-header` (después del GlobalFilterBar), mientras que en TransactionsPage está en su propio `.tx-page-header`. Para consistencia estructural:

```tsx
// AnalyticsPage.tsx — CAMBIAR de:
<div className="dashboard-header">
  <GlobalFilterBar ... />
  <h1 className="analytics-page-title">{t.analyticsTitle}</h1>
</div>

// A:
<div className="tx-page-header">
  <h1 className="tx-page-title">{t.analyticsTitle}</h1>
</div>
<GlobalFilterBar ... />
```

Esto pone el título arriba (igual que Transacciones) y el FilterBar debajo. **Nota:** GlobalFilterBar usa `.dashboard-header` para padding, así que envolver en `<div className="dashboard-header">` si se necesita el spacing.

**Fix mínimo (si no se quiere reestructurar):** Solo cambiar la clase CSS en el `<h1>`:

```tsx
<h1 className="tx-page-title">{t.analyticsTitle}</h1>
```

Esto iguala tamaño y peso visual. **Recomiendo el fix mínimo** para evitar riesgo de romper el layout del GlobalFilterBar.

### CSS cleanup (opcional)

Después del fix, la regla `.analytics-page-title` en index.css (línea 942-947) queda huérfana y puede eliminarse.

---

## Resumen de trabajo para Vision

| Prioridad | Tarea | Archivos |
|---|---|---|
| 1 | Settings 4-group en Layout.tsx | Layout.tsx, i18n/* |
| 2 | Tendencias title fix | AnalyticsPage.tsx, (opcional: index.css cleanup) |
| 3 | Nav restructure: Finanzas expandible + Inversiones directo | Layout.tsx, App.tsx, i18n/* |
| 4 | FinancesOverviewPage | FinancesOverviewPage.tsx (nuevo), App.tsx |
| 5 | InvestmentsLandingPage → combined overview | InvestmentsLandingPage.tsx, i18n/* |

**Dependencia backend (punto B):** El overview combinado de inversiones necesita que Shuri construya `GET /api/investments/combined-overview` con el shape definido arriba. Vision puede maquetar con datos mock mientras tanto.


---

# Decision: Indexa Portfolio Cache — DB Cache + Async Background Refresh

**Date:** 2026-07-15  
**Author:** Shuri (Backend Engineer)  
**Status:** Implemented  
**Requested by:** DrDonoso (David)

---

## Problema

La vista Indexa Capital era lenta al abrirse porque el endpoint `GET /api/investments/portfolio` hacía llamadas en vivo a la API de Indexa en cada page load (~2-3 s de espera mínima, más con múltiples cuentas).

Owner spec: *"cachear en BD, congelar 1 día está bien, y que la búsqueda se haga en async en background."*

---

## Decisión

Implementar un caché de BD por conexión (`investment_portfolio_cache`) con ventana de frescura de **24 horas** y refresh asíncrono vía FastAPI `BackgroundTasks`.

---

## Diseño

### Nueva tabla: `investment_portfolio_cache`

| Columna | Tipo | Notas |
|---|---|---|
| `id` | Integer PK | autoincrement |
| `connection_id` | Integer UNIQUE FK → `investment_connections.id` | ON DELETE CASCADE |
| `payload` | JSON | `NormalizedPortfolio` serializado con `dataclasses.asdict()` |
| `fetched_at` | DateTime (timezone) | UTC del último fetch |

Una fila por conexión. ON DELETE CASCADE limpia la fila cuando se elimina la conexión.

### Comportamiento del endpoint

```
GET /api/investments/portfolio
→ para cada InvestmentConnection activa con token_enc:

  FRESH  (ahora − fetched_at < 24h)
    → retorna payload del caché. No toca Indexa.

  STALE  (ahora − fetched_at >= 24h)
    → retorna payload stale inmediatamente.
    → programa BackgroundTask(_bg_refresh_connection)
       que re-fetcha de Indexa y actualiza la fila DESPUÉS de enviar respuesta.
    → cache_stale=True en la respuesta.

  MISSING (sin fila de caché)
    → fetch en vivo de Indexa (primera carga, más lenta).
    → INSERT fila de caché.
    → retorna datos frescos.
```

### Campos opcionales añadidos a `InvestmentPortfolioOut`

```python
cached_at: str | None = None   # ISO datetime del fetch más antiguo (o None si vino en vivo)
cache_stale: bool = False      # True cuando se devuelven datos stale + background en curso
```

Son **aditivos y opcionales** — el frontend existente los ignora. Vision puede usarlos para un indicador de "últimos datos de hace X horas" si se desea.

### Guard `_refresh_in_flight: set[int]`

Módulo-nivel. Evita programar tareas duplicadas cuando múltiples requests llegan durante el ventana stale. Asyncio es single-threaded, el check-then-add es atómico sin Lock.

### `_bg_refresh_connection`

```python
async def _bg_refresh_connection(
    connection_id: int, token_enc: str,
    account_label_masked: str | None, plugin_id: str
) -> None
```

- Crea su propia sesión DB via `async_session_factory()`.
- Descifra token, valida con Indexa, fetcha portfolio.
- UPSERT de la fila de caché + `last_synced_at` en una sola transacción `async with bg_db.begin()`.
- `try/except Exception` con log warning — nunca crashea silenciosamente sin dejar rastro.
- `finally: _refresh_in_flight.discard(connection_id)`.

### Serialización

`_serialize_portfolio(p)` → `dataclasses.asdict(p)` (recursivo, JSON-safe).  
`_deserialize_portfolio(data)` → reconstruye jerarquía de dataclasses. Las claves de `months_pct`/`months_eur` se convierten de `str` (JSON) a `int` (Python): `{int(k): v for k, v in d.items()}`.

---

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Redis / TTL cache externo | Dependencia extra de infraestructura; innecesaria para el caso de uso single-user |
| In-memory cache (lo existente, 5 min) | No persiste entre reinicios; no cumple el req de 24h; no hace refresh async |
| Caché a nivel de `InvestmentPortfolioOut` (ya agregado) | Perdería granularidad por conexión; dificulta invalidación parcial |

---

## Impacto en tests

- **8 tests nuevos** en `tests/investments/test_portfolio_cache.py`: serialización (round-trip, claves int, None performance, drawdown), cache hit/miss/stale, in-flight guard.
- **2 tests existentes actualizados** (`test_portfolio_service_maps_holdings_gain_loss_and_returns`, `test_aggregate_single_account_passes_through_monthly_and_drawdown`): eliminado `_portfolio_cache.clear()`; añadido `execute_result.scalar_one_or_none.return_value = None` para simular cache miss.
- **Suite completa:** 1112 passed, 2 skipped, 0 failed.

---

## Nota para Vision

El campo `cache_stale: bool` está disponible en la respuesta de `GET /api/investments/portfolio`. Si se quiere mostrar un indicador tipo *"Datos de hace X horas — actualizando..."* en la IndexaView, Vision puede leer `cache_stale` y `cached_at` para construirlo. No es obligatorio; el comportamiento actual es correcto sin cambios de frontend.


---

# Decision: Combined Investments Overview Endpoint

**Autora:** Shuri (Backend Engineer)  
**Fecha:** 2026-07-15  
**Estado:** Implementado ✅

---

## Endpoint

`GET /api/investments/combined-overview`  
→ Autenticado (session cookie, igual que todos los endpoints de inversiones)

---

## Response Shape (implementada — coincide exactamente con spec de Wanda)

```json
{
  "total_value_eur": 48518.52,
  "total_invested_eur": 27500.00,
  "total_gain_loss_eur": 21018.52,
  "total_gain_loss_pct": 76.4310,
  "by_provider": [
    { "provider": "indexa", "label": "Indexa Capital", "value_eur": 30000.00, "pct": 61.83 },
    { "provider": "fidelity", "label": "Fidelity ESPP",  "value_eur": 18518.52, "pct": 38.17 }
  ],
  "by_asset_class": [
    { "asset_class": "equity",       "label": "Renta Variable", "value_eur": 20000.00, "pct": 41.22 },
    { "asset_class": "espp_stock",   "label": "ESPP Stock",     "value_eur": 18518.52, "pct": 38.17 },
    { "asset_class": "fixed_income", "label": "Renta Fija",     "value_eur": 8000.00,  "pct": 16.49 },
    { "asset_class": "cash",         "label": "Efectivo",       "value_eur": 2000.00,  "pct": 4.12  }
  ],
  "providers": [
    {
      "id": "indexa",
      "name": "Indexa Capital",
      "icon": "🏦",
      "value_eur": 30000.00,
      "gain_loss_eur": 5000.00,
      "gain_loss_pct": 20.0,
      "route": "/investments/indexa"
    },
    {
      "id": "fidelity",
      "name": "Fidelity ESPP",
      "icon": "📊",
      "value_eur": 18518.52,
      "gain_loss_eur": 16018.52,
      "gain_loss_pct": 640.74,
      "route": "/investments/fidelity"
    }
  ]
}
```

### Campos siempre presentes
- `total_value_eur` — siempre float (0.0 si sin conexiones)
- `by_provider`, `by_asset_class`, `providers` — siempre arrays (vacíos si sin conexiones)

### Campos opcionales (null posible)
- `total_invested_eur`, `total_gain_loss_eur`, `total_gain_loss_pct` — null si no hay datos de coste o si la suma es inconsistente
- `providers[].value_eur`, `providers[].gain_loss_eur`, `providers[].gain_loss_pct` — null cuando precio MSFT no disponible

---

## Fuentes de datos

| Campo | Fuente |
|---|---|
| Indexa `value_eur`, holdings, asset classes | `inv_service.get_portfolio()` — caché 24h DB |
| Fidelity `value_eur` | `Σ(lot.shares) × MSFT_close_usd × fx_eur_usd` via `get_latest_price()` |
| Fidelity `invested_eur` | `Σ(lot.cost_basis)` — siempre conocido cuando hay lots |
| `espp_stock` label | Clase fija para Fidelity ESPP (visibilidad en donut separada de `equity` Indexa) |

---

## Labels de asset class (por defecto)

| `asset_class` | `label` |
|---|---|
| `equity` | Renta Variable |
| `fixed_income` | Renta Fija |
| `cash` | Efectivo |
| `espp_stock` | ESPP Stock |
| `other` | Otros |
| `mixed` | Mixto |

> Los labels son defaults; i18n los localiza en el frontend.

---

## Comportamiento por estado

| Estado | Respuesta |
|---|---|
| Sin conexiones activas | 200 · `total_value_eur: 0.0` · todos los arrays vacíos |
| Solo Indexa | Solo Indexa en `by_provider` / `providers`; no `espp_stock` |
| Solo Fidelity | Solo Fidelity en `by_provider` / `providers`; solo `espp_stock` en `by_asset_class` |
| Precio MSFT no disponible | Fidelity en `providers[]` con `value_eur: null`; omitido de `by_provider` y `by_asset_class` |
| Encryption key ausente | HTTP 503 (Romanoff fail-closed) |

---

## Archivos implementados

| Archivo | Cambio |
|---|---|
| `src/finlytics/api/schemas.py` | `ProviderAllocationItem`, `AssetClassAllocationItem`, `ProviderCardOut`, `CombinedOverviewOut` |
| `src/finlytics/api/investments.py` | `combined_overview` endpoint + `_PROVIDER_LABELS`, `_ASSET_CLASS_LABELS`, `_empty_overview()` |
| `tests/api/test_investments.py` | 8 tests: no connections, both providers (totals + pcts ~100 + shape), indexa-only, fidelity-only, degraded price (null), 401 |


---

# IMPL MEMO: Nav restructure + Finanzas overview + Investments combined

**Autor:** Vision (Frontend Engineer)
**Fecha:** 2026-07-15T14:10:06+02:00
**Spec origen:** `.squad/decisions/inbox/wanda-nav-restructure-overviews.md`
**Estado:** Implementado · build limpio · pendiente endpoint Shuri

---

## Resumen ejecutivo

Se implementa la reestructuración de navegación completa de Wanda + las 2 páginas overview + la corrección del título de Tendencias + el reagrupamiento de Ajustes en 4 grupos. Build: 0 errores TypeScript.

---

## Cambios entregados

### 1) Nav restructure (Layout.tsx)

**Antes:**
```
Inicio → Transacciones → Tendencias → Inversiones (acordeón) → Extractos → Ajustes (acordeón, 1 grupo)
```

**Después:**
```
Inicio
💳 Finanzas (expandible) → /finances
   ├── Transacciones → /transactions
   ├── Tendencias → /analytics
   └── Extractos → /statements
💰 Inversiones (NavLink directo) → /investments
⚙️ Ajustes (expandible)
   ├── DATOS: Categorías, Etiquetas, Cuentas
   ├── REGLAS: Reglas
   ├── SISTEMA: Conectores, Copia de seguridad
   └── APLICACIÓN: Apariencia
```

**Notas técnicas:**
- Inversiones ya no tiene acordeón ni sub-links de plugins en la nav. La navegación al detalle de cada plugin se hace desde la landing page de `/investments` (provider cards).
- Se eliminaron los imports de `getConnections`, `InvestmentConnection`, `PLUGIN_VIEW_REGISTRY` de Layout.tsx — ya no son necesarios en la nav.
- El estado `isOnFinances` incluye `/finances`, `/transactions`, `/analytics`, `/statements` para que el acordeón se auto-expanda en cualquiera de esas rutas.

### 2) FinancesOverviewPage.tsx (NUEVO)

- Ruta: `/finances`
- Componentes: GlobalFilterBar + KpiCards (con comparativa mes anterior) + SpendingByCategory + TopMerchants
- Patrón de data-fetching copiado de Dashboard.tsx — sin heatmap, sin movers, sin ImportModal, sin globalOverview, sin toast
- Título: `<h1 className="tx-page-title">` (consistencia visual)

### 3) InvestmentsLandingPage.tsx (RECONSTRUIDO)

- Endpoint: `GET /api/investments/combined-overview` (Shuri construye, shape en spec §B)
- Layout: KPI strip (3 cards: valor total / aportaciones / ganancia) + 2 donuts (Recharts PieChart, patrón `cat-chart-layout`) + provider cards (`inv-provider-card`)
- Fallback: si el endpoint falla o `providers.length === 0` → empty state con CTA a Conectores
- **Estado actual:** muestra empty state hasta que Shuri entregue el endpoint

### 4) Settings 4-group (Layout.tsx Ajustes accordion)

- Añadidos 3 separadores de grupo: `settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp`
- Mapping aplicado: Datos (Categorías/Etiquetas/Cuentas) → Reglas (Reglas) → Sistema (Conectores/Backup) → Aplicación (Apariencia)

### 5) Tendencias title fix (AnalyticsPage.tsx)

- `analytics-page-title` → `tx-page-title` (22px / 700, igual que Transacciones e Inversiones)

### 6) i18n

Añadidas 10 nuevas claves a `index.ts`, `es.ts`, `en.ts`:
- `navFinances`, `financesOverviewTitle`
- `settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp`
- `invCombinedTitle`, `invCombinedTotalValue`, `invCombinedTotalGain`, `invCombinedByProvider`, `invCombinedByAssetClass`

### 7) API (tipos + cliente)

- `api/types.ts`: 4 nuevas interfaces para `CombinedOverview`
- `api/client.ts`: `getCombinedOverview(): Promise<CombinedOverview>`

### 8) CSS (index.css)

Nuevas clases añadidas al final:
- `.inv-kpi-strip` — grid 3 columnas responsive
- `.inv-kpi-card` + subclases (`__label`, `__value`, `__sub`, `--pos`, `--neg`)
- `.inv-provider-cards` — grid `auto-fill minmax(260px, 1fr)`
- `.inv-provider-card` + subclases (`__header`, `__icon`, `__name`, `__value`, `__gain`, `__gain--positive/--negative`, `__cta`)

---

## Dependencia Shuri pendiente

`GET /api/investments/combined-overview` con el shape exacto definido en `wanda-nav-restructure-overviews.md §B`:
```json
{
  "total_value_eur": number,
  "total_invested_eur": number,
  "total_gain_loss_eur": number,
  "total_gain_loss_pct": number,
  "by_provider": [...],
  "by_asset_class": [...],
  "providers": [...]
}
```

Hasta que Shuri entregue el endpoint, `/investments` mostrará el empty state (no rompe nada).

---

## Paso 7 (Indexa cache indicator)

Omitido. El archivo `.squad/decisions/inbox/shuri-indexa-portfolio-cache.md` no existe. Si Shuri añade campo `stale`/`cached_at` en el futuro, Vision añadirá el indicador "actualizando…" en IndexaView en ese momento.

---

## Build result

```
tsc --noEmit && vite build
✓ 893 modules transformed.
✓ built in 4.90s
```

**0 errores TypeScript. 0 nuevos warnings.** Pre-existing chunk-size warning presente (conocido, no es regresión).


---

## Decision: Fidelity Evolution Chart — Daily Market-Day Resolution

**Date:** 2026-07-15  
**Agent:** Shuri (Backend Engineer)  
**Status:** Implemented ✅

---

### Context

The Fidelity ESPP evolution chart plots portfolio value over time.  
Previous implementation applied `use_weekly = total_days > 365`, which for the owner's ~4.5-year history produced **weekly buckets (~75 points)**. That hid the day-to-day price movement the chart is intended to show.

---

### Decision

Change `compute_evolution_series` to emit **one value point per actual MSFT trading day** (market-day resolution) for ranges up to ~6 years, with a weekly fallback only for extreme ranges.

#### Before

```
use_weekly = total_days > 365
if use_weekly:
    # iterate over Mondays
else:
    # iterate over all calendar days (forward-filled weekends included)
```

#### After

```
use_weekly = total_days > 2200          # ~6-year guardrail
if use_weekly:
    # weekly Mondays with forward-fill (extreme ranges only)
else:
    # iterate over price_map keys in [min_date, max_date]
    series_dates = sorted(d for d in price_map if min_date <= d <= max_date)
```

---

### Rationale

| Concern | Resolution |
|---|---|
| Day-to-day MSFT movement hidden | Now every trading day (close price) is a point |
| Weekend/holiday redundancy | Eliminated — only real market days in series |
| Payload size (~4.5y) | ~1100–1150 points (Recharts handles fine; was ~75) |
| Extreme-range safety | >2200 days → weekly (~300-365 points max) |
| Both series on same x-axis | Contributions also emitted at market-day dates |
| KPIs/lots endpoints | Not touched — no change to current-value logic |
| Price source/backfill | Not touched |

---

### Files Changed

| File | Change |
|---|---|
| `src/finlytics/api/fidelity.py` | `use_weekly` threshold 365→2200; daily path iterates `price_map` keys; renamed `filled`→`price_lookup`; updated docstring |
| `tests/investments/test_market_data.py` | 4 granularity tests updated; weekend-fill test renamed to market-day test; new extreme-range guardrail test |
| `tests/investments/test_fidelity_provider.py` | 2 boundary tests renamed/updated (366d, 365d now daily) |

---

### Test Result

```
1089 passed, 2 skipped, 0 failed
```

---

## Decision: Fidelity Price Top-Up — Incremental UPSERT for Daily Closes

**Author:** Shuri  
**Date:** 2026-07-15  
**Status:** Implemented ✅  
**Affects:** `src/finlytics/investments/market_data.py`, `src/finlytics/api/fidelity.py`

---

### Problem

`get_latest_price` stored today's price with `ON CONFLICT DO NOTHING`. Once an intraday value was written (e.g. 384 at 14:00), it was never corrected to the official close (e.g. 350 at 22:00). The bug persisted across days: tomorrow's KPIs still showed the stale intraday value for yesterday.

Historical backfill only ran when `price_history` was completely empty — it never touched the recent tail.

---

### Decision

#### 1. `topup_recent_prices(db: AsyncSession) → None`

A new public helper that runs an **incremental top-up** on each read:

- **Window:** `[max(price_date), today]` — always includes the last stored day.
- **Fetch:** Yahoo Chart daily history (`interval=1d`, `period1=max_stored_date`, `period2=today`) for both MSFT and EURUSD=X.
- **UPSERT:** `pg_insert(...).on_conflict_do_update(...)` — overwrites `close_usd`, `fx_eur_usd`, `close_eur` for every day in the window.
  - **Why DO UPDATE instead of DO NOTHING:** The last stored day may hold an intraday provisional value. Yahoo's daily history endpoint returns the settled official close once the market has closed. DO UPDATE ensures that provisional value is corrected when the top-up runs the following session.
- **Graceful degradation:** Any network failure is logged and silently swallowed. Existing data is never touched on failure.
- **Empty history:** Returns immediately without fetching — the full backfill (triggered at `import_confirm`) handles first-time population.
- **FX direction preserved:** `fx_eur_usd = 1 / eurusd_quote` (EUR per USD); `close_eur = close_usd × fx_eur_usd`. Same convention as existing code.

#### 2. `get_latest_price` simplified

Removed: intraday snapshot fetch, `on_conflict_do_nothing` write, fallback chain for snapshot.  
Replaced with:
1. `await topup_recent_prices(db)` (with try/except).
2. Read latest row from `price_history`.
3. `price_stale = price_date < _last_business_day()` — stale only if genuinely no recent close.

#### 3. Endpoint wiring

- **`fidelity_kpis` / `fidelity_lots`:** Top-up happens inside `get_latest_price`, called first before any other SQL. No change needed in the endpoint code.
- **`fidelity_evolution`:** Calls `topup_recent_prices(db)` explicitly after `await db.commit()` to break the autobegin read transaction before topup opens its own `db.begin()` blocks. The existing full-backfill lazy path is preserved for when `price_history` is empty.

#### 4. Full backfill unchanged

`backfill_price_history` (called at `import_confirm` and lazy in `fidelity_evolution`) is unchanged. It handles the initial full population of `price_history` from the earliest lot date. The top-up handles the recent tail from that point forward.

---

### Alternatives Considered

| Option | Rejected because |
|---|---|
| Keep snapshot + DO NOTHING, invalidate daily on close | Complex cache invalidation; race conditions at market close |
| Cron job / background task for daily settlement | Adds infrastructure complexity; top-up on read is simpler and keeps the DB always fresh |
| Always re-fetch entire history on read | Too expensive for a frequently called endpoint |

---

### Impact

- **KPIs `valor actual`:** Uses settled daily close after market close; provisional during session.
- **Evolution chart:** Same — the price_map is now built from settled closes.
- **Lots endpoint:** Same.
- **Test suite:** 1104 passed, 2 skipped, 0 failed. New test classes: `TestTopupRecentPrices`, `TestGetLatestPrice`.

---

**Coordinators:** Shuri (Backend), Vision (Frontend), Rocket (DevOps)  
**Status:** COMPLETE & VERIFIED IN DOCKER  

**Summary:**
- ✅ Plugin discovery: Fidelity ESPP registered in _PLUGIN_REGISTRY + dynamic status in list_plugins (1070 → 1088 tests)
- ✅ Price source: Yahoo Chart API primary (browser User-Agent required; query1→query2 fallback) with lazy backfill
- ✅ Upload UI: Styled file picker + SP/DO tooltips (i18n ES/EN) 
- ✅ Verified in Docker: MSFT €337.04, EUR/USD 0.87558, evolution chart functional
- 🔄 Repo code: Uncommitted; owner testing/iterating
# ADR: Yahoo Chart API como fuente de precio primaria para Fidelity ESPP

**Fecha:** 2026-07-15  
**Autor:** Shuri (Backend Engineer)  
**Estado:** Implementado  
**Contexto:** Bugfix — precio MSFT nulo en Docker, gráfico de evolución sin datos

---

## Problema

El feed de precios Fidelity devolvía `null` en producción (Docker):

- **Stooq** sirve un JS anti-bot challenge / soft-404 → inutilizable.
- **yfinance** llama a `fc.yahoo.com` — inaccesible desde el container.
- Resultado: `current_value` / `gain` nulos, "price stale" visible, gráfico de evolución vacío.

---

## Decisión

**Yahoo Chart JSON API** como fuente primaria, con fallback a Stooq → yfinance.

### Endpoint

```
GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
```

Con query params para histórico: `?interval=1d&period1={unix}&period2={unix}`

### User-Agent requerido

Sin browser UA → HTTP 429. Con el siguiente UA → 200 (verificado en el container):

```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36
```

Almacenado como constante `_YAHOO_UA` en `market_data.py`.

### Fallback query1 → query2

Si `query1.finance.yahoo.com` devuelve 429 o falla por conexión, se reintenta automáticamente en `query2.finance.yahoo.com`. Implementado en `_yahoo_get()`.

### Estructura de respuesta

```json
{
  "chart": {
    "result": [{
      "meta": {
        "regularMarketPrice": 445.0,
        "regularMarketTime": 1752019200,
        "currency": "USD"
      },
      "timestamp": [1751932800, 1752019200],
      "indicators": {
        "quote": [{ "close": [441.5, 445.0] }]
      }
    }]
  }
}
```

- `close` puede contener `null` (festivos) → se omiten al parsear.
- Timestamps son Unix seconds en UTC → `datetime.fromtimestamp(ts, tz=timezone.utc).date()`.

---

## FX Direction (EURUSD=X)

`EURUSD=X regularMarketPrice` = **USD por 1 EUR** (e.g. 1.0823).  
Misma dirección que Stooq/yfinance (convención no cambia):

```python
fx_eur_usd = 1.0 / regularMarketPrice   # EUR por USD ≈ 0.9239
close_eur  = close_usd * fx_eur_usd     # = close_usd / eurusd_quote
```

Ejemplo: MSFT $450, EURUSD=1.08 → €416.67 ✓ (no €486 que daría sin invertir).

---

## Lazy Backfill

**Problema:** El owner ya había importado los lots antes del fix. `price_history` estaba vacía porque el backfill inicial falló (Stooq/yfinance rotos). El endpoint `/evolution` devolvía "no data" aunque los lots existían.

**Solución:** En `fidelity_evolution`, si `prices == []` tras la query inicial:

```python
if not prices:
    await db.commit()          # cierra la autobegin transaction (read-only, safe)
    await backfill_price_history(min_date, db)  # abre su propio begin()
    prices = await db.execute(price_query).scalars().all()  # re-query
```

**Por qué `await db.commit()` antes de backfill:**  
`backfill_price_history` usa `async with db.begin()`, que falla con `InvalidRequestError` si ya hay una transacción activa (autobegin). El commit cierra la transacción de lectura antes de que backfill inicie la suya.

**Idempotencia:** `ON CONFLICT (ticker, price_date) DO NOTHING`. Si backfill ya se ejecutó (re-deploy, retry), no duplica datos.

---

## Alternativas descartadas

| Opción | Razón de rechazo |
|---|---|
| Alpha Vantage / Finnhub | Requieren API key; complicación operacional innecesaria |
| Polygon.io | Misma razón |
| Webscraping Yahoo Finance HTML | Frágil; estructura HTML cambia con frecuencia |
| Reconstruir desde yfinance sin `fc.yahoo.com` | yfinance v0.2+ depende de ese endpoint; no parcheable sin fork |

---

## Impacto en tests

- `TestParseYahooHistory`: parseo de JSON, null skipping, sort.
- `TestParseYahooSnapshot`: parseo de meta.
- `TestYahooUserAgent`: mock httpx → verifica UA header, 429→query2 fallback, ambos hosts fallan → None.
- Stooq CSV tests mantenidos (parser aún existe como fallback).
- **Sin red real en tests** — todo mockeado con `unittest.mock`.

---

## Archivos modificados

| Archivo | Cambio |
|---|---|
| `src/finlytics/investments/market_data.py` | Reescrito: Yahoo primario, Stooq/yfinance fallback |
| `src/finlytics/api/fidelity.py` | Lazy backfill en `fidelity_evolution` |
| `tests/investments/test_market_data.py` | +18 tests Yahoo (total: 47) |

---

## 2026-07-15T10:08:20+02:00 — Fidelity ESPP Connector — Implementation Wave 1–2 Decision Record

**Coordinators:** Shuri (Backend), Banner (Parser), Vision (Frontend), Rocket (DevOps)  
**Reviewers:** Fury (Architecture & Contract), Romanoff (Privacy), Barton (QA)  
**Status:** APPROVED & RUNNING (Docker http://localhost:7777)  
**Context:** Multi-wave implementation (foundation + parser + endpoints + frontend + tests + DevOps) with reviewer-driven contract fixes. Feature complete, awaiting owner CSV testing.

---

### Wave 1–A: Shuri Foundation — Database & Service Skeleton

#### Decisiones de implementación (Shuri)

**Cambio 1: `cost_basis NUMERIC(18,2)` (spec Wave 1)**
- Spec Wave 1 says explícitamente `NUMERIC(18,2)`.
- **Decisión:** Use 18,2 according to task spec (2 decimals sufficient for EUR).

**Cambio 2: `import_run_id` NOT added to `espp_lots` in Wave 1**
- Omitted per spec. Can be added in Wave 2 with migration 0015 if needed for ORM navigation.

**Confirmaciones:**
- `dedup_hash`: sha256(ticker|purchase_date|shares:.8f|cost_basis_per_share:.6f|share_source|dedup_ordinal)
- `token_enc` → NULLABLE in migration 0014 and ORM model
- `_PROVIDERS` dict: `{"indexa-capital": IndexaProvider(), "fidelity-espp": FidelityESPPProvider()}`
- `provider_type = "live_api"` in ABC; `FidelityESPPProvider.provider_type = "statement_import"`
- FidelityESPPProvider does NOT import fidelity_csv.py (Banner in parallel)
- Test suite: 971 passed, 0 failed

---

### Wave 1–B: Banner CSV Parser

#### Decisión 1: Auto-detección del separador decimal (con moneda como desempate)

**Spec original:** "handle both US ('.') and EU (',') decimal styles based on detected currency"

**Implementación real:** Primary strategy = auto-detect per field; currency used only for ambiguous case (comma-only, no dot):

| Caso | Ejemplo | Resolución |
|------|---------|-----------|
| Ambos, último punto | `1,234.56` | Siempre US (dot = decimal) |
| Ambos, última coma | `1.234,56` | Siempre EU (comma = decimal) |
| Solo coma + currency=EUR | `50,0000` | EU: coma = decimal |
| Solo coma + currency=USD | `1,234` | US: coma = thousands |
| Solo punto | `2000.00` | Siempre US |

**Razón:** CSV real de Fidelity usa EUR en footer pero puntos como decimal (notación US). La auto-detección es más robusta. Para el CSV Fidelity real (todos sus números tienen punto), `eu_style` es inerte.

#### Decisión 2: Header scan dinámico (no índice fijo)

**Implementación:** Parser escanea buscando primer field = `"date acquired"` (case-insensitive), no asume línea 0.

**Razón:** Defensive parsing — si Fidelity añade línea de título antes de cabecera, parser no se rompe.

#### Decisión 3: Filas omitidas

Descartadas sin error:
1. Filas con < 11 celdas no vacías (separadores, footer)
2. Primera celda empieza por `"total"` (fila agregada)
3. Primera celda contiene `"values are displayed"` (footer)
4. Date acquired no parseable

**Sin cambios vs spec:** `NormalizedLot`, `ParsedOpenLots`, firma de `parse_open_lots_csv` coinciden exactamente.

**Suite de tests:** 50 new tests + existing 921 = 971 passed

---

### Wave 1–C: CRITICAL CORRECTION — CSV Currency (Fury + Romanoff + Banner)

**Earlier assumption:** CSV sería USD.  
**Real discovery (Banner empirical probe):** Footer de "View open lots.csv" ACTUAL dice EUR. **Todos los valores ya están en EUR** — cost basis, per-share prices, value fields.

**Consecuencias:**
- `NormalizedLot.currency = "EUR"` (hardcoded para MSFT ESPP, no USD)
- Phase 1 (parse + display) = SIN conversión FX; cost basis es final
- FX conversion SOLO en Phase 2 (live USD market price → EUR valuation)

**Simplificación:** Phase 1 no tiene multi-moneda math.

#### Idempotency refinement — Duplicate DO Lots

Multiple dividend-reinvestment (DO) lots pueden tener identical (date, qty, cbps). Dedup strategy:
- File-level: sha256(file_bytes) para gross dedup
- Lot-level: sha256(ticker|date|qty|cost_per_share|share_source|ordinal_within_group) para dedup estable
- Ordinal index (0-based within identical groups in CSV order) → dedup estable en re-exports

---

### Wave 2: Shuri Endpoints — Market Data + 5 HTTP Endpoints

#### Resumen

Wave 2 implementada conforme spec. 1000+ tests green. Divergencias documentadas:

**1. FX Direction** ✅ Correcto y documentado en tests
```
Stooq/yfinance eurusd = USD por 1 EUR (e.g. 1.0823)
fx_eur_usd = 1 / eurusd_quote                (EUR por USD = 0.9239)
close_eur = close_usd × fx_eur_usd            (= close_usd / eurusd_quote)
```
Caso canónico: MSFT $450, EURUSD=1.08 → €416.67 ✓

**2. `compute_evolution_series` — Función pura exportada**
- Spec: lógica implícita dentro endpoint
- Implementación: extraída a `compute_evolution_series(lots, price_map, min_date, max_date)` exportada y testeable
- Razón: facilita tests de Barton (full suite sin mocks DB/red)

**3. `get_latest_price` — Doble `async with db.begin()` (transacciones)**
- Spec: no especificaba internals
- Implementación: dos bloques `async with db.begin()` secuenciales
  - Primero: SELECT caché (read-only)
  - Segundo (condicional): INSERT precio fresco
- Contrato: función debe llamarse sin SQL previo

**4. Backfill — `inserted > 0` para disparar**
- Spec: trigger on first confirm
- Implementación: solo dispara si `inserted > 0` (hay lotes nuevos)
- Razón: re-import del mismo fichero (dedup) → `inserted=0` → no backfill (idempotente, sin fetch innecesario)

**5. `source_filename` NOT presente en Wave 1 model**
- History mencionaba pero model real (0014 migration) no lo incluye
- Si se necesita futuro: migración 0015

**6. Rutas Fidelity**
- `POST /api/investments/fidelity/import/preview`
- `POST /api/investments/fidelity/import/confirm`
- `GET  /api/investments/fidelity/kpis`
- `GET  /api/investments/fidelity/evolution`
- `GET  /api/investments/fidelity/lots`

Router usa prefix="/investments", coexiste con investments.py router bajo `/api/investments/`.

---

### Wave 2–B: Privacy Review (Romanoff) — ✅ PASS

#### Respuestas a cuatro preguntas

**1. ¿CSV almacena/transmite PII de identidad?** NO.
- CSV Fidelity no contiene nombre, dirección, ID empleado
- Parser no introduce campos identidad adicionales
- Raw CSV NUNCA escrito a disco — en memoria solo
- Endpoints persisten solo: file hash (SHA-256, opaco) + dedup hashes + datos estructurados lot

**2. ¿Qué sale a servicios externos?** SOLO símbolos públicos.
- A Stooq: `s=msft.us`, `s=eurusd` + rango fechas
- A yfinance (fallback): `MSFT`, `EURUSD=X`
- CERO datos usuario/posiciones/acciones/lotes

**3. ¿Almacenamiento coherente con paridad + gitignore?** SÍ — más estricto.
- Decisión previa: PDFs extracto bancario persisten en `/app/data/uploads/` (volumen montado, cubierto `.gitignore`)
- Ruta CSV Fidelity: NO persiste en disco (más estricto aún)

**4. ¿Riesgo de secretos?** NO.
- Stooq/yfinance = servicios públicos sin autenticación
- `InvestmentConnection.token_enc=None` para Fidelity/ESPP (keyless intencional)
- Sin credenciales hardcodeadas ni en logs

#### Logging
Todos limpios (solo excepción + símbolo + conteo, nunca importes/shares/costbasis):
- `api/fidelity.py:310` — `log.warning("Price backfill failed (non-fatal): %s", exc)` ✅
- `market_data.py` (4 logs) — símbolos + excepciones + conteos ✅

#### Nota menor (no bloqueante)
Error parsing CSV expuesto en 400 detail. Para single-user autoalojada, no es problema. Multi-user futuro: considerar sanitizar.

#### Veredicto: ✅ **PASS**
Cumple criterios privacidad: sin PII, sin datos usuario externos, almacenamiento inexistente en disco, sin secretos, logging limpio.

---

### Wave 2–C: Barton QA — Test Coverage (69 new tests)

#### Files Created
| File | Tests | Description |
|---|---|---|
| `tests/investments/test_fidelity_provider.py` | 23 | Provider unit + evolution edge cases |
| `tests/api/test_fidelity.py` | 46 | HTTP endpoint integration tests |

#### Coverage Areas

**1. `_compute_dedup_hash` (7 tests)** — Determinism, sensitivity to inputs, ordinal-0 ≠ ordinal-1

**2. `import_lots` idempotency (10 tests)**
- File-level: existing file_hash → previous (inserted, skipped)
- Lot-level: conflicts, partial inserts, empty lists
- Audit: InvestmentImportRun created for new files only

**3. `compute_evolution_series` edge cases (6 tests)**
- 366-day range → weekly granularity
- 365-day range → daily granularity
- Step function: lot included from purchase_date
- Identical DO lots both accumulate

**4. Auth guards (5 tests)** — All 5 endpoints enforce 401 without session

**5. Preview endpoint (11 tests)** — shape, currency, duplicate detection, non-persisting, 400 on malformed

**6. Confirm endpoint (8 tests)** — shape, backfill trigger condition (`inserted > 0`), idempotency

**7. KPIs endpoint (8 tests)** — no connection, missing price, formulas, stale flag, **BUG documented**

**8. Evolution endpoint (6 tests)** — series shape, ISO dates

**9. Lots endpoint (7 tests)** — field presence, formulas, null values

#### BUG FOUND — BUG #KPI-1

**Title:** `fidelity_kpis` (and `fidelity_lots`) crash on DB error at `get_latest_price`

**Severity:** Medium — affects users at startup or DB momentarily unavailable

**Root cause:** Both endpoints call `get_latest_price(db)` with NO guard. While `get_latest_price` catches network errors, a DB error on initial cache read propagates uncaught.

**Recommended fix:** Wrap in try/except, degrade to `price = None` path (HTTP 200 with null fields instead of 500).

---

### Wave 2–D: Fury Review #1 — ❌ REJECT (4 contract mismatches)

#### Blocking Issues

**1. `gain_loss_pct` double-multiply → renders 1250% instead of 12.5%**
- Backend: sends 12.5 (percentage)
- Frontend type comment: "decimal: 0.15 = 15%" (contradicts)
- Frontend display: `{kpis.gain_loss_pct * 100}.toFixed(2)%` → 1250% BUG
- Fix: Remove `* 100` in frontend OR backend send 0.125
- **Assign to:** Vision (frontend/type owner) — align types + display

**2. `FidelityImportPreviewLot` field name mismatch**
- Backend sends: `cost_basis_per_share`, `cost_basis`
- Frontend expects: `cost_basis_per_share_eur`, `cost_basis_total_eur`
- Result: Preview table shows `undefined`
- Fix: Rename backend fields to `_eur` suffix (cleaner, matches /lots endpoint already)

**3. `new_count` field doesn't exist in backend**
- Frontend: `importPreview.new_count`
- Backend: sends `new_lots` array (no `new_count` field)
- Result: Import preview shows `NaN` or blank
- Fix: Frontend use `importPreview.new_lots.length`

**4. `skipped` vs `duplicates`**
- Backend: `FidelityImportResult` sends `skipped: int`
- Frontend: expects `duplicates: number`
- Fix: Rename backend field to `duplicates` or frontend to `skipped` (backend rename reads better)

#### Non-blocking Nits
1. `uq_investment_import_runs_file_hash` is global unique instead of composite (single-user safe)
2. Frontend `FidelityImportPreview.filename` (dead field, not harmful)
3. TypeScript type comment source of confusion

#### What Passed ✓
- Money math/FX direction ✓
- Cost basis as EUR ✓
- Lot-level idempotency ✓
- File-level idempotency ✓
- Plugin_id consistency ✓
- Evolution series ✓
- Provider abstraction ✓
- Migration pattern ✓
- Graceful degradation (Stooq→yfinance) ✓
- Indexa untouched ✓
- CSV parser ✓
- i18n ✓

#### Summary
4 blocking contract mismatches → runtime integration failures. Core architecture, money math, idempotency solid. Fix 4 field/convention mismatches → ships.

---

### Wave 2–E: Banner Contract Fix (NON-AUTHOR per reviewer-lockout rule)

#### Status: ✅ APPLIED — all fixes merged, 1069 tests green, 0 TS errors

#### Fixes Applied

| Issue | File(s) | Change |
|---|---|---|
| **#1 gain_loss_pct ×100** | FidelityView.tsx | Removed `* 100`; backend sends percentage directly |
| **#2 preview field names** | schemas.py, fidelity.py | `cost_basis_per_share` → `cost_basis_per_share_eur`; `cost_basis` → `cost_basis_total_eur` |
| **#3 new_count** | FidelityView.tsx, types.ts | Removed non-existent `new_count`; view uses `new_lots.length` |
| **#4 skipped → duplicates** | schemas.py, fidelity.py | `FidelityImportResult.skipped` → `.duplicates` |
| **BUG #KPI-1** | fidelity.py | `get_latest_price` wrapped in try/except in both `fidelity_kpis` and `fidelity_lots` |
| **types.ts hygiene** | types.ts | Removed dead `filename`; added `total_in_file`, `source_currency`, `file_already_imported` |
| **comment fix** | types.ts | Updated comment to `// percentage: 12.5 = 12.5%` |

#### Final Contract — 5 Endpoints

**GET /kpis:**
- `gain_loss_pct` = percentage (12.5 = +12.5%), render as `pct.toFixed(2) + "%"` — do NOT multiply

**POST /preview:**
- `new_lots`, `duplicate_count`, `total_in_file`, `source_currency`, `file_already_imported`
- Per-lot: `purchase_date`, `shares`, `cost_basis_per_share_eur`, `cost_basis_total_eur`, `share_source`, `grant_date`

**POST /confirm:**
- Response: `{inserted, duplicates}` (was `skipped`)

#### Tests Updated
- Confirm tests: `data["skipped"]` → `data["duplicates"]`
- KPIs test: Renamed `test_kpis_get_latest_price_raises_propagates_bug` → `test_kpis_get_latest_price_raises_returns_degraded_200`; assert HTTP 200 + null instead of RuntimeError

#### Verification
```
pytest -q  →  1069 passed, 2 skipped  ✅
npm run build  →  0 TS errors  ✅
```

---

### Wave 2–F: Fury Review #2 — ✅ APPROVE

#### Prior Verdict: REJECT (4 blocking contract mismatches) — ALL RESOLVED

**Issue 1 — `gain_loss_pct`** ✅
- `FidelityView.tsx:355,536` → no `* 100`
- `types.ts:489` comment updated to `// percentage: 12.5 = 12.5%`
- Consistent across endpoints

**Issue 2 — Preview lot field names** ✅
- `schemas.py` → `cost_basis_per_share_eur`, `cost_basis_total_eur`
- Frontend types match exactly

**Issue 3 — `new_count`** ✅
- Removed from type
- Frontend derives: `new_lots.length`

**Issue 4 — `skipped` → `duplicates`** ✅
- `schemas.py:594` → `duplicates: int`
- `types.ts:517` → `duplicates: number`

**BUG #KPI-1** ✅
- Both endpoints wrapped in try/except
- Degrade to HTTP 200 with null fields (not 500)

#### Full Contract Cross-Check (5 endpoints) — Zero Remaining Mismatches ✅

| Endpoint | Match |
|---|---|
| GET kpis | ✅ |
| GET evolution | ✅ |
| GET lots | ✅ |
| POST preview | ✅ |
| POST preview (per-lot) | ✅ (source_currency backend-only, harmless) |
| POST confirm | ✅ |

#### Conclusion
Banner's fixes correct, complete, verified. All 4 blocking mismatches resolved. BUG #KPI-1 graceful degradation in place. Both test suites green (1069 pytest, 0 TS errors). **This ships.**

---

### Wave 3: Vision Frontend — Fidelity ESPP Visualization

#### Implementation Notes

**1. Full implementation in single phase (vs phasing plan)**
- Plan described 3 phases; spec requested everything in one PR
- View auto-detects null fields, shows "—" automatically
- Behavior of phases 1/2 covered without re-deploy

**2. Multipart file upload for both preview + confirm**
- Both endpoints send CSV in multipart POST
- Backend re-parses, re-inserts (idempotent with dedup)
- Obligation: save File reference during wizard

**3. Carry-forward for `contributions_series` sparse**
- Plan: use `contribMap.get()` with `connectNulls` (from IndexaView)
- Implemented: Carry-forward last known value for each value_series point
- Reason: sparse series (1 point per new lot); carry-forward guarantees perfect step function visually

**4. isEmpty condition: `lots.length === 0 && kpis === null`**
- Plan: empty state when no lots
- Implemented: empty state only when BOTH conditions true
- Reason: avoids treating real cartera (kpis available) as "empty" if lots temporarily empty

**5. New CSS classes**
- `kpi-sub--pos` / `kpi-sub--neg` — gain/loss pct below KPI card, green/red
- `fid-source-badge--sp` / `fid-source-badge--do` — lot source badge (SP/DO), dark-mode support

**6. Omitted: toggle €/%**
- Plan contemplated; implemented without
- Reason: mono-activo (single stock), % adds no useful info for ESPP

#### Matched vs Plan
- ResponsiveContainer height numeric ✅
- XAxis dataKey + tickFormatter ✅
- Tooltip labelFormatter → formatDDMMYYYY ✅
- Default period: 'Todo' ✅
- Periods: 1M/3M/1A/dynamic years/Todo ✅
- price_stale banner (amber, non-blocking) ✅
- Loading/empty/error as first-class states ✅
- No pagination in lots table ✅
- No donut or returns matrix ✅

---

### FUTURE: Investments Plugin Navigation & Settings Reorganization (Fury + Wanda)

#### Navigation Architecture Proposal (Fury)

**Target:** Investments expandable sidebar section (like Settings). Routes:
- `/investments` → Landing hub (connected plugins as cards)
- `/investments/:pluginId` → Per-plugin view (e.g. `/investments/fidelity-espp`)

**Backend impact:** NONE (routes already exist).

**Frontend changes:**
1. Extract Indexa view from InvestmentsPage → `views/IndexaView.tsx`
2. New `InvestmentsLandingPage.tsx` — hub with cards
3. Plugin view registry (`frontend/src/investments/registry.ts`) — map `{pluginId → LazyComponent}`
4. Plugin view wrapper (`PluginViewWrapper.tsx`) — reads `:pluginId` from URL, renders or 404
5. Update `App.tsx` routes: nested `/investments` + `/investments/:pluginId`
6. Update `Layout.tsx` sidebar: accordion pattern (clone Settings)
7. i18n: 3 new keys × 2 langs

**Rules for visibility:**
- Plugin appears in sidebar only if: (1) registered in PLUGIN_VIEW_REGISTRY AND (2) user has active connection

**Sequencing:**
1. Wanda confirms sidebar section CSS reusable
2. Vision implements all 7 items
3. Barton updates/adds tests
4. Fury reviews

#### Settings Reorganization (Wanda) — Part A REVISED

**Decision: sub-headers inside accordion (option a, not nested submenus)**

**Rationale:** Sub-headers = visual grouping without tap depth on mobile.

**Structure (owner constraints applied):**
```
⚙️ Settings
 ├── DATOS / DATA
 │   ├── Categorías
 │   ├── Etiquetas
 │   └── Cuentas
 ├── REGLAS / RULES
 │   └── Reglas  ← MOVED from top-level (solo group)
 ├── SISTEMA / SYSTEM
 │   ├── Copia de seguridad
 │   └── Conectores
 └── APLICACIÓN / APP
     └── Apariencia
```

**Rules: YES, move to Settings**
- Removed from top-level nav
- Lives alone under REGLAS group inside Settings
- Route: `/settings/rules` (for consistency)

**Group label CSS:**
```css
.sidebar-group-label {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  padding: 10px 12px 2px;
  opacity: 0.6;
  user-select: none;
}
.sidebar-subnav > .sidebar-group-label:first-child {
  padding-top: 4px;
}
```

**i18n keys (group labels):**
- `settingsGroupData` / `settingsGroupRules` / `settingsGroupSystem` / `settingsGroupApp`

#### Investments Expandable Section (Wanda) — Part B

**Pattern:** Exact reuse of Settings accordion (.sidebar-section + .sidebar-section-btn + .sidebar-subnav).

**Behavior:**
- Auto-expands on `location.pathname.startsWith('/investments')`
- Collapse/expand on click
- Mobile: overlay, close on route change

**DOM:**
```
<div class="sidebar-section">
  <button class="sidebar-section-btn">
    💰 Investments ▾
  </button>
  {investmentsExpanded && (
    <div class="sidebar-subnav">
      <NavLink to="/investments">Resumen</NavLink>
      {connectedPlugins.map(plugin => (
        <NavLink to={`/investments/${plugin.id}`}>{plugin.name}</NavLink>
      ))}
      {connectedPlugins.length === 0 && <span class="sidebar-plugin-hint">Conecta un plugin →</span>}
    </div>
  )}
</div>
```

**Plugin sub-item styling:** Same `.sidebar-nav-link` + `nav-icon` (emoji from registry) + `nav-label`.

**Empty state CSS:**
```css
.sidebar-plugin-hint {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
  padding: 2px 12px 6px;
  opacity: 0.7;
  display: block;
}
```

**New i18n keys (Part B):**
- `navInvestmentsOverview` ("Resumen" / "Overview")
- `invNoPluginsHint` ("Conecta un plugin →" / "Connect a plugin →")

**Total changes:** ~14 lines CSS (additive), 20 lines JSX, 5 lines state/effect. No visual regressions.

---

## 2026-07-14T11:10:33+02:00 — Phase 2: Indexa Capital Connector — Complete Design & Implementation Record

**Coordinators:** Fury (Lead)  
**Contributors:** Romanoff (Security), Shuri (Backend), Wanda (Design), Vision (Frontend), Barton (QA), Rocket (DevOps)  
**Status:** APPROVED & SHIPPED (commit 4a7673c, local)  
**Context:** Phase 2 — multi-agent implementation of Indexa Capital read-only connector with encrypted token storage, wizard UI, and portfolio aggregation.

---

### Architecture Plan (Fury)

# Phase 2: Indexa Capital Connector — Architecture & Plan

**Author:** Fury (Lead/Architect)  
**Date:** 2026-07-14  
**Status:** DRAFT — awaiting owner sign-off  
**Depends on:** Phase 1 shipped (investments skeleton), Romanoff's security policy (approved)

---

## 1. Connector Architecture

### Where the code lives

```
src/finlytics/investments/
├── __init__.py
├── base.py            # InvestmentProvider ABC (small — 3 methods)
├── indexa.py           # IndexaProvider(InvestmentProvider) — the real client
├── crypto.py           # encrypt_token() / decrypt_token() — Fernet helpers per Romanoff
└── service.py          # Orchestrator: resolves connections → calls provider → returns normalized shapes
```

New package `src/finlytics/investments/`, separate from `src/finlytics/api/`. The API layer (`api/investments.py`) stays thin — it calls `service.py`, which owns the business logic.

### Provider abstraction (smallest thing that works)

```python
class InvestmentProvider(ABC):
    """Base interface for investment connectors."""
    plugin_id: str

    async def validate_token(self, token: str) -> ValidationResult:
        """Call external API to verify token is valid. Return discovered accounts."""
        ...

    async def get_portfolio(self, token: str, accounts: list[str]) -> NormalizedPortfolio:
        """Fetch holdings + performance + allocation. Return normalized data."""
        ...

    async def get_performance(self, token: str, account: str) -> NormalizedPerformance:
        """Fetch returns + value series for one account."""
        ...
```

Only 3 methods. `IndexaProvider` implements them by calling the 3 Indexa GET endpoints (`/users/me`, `/accounts/{acc}/fiscal-results`, `/accounts/{acc}/performance`). Future providers (broker, crypto) implement the same interface.

### Indexa → normalized mapping

| Indexa endpoint | Maps to |
|---|---|
| `GET /users/me` | `validate_token()` → discover accounts, validate auth |
| `GET /accounts/{acc}/fiscal-results` | `get_portfolio()` → `InvestmentHoldingOut[]` — each `fiscal_result` becomes a holding |
| `GET /accounts/{acc}/performance` | `get_performance()` → KPIs (total_amount, investment, pl, twr_annual, xirr) + value series (`total_amounts`) + cash/invested split (`portfolios[0]`) |

`GET /accounts/{acc}` (account detail) is called only during validation to store `type` and `risk_profile` — not on every portfolio fetch.

### Caching strategy: **on-demand with short TTL**

- **No background sync.** Fetch live from Indexa on each page load.
- **In-memory TTL cache (5 min)** per connection_id to avoid hammering Indexa if the user refreshes. Use a simple dict + timestamp — no Redis, no DB cache table.
- **Rationale:** Indexa data is 1-business-day lagged anyway. No documented rate limits. A 5-min TTL means the user sees fresh data on each visit but rapid refreshes don't spam. Simpler than a sync cron + cache invalidation.
- **Multi-account:** If a user has 2 Indexa accounts, both are fetched and aggregated in a single `/portfolio` call.

---

## 2. Persistence

### `investment_connections` table

Romanoff's security design (already approved) specifies the schema. Using her exact column set:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` default |
| `user_id` | INT FK → users.id | |
| `plugin_id` | TEXT NOT NULL | `'indexa-capital'` |
| `status` | TEXT NOT NULL | `'active'` \| `'error'` \| `'disconnected'` |
| `account_label_masked` | TEXT | `'PBK•••Z5'` — first 3 + `•••` + last 2 |
| `token_enc` | TEXT NOT NULL | Fernet ciphertext only |
| `created_at` | TIMESTAMPTZ | server default `now()` |
| `last_synced_at` | TIMESTAMPTZ | nullable |

**One row per Indexa account.** If the user's token discovers 2 accounts and they connect both → 2 rows sharing the same `token_enc`. This keeps the model simple and lets the user disconnect individual accounts.

### Alembic migration

- Current head: **`0012`** (`0012_add_source_path_to_import_runs.py`)
- Next migration: **`0013_add_investment_connections.py`**
- Additive only (new table, no ALTER on existing tables)

### Encryption

Per Romanoff's approved policy:
- `cryptography.Fernet` with `INDEXA_ENCRYPTION_KEY` env var
- Fail-closed: app refuses to start if key is absent
- Hard-delete on disconnect (not soft-delete)
- Token never appears in any API response or log

Shuri implements `crypto.py` following Romanoff's spec exactly. No deviations.

---

## 3. API Endpoints

Four new endpoints on the existing `investments` router. The existing `GET /plugins` stays.

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| **POST** | `/api/investments/connections` | Connect wizard: validate token → store encrypted → return discovered accounts | `{ token: string }` | `{ connection_id, accounts: [{ account_number_masked, type, status }] }` |
| **GET** | `/api/investments/connections` | List user's connected plugins | — | `[{ id, plugin_id, status, account_label_masked, created_at, last_synced_at }]` |
| **DELETE** | `/api/investments/connections/{id}` | Disconnect: hard-delete row + clear cache | — | `204 No Content` |
| **GET** | `/api/investments/portfolio` | Aggregated portfolio: KPIs + holdings + value series + allocation | `?connection_id=` (optional, for single-account view) | Extended `InvestmentPortfolioOut` (see §4) |

### POST /connections flow (wizard backend)

1. Receive `{ token }` in request body.
2. Call `IndexaProvider.validate_token(token)` → `GET /users/me`.
3. If 401/403 → return `400 { detail: "Token inválido" }`. Never store.
4. If 200 → discover accounts. For each account, call `GET /accounts/{acc}` for type/profile.
5. Encrypt token with Fernet → insert row(s) into `investment_connections`.
6. Return connection IDs + masked account labels.

### GET /plugins behavior change

The existing static registry stays. But `status` for `indexa-capital` becomes **dynamic**: if the user has an active connection → `"connected"`, otherwise → `"available"` (no longer `"coming_soon"`). The other two plugins remain `"coming_soon"`.

---

## 4. Schema Extensions

### Extended `InvestmentPortfolioOut`

Add to the existing schema (currently: total_value, total_invested, total_gain_loss, total_gain_loss_pct, currency, holdings, plugins_connected, last_updated):

```python
class InvestmentReturns(BaseModel):
    """Performance metrics from Indexa /performance endpoint."""
    twr_annual: float | None = None        # time-weighted return, annualized
    xirr: float | None = None              # money-weighted annualized return
    pl: float | None = None                # absolute P&L (EUR)
    invested: float | None = None          # net capital invested

class ValuePoint(BaseModel):
    date: str    # "YYYYMMDD" or "YYYY-MM-DD"
    value: float

class CashInvestedSplit(BaseModel):
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float

class InvestmentPortfolioOut(BaseModel):    # EXTENDED — new fields below
    # ... existing fields unchanged ...
    returns: InvestmentReturns | None = None
    value_series: list[ValuePoint] = []           # from total_amounts dict
    cash_invested: CashInvestedSplit | None = None  # from portfolios[0]
```

### `InvestmentHoldingOut` — already sufficient

The existing shape covers fiscal-results mapping:

| Existing field | Indexa source |
|---|---|
| `name` | `instrument.name` |
| `ticker` | `instrument.identifier` (ISIN) |
| `asset_class` | `instrument.asset_class` (map Indexa classes → our enum) |
| `units` | `titles` |
| `current_value` | `amount` |
| `cost_basis` | `cost_amount` |
| `gain_loss` | `profit_loss` |
| `gain_loss_pct` | `profit_loss / cost_amount` (computed) |

**Asset class mapping** (Indexa → ours):
- `equity_europe`, `equity_north_america`, `equity_pacific`, `equity_emerging` → `"equity"`
- `fixed_income_*` → `"fixed_income"`
- `cash`, `money_market` → `"cash"`
- anything else → `"other"`

Weight % = `amount / total_amount` (computed client-side from the holdings array, not stored).

---

## 5. Wizard UX Flow

Launched from the Indexa connector card on **Ajustes → Conectores** (`/settings/connectors`). The card's "Conectar" button opens a multi-step modal/drawer.

### Step 1 — Intro

- Indexa logo + brief explanation: "Conecta tu cartera de Indexa Capital (solo lectura)."
- Link to Indexa's token page: "Genera tu token en → Área privada → Configuración de usuario → Aplicaciones."
- "Siguiente" button.
- **Backend calls:** None.

### Step 2 — Paste token

- Single text input: "Pega tu token de solo lectura."
- Security note: "Tu token se almacenará cifrado. Finlytics solo accede en modo lectura."
- "Validar" button (disabled until input non-empty).
- **Backend calls:** None yet — proceeds to step 3 on click.

### Step 3 — Validate & discover

- Spinner: "Verificando token…"
- **Backend call:** `POST /api/investments/connections` with `{ token }`.
- **On success:** Show discovered account(s) with masked labels and types. If multiple accounts: checkboxes to pick which to connect (all selected by default). "Conectar" button.
- **On 400 (invalid token):** Error message inline, back to step 2. No stored data.
- **On network error:** Generic error, retry affordance.

### Step 4 — Confirm / done

- Success state: "✅ Conectado — tu cartera se cargará en Inversiones."
- Show connected account(s) summary.
- "Ver inversiones" button → navigate to `/investments`.
- At this point, `/investments` page auto-fetches `GET /portfolio` and renders real data.
- **Backend calls:** The POST in step 3 already stored the connection. No additional call needed.

### Disconnect flow

On `Ajustes → Conectores`, connected plugins show a "Desconectar" button instead of "Conectar". Click → confirmation dialog → `DELETE /api/investments/connections/{id}` → card reverts to "Conectar".

---

## 6. Decomposition & Sequencing

### Agents & responsibilities

| Agent | Scope | Key deliverables |
|---|---|---|
| **Shuri** (backend) | Migration + provider + endpoints | `0013` migration, `investments/` package (base.py, indexa.py, crypto.py, service.py), extend `api/investments.py` with 3 new endpoints, config additions |
| **Vision** (frontend) | Wizard UI + real data viz | Wizard modal component, InvestmentsPage data-connected (KPIs, value chart, allocation donut, holdings table), ConnectorsPage card states (available/connected/error) |
| **Wanda** (design) | Wizard + viz visual design | Wizard step mockups, chart styling, allocation donut specs, new i18n keys, responsive specs for data-populated state |
| **Romanoff** (security) | Review gate (parallel) | Already delivered security policy. Reviews all PRs for compliance before merge. |
| **Barton** (tests) | Mocked integration tests | Backend: mock Indexa HTTP responses (httpx mock), test connection CRUD + portfolio aggregation. Frontend: test framework TBD. |

**Banner is NOT needed** — no AI/LLM extraction in this flow.

### Sequencing (dependency order)

```
                    ┌─ Romanoff: security policy ─── DONE ✅
                    │
Phase 2 start ──────┼─ Wanda: wizard + viz design specs ──────────────────┐
                    │                                                      │
                    └─ Shuri: migration + crypto + provider + endpoints ───┤
                                                                          │
                         Vision: wizard UI + real viz ─────────────────────┤
                                                                          │
                         Barton: backend tests (mock HTTP) ───────────────┘
```

1. **Romanoff** — already done (security policy approved).
2. **Wanda** + **Shuri** can start in parallel:
   - Wanda: wizard step designs, chart/donut specs, i18n keys.
   - Shuri: migration, crypto.py, IndexaProvider, service.py, API endpoints.
3. **Vision** — needs Wanda's designs + Shuri's endpoints (contract). Can start wizard UI as soon as Wanda delivers step designs, chart viz as soon as Shuri's portfolio endpoint is up.
4. **Barton** — starts as soon as Shuri's endpoints are testable. Mocked Indexa responses only (no live API calls in tests).

### MVP (first shippable slice)

**MVP = connect one Indexa account + see KPIs + holdings table.**

This requires:
- Shuri: migration + crypto + provider (fiscal-results only) + POST/GET/DELETE connections + GET portfolio
- Vision: wizard (4 steps) + KPI cards with real data + holdings table
- Barton: backend connection + portfolio tests

**Deferred (post-MVP):**
- Value-over-time chart (needs `total_amounts` series → chart component)
- Allocation donut (needs asset_class grouping → donut component)
- Cash vs invested split display
- Multi-account aggregation UI (if user has >1 Indexa account, MVP connects all but shows aggregated)
- Transactions, fees, benchmark, volatility
- Frontend test infrastructure (vitest setup)

---

## 7. Open Questions for Owner

| # | Question | Default if no answer |
|---|---|---|
| 1 | **Multi-account handling:** If a user's Indexa token reveals 2+ accounts (mutual + pension), connect all automatically, or let them pick? | Default: show checkboxes, all pre-selected. User can deselect. |
| 2 | **Auto-refresh on page load?** Should `/investments` call `GET /portfolio` every time the page mounts, or show a manual "Actualizar" button? | Default: auto-fetch on mount with 5-min in-memory TTL (transparent to user). |
| 3 | **Dev bootstrap:** Allow `INDEXA_API_TOKEN` in `.env` for dev testing without the wizard? (Romanoff says OK if dev-only + documented.) | Default: yes, per Romanoff's policy §7 — commented out in `.env.example`. |
| 4 | **Chart scope for MVP?** Include the value-over-time chart in MVP, or ship KPIs + holdings first and add the chart in a fast follow-up? | Default: defer chart to post-MVP. KPIs + holdings table = shippable and useful on its own. |
| 5 | **`INDEXA_ENCRYPTION_KEY` required at startup?** Romanoff says fail-closed (app won't start without it). This means existing users must set this env var even if they don't use Indexa. Acceptable? | Default: yes, fail-closed — add to `.env.example` with generation instructions. Low friction for a single-user app. |


---

### Fury Review — Integer PK Consistency (Re-evaluated, Approved)

# Phase 2: Indexa Capital Connector — Review

**Author:** Fury
**Date:** 2026-07-14T11:10:33+02:00
**Status:** APPROVED

## Verdict
**APPROVE**

## Evaluation
Upon re-review with full context:
1. **Integer PK:** The use of an auto-incrementing integer PK for investment_connections instead of a UUID was explicitly requested to match the User, Account, Category, Tag, and ImportRun models. Introducing a single UUID table in an otherwise entirely integer-PK schema violates the principle of consistency, making it harder for a solo owner to maintain. Since enumeration risks are mitigated by user-scoped 404s on access, the Integer PK is correct.
2. **Missing .env.example nit:** Acknowledged as an intentional choice to enforce the wizard-only setup and minimize paths to exposed tokens. 

The implementation fully aligns with the codebase conventions and the core architectural principles of Finlytics. The changeset is ready for commit.


---


### Security Design (Romanoff) — All 8 Invariants Verified

# Security Design: Indexa Capital Token Handling

**Author:** Romanoff (Security & Privacy Engineer)  
**Date:** 2026-07-14  
**Status:** VERIFIED ✅ — Policy + implementation review complete (2026-07-14). All 8 invariants PASS.  
**Context:** Phase 2 — real Indexa Capital connector. User pastes a read-only API token in a setup wizard; app stores it and calls Indexa GET endpoints.

---

## ⚠️ Owner Overrides (post-design, APPROVED — supersede §1 below)

Two decisions were made by DrDonoso AFTER this spec was written. They are **correct as implemented** — this doc was stale; code is right:

1. **Encryption key is `FINLYTICS_ENCRYPTION_KEY`** (general app-wide key for all connectors), NOT `INDEXA_ENCRYPTION_KEY`. The env var name in `.env.example`, `config.py`, and `crypto.py` is `FINLYTICS_ENCRYPTION_KEY`. Anywhere this doc says `INDEXA_ENCRYPTION_KEY`, substitute `FINLYTICS_ENCRYPTION_KEY`.

2. **Scoped fail-closed** (not global): The app **starts normally** without `FINLYTICS_ENCRYPTION_KEY`. Only encrypt/decrypt operations fail (raise `EncryptionNotConfiguredError` → HTTP 503). "Refuse to start" is NOT required and NOT implemented. This is correct per owner's decision. Any reference in this doc to "refuse to start" should be read as "encrypt/decrypt operations fail with 503".

---

## 1. Encryption at Rest

**Decision: Fernet confirmed.** Use `cryptography.Fernet` (AES-128-CBC + HMAC-SHA256) with a 32-byte urlsafe-base64 key from env **`FINLYTICS_ENCRYPTION_KEY`** (general app-wide key).

### Key Generation (run once, store result in `.env`)

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### `.env.example` Entry

```
# App-wide Fernet key for encrypting all connector API tokens at rest.
# The app starts normally without this key; only encrypt/decrypt operations
# (connecting or fetching a portfolio) fail with HTTP 503 when it is absent.
# Required to use the Indexa Capital connector (and any future connector).
#
# Generate once, store in .env, NEVER commit the actual key to version control:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# FINLYTICS_ENCRYPTION_KEY=
```

### Fail-Closed Behavior (SCOPED — per owner decision)

- If `FINLYTICS_ENCRYPTION_KEY` is **absent** or **invalid**: the app starts normally. Only `encrypt_token()` and `decrypt_token()` raise `EncryptionNotConfiguredError`, which the API layer catches and returns as HTTP 503. Do NOT fall back to plaintext storage under any circumstances.
- If decryption fails at read time (e.g., key was rotated without re-encrypting): return a connection-error 503 to the caller — never propagate the garbled ciphertext to the UI or logs.

### What is Encrypted

- **Column `connections.token_enc`** (TEXT): stores the Fernet ciphertext (not the plaintext token). This is the one and only column that holds any form of the credential.
- No other column stores any part of the token, partial or full.

### Key Rotation

Key rotation is out of scope for the initial build but **must** be documented in a future ops runbook: to rotate, re-encrypt all `token_enc` values before switching the env key. Until rotation is implemented, treat key loss as permanent token loss — the user must reconnect via the wizard.

---

## 2. Storage & Exposure Rules

### What Is Stored (connections table)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | FK → users | |
| `plugin_id` | TEXT | e.g. `'indexa-capital'` |
| `status` | TEXT | `'active'` \| `'error'` \| `'disconnected'` |
| `account_label_masked` | TEXT | e.g. `'PBK•••Z5'` — see masking rule below |
| `token_enc` | TEXT | Fernet ciphertext ONLY |
| `created_at` | TIMESTAMP | |
| `last_synced_at` | TIMESTAMP | nullable |

**Explicitly NOT stored:** plaintext token, Indexa account email, national document/ID (DNI/NIE/passport), any password.

### What the API MAY Return to the Frontend

- Connection `id`, `plugin_id`, `status`
- `account_label_masked` (see format below)
- `created_at`, `last_synced_at`

**The API MUST NEVER return:** `token_enc`, any decrypted token, any partial token, email, document number.

### Account Label Masking Format

The Indexa `/users/me` response may include an account identifier or username. Mask as:

> Preserve first **3** characters + `•••` + last **2** characters

Example: `PBKXXXXXXZ5` → `PBK•••Z5`

If the identifier is shorter than 6 characters, mask all but the last 2.  
Apply masking immediately on receipt from Indexa — store only the masked form. Never persist the full account identifier.

---

## 3. Token Validation Before Storage

Before persisting the token (encrypted or otherwise), the app **MUST** validate it:

1. Call `GET https://api.indexacapital.com/users/me` with header `X-AUTH-TOKEN: <token>`.
2. `200 OK` → token is valid; proceed to encrypt and store.
3. `401` or `403` → invalid or revoked token → **reject** the wizard submission with a user-facing error ("Token inválido — verifícalo en Indexa Capital."). Do NOT store anything.
4. Any other error (timeout, 5xx) → reject with a generic "no se pudo verificar el token" message. Do NOT store anything.

**Critical:** when constructing error messages or log entries about validation failures, include only the HTTP status code. Never echo the token value back in any message, exception, or log line.

---

## 4. Transport

- **HTTPS only.** All calls to `https://api.indexacapital.com` must use HTTPS. Plaintext HTTP is not acceptable.
- **TLS verification enforced.** `verify=True` always. `verify=False` is banned — treat it as a build-blocking defect.
- **Timeouts required.** Set explicit timeouts on every Indexa HTTP call: `connect_timeout=10s`, `read_timeout=30s`. Never make an unbounded call.
- **No token in redirects.** Disable automatic redirect following, or ensure the `X-AUTH-TOKEN` header is stripped before any redirect. Do not let the HTTP client silently forward auth headers to a redirected URL.

---

## 5. Least Privilege & No Over-Collection

### Read-Only Enforcement

- The app MUST ONLY make `GET` calls to the Indexa API. No `POST`, `PUT`, `PATCH`, `DELETE`.
- The app MUST NOT implement, accept, or route any call to `POST /auth/authenticate` (the Indexa password-auth flow). If this path appears in any code under review, it is a blocking defect.
- The wizard MUST NOT present fields for email, DNI/NIE, or any password. If a user somehow submits them, they must be silently discarded at the API boundary — never stored.

### Data Minimization

- Store only: the encrypted token + masked account refs + sync timestamps.
- Do NOT persist full transaction history from Indexa unless a specific user-facing feature explicitly requires it.
- Do NOT cache full `/users/me` response bodies — extract only what's needed (e.g., an account identifier for masking), then discard the rest.

---

## 6. Logging & Redaction

**NEVER log:**
- The Indexa token (plaintext or ciphertext)
- Full account numbers or identifiers
- Email addresses obtained from Indexa `/users/me`
- Document numbers (DNI/NIE/passport)
- The `INDEXA_ENCRYPTION_KEY` value

**MAY log:**
- HTTP status codes from Indexa (e.g., "Indexa validation returned 403")
- Connection `id` (UUID) and `plugin_id`
- Sync timestamps and duration
- Generic error categories (timeout, network error, bad status) — never the response body that might contain PII

**Implementation note for Shuri:** extend the existing `redaction.py` pattern to cover Indexa-specific patterns if they can appear in log strings (e.g., apply token masking if token values could leak into exception messages from the HTTP library).

---

## 7. The `.env` Token (`INDEXA_API_TOKEN`)

**Decision: Retain as dev-only bootstrap, clearly documented. DB-stored encrypted token is the source of truth.**

**Rationale:**  
Banning `INDEXA_API_TOKEN` from `.env` entirely would break any dev/smoke-test workflow that doesn't need a full wizard flow. Keeping it is acceptable provided the precedence and scope are explicit.

### Rules

1. `INDEXA_API_TOKEN` is a **dev-only convenience** for testing the connector without running the wizard. It MUST be clearly labeled as such in `.env.example`.
2. The backend MUST treat the **DB-stored encrypted token as the source of truth**. If a connection record exists in the DB, use that token — ignore `INDEXA_API_TOKEN`.
3. `INDEXA_API_TOKEN` MUST NOT be present in any production deployment, CI pipeline, Docker image, or server environment. Rocket must ensure it is absent from non-dev environments.
4. `.env.example` entry:

```
# DEV ONLY — optional bootstrap token for testing the Indexa connector without the UI wizard.
# In production, the token is stored encrypted in the DB via the wizard. Remove this from any
# non-local environment. NEVER commit a real token value.
# INDEXA_API_TOKEN=
```

5. The variable is commented out by default in `.env.example` — it must not accidentally look "required."

---

## 8. Disconnect / Revocation

**On DELETE /api/connections/{id}:**

1. **Hard-delete** the connection row — including `token_enc`. Not a soft-delete, not a status flag flip. The ciphertext must be gone.
2. **Clear any cached portfolio/holdings data** associated with that connection (delete rows keyed to `connection_id` in any holdings/snapshot tables).
3. **Inform the user** in the UI: "Tu token ha sido eliminado de Finlytics. Para mayor seguridad, también puedes revocarlo desde el panel de Indexa Capital." — the user retains independent control to revoke in Indexa's UI.
4. **On revocation detected at sync time** (Indexa returns 401/403): transition the connection to `status='error'`, surface a "Token revocado — reconecta o verifica en Indexa Capital" message. Do not delete automatically (let the user explicitly disconnect to avoid surprise data loss).

---

## 9. Threat Model Summary

| Risk | Mitigation | Build blocker? |
|------|-----------|----------------|
| **Token theft from DB** | Fernet encryption at rest; key in env, separate from DB | ✅ BLOCK if stored plaintext |
| **Token in logs** | Logging policy §6; redaction layer; never log token | ✅ BLOCK if token appears in any log |
| **Token in API response** | API schema §2 never includes `token_enc` or decrypted value | ✅ BLOCK if returned to frontend |
| **MITM to Indexa** | TLS verify=True enforced; HTTPS only; timeout guards | ✅ BLOCK if verify=False anywhere |
| **Encryption key exposure** | `FINLYTICS_ENCRYPTION_KEY` in .env, git-ignored, never in image/logs | ✅ BLOCK if key committed or logged |
| **Parallel .env credential path** | `INDEXA_API_TOKEN` dev-only; DB wins; banned in production | ⚠️ Flag in code review; not a build blocker if documented correctly |
| **Email/document over-collection** | Wizard accepts token only; `/users/me` used for validation only; PII discarded immediately | ✅ BLOCK if email/doc stored |
| **POST /auth/authenticate (credential stuffing surface)** | Path must not be implemented; ban in code review | ✅ BLOCK if present in any form |
| **Missing encryption key at startup** | Scoped fail-closed: app starts; only encrypt/decrypt ops fail (HTTP 503) | ✅ BLOCK if silently falls back to plaintext |
| **Indexa data injected into LLM pipeline** | Indexa data MUST NOT enter the LLM extraction pipeline | ⚠️ Flag now; enforce at Banner boundary |

### Summary of Build Blockers (non-negotiable before shipping Phase 2)

1. `token_enc` in DB is Fernet ciphertext — never plaintext.
2. `FINLYTICS_ENCRYPTION_KEY` absent → encrypt/decrypt fail with HTTP 503 (not silent plaintext fallback).
3. Token never appears in any API response, log line, or error message.
4. `verify=True` on all Indexa HTTP calls.
5. `POST /auth/authenticate` path does not exist anywhere in the codebase.
6. Wizard does not accept, store, or transmit email/document/password fields.
7. Disconnect hard-deletes the ciphertext.

---

## 10. Implementation Review — 2026-07-14

**Reviewer:** Romanoff (independent — designed policy, Shuri implemented)  
**Verdict: ✅ PASS — all 8 security invariants satisfied**

| # | Invariant | Verdict | Key citation |
|---|-----------|---------|--------------|
| 1 | Token encrypted at rest | ✅ PASS | `investments/service.py:129` — `encrypt_token(token)` before any DB write; `db/models.py:303` — `token_enc` TEXT Fernet ciphertext only; migration `0013_add_investment_connections.py` |
| 2 | Token never in API response / logs | ✅ PASS | `api/schemas.py:ConnectionOut` — no token field; `api/investments.py:107,145` — error messages use HTTP status, never echo token; `investments/indexa.py:141` — logs only count; `investments/service.py:281-312` — logs conn IDs + generic exception strings |
| 3 | Account masking | ✅ PASS | `investments/service.py:50-55` — `_mask_account()` correct format first3•••last2; raw `account_number` returned transiently in `/validate` only (documented intentional, never stored); `db/models.py:293` — only `account_label_masked` stored |
| 4 | Fail-closed (scoped) | ✅ PASS | `investments/crypto.py:24-36` — raises `EncryptionNotConfiguredError` on absent/invalid key; `api/investments.py:139,196` — catches → 503; never falls back to plaintext |
| 5 | Transport | ✅ PASS | `investments/indexa.py:62-69` — `verify=True`, `follow_redirects=False`, timeouts 10s/30s, base URL `https://` |
| 6 | Least privilege | ✅ PASS | Only `client.get()` calls; no POST/auth/authenticate anywhere in codebase; wizard has one field (`type="password"` input = token only); no email/document/password in any schema |
| 7 | Disconnect hard-deletes | ✅ PASS | `investments/service.py:215` — `await db.delete(row)`; `service.py:217` — `clear_connection_cache()` |
| 8 | Data minimization | ✅ PASS | Migration/model: no email/doc columns; `investments/indexa.py:133-139` — only account_number/type/status extracted from `/users/me`; email/username discarded immediately |

**Tests cross-checked:** `test_connect_response_never_contains_raw_token`, `test_get_connections_no_token_enc_in_response`, `test_connect_missing_encryption_key_returns_503`, `test_portfolio_missing_encryption_key_returns_503`, `test_indexa_client_tls_verify_and_no_redirects`, `test_crypto_missing_key_encrypt_raises`, `test_crypto_missing_key_decrypt_raises`, `test_crypto_tampered_ciphertext_raises`, `test_validate_stores_nothing_in_db`, `test_mask_account_standard` — all genuinely assert the invariants, not just name them.

**One observation (not a fail):** `DiscoveredAccountOut.account_number` (raw) is returned in `/connections/validate` responses. This is intentional: the wizard needs it for the subsequent connect call. The server re-validates ownership in `connect_plugin()` (`service.py:117-127`), so a client cannot use this to spoof a different account. The field is transient (no storage), and account numbers are internal Indexa identifiers, not IBANs/emails/DNI.


---

### Backend Implementation Contract (Shuri) — 5 Endpoints, 858 Tests PASS

# Shuri → Backend Contract: Indexa Capital Phase 2

**Author:** Shuri (Backend Engineer)  
**Date:** 2026-07-14  
**Status:** SHIPPED — 838 tests green  
**For:** Vision (frontend), Barton (tests), Wanda (i18n keys)

---

## Base URL

All endpoints are prefixed `/api/investments`.  All require a valid session cookie (401 if absent).

---

## 1. GET /api/investments/plugins

Returns the plugin registry.  **Indexa Capital status is dynamic** from Phase 2.

```
GET /api/investments/plugins
Authorization: session cookie
```

**Response 200** `list[InvestmentPluginOut]`

```json
[
  {
    "id": "indexa-capital",
    "name": "Indexa Capital",
    "description": "Automated index-fund portfolio management",
    "icon": "🏦",
    "status": "available" | "connected",
    "auth_type": "token",
    "supported_features": ["holdings", "transactions", "performance"]
  },
  {
    "id": "generic-broker",
    "status": "coming_soon",
    ...
  },
  {
    "id": "crypto-exchange",
    "status": "coming_soon",
    ...
  }
]
```

`indexa-capital.status`:
- `"connected"` — user has ≥1 active connection
- `"available"` — no active connections; wizard CTA shown

---

## 2. POST /api/investments/connections/validate  ← Step 1 of wizard

Validate a token and discover accounts.  **Stores NOTHING** — no DB writes, no token persisted, no encryption required.

```
POST /api/investments/connections/validate
Content-Type: application/json

{ "token": "<indexa-read-only-token>" }
```

**Response 200** `ValidateTokenResponse`

```json
{
  "accounts": [
    {
      "account_number": "PBKLBYZ5",
      "account_number_masked": "PBK•••Z5",
      "type": "mutual",
      "status": "active"
    }
  ]
}
```

`account_number` is the raw identifier (transient — only use it in the next connect call; it is NEVER stored).  
`account_number_masked` is for display in the wizard checkbox list.

**Errors:**

| Code | Condition | Detail |
|---|---|---|
| 400 | Indexa rejects token (401/403) | `"Token inválido — verifícalo en Indexa Capital."` |
| 503 | Network / timeout error | `"No se pudo verificar el token — error de red con Indexa Capital."` |

---

## 3. POST /api/investments/connections  ← Step 2 of wizard

Re-validate token server-side, persist **only the selected accounts**.  
Server enforces ownership: any `account_number` not owned by the token is silently dropped.

```
POST /api/investments/connections
Content-Type: application/json

{
  "token": "<indexa-read-only-token>",
  "account_numbers": ["PBKLBYZ5"]
}
```

`account_numbers` must be non-empty and should come from the validate step.

**Response 201** `list[ConnectionOut]` — one entry per connected account

```json
[
  {
    "id": 1,
    "plugin_id": "indexa-capital",
    "status": "active",
    "account_label_masked": "PBK•••Z5",
    "created_at": "2026-07-14T11:10:33+02:00",
    "last_synced_at": null
  }
]
```

**⚠️ Token NEVER appears in any response.**

**Errors:**

| Code | Condition | Detail |
|---|---|---|
| 400 | `account_numbers` is empty | `"account_numbers must not be empty."` |
| 400 | Indexa rejects token (401/403) | `"Token inválido — verifícalo en Indexa Capital."` |
| 400 | All `account_numbers` non-owned | `"Los account_numbers seleccionados no pertenecen a este token."` |
| 503 | Network / timeout error | `"No se pudo verificar el token — error de red con Indexa Capital."` |
| 503 | `FINLYTICS_ENCRYPTION_KEY` absent | `"Server not configured for encryption — contact the administrator."` |

---

## 4. GET /api/investments/connections

List all connected plugins for the authenticated user.

```
GET /api/investments/connections
```

**Response 200** `list[ConnectionOut]`

```json
[
  {
    "id": 1,
    "plugin_id": "indexa-capital",
    "status": "active",               // active | error | disconnected
    "account_label_masked": "PBK•••Z5",
    "created_at": "2026-07-14T11:10:33+02:00",
    "last_synced_at": "2026-07-14T11:12:00+02:00"
  }
]
```

**`status` values:**
- `active` — token valid, data fetchable
- `error` — Indexa returned 401/403 at last sync; user should reconnect
- `disconnected` — manually disconnected (hard-deleted; this value appears in cache only)

---

## 5. DELETE /api/investments/connections/{id}

Hard-deletes the connection row **and its encrypted token ciphertext**.  No soft-delete.

```
DELETE /api/investments/connections/1
```

**Response 204** — no body

**Errors:**

| Code | Condition |
|---|---|
| 404 | connection not found (or belongs to another user) |

---

## 6. GET /api/investments/portfolio

Aggregate portfolio for all active connections.  Includes everything Vision needs for the full Inversiones page.

```
GET /api/investments/portfolio
```

**Response 200** `InvestmentPortfolioOut`

```json
{
  "total_value": 12345.67,
  "total_invested": 11000.00,
  "total_gain_loss": 1345.67,
  "total_gain_loss_pct": 0.1223,
  "currency": "EUR",
  "plugins_connected": 1,
  "last_updated": "2026-07-14T11:12:00.123456+00:00",

  "returns": {
    "twr_annual": 0.0851,
    "xirr": 0.0912,
    "pl": 1345.67,
    "invested": 11000.00
  },

  "value_series": [
    { "date": "20240101", "value": 10200.00 },
    { "date": "20240201", "value": 10450.00 }
  ],

  "cash_invested": {
    "cash_amount": 250.00,
    "instruments_amount": 12095.67,
    "instruments_cost": 10750.00,
    "total_amount": 12345.67
  },

  "holdings": [
    {
      "plugin_id": "indexa-capital",
      "name": "Vanguard Global Stock Index Fund",
      "ticker": "IE00B03HCZ61",
      "asset_class": "equity",
      "units": 42.5,
      "current_value": 8320.00,
      "cost_basis": 7500.00,
      "currency": "EUR",
      "gain_loss": 820.00,
      "gain_loss_pct": 0.1093,
      "last_updated": "2026-07-14T11:12:00.123456+00:00"
    }
  ]
}
```

**No-connection empty state (no wizard completed):**

```json
{
  "total_value": 0.0,
  "total_invested": null,
  "total_gain_loss": null,
  "total_gain_loss_pct": null,
  "currency": "EUR",
  "plugins_connected": 0,
  "last_updated": null,
  "returns": null,
  "value_series": [],
  "cash_invested": null,
  "holdings": []
}
```

**Errors:**

| Code | Condition |
|---|---|
| 503 | `FINLYTICS_ENCRYPTION_KEY` absent — cannot decrypt tokens |

**Caching:** 5-minute in-memory TTL per `connection_id`.  Rapid page refreshes reuse cached data; the cache is evicted on DELETE.

---

## Extended Schema Reference

### InvestmentPortfolioOut (extended)

```python
class InvestmentReturns(BaseModel):
    twr_annual: float | None = None    # time-weighted annualised return
    xirr: float | None = None          # money-weighted annualised return
    pl: float | None = None            # absolute P&L in EUR
    invested: float | None = None      # net capital invested

class ValuePoint(BaseModel):
    date: str     # "YYYYMMDD" — matches Indexa total_amounts keys
    value: float

class CashInvestedSplit(BaseModel):
    cash_amount: float
    instruments_amount: float
    instruments_cost: float
    total_amount: float

class InvestmentPortfolioOut(BaseModel):
    # existing fields unchanged
    total_value: float
    total_invested: float | None
    total_gain_loss: float | None
    total_gain_loss_pct: float | None
    currency: str
    holdings: list[InvestmentHoldingOut]
    plugins_connected: int
    last_updated: str | None
    # Phase 2 additions
    returns: InvestmentReturns | None = None
    value_series: list[ValuePoint] = []
    cash_invested: CashInvestedSplit | None = None
```

### ConnectionOut

```python
class ConnectionOut(BaseModel):
    id: int
    plugin_id: str
    status: str                         # active | error | disconnected
    account_label_masked: str | None    # e.g. "PBK•••Z5"
    created_at: datetime
    last_synced_at: datetime | None
```

**`token_enc` is NEVER included in `ConnectionOut` or any API response.**

### ConnectCreate (Step 2 body)

```python
class ConnectCreate(BaseModel):
    token: str               # raw Indexa read-only token
    account_numbers: list[str]  # from validate step; server re-validates ownership
```

### ValidateTokenRequest (Step 1 body)

```python
class ValidateTokenRequest(BaseModel):
    token: str
```

### ValidateTokenResponse (Step 1 response)

```python
class DiscoveredAccountOut(BaseModel):
    account_number: str          # raw — transient, never stored
    account_number_masked: str   # PBK•••Z5 — for display
    type: str
    status: str

class ValidateTokenResponse(BaseModel):
    accounts: list[DiscoveredAccountOut]
```

---

## Indexa → Finlytics Field Mapping

| Indexa source | Finlytics field |
|---|---|
| `fiscal_results[].instrument.name` | `holding.name` |
| `fiscal_results[].instrument.identifier` (ISIN) | `holding.ticker` |
| `fiscal_results[].instrument.asset_class` (mapped) | `holding.asset_class` |
| `fiscal_results[].titles` | `holding.units` |
| `fiscal_results[].amount` | `holding.current_value` |
| `fiscal_results[].cost_amount` | `holding.cost_basis` |
| `fiscal_results[].profit_loss` | `holding.gain_loss` |
| `profit_loss / cost_amount` | `holding.gain_loss_pct` |
| `performance.total_amount` | `total_value` |
| `performance.return.investment` | `total_invested` / `returns.invested` |
| `performance.return.pl` | `total_gain_loss` / `returns.pl` |
| `performance.return.time_return_annual` | `returns.twr_annual` |
| `performance.return.XIRR` | `returns.xirr` |
| `performance.total_amounts` (dict) | `value_series` |
| `performance.portfolios[-1]` | `cash_invested` |

**Asset class mapping:**

| Indexa value | Finlytics asset_class |
|---|---|
| `equity_europe`, `equity_north_america`, `equity_pacific`, `equity_emerging` (any `equity_*`) | `"equity"` |
| `fixed_income_*` | `"fixed_income"` |
| `cash`, `money_market` | `"cash"` |
| anything else | `"other"` |

---

## Notes for Barton (test mocking)

Wizard flow is now two steps — mock both:

**Step 1 — Validate:**
- `POST /connections/validate` with valid mock token → 200 `{ "accounts": [...] }`.
- `POST /connections/validate` with mock returning 401 → 400 `"Token inválido"`.
- Response always has `accounts` key; `account_number` present (raw), `account_number_masked` present.

**Step 2 — Connect:**
- `POST /connections` with `{ token, account_numbers: ["ACC1"] }` → 201 list.
- `POST /connections` with `account_numbers: []` → 400 (no service call).
- `POST /connections` with all `account_numbers` not owned → 400 `NoValidAccountsError`.
- `POST /connections` with a mix of owned + non-owned → only owned ones in response.
- `POST /connections` when `FINLYTICS_ENCRYPTION_KEY` absent → 503.

**Other endpoints:**
- Mock `GET https://api.indexacapital.com/users/me` with `httpx.MockTransport` or `respx`.
- Mock `GET /accounts/{acc}/fiscal-results` and `GET /accounts/{acc}/performance`.
- `GET /portfolio` with no connections → 200 with `total_value=0, holdings=[]`.
- `DELETE /connections/999` → 404.

## Notes for Vision (frontend)

- `value_series[].date` is `"YYYYMMDD"` format (from Indexa) — parse with `dayjs(date, "YYYYMMDD")` or equivalent.
- `returns.twr_annual` and `returns.xirr` are `null` when user has multiple connected accounts (non-aggregatable).
- `holdings[].gain_loss_pct` is a decimal (0.1093 = 10.93%) — multiply by 100 for display.
- `total_gain_loss_pct` same convention.
- `cash_invested.instruments_cost` = total amount invested in instruments (cost basis); `instruments_amount` = current market value.


---

### Design Spec (Wanda) — Wizard + Viz CSS Complete

# Wanda Design Spec — Indexa Phase 2

**Author:** Wanda (UX/UI)  
**Date:** 2026-07-14  
**Status:** READY FOR VISION  
**Depends on:** Shuri's endpoints (§3 of fury-indexa-phase2-plan.md)

All CSS is in `frontend/src/index.css` — appended after the existing investments skeleton block. Build verified: `npm run build` passes with 0 errors.

---

## REUSE MAP (no new CSS needed for these)

| UI element | Reuse | Notes |
|---|---|---|
| Modal shell | `.modal-backdrop` `.modal` `.modal-header` `.modal-title` `.modal-close` `.modal-body` `.modal-footer` | Standard modal pattern |
| Spinner | `.spinner-wrap` `.spinner` `.spinner-label` | Validation step |
| KPI row | `.kpi-grid` `.kpi-card` `.kpi-label` `.kpi-value` `.kpi-sub` | KPIs + `.kpi-value.income/expense` for P&L |
| Allocation donut | `.cat-chart-layout` `.cat-donut-wrap` `.cat-donut-center` `.cat-table-wrap` `.cat-table` `.cat-row` | 1:1 reuse from SpendingByCategory |
| State boxes | `.state-box` `.state-box.error` | Loading + error |
| Recharts tooltip | `.recharts-default-tooltip` global override | Already dark-mode correct |
| Form inputs | `.form-input` `.form-group` `.form-hint` | General modal forms |
| Buttons | `.btn-primary` `.btn-secondary` `.btn-danger` | Footer CTAs |
| Page layout | `.dashboard` | InvestmentsPage root |
| Plugin card shell | `.plugin-card` `.plugin-card__icon` `.plugin-card__name` `.plugin-card__description` | ConnectorsPage |
| Coming-soon badge | `.coming-soon-badge` | Non-Indexa cards |

---

## Deliverable A — Indexa Wizard

### Overview

A 4-step modal launched from the Indexa card on `ConnectorsPage`. Uses the standard `.modal` shell with a new narrow variant `.modal.inv-wizard` (480px desktop / full bottom-sheet mobile ≤600px).

### DOM structure

```jsx
{/* Trigger: onClick → open wizard */}
<button className="btn-primary" onClick={onOpenWizard}>{t.wizardOpen}</button>

{/* Wizard modal */}
<div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="wizard-title">
  <div className="modal inv-wizard">

    {/* Step progress indicator (above modal header) */}
    <div className="inv-wizard__progress" aria-label={t.wizardProgressLabel}>
      <span className="inv-wizard__step-dot inv-wizard__step-dot--done" />
      <span className="inv-wizard__step-sep inv-wizard__step-sep--done" />
      <span className="inv-wizard__step-dot inv-wizard__step-dot--active" />
      <span className="inv-wizard__step-sep" />
      <span className="inv-wizard__step-dot" />
      <span className="inv-wizard__step-sep" />
      <span className="inv-wizard__step-dot" />
    </div>

    {/* Standard modal header */}
    <div className="modal-header">
      <span className="modal-title" id="wizard-title">{t.wizardTitle}</span>
      <button className="modal-close" onClick={onClose} aria-label={t.wizardClose}>✕</button>
    </div>

    {/* Modal body — one of four step variants */}
    <div className="modal-body">
      {/* ── Step 1: Intro ─────────────────────────────── */}
      <div className="inv-wizard__body">
        <span className="inv-wizard__logo" aria-hidden="true">📈</span>
        <h2 className="inv-wizard__title">{t.wizardStep1Title}</h2>
        <p className="inv-wizard__desc">{t.wizardStep1Desc}</p>
        <a
          className="inv-wizard__link"
          href="https://app.indexacapital.com/user/settings"
          target="_blank"
          rel="noopener noreferrer"
        >
          🔑 {t.wizardStep1Link}
        </a>
        <div className="inv-wizard__security-note">
          <span className="inv-wizard__security-note-icon" aria-hidden="true">🔒</span>
          <span>{t.wizardSecurityNote}</span>
        </div>
      </div>

      {/* ── Step 2: Paste token ───────────────────────── */}
      <div className="inv-wizard__body">
        <h2 className="inv-wizard__title">{t.wizardStep2Title}</h2>
        <div className="inv-wizard__token-field">
          <label className="inv-wizard__token-label" htmlFor="indexa-token">
            {t.wizardTokenLabel}
          </label>
          <input
            id="indexa-token"
            type="password"
            className="inv-wizard__token-input"
            placeholder={t.wizardTokenPlaceholder}
            value={token}
            onChange={e => setToken(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <div className="inv-wizard__security-note">
          <span className="inv-wizard__security-note-icon" aria-hidden="true">🔒</span>
          <span>{t.wizardSecurityNote}</span>
        </div>
      </div>

      {/* ── Step 3a: Validating (spinner) ────────────── */}
      <div className="spinner-wrap">
        <div className="spinner" role="status" aria-label={t.wizardStep3Validating} />
        <p className="spinner-label">{t.wizardStep3Validating}</p>
      </div>

      {/* ── Step 3b: Error (invalid token) ───────────── */}
      <div className="inv-wizard__body">
        <div className="inv-wizard__error-banner" role="alert">
          <span className="inv-wizard__error-banner-icon" aria-hidden="true">⚠️</span>
          <span>{t.wizardErrorInvalidToken}</span>
        </div>
        <div className="inv-wizard__token-field">
          {/* re-show token input for correction */}
          <label className="inv-wizard__token-label" htmlFor="indexa-token-retry">
            {t.wizardTokenLabel}
          </label>
          <input
            id="indexa-token-retry"
            type="password"
            className="inv-wizard__token-input"
            placeholder={t.wizardTokenPlaceholder}
            value={token}
            onChange={e => setToken(e.target.value)}
            autoComplete="off"
          />
        </div>
      </div>

      {/* ── Step 3c: Accounts discovered ─────────────── */}
      <div className="inv-wizard__body">
        <h2 className="inv-wizard__title">{t.wizardStep3Title}</h2>
        <p className="inv-wizard__desc">{t.wizardStep3Desc}</p>
        <div className="inv-wizard__account-list">
          {accounts.map(acc => (
            <label
              key={acc.account_number_masked}
              className={`inv-wizard__account-item${selectedAccounts.includes(acc.connection_id) ? ' inv-wizard__account-item--checked' : ''}`}
            >
              <input
                type="checkbox"
                className="inv-wizard__account-checkbox"
                checked={selectedAccounts.includes(acc.connection_id)}
                onChange={() => toggleAccount(acc.connection_id)}
              />
              <div className="inv-wizard__account-info">
                <span className="inv-wizard__account-label">{acc.account_number_masked}</span>
                <span className="inv-wizard__account-type">{acc.type}</span>
              </div>
            </label>
          ))}
        </div>
      </div>

      {/* ── Step 4: Success ───────────────────────────── */}
      <div className="inv-wizard__success">
        <span className="inv-wizard__success-icon" aria-hidden="true">✅</span>
        <h2 className="inv-wizard__success-title">{t.wizardStep4Title}</h2>
        <p className="inv-wizard__success-desc">{t.wizardStep4Desc}</p>
        <div className="inv-wizard__success-accounts">
          {connectedAccounts.map(acc => (
            <div className="inv-wizard__success-account" key={acc.account_number_masked}>
              <em className="inv-wizard__success-account-check" aria-hidden="true">✓</em>
              {acc.account_number_masked}
            </div>
          ))}
        </div>
      </div>
    </div>

    {/* Modal footer — buttons vary per step */}
    <div className="modal-footer">
      {/* Step 1 */}
      <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
      <button className="btn-primary" onClick={goToStep2}>{t.wizardNext}</button>

      {/* Step 2 */}
      <button className="btn-secondary" onClick={goBack}>{t.wizardBack}</button>
      <button className="btn-primary" onClick={validateToken} disabled={!token.trim()}>
        {t.wizardValidate}
      </button>

      {/* Step 3b (error) */}
      <button className="btn-secondary" onClick={onClose}>{t.wizardClose}</button>
      <button className="btn-primary" onClick={validateToken} disabled={!token.trim()}>
        {t.wizardRetry}
      </button>

      {/* Step 3c (accounts) */}
      <button className="btn-secondary" onClick={goBack}>{t.wizardBack}</button>
      <button className="btn-primary" onClick={connect} disabled={selectedAccounts.length === 0}>
        {t.wizardConnect}
      </button>

      {/* Step 4 */}
      <button className="btn-primary" onClick={goToInvestments}>{t.wizardViewInvestments}</button>
    </div>

  </div>
</div>
```

### Step states summary

| Step | `inv-wizard__progress` dots | Body content | Footer |
|---|---|---|---|
| 1 — Intro | dot 1 active | logo + title + desc + link + security note | Cerrar / Siguiente |
| 2 — Token | dot 2 active | title + token-field + security note | ← Volver / Validar (disabled until non-empty) |
| 3a — Validating | dot 3 active | `.spinner-wrap` | — (no buttons, auto-advances) |
| 3b — Error | dot 2 active (back to 2) | error-banner + token-field (pre-filled) | Cerrar / Reintentar |
| 3c — Accounts | dot 3 active | title + desc + account-list | ← Volver / Conectar (disabled if none selected) |
| 4 — Success | all dots done | `.inv-wizard__success` block | Ver inversiones → |

---

## Deliverable B — InvestmentsPage Populated

### Page root

When a connection exists, **replace** the empty state with the fully populated layout below. Reuse the existing `<main className="dashboard">` as the page root.

```jsx
<main className="dashboard">

  {/* 1. Page header */}
  <div className="investments-header">
    <h1 className="investments-page-title">{t.investmentsTitle}</h1>
  </div>

  {/* 2. Connected account header strip */}
  <div className="inv-account-header">
    <div className="inv-account-header__left">
      <span className="inv-account-header__icon" aria-hidden="true">🔗</span>
      <span className="inv-account-header__label">{connection.account_label_masked}</span>
      {connection.last_synced_at && (
        <span className="inv-account-header__updated">
          {t.invAccountUpdated(formatRelativeTime(connection.last_synced_at))}
        </span>
      )}
    </div>
    {/* "Desconectar" lives on the ConnectorsPage — nothing needed here */}
  </div>

  {/* 3. KPI row — reuse .kpi-grid + .kpi-card */}
  <div className="kpi-grid">
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalValue}</div>
      <div className="kpi-value">{formatCurrency(portfolio.total_value)}</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiTotalInvested}</div>
      <div className="kpi-value">{formatCurrency(portfolio.returns?.invested ?? portfolio.total_invested)}</div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.investmentsKpiPnL}</div>
      <div className={`kpi-value ${portfolio.total_gain_loss >= 0 ? 'income' : 'expense'}`}>
        {formatCurrency(portfolio.total_gain_loss)}
      </div>
      <div className="kpi-sub">
        {portfolio.total_gain_loss_pct >= 0 ? '+' : ''}{portfolio.total_gain_loss_pct.toFixed(2)}%
      </div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.invKpiTwr}</div>
      <div className={`kpi-value ${(portfolio.returns?.twr_annual ?? 0) >= 0 ? 'income' : 'expense'}`}>
        {portfolio.returns?.twr_annual != null
          ? `${(portfolio.returns.twr_annual * 100).toFixed(2)}%`
          : '—'}
      </div>
    </div>
    <div className="kpi-card">
      <div className="kpi-label">{t.invKpiXirr}</div>
      <div className={`kpi-value ${(portfolio.returns?.xirr ?? 0) >= 0 ? 'income' : 'expense'}`}>
        {portfolio.returns?.xirr != null
          ? `${(portfolio.returns.xirr * 100).toFixed(2)}%`
          : '—'}
      </div>
    </div>
  </div>

  {/* 4. Charts row: value-over-time + allocation donut */}
  <div className="inv-charts-row">

    {/* 4a. Value over time */}
    <div className="card inv-chart-card inv-chart-card--value">
      <div className="card-title">{t.invChartValueTitle}</div>
      {loading && <div className="state-box"><span className="icon">⏳</span><span>{t.loading}</span></div>}
      {!loading && portfolio.value_series.length === 0 && (
        <div className="state-box"><span className="icon">📈</span><span>{t.noDataPeriod}</span></div>
      )}
      {!loading && portfolio.value_series.length > 0 && (
        <div className="inv-value-chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="invValueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="var(--primary)" stopOpacity={0.22} />
                  <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tickFormatter={v => `${(v / 1000).toFixed(0)}k€`}
                tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                axisLine={false}
                tickLine={false}
                width={52}
              />
              <Tooltip
                contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                labelStyle={{ color: 'var(--text)' }}
                itemStyle={{ color: 'var(--text)' }}
                formatter={(value: number) => [formatCurrency(value), t.investmentsKpiTotalValue]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke="var(--primary)"
                strokeWidth={2}
                fill="url(#invValueGrad)"
                dot={false}
                activeDot={{ r: 4, fill: 'var(--primary)' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>

    {/* 4b. Allocation donut — REUSE cat-chart-layout */}
    <div className="card inv-chart-card inv-chart-card--allocation">
      <div className="card-title">{t.invChartAllocationTitle}</div>
      {loading && <div className="state-box"><span className="icon">⏳</span><span>{t.loading}</span></div>}
      {!loading && allocationData.length === 0 && (
        <div className="state-box"><span className="icon">🍩</span><span>{t.noDataPeriod}</span></div>
      )}
      {!loading && allocationData.length > 0 && (
        <div className="cat-chart-layout">
          <div className="cat-donut-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={allocationData}
                  cx="50%"
                  cy="50%"
                  innerRadius={72}
                  outerRadius={100}
                  dataKey="value"
                  paddingAngle={2}
                >
                  {allocationData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} opacity={0.9} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                  labelStyle={{ color: 'var(--text)' }}
                  itemStyle={{ color: 'var(--text)' }}
                  formatter={(value: number, name: string) => [formatCurrency(value), t[`invAsset${capitalize(name)}`]]}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="cat-donut-center">
              <span className="cat-donut-label">{t.invChartAllocationTitle}</span>
              <span className="cat-donut-total">{formatCurrency(portfolio.total_value)}</span>
            </div>
          </div>
          <div className="cat-table-wrap">
            <table className="cat-table">
              <thead>
                <tr>
                  <th className="cat-th-name">{t.invColClass}</th>
                  <th className="cat-th-num">{t.catColValue}</th>
                  <th className="cat-th-num">{t.catColWeight}</th>
                </tr>
              </thead>
              <tbody>
                {allocationData.map((item, i) => (
                  <tr key={item.name} className="cat-row">
                    <td className="cat-td-name">
                      <div className="cat-td-name-inner">
                        <span className="cat-swatch" style={{ background: item.color }} />
                        <span className="cat-td-label">{t[`invAsset${capitalize(item.name)}`]}</span>
                      </div>
                    </td>
                    <td className="cat-td-num">{formatCurrency(item.value)}</td>
                    <td className="cat-td-num cat-td-weight">
                      {(item.value / portfolio.total_value * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>

  </div>

  {/* 5. Holdings table */}
  <div className="card inv-holdings-card">
    <div className="card-title card-title--has-action">
      <span>{t.investmentsHoldingsTitle}</span>
      <span className="kpi-sub">{portfolio.holdings.length} {t.invHoldingsCount}</span>
    </div>
    {portfolio.holdings.length === 0 ? (
      <div className="state-box">
        <span className="icon">📋</span>
        <span>{t.invHoldingsEmpty}</span>
      </div>
    ) : (
      <div className="inv-holdings-table-wrap">
        <table className="inv-holdings-table">
          <thead>
            <tr>
              <th className="inv-th-sortable">{t.invColName}</th>
              <th>{t.invColISIN}</th>
              <th>{t.invColClass}</th>
              <th className="inv-th-num inv-th-sortable inv-th-sort-active">{t.invColValue}</th>
              <th className="inv-th-num">{t.invColWeight}</th>
              <th className="inv-th-num">{t.invColCost}</th>
              <th className="inv-th-num inv-th-sortable">{t.invColPnL}</th>
              <th className="inv-th-num">{t.invColPnLPct}</th>
            </tr>
          </thead>
          <tbody>
            {portfolio.holdings.map(h => {
              const weight = portfolio.total_value > 0 ? (h.current_value / portfolio.total_value * 100).toFixed(1) : '0.0'
              const isPos = h.gain_loss >= 0
              return (
                <tr key={h.ticker}>
                  <td className="inv-td-name" title={h.name}>{h.name}</td>
                  <td className="inv-td-isin">{h.ticker}</td>
                  <td>
                    <span className={`inv-asset-class-badge inv-asset-class-badge--${h.asset_class}`}>
                      {t[`invAsset${capitalize(h.asset_class)}`] ?? h.asset_class}
                    </span>
                  </td>
                  <td className="inv-td-num">{formatCurrency(h.current_value)}</td>
                  <td className="inv-td-weight">{weight}%</td>
                  <td className="inv-td-num">{formatCurrency(h.cost_basis)}</td>
                  <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                    {isPos ? '+' : ''}{formatCurrency(h.gain_loss)}
                  </td>
                  <td className={`inv-td-num ${isPos ? 'inv-pnl--pos' : 'inv-pnl--neg'}`}>
                    {isPos ? '+' : ''}{(h.gain_loss_pct * 100).toFixed(2)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>

  {/* Loading / error states (replaces the above when applicable) */}
  {loading && (
    <div className="card">
      <div className="state-box">
        <span className="icon">⏳</span>
        <span>{t.loading}</span>
      </div>
    </div>
  )}
  {error && (
    <div className="card">
      <div className="state-box error">
        <span className="icon">⚠️</span>
        <span>{t.invErrorLoading}: {error}</span>
      </div>
    </div>
  )}

</main>
```

### Recharts: value-over-time chart spec

| Prop | Value |
|---|---|
| Chart type | `AreaChart` (Recharts) |
| `ResponsiveContainer` | `width="100%" height="100%"` inside `.inv-value-chart-wrap` (height: 260px CSS) |
| X-axis data key | `date` — format `"MMM YY"` from `YYYY-MM-DD` |
| Y-axis formatter | `v => ${(v/1000).toFixed(0)}k€` |
| Area stroke | `var(--primary)`, strokeWidth 2 |
| Area fill | SVG gradient `invValueGrad`: 22% opacity top → 2% bottom |
| Grid | horizontal only (`vertical={false}`), `var(--border)` |
| Tooltip | existing app style: `var(--surface)` bg, `var(--border)` border |
| Dot | `dot={false}`, `activeDot` r=4 fill `var(--primary)` |

### Allocation donut color palette

Use asset-class fixed colors (not random) for consistent visual identity:

```ts
const ASSET_CLASS_COLORS: Record<string, string> = {
  equity:       '#2563eb',   // primary blue
  fixed_income: '#22c55e',   // income green
  cash:         '#94a3b8',   // muted slate
  other:        '#8b5cf6',   // purple
}
```

---

## Deliverable C — ConnectorsPage Card States

### Available (current, unchanged)
```jsx
<div className="plugin-card">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  {/* No badge when available */}
  <button className="btn-primary" onClick={onOpenWizard}>{t.investmentsConnect}</button>
</div>
```

### Connected
```jsx
<div className="plugin-card connector-card--connected">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  <span className="connected-badge">✓ {t.connectorConnected}</span>
  <button className="btn-disconnect" onClick={onDisconnect}>{t.connectorDisconnect}</button>
</div>
```

### Error
```jsx
<div className="plugin-card connector-card--error">
  <span className="plugin-card__icon">📈</span>
  <span className="plugin-card__name">{plugin.name}</span>
  <p className="plugin-card__description">{plugin.description}</p>
  <span className="error-badge">⚠ {t.connectorError}</span>
  <button className="btn-primary" onClick={onOpenWizard}>{t.connectorErrorRetry}</button>
</div>
```

### Coming Soon (other cards, unchanged)
```jsx
<div className="plugin-card">
  {/* ... */}
  <span className="coming-soon-badge">{t.investmentsComingSoon}</span>
  <button className="btn-primary" disabled aria-disabled="true">{t.investmentsConnect}</button>
</div>
```

---

## Full i18n key list (new keys only)

Vision must add these to `frontend/src/i18n/es.ts`, `en.ts`, and `Dict` in `index.ts`.

### Wizard keys

| Key | ES | EN |
|---|---|---|
| `wizardTitle` | `'Conectar Indexa Capital'` | `'Connect Indexa Capital'` |
| `wizardProgressLabel` | `'Progreso del asistente'` | `'Wizard progress'` |
| `wizardStep1Title` | `'Conecta tu cartera de Indexa Capital'` | `'Connect your Indexa Capital portfolio'` |
| `wizardStep1Desc` | `'Solo lectura. Finlytics nunca realiza operaciones en tu nombre.'` | `'Read-only. Finlytics never trades on your behalf.'` |
| `wizardStep1Link` | `'Genera tu token → Área privada → Configuración → Aplicaciones'` | `'Generate your token → Private area → Settings → Applications'` |
| `wizardSecurityNote` | `'Tu token se almacenará cifrado. Finlytics solo accede en modo lectura.'` | `'Your token is stored encrypted. Finlytics only accesses in read-only mode.'` |
| `wizardNext` | `'Siguiente'` | `'Next'` |
| `wizardStep2Title` | `'Pega tu token de solo lectura'` | `'Paste your read-only token'` |
| `wizardTokenLabel` | `'Token de acceso'` | `'Access token'` |
| `wizardTokenPlaceholder` | `'Pega aquí tu token…'` | `'Paste your token here…'` |
| `wizardValidate` | `'Validar'` | `'Validate'` |
| `wizardStep3Validating` | `'Verificando token…'` | `'Verifying token…'` |
| `wizardStep3Title` | `'Cuentas encontradas'` | `'Accounts found'` |
| `wizardStep3Desc` | `'Selecciona las cuentas que quieres conectar.'` | `'Select the accounts you want to connect.'` |
| `wizardConnect` | `'Conectar'` | `'Connect'` |
| `wizardStep4Title` | `'¡Conectado!'` | `'Connected!'` |
| `wizardStep4Desc` | `'Tu cartera se cargará en Inversiones.'` | `'Your portfolio will load in Investments.'` |
| `wizardViewInvestments` | `'Ver inversiones'` | `'View investments'` |
| `wizardErrorInvalidToken` | `'Token inválido. Comprueba que es correcto y vuelve a intentarlo.'` | `'Invalid token. Check it\'s correct and try again.'` |
| `wizardErrorNetwork` | `'Error de conexión. Comprueba que el servidor está en marcha.'` | `'Connection error. Check the server is running.'` |
| `wizardBack` | `'← Volver'` | `'← Back'` |
| `wizardRetry` | `'Reintentar'` | `'Retry'` |
| `wizardClose` | `'Cerrar'` | `'Close'` |
| `wizardOpen` | `'Conectar'` | `'Connect'` |

### Investments page keys

| Key | ES | EN |
|---|---|---|
| `invKpiTwr` | `'TWR anual'` | `'Annual TWR'` |
| `invKpiXirr` | `'XIRR'` | `'XIRR'` |
| `invChartValueTitle` | `'Evolución del valor'` | `'Value over time'` |
| `invChartAllocationTitle` | `'Asignación por clase'` | `'Allocation by class'` |
| `invHoldingsEmpty` | `'Sin posiciones en cartera'` | `'No holdings in portfolio'` |
| `invHoldingsCount` | `'posiciones'` | `'holdings'` |
| `invAccountUpdated` | `(t: string) => \`Actualizado \${t}\`` | `(t: string) => \`Updated \${t}\`` |
| `invColName` | `'Instrumento'` | `'Instrument'` |
| `invColISIN` | `'ISIN'` | `'ISIN'` |
| `invColClass` | `'Clase'` | `'Class'` |
| `invColValue` | `'Valor'` | `'Value'` |
| `invColWeight` | `'Peso'` | `'Weight'` |
| `invColCost` | `'Coste'` | `'Cost'` |
| `invColPnL` | `'G/P'` | `'P&L'` |
| `invColPnLPct` | `'G/P %'` | `'P&L %'` |
| `invAssetEquity` | `'Renta variable'` | `'Equity'` |
| `invAssetFixed_income` | `'Renta fija'` | `'Fixed income'` |
| `invAssetCash` | `'Efectivo'` | `'Cash'` |
| `invAssetOther` | `'Otros'` | `'Other'` |
| `invErrorLoading` | `'Error al cargar la cartera'` | `'Error loading portfolio'` |

> **Asset class key note:** The `capitalize()` helper converts `"fixed_income"` → `"Fixed_income"`, so the key is `invAssetFixed_income`. Alternatively, use a direct lookup map instead of string interpolation — Vision's choice.

### Connectors page keys

| Key | ES | EN |
|---|---|---|
| `connectorConnected` | `'Conectado'` | `'Connected'` |
| `connectorError` | `'Error de conexión'` | `'Connection error'` |
| `connectorDisconnect` | `'Desconectar'` | `'Disconnect'` |
| `connectorErrorRetry` | `'Reconectar'` | `'Reconnect'` |

---

## CSS class name index

| Class | Purpose | File section |
|---|---|---|
| `.modal.inv-wizard` | Narrow wizard modal (480px) | Wizard |
| `.inv-wizard__progress` | Step dots container | Wizard |
| `.inv-wizard__step-dot` | Inactive step dot | Wizard |
| `.inv-wizard__step-dot--active` | Current step dot (scale 1.4×, primary) | Wizard |
| `.inv-wizard__step-dot--done` | Completed step dot (income green) | Wizard |
| `.inv-wizard__step-sep` | Connector line between dots | Wizard |
| `.inv-wizard__step-sep--done` | Completed connector line (income green) | Wizard |
| `.inv-wizard__body` | Step content container (flex-col, centered) | Wizard |
| `.inv-wizard__logo` | Large emoji/icon (56px) | Wizard step 1 |
| `.inv-wizard__title` | Step title (18px/700) | Wizard |
| `.inv-wizard__desc` | Step description (14px, muted) | Wizard |
| `.inv-wizard__link` | Styled external link | Wizard step 1 |
| `.inv-wizard__security-note` | Encrypted-storage note block | Wizard steps 1+2 |
| `.inv-wizard__security-note-icon` | Lock icon inside note | Wizard |
| `.inv-wizard__token-field` | Token input group (flex-col) | Wizard step 2 |
| `.inv-wizard__token-label` | Token input label | Wizard step 2 |
| `.inv-wizard__token-input` | Monospace password input (44px) | Wizard step 2 |
| `.inv-wizard__account-list` | Discovered accounts list | Wizard step 3 |
| `.inv-wizard__account-item` | Single account row (checkbox + info) | Wizard step 3 |
| `.inv-wizard__account-item--checked` | Selected account (primary border tint) | Wizard step 3 |
| `.inv-wizard__account-checkbox` | Native checkbox (accent-color primary) | Wizard step 3 |
| `.inv-wizard__account-info` | Text block inside account item | Wizard step 3 |
| `.inv-wizard__account-label` | Masked account label (monospace, 14px/600) | Wizard step 3 |
| `.inv-wizard__account-type` | Account type (11px, muted, capitalize) | Wizard step 3 |
| `.inv-wizard__success` | Success state container | Wizard step 4 |
| `.inv-wizard__success-icon` | Large success emoji (52px) | Wizard step 4 |
| `.inv-wizard__success-title` | Success heading | Wizard step 4 |
| `.inv-wizard__success-desc` | Success description | Wizard step 4 |
| `.inv-wizard__success-accounts` | Connected accounts summary list | Wizard step 4 |
| `.inv-wizard__success-account` | Single connected account row | Wizard step 4 |
| `.inv-wizard__success-account-check` | Green checkmark | Wizard step 4 |
| `.inv-wizard__error-banner` | Error alert (red bg, expense color) | Wizard error state |
| `.inv-wizard__error-banner-icon` | Warning icon inside banner | Wizard error state |
| `.inv-account-header` | Connected account strip (surface card) | Investments populated |
| `.inv-account-header__left` | Flex group: icon + label | Investments |
| `.inv-account-header__icon` | Connector icon (18px) | Investments |
| `.inv-account-header__label` | Masked account (monospace, 14px/600) | Investments |
| `.inv-account-header__updated` | "Actualizado …" timestamp (12px, muted) | Investments |
| `.inv-charts-row` | 2-col grid (3fr / 2fr, stacks ≤900px) | Investments |
| `.inv-chart-card` | Chart card (flex-col) | Investments |
| `.inv-chart-card--value` | Value-over-time modifier | Investments |
| `.inv-chart-card--allocation` | Allocation donut modifier | Investments |
| `.inv-value-chart-wrap` | 260px wrapper for Recharts AreaChart | Investments |
| `.inv-holdings-card` | Holdings card (min-height 200px) | Investments |
| `.inv-holdings-table-wrap` | Scrollable table wrapper | Investments |
| `.inv-holdings-table` | Holdings data table (min-width 720px) | Investments |
| `.inv-th-num` | Right-aligned header | Holdings table |
| `.inv-th-sortable` | Sortable header (cursor, hover) | Holdings table |
| `.inv-th-sort-active` | Active sort column (text color) | Holdings table |
| `.inv-td-name` | Instrument name (500, ellipsis) | Holdings table |
| `.inv-td-isin` | ISIN (monospace, 12px, muted) | Holdings table |
| `.inv-td-num` | Numeric cell (right, tabular-nums) | Holdings table |
| `.inv-td-weight` | Weight % (12px, muted, right) | Holdings table |
| `.inv-pnl--pos` | Positive P&L (income green, 600) | Holdings table |
| `.inv-pnl--neg` | Negative P&L (expense red, 600) | Holdings table |
| `.inv-asset-class-badge` | Asset class pill (base) | Holdings table |
| `.inv-asset-class-badge--equity` | Blue equity tint | Holdings table |
| `.inv-asset-class-badge--fixed-income` | Green fixed-income tint | Holdings table |
| `.inv-asset-class-badge--cash` | Muted cash tint | Holdings table |
| `.inv-asset-class-badge--other` | Purple other tint | Holdings table |
| `.connector-card--connected` | Green border modifier on `.plugin-card` | ConnectorsPage |
| `.connected-badge` | Green "Conectado" pill | ConnectorsPage |
| `.connector-card--error` | Red border modifier on `.plugin-card` | ConnectorsPage |
| `.error-badge` | Red "Error" pill | ConnectorsPage |
| `.btn-disconnect` | Small muted disconnect button (red hover) | ConnectorsPage |

---

## Responsive behaviour summary

| Breakpoint | Change |
|---|---|
| `≤900px` | `.inv-charts-row` stacks to 1 column |
| `≤600px` | `.modal.inv-wizard` → full-width bottom-sheet; `.btn-disconnect` → 36px touch target |

---

## Dark mode

All new classes use only CSS token variables or dual-pattern raw rgba overrides (`[data-theme="dark"]` + `@media (prefers-color-scheme: dark)` with `:root:not([data-theme="light"])`). No class-based theme switching needed.


---

### Frontend Implementation (Vision) — Wizard + Real Data Viz Shipped

# Vision → Indexa Phase 2 Frontend

**Author:** Vision (Frontend Engineer)  
**Date:** 2026-07-14  
**Status:** SHIPPED — `npm run build` 0 TS errors  
**Depends on:** Shuri's backend (858 tests green), Wanda's design spec

---

## Summary

Full Phase 2 frontend: Indexa Capital wizard, connection management on ConnectorsPage, and the fully-populated InvestmentsPage (KPIs + area chart + allocation donut + holdings table).

---

## Files Changed

| File | Change |
|---|---|
| `frontend/src/api/types.ts` | Added `InvestmentReturns`, `ValuePoint`, `CashInvestedSplit`, `InvestmentHolding`, `InvestmentPortfolio`, `InvestmentConnection`, `ValidatedAccount`, `ValidateAccountsResponse` |
| `frontend/src/api/client.ts` | Added `validateIndexaToken`, `connectPlugin`, `getConnections`, `disconnectConnection`, `getInvestmentPortfolio` |
| `frontend/src/api/mock.ts` | Added mocks for all 5 new calls; `_mockConnected` flag drives demo-mode state; `mockGetInvestmentPlugins` now reflects dynamic connected status |
| `frontend/src/i18n/index.ts` | Added 44 keys to `Dict` interface (24 wizard, 15 investments-populated, 4 connector-card-state, 1 `invAccountUpdated` fn) |
| `frontend/src/i18n/es.ts` | 44 ES translations |
| `frontend/src/i18n/en.ts` | 44 EN translations |
| `frontend/src/components/IndexaWizard.tsx` | **NEW** — 4-step modal wizard per Wanda's `.modal.inv-wizard` spec |
| `frontend/src/pages/ConnectorsPage.tsx` | Rewritten — fetches plugins + connections, renders Indexa card in 3 states (available/connected/error), launches wizard, handles disconnect |
| `frontend/src/pages/InvestmentsPage.tsx` | Rewritten — full populated viz (KPIs, charts, table) or empty state based on `plugins_connected` |

---

## Contract Implemented

### Wizard (two-step — override of Shuri's original single-POST)

1. **Validate:** `POST /api/investments/connections/validate` `{ token }` → `{ accounts: [{ account_number, account_number_masked, type, status }] }`  
   - 400 → invalid token banner, back to step 2  
   - 503 → network error banner, back to step 2  

2. **Connect:** `POST /api/investments/connections` `{ token, account_numbers: string[] }` → `ConnectionOut[]`  
   - Sends raw `account_number`s (not masked); displays `account_number_masked` in checkboxes  
   - All accounts pre-selected  

### Other endpoints

- `GET /api/investments/connections` — lists active connections for ConnectorsPage + InvestmentsPage header strip  
- `DELETE /api/investments/connections/{id}` — hard-delete; triggered after `window.confirm`  
- `GET /api/investments/portfolio` — aggregated portfolio with holdings, value_series, returns  

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| `WizardStep` union type with string literals (`'3-loading' \| '3-error' \| '3-accounts'`) | Avoids extra boolean flags; step + substep in one state atom |
| `assetLabel()` lookup map (not template-literal key access) | Type-safe; `invAssetFixed_income` underscore key works without `as any` |
| `asset_class.replace(/_/g, '-')` for CSS badge class | CSS uses `inv-asset-class-badge--fixed-income` (hyphen), backend sends `fixed_income` (underscore) |
| Parallel `Promise.all([getInvestmentPortfolio(), getConnections()])` on InvestmentsPage | Single loading state; connection header strip needs separate connection data |
| `_mockConnected` flag in mock.ts | Allows full connect→view flow in demo mode (VITE_USE_MOCK=1) |
| `formatRelativeTime()` inline helper | App had no relative-time utility; simple implementation avoids a new dep |
| `gain_loss_pct × 100` for display | Shuri's spec: decimal format (0.1093 = 10.93%) |
| `total_gain_loss_pct × 100` same | Same decimal convention; applied in KPI sub-label |

---

## i18n Keys Added (44 total)

### Wizard (24 keys)
`wizardTitle`, `wizardProgressLabel`, `wizardStep1Title`, `wizardStep1Desc`, `wizardStep1Link`, `wizardSecurityNote`, `wizardNext`, `wizardStep2Title`, `wizardTokenLabel`, `wizardTokenPlaceholder`, `wizardValidate`, `wizardStep3Validating`, `wizardStep3Title`, `wizardStep3Desc`, `wizardConnect`, `wizardStep4Title`, `wizardStep4Desc`, `wizardViewInvestments`, `wizardErrorInvalidToken`, `wizardErrorNetwork`, `wizardBack`, `wizardRetry`, `wizardClose`, `wizardOpen`

### Investments populated (15 keys + 1 fn)
`invKpiTwr`, `invKpiXirr`, `invChartValueTitle`, `invChartAllocationTitle`, `invHoldingsEmpty`, `invHoldingsCount`, `invAccountUpdated` (fn), `invColName`, `invColISIN`, `invColClass`, `invColValue`, `invColWeight`, `invColCost`, `invColPnL`, `invColPnLPct`, `invAssetEquity`, `invAssetFixed_income`, `invAssetCash`, `invAssetOther`, `invErrorLoading`

### Connector card states (4 keys)
`connectorConnected`, `connectorError`, `connectorDisconnect`, `connectorErrorRetry`

---

## Mock Data (demo mode)

- `validateIndexaToken`: accepts any token ≥8 chars; returns one account `PBK•••Z5`
- `mockGetInvestmentPortfolio` when connected: `total_value=12345.67`, 3 holdings (equity/fixed_income/cash), 15-point `value_series` from Jan 2023 → Mar 2024
- `mockGetConnections` when connected: single active connection `id=1, plugin_id=indexa-capital`


---

### QA Findings (Barton) — 28 Tests, 2 Owner Decisions on Config/Startup

# Barton → QA Findings: Indexa Phase 2 Backend

**Author:** Barton (Tester/QA)  
**Date:** 2026-07-14  
**For:** Coordinator (Fury), Shuri (fix owner), Romanoff (spec owner)  
**Status:** OPEN — 2 bugs, both require a fix before Phase 2 ships to production

---

## Context

Ran full security + functional test pass on `src/finlytics/investments/` and `src/finlytics/api/investments.py`. All 44 investment tests pass (896 suite-wide). Two discrepancies found between Romanoff's security spec and Shuri's implementation.

---

## BUG-1: Env var name mismatch — `INDEXA_ENCRYPTION_KEY` vs `FINLYTICS_ENCRYPTION_KEY`

**Severity:** HIGH (operational failure; security mis-configuration possible)  
**Files:** `src/finlytics/config.py:82`, `.env.example`, `romanoff-indexa-token-security.md §1`

### What the spec says (Romanoff §1)

```
INDEXA_ENCRYPTION_KEY=
```

### What is implemented (Shuri)

```python
# config.py
finlytics_encryption_key: str | None = None
```

```
# .env.example
# FINLYTICS_ENCRYPTION_KEY=
```

### Impact

Anyone following Romanoff's spec to configure the production environment will set `INDEXA_ENCRYPTION_KEY=<key>`. The application reads `FINLYTICS_ENCRYPTION_KEY`. The key is **silently ignored**: `settings.finlytics_encryption_key` stays `None`, every connect/portfolio call returns HTTP 503, and the wizard is permanently broken.

No plaintext storage occurs (fail-closed is preserved), but the connector is **inoperable until the operator learns the correct variable name**. This is an ops footgun.

### Recommended fix

Either:
- **Option A (preferred):** Update Romanoff's spec to document `FINLYTICS_ENCRYPTION_KEY` (the broader name makes sense as it covers future connectors).
- **Option B:** Shuri renames the field to `indexa_encryption_key` and updates `config.py` + `.env.example` to match Romanoff's spec.

If Option A, Romanoff must re-publish the updated `.env.example` entry and threat model section.

---

## BUG-2: Startup behavior mismatch — "refuse to start" vs "503 on use"

**Severity:** MEDIUM (security policy violation; not a data-exposure risk)  
**Files:** `src/finlytics/config.py:77–82`, `romanoff-indexa-token-security.md §1`

### What the spec says (Romanoff §1)

> If `INDEXA_ENCRYPTION_KEY` is **absent** or **invalid** at startup: **refuse to start** (raise a configuration error). Do NOT fall back to plaintext storage under any circumstances.

### What is implemented (Shuri)

```python
# config.py comment (line 79–80):
# Scoped fail: app starts normally when absent; only encrypt/decrypt
# operations fail (HTTP 503) if the key is missing or invalid.
```

The application boots without error when `FINLYTICS_ENCRYPTION_KEY` is absent. The first encrypt or decrypt call raises `EncryptionNotConfiguredError` → surfaced as HTTP 503. Plaintext storage never occurs.

### Impact

The **data-safety property is preserved** (no plaintext tokens are ever stored or returned). However, the spec demands a startup-time hard failure, which:

1. Surfaces mis-configuration immediately (fail-fast principle) rather than at first user action.
2. Prevents the app from starting in an environment where the connector is expected to work, which could confuse operators into thinking the wizard is broken for other reasons.

In practice: the current behavior is _operationally safer_ than a silent start in some deployment models (e.g., a rolling update where the key was accidentally dropped from the env). But it violates Romanoff's documented policy.

### Recommended fix

**Shuri:** Add a `model_validator` (or startup event) that raises at application startup if `finlytics_encryption_key` is absent and a connection row exists in the DB — or, simpler, raise unconditionally at startup (matching the spec). Coordinate with Romanoff on whether the "scoped fail" model is acceptable.

**Romanoff:** If the "503 on use" design is intentional and accepted, update §1 to document the approved behavior so the spec and code match.

---

## Tests that assert the fail-closed property (passing)

The following tests confirm the fail-closed behavior **as implemented** (503 responses):

- `test_connect_missing_encryption_key_returns_503`
- `test_portfolio_missing_encryption_key_returns_503`
- `test_crypto_missing_key_encrypt_raises`
- `test_crypto_missing_key_decrypt_raises`

If BUG-2 is fixed to add startup-time refusal, additional startup tests should be added in `tests/test_startup.py` (deferred to coordinator decision).

---

## No other security issues found

The following Romanoff build-blockers were explicitly verified and pass:

| Build-blocker | Test | Status |
|---|---|---|
| Token never in API response | `test_connect_response_never_contains_raw_token`, `test_validate_happy_path_returns_accounts`, `test_get_connections_no_token_enc_in_response` | ✅ PASS |
| `account_label_masked` always masked | `test_get_connections_no_token_enc_in_response`, `test_mask_account_standard`, `test_mask_account_short_gets_bullet_prefix` | ✅ PASS |
| `TLS verify=True` always | `test_indexa_client_tls_verify_and_no_redirects` | ✅ PASS |
| `follow_redirects=False` | `test_indexa_client_tls_verify_and_no_redirects` | ✅ PASS |
| Encrypt→decrypt round-trip correct | `test_crypto_encrypt_decrypt_roundtrip` | ✅ PASS |
| Tampered ciphertext raises | `test_crypto_tampered_ciphertext_raises` | ✅ PASS |
| Missing key → fail-closed | `test_crypto_missing_key_encrypt_raises`, `test_crypto_missing_key_decrypt_raises` | ✅ PASS |
| `POST /auth/authenticate` absent | Not present in codebase (grep confirms) | ✅ PASS |
| Hard-delete removes ciphertext | `test_delete_connection_returns_204` + service logic review | ✅ PASS |


---

## 2026-07-14 — Recommendations: Connectors → Settings, Cartera Phase 2 Plan

# Decisions Log

---

## 2026-07-14 — Recommendations: Connectors → Settings, Cartera Phase 2 Plan

**Authors:** Wanda (UX/UI), Vision (Frontend)  
**Status:** Approved / Planned

### Wanda: Connector Catalog Placement (IA Recommendation)

**Decision:** Move the full connector catalog from `InvestmentsPage` to a new Settings sub-page (`/settings/connectors`). Replace the catalog on Investments with a single "Gestionar conectores →" CTA.

**Rationale:**
- Connecting a plugin = config (credentials, tokens) → belongs in Settings, not portfolio view
- Even Phase 1 benefits: eliminates visual weight of disabled "coming soon" cards
- Mobile-first: clean Investments page + one tap to Settings
- Phase 2 readiness: connect flows built in Settings from the start (no migration needed)

**Result:** Wanda's recommendation was approved by DrDonoso and implemented by Vision (see "Connectors Moved to Settings" section below).

### Vision: Cartera / Holdings Visualization Plan (Phase 2)

**Current state (Phase 1):** Holdings area shows empty-state placeholder.  
**Phase 2 plan:**

| Feature | Details |
|---------|---------|
| KPI row | 4 cards: Total value, Total invested, Gain/Loss, Plugins connected |
| Asset allocation | Donut chart grouped by asset class (equity, fixed_income, crypto, cash, mixed, other) — reuse SpendingByCategory pattern |
| Holdings table | Name, ticker, asset class, current value, cost basis, P&L (€ + %), currency — sortable by name/value/P&L% |
| Multi-currency | Holdings display native currency; KPI totals in portfolio currency (EUR assumed) |
| All states | No plugins (current), loading, data available, error, empty holdings |

This page layout and component structure are pre-planned so real data in Phase 2 slots in cleanly without rework.

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

## 2026-07-14 — Frontend Implementation: Connectors Moved to Settings

**Author:** Vision (Frontend Engineer)  
**Status:** Shipped

### Placement

- **InvestmentsPage (`/investments`):** KPI row + holdings empty state + "Gestionar conectores →" NavLink to `/settings/connectors`
- **ConnectorsPage (`/settings/connectors`):** Full plugin catalog grid (3 cards: Indexa Capital, Broker, Crypto Exchange — all "Coming soon", all disabled)

### Implementation

| File | Change |
|------|--------|
| `frontend/src/pages/ConnectorsPage.tsx` | **Created** — plugin catalog under settings layout |
| `frontend/src/pages/InvestmentsPage.tsx` | Removed catalog; added NavLink CTA |
| `frontend/src/App.tsx` | Added `settings/connectors` route |
| `frontend/src/components/Layout.tsx` | Added "Conectores" sub-link in Ajustes accordion |
| `frontend/src/i18n/index.ts`, `es.ts`, `en.ts` | Added `settingsSubConnectors`, `investmentsManageConnectors` keys |

**Result:** 0 TypeScript errors. Build succeeded. Connector catalog cleanly moved; Investments page refocused as pure view + CTA. In Phase 2, disabled Connect buttons become real auth flows — page already the right home.

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

## 2026-07-14 — DevOps: Local Commit & Rebuild

**Author:** Rocket (DevOps/Platform)  
**Status:** Done — local only, not pushed

### Commit

Committed complete Investments Phase 1 skeleton locally:

```
afbcd89  feat(investments): add plugin-based investments section skeleton
```

15 files changed (11 modified, 4 new): all under `frontend/`, `src/`, and `tests/`. `.squad/` files deliberately excluded.

### Rebuild

```powershell
docker compose -f docker-compose.local.yml up -d --build
```

**Result:** ✅  
- `finlytics-db-1` healthy (postgres:16-alpine)  
- `finlytics-api-1` up, port 7777  
- `GET http://localhost:7777/` → **200**  
- `GET http://localhost:7777/api/investments/plugins` → **401** (auth guard active = new route live)

### What Owner Sees

- 💰 **Inversiones** sidebar → `/investments` with 3 KPI (—) + holdings empty state + "Gestionar conectores →" CTA
- **Ajustes → Conectores** → plugin catalog (Indexa, Broker, Crypto — all "Próximamente")

### Local Run Pattern (Established)

For uncommitted feature code: **Always use `docker-compose.local.yml` with `--build`** (includes `build: .` from current working tree). Default `docker-compose.yml` pulls published Hub image (stale). 401 smoke check confirms new route is live.

---



---

# Shuri — Evolución de la Cuenta: Live Probe Findings
**Date:** 2026-07-14  
**Requested by:** DrDonoso (owner)  
**Status:** FRONTEND BUG — backend returns full data  
**Account probed:** mask `96E•••BH` (read-only, owner's real account)

---

## Verdict

**The backend is NOT the culprit.** `value_series` is populated with 709 data points covering 2024-08-04 → 2026-07-13. The "Evolución de la cuenta" chart loading issue is a **frontend bug**.

---

## Probe Results (Live, Real Account)

### `value_series` — 709 points ✅

| Position | Date | Value (EUR) |
|---|---|---|
| first | 2024-08-04 | 0.00 |
| 2nd | 2024-08-05 | 2,600.00 |
| 2nd-to-last | 2026-07-12 | 20,528.36 |
| last | 2026-07-13 | 20,559.52 |

Source in code: `data["return"]["total_amounts"]` (YYYYMMDD keys → reformatted to YYYY-MM-DD).  
**Top-level `data["total_amounts"]` = `None`** — correct, the fix is working.

### `contributions_series` — 716 points ✅

| Position | Date | Value (EUR) |
|---|---|---|
| first | 2024-07-28 | 0.00 |
| 2nd | 2024-07-29 | 0.00 |
| 2nd-to-last | 2026-07-12 | 17,999.99 |
| last | 2026-07-13 | 17,999.99 |

Source: `data["net_amounts"]` (YYYYMMDD keys → YYYY-MM-DD). Step-function shape — values stay flat between deposits.

### `data["return"]["total_amounts"]` ✅

- Present at correct nested path: **709 keys**
- Key format: `YYYYMMDD` (e.g. `"20240804"` → `"20260713"`)
- Correctly reformatted to `YYYY-MM-DD` by `_fmt_date()`
- Top-level `total_amounts` field: **absent** (`None`) — confirms the path fix is correct

### `monthly_returns` — 3 rows ✅

3 annual rows (2024, 2025, 2026), each with monthly sub-entries. Populated correctly.

### `drawdown` — populated ✅

- `max_drawdown` = -10.05%  
- `max_drawdown_eur` = -€1,356.93  
- Period: 2025-02-20 → 2025-04-08

### Box Numbers — all non-null ✅

| Field | Value |
|---|---|
| `total_value` | €20,559.52 |
| `aportaciones` | €18,000.00 |
| `retenciones` | €0.01 *(positive — UI should negate for display)* |
| `rentabilidad_eur` | €2,559.53 |
| `rentabilidad_pct` | 0.2133 (21.33%) |
| `sharpe_ratio` | 1.325 |

Reconciliation: 18,000.00 − 0.01 + 2,559.53 = **20,559.52** ✓

---

## API Response Shape Confirmed

```
data = {
  "return": {
    "total_amounts": { "20240804": 0.0, "20240805": 2600.0, ..., "20260713": 20559.52 }
    # 709 YYYYMMDD keys
  },
  "net_amounts": { "20240728": 0.0, ..., "20260713": 17999.99 }
  # 716 YYYYMMDD keys — top-level (NOT under return)
  # ...
}
```

---

## For Vision: Reproducing the Chart

The `/api/investments/portfolio` response (field `value_series`) looks like:

```json
[
  { "date": "2024-08-04", "value": 0.00 },
  { "date": "2024-08-05", "value": 2600.00 },
  ...
  { "date": "2026-07-12", "value": 20528.36 },
  { "date": "2026-07-13", "value": 20559.52 }
]
```

`contributions_series`:

```json
[
  { "date": "2024-07-28", "value": 0.00 },
  { "date": "2024-07-29", "value": 0.00 },
  ...
  { "date": "2026-07-12", "value": 17999.99 },
  { "date": "2026-07-13", "value": 17999.99 }
]
```

Both arrays are sorted ascending by date. The chart should receive these from the API and render them. If the chart shows no data, check:

1. Whether the frontend is correctly reading `portfolio.value_series` (not `portfolio.performance.value_series` or a different nesting)
2. Whether the chart library is parsing `"2024-08-04"` date strings vs expecting numeric timestamps
3. Whether an empty-array guard (`if (!valueSeries.length) return`) fires incorrectly
4. Whether the first point `value=0.00` on `2024-08-04` confuses the chart's zero-filtering logic
5. Network: confirm the API response actually includes `value_series` (not stripped by a serialiser)

---

## No Backend Changes Made

All backend paths confirmed correct. Tests remain at **921 passed, 2 skipped** (unchanged).


---

# Shuri — Indexa API Data Probe Findings
**Date:** 2026-07-14  
**Status:** Findings only — no production code changed  
**Source:** Live READ-ONLY probe of owner's real Indexa account (1 account, type=mutual, status=active)

---

## Root-Cause: `value_series` Always Empty

**Bug:** `indexa.py` line `total_amounts: dict = data.get("total_amounts", {})` looks at the **top level** of the performance response. The field does not exist there.

**Reality:** `total_amounts` is nested inside `data["return"]["total_amounts"]`.

```python
# BROKEN (current code)
total_amounts = data.get("total_amounts", {})          # → always {}

# FIX — correct path
total_amounts = data.get("return", {}).get("total_amounts", {})
```

**Additional gotcha — wrong date format:** `return.total_amounts` keys are **YYYYMMDD** (8 chars, no dashes), e.g. `"20240804"`. `NormalizedValuePoint.date` is YYYY-MM-DD. Keys must be reformatted:
```python
from datetime import datetime
date_str = datetime.strptime(k, "%Y%m%d").strftime("%Y-%m-%d")
```

**Secondary bug (same function):** `portfolios` are sorted **newest-first** (index 0 = today, index -1 = account open date with `total_amount=0.0`). Current code does `latest = portfolios[-1]` → oldest entry → all zeros → `total_value=0.0` for `cash_invested` and value fallback.  
Fix: `latest = portfolios[0]`.

---

## Feature Availability Matrix

### 1 — Portfolio Value Daily Series

| Item | Status |
|---|---|
| Available? | ✅ YES — two sources |
| **Preferred source** | `portfolios[]` — 716 daily entries, keys at `date` (YYYY-MM-DD), value at `total_amount` (float). Sorted **newest-first**; reverse before building series. |
| **Alternative source** | `data["return"]["total_amounts"]` — 709 entries, YYYYMMDD keys (reformat needed), same values. |
| Date range | 2024-08-04 → 2026-07-13 (approx 23.5 months) |
| Sample | `2026-07-13 = 20559.52`, `2025-07-20 = 13382.93`, `2024-08-04 = 0.00` |
| Gotchas | YYYYMMDD vs YYYY-MM-DD; `portfolios[-1]` = oldest (all zeros), NOT latest |

Also available: `data["return"]["index"]` — 709 entries, YYYYMMDD keys, daily TWR index normalized to 1.0 at account open (last = 1.2373). Useful for computing per-day returns and max drawdown from scratch.

---

### 2 — Aportaciones (Cumulative Contributions) Daily/Stepwise Series

| Item | Status |
|---|---|
| Available? | ✅ YES — multiple sources |
| **Preferred: `net_amounts` (top-level)** | Dict, **716 daily entries**, YYYYMMDD keys, latest = `17999.99`. Cumulative net invested (inflows − taxes), already a step-series ready for the chart. Reformat keys YYYYMMDD → YYYY-MM-DD. |
| **Alternative: `portfolios[].inflows`** | Each portfolio entry has a daily `inflows` float (0.0 on non-deposit days). Cumulatively sum over sorted entries. |
| **Alternative: cash-transactions** | Filter `operation_type = "TRANSFERENCIA SEPA"` (9 entries) for actual user wire transfers. Fields: `date` (YYYY-MM-DD), `amount` (float, positive for deposits). Cumsum gives deposit step-line. |
| Gotchas | `net_amounts` values = `inflows - tax_outflows` (not raw inflows). Use `return.inflows` for gross; use `net_amounts` for net-of-retenciones. TRANSFERENCIA SEPA are user deposits; the 38 SUSCRIPCIÓN entries are fund purchases (not user cash). |

---

### 3 — Monthly Returns Matrix (month × year)

| Item | Status |
|---|---|
| Available? | ✅ YES |
| Source | `data["history"]` — dict, **23 end-of-month entries** (2024-08-31 → 2026-06-30), keys are **YYYY-MM-DD**, values are **cumulative TWR multipliers** from inception (1.0 = start). |
| Derive monthly return | `history[month] / history[prev_month] − 1.0`. For the first month: `history[first] − 1.0`. |
| Sample | `2024-08-31 = 1.034754` (+3.47%), `2024-09-30 = 1.049695`, `2024-12-31 = 1.072171`, `2026-06-30 = 1.236281` |
| Gotchas | Values are NOT monthly returns directly — they're cumulative multipliers. Division between consecutive months is required. Current month (July 2026) not present in `history` yet (incomplete month). |

---

### 4 — Benchmark Comparison

| Item | Status |
|---|---|
| Available? | ✅ YES |
| Source | `data["benchmark"]` — dict, **23 entries** (2024-08-31 → 2026-06-30), same date keys as `history` |
| Per-entry shape | `{"date": "YYYY-MM-DD", "benchmark_id": "2", "benchmark": <float>, "benchmark_percentage_return": <string or 0 int>}` |
| Cumulative value | `benchmark` field — starts at 100.0 (not 1.0 like `history`). E.g. `2024-08-31 = 100.0`, `2024-09-30 = 100.9512`. |
| Monthly return | `benchmark_percentage_return` — **string** (except first month = integer `0`). Must `float(v.get("benchmark_percentage_return", 0))` to parse. |
| Samples | `2024-08-31: 0.0`, `2024-09-30: "0.009511..."`, `2024-10-31: "-0.007513..."` |
| Gotchas | First-month value is integer `0`, not string. Parse defensively: `float(val)` handles both. Align on same month keys as `history`; both have identical date ranges. |

---

### 5 — Max Drawdown

| Item | Status |
|---|---|
| Available? | ✅ YES — directly provided |
| Source | `data["drawdowns"]` — top-level object |
| Fields | `max_drawdown` (float, e.g. `-0.10050`), `max_drawdown_EUR` (float, e.g. `-1356.93`), `start_date_max_drawdown` (YYYYMMDD int, `20250220`), `end_date_max_drawdown` (YYYYMMDD int, `20250408`) |
| Real values | −10.05%, −€1,356.93, from 2025-02-20 to 2025-04-08 |
| Gotchas | Dates are **integers** in YYYYMMDD format. Parse with `str(int)` → `datetime.strptime(str(v), "%Y%m%d")`. No computation needed — use directly. |

Also available: `data["sharpe_ratio"]` = 1.325 (float, top-level).

---

### 6 — The Four "Valor Total" Box Numbers

| UI Label | Value | API Field | Notes |
|---|---|---|---|
| **Valor total** | €20,559.52 | `portfolios[0].total_amount` | `portfolios[0]` = most recent day (newest-first!). Current code uses `[-1]` which is oldest (=0). |
| **Aportaciones** | €18,000.00 | `data["return"]["inflows"]` | Gross cash transferred in by user |
| **Retenciones** | −€0.01 | `data["return"]["tax_outflows"]` | Store/display as negative. `return.pl_net_tax` = pl after tax. |
| **Rentabilidad €** | +€2,559.53 | `data["return"]["pl"]` | Profit/loss in EUR |
| **Rentabilidad %** | +14.2% | `data["return"]["money_return"]` = 0.2133 | Money-weighted return (not TWR). TWR = `time_return` = 0.2373. |

Reconciliation: `18000.00 − 0.01 + 2559.53 = 20,559.52` ✓

Additional return fields confirmed present:
- `return.time_return` = 0.2373 (TWR total)
- `return.time_return_annual` = 0.1162 (annualised TWR)  
- `return.XIRR` = 0.1050 (money-weighted annualised, IRR)
- `return.time_return_last_week/month/year` present ✓
- `return.volatility` = 0.0707  
- `return.money_return_annual` — present (not yet surfaced in our schema)

---

## Cash-Transactions Structure

- **Response:** JSON array, 69 entries
- **Keys:** `account_number`, `amount`, `comments`, `currency`, `date` (YYYY-MM-DD), `fees`, `instrument_transaction`, `operation_code`, `operation_type`, `reference`, `status`
- **No `type` field** — our probe was checking wrong key; use `operation_type`

| `operation_type` | Count | Meaning |
|---|---|---|
| `SUSCRIPCIÓN FONDOS INVERSIÓN SF` | 38 | Fund purchases |
| `CARGO COMISION GESTION` | 8 | Management fees |
| `CUSTODIA INVERSIS` | 8 | Custody fees |
| `TRANSFERENCIA SEPA` | 9 | **User cash deposits** ← aportaciones |
| `DIF.REDONDEO FONDOS` | 3 | Rounding diffs |
| `REEMBOLSO FONDO INVERSIÓN SF` | 1 | Fund redemption |
| `ABONO INCENTIVO IICS SF` | 1 | Incentive/bonus |
| `RETENCION DE IMPUESTOS` | 1 | Tax withholding |

For the aportaciones step-line from cash-transactions: filter `TRANSFERENCIA SEPA` with `status="closed"`, sort by `date` ASC, cumsum `amount`.

---

## Summary for Implementation (Next Steps)

1. **Fix `value_series`**: change `data.get("total_amounts", {})` → `data.get("return", {}).get("total_amounts", {})` in `_fetch_performance`. Convert YYYYMMDD keys to YYYY-MM-DD.
2. **Fix `portfolios[-1]` → `portfolios[0]`**: portfolios are newest-first; fix all three uses (cash_invested, total_value fallback, cash_invested merge).
3. **Add `history` + `benchmark` to `NormalizedPerformance`**: for the monthly returns matrix.
4. **Add `drawdowns` to `NormalizedPerformance`**: `max_drawdown`, `max_drawdown_EUR`, dates.
5. **Add `net_amounts` series**: for the contributions step-line (or derive from TRANSFERENCIA SEPA cash-transactions).
6. **Add `sharpe_ratio`** and `money_return_annual` to `NormalizedReturns`.


---

# Shuri — Indexa Connector Bug Fixes & Enhancement

**Date:** 2026-07-14  
**Author:** Shuri (Backend)  
**Status:** SHIPPED  
**Audience:** Vision (Frontend), Barton (QA)

---

## 1. BUG A — `total_value` now uses a reliable fallback chain

**Problem:** `_fetch_performance` was reading `total_value` from the top-level `data["total_amount"]`. For some real accounts this field is 0 or absent, causing the KPI to show €0.

**Fix — fallback chain (in order):**
1. `portfolios[-1].total_amount` — the most-recent daily snapshot (= `cash_amount + instruments_amount`). This is authoritative.
2. Last entry in the `total_amounts` daily series (`max(total_amounts.keys())`).
3. Top-level `data["total_amount"]`.
4. Sum of holdings `current_value` — applied in `get_portfolio` if `_fetch_performance` still returns 0.

A `DEBUG`-level log fires when the top-level field is absent (never logs the token).

**Real-account example:** cash (67.16 €) + funds (20,492.36 €) = **20,559.52 €** — now correctly derived from `portfolios[-1].total_amount`.

---

## 2. BUG B — Holdings now deduplicated by ISIN

**Problem:** Indexa's `/fiscal-results` returns one entry per subscription lot, so a fund bought at different times appeared multiple rows in the holdings list.

**Fix:** `get_portfolio` now groups `fiscal_results` by `instrument.identifier` (ISIN), falling back to `instrument.name`. Per group:

| Field | Aggregation |
|---|---|
| `amount` → `current_value` | SUM |
| `cost_amount` → `cost_basis` | SUM |
| `titles` → `units` | SUM |
| `profit_loss` → `gain_loss` | SUM |
| `gain_loss_pct` | Recomputed: `sum(profit_loss) / sum(cost_amount)` |

Holdings are sorted by `current_value` descending. Result: **one holding per fund**, matching Indexa's own fiscal view.

---

## 3. Enhancement — Extended return fields in `InvestmentReturns`

Both `NormalizedReturns` (internal) and `InvestmentReturns` (API schema `schemas.py`) now expose:

| API field | Indexa source | Aggregatable (multi-account)? |
|---|---|---|
| `twr_annual` | `return.time_return_annual` | ❌ None for multi-account |
| `twr_total` | `return.time_return` | ❌ None for multi-account |
| `twr_last_week` | `return.time_return_last_week` | ❌ None for multi-account |
| `twr_last_month` | `return.time_return_last_month` | ❌ None for multi-account |
| `twr_last_year` | `return.time_return_last_year` | ❌ None for multi-account |
| `money_return` | `return.money_return` | ✅ SUM across accounts |
| `volatility` | top-level `data.volatility` | ❌ None for multi-account |
| `xirr` | `return.XIRR` | ❌ None for multi-account |
| `pl` | `return.pl` | ✅ SUM across accounts |
| `invested` | `return.investment` | ✅ SUM across accounts |

All new fields are `float | None = None` — safe to render as `null` in JSON.

**Frontend contract:** multiply decimals × 100 to display as percentages (existing convention). `money_return`, `pl`, `invested` are already in EUR.

---

## Files changed

| File | Change |
|---|---|
| `src/finlytics/investments/base.py` | `NormalizedReturns` — 6 new fields |
| `src/finlytics/investments/indexa.py` | `_fetch_performance` fallback chain + new fields; `get_portfolio` ISIN aggregation |
| `src/finlytics/api/schemas.py` | `InvestmentReturns` — 6 new fields |
| `src/finlytics/investments/service.py` | `_aggregate` — propagate + sum new fields; null non-aggregatable for multi-account |
| `tests/api/test_investments.py` | 9 new tests for BUG A, BUG B, and new fields |


---

# Shuri — Indexa Redesign Backend: Extended Response Shape

**Date:** 2026-07-14  
**Status:** SHIPPED — all 916 tests passing (2 skipped, unrelated)  
**Branch:** main  
**For:** Vision (frontend charts), Wanda (tests/E2E), Barton (integration)

---

## What Changed

`GET /api/investments/portfolio` → `InvestmentPortfolioOut` extended with:
1. **Value series bug fixed** — dates now YYYY-MM-DD (was always empty, YYYYMMDD bug)
2. **Total value fixed** — from `portfolios[0]` (newest-first), not `portfolios[-1]` (was all-zeros)
3. **"Valor total" box numbers** on `returns` object
4. **`contributions_series`** — daily cumulative net contributions step-line
5. **`monthly_returns`** — month × year matrix for the returns calendar
6. **`drawdown`** — max drawdown object
7. **Multi-account**: contributions_series summed by date; matrix/drawdown/twr/sharpe = null

---

## Full Response Shape

### `InvestmentPortfolioOut` (top-level)

```json
{
  "total_value": 20559.52,
  "total_invested": 18000.0,
  "total_gain_loss": 2559.53,
  "total_gain_loss_pct": 0.1422,
  "currency": "EUR",
  "holdings": [...],
  "plugins_connected": 1,
  "last_updated": "2026-07-14T12:00:00+00:00",

  "returns": { ... },               // InvestmentReturns — see below
  "value_series": [ ... ],          // list[ValuePoint]
  "contributions_series": [ ... ],  // list[ValuePoint]
  "monthly_returns": [ ... ],       // list[MonthlyReturnRow] | null
  "drawdown": { ... },              // DrawdownOut | null
  "cash_invested": { ... }          // CashInvestedSplit | null
}
```

---

### `InvestmentReturns` (on `returns` key)

All fields `float | null`. New fields marked ★.

| Field | Type | Source | Description |
|---|---|---|---|
| `twr_annual` | float\|null | `return.time_return_annual` | Annualised TWR |
| `twr_total` | float\|null | `return.time_return` | Cumulative TWR from inception (0.2373 = +23.73%) |
| `twr_last_week` | float\|null | `return.time_return_last_week` | |
| `twr_last_month` | float\|null | `return.time_return_last_month` | |
| `twr_last_year` | float\|null | `return.time_return_last_year` | |
| `money_return` | float\|null | `return.money_return` | Money-weighted total return |
| ★ `money_return_annual` | float\|null | `return.money_return_annual` | Annualised money-weighted return |
| `volatility` | float\|null | top-level `data.volatility` | Portfolio volatility |
| `xirr` | float\|null | `return.XIRR` | Money-weighted annualised IRR |
| `pl` | float\|null | `return.pl` | Absolute P&L EUR |
| `invested` | float\|null | `return.investment` | Net invested EUR |
| ★ `aportaciones` | float\|null | `return.inflows` | Gross inflows (18000.00) |
| ★ `retenciones` | float\|null | `return.tax_outflows` | Tax outflows, negative (−0.01) |
| ★ `rentabilidad_eur` | float\|null | `return.pl` | Same as `pl` — for "Valor total" box |
| ★ `rentabilidad_pct` | float\|null | `return.money_return` | Same as `money_return` — for box |
| ★ `sharpe_ratio` | float\|null | top-level `data.sharpe_ratio` | Sharpe ratio (1.325) |

**Reconciliation:** `aportaciones + retenciones + rentabilidad_eur = total_value`  
(`18000.00 + (−0.01) + 2559.53 = 20559.52` ✓)

**Multi-account rule:** `aportaciones`, `retenciones`, `rentabilidad_eur`, `pl`, `money_return` are **summed**. `twr_*`, `xirr`, `volatility`, `sharpe_ratio`, `money_return_annual`, `rentabilidad_pct` are **null** for multi-account.

---

### `ValuePoint` (used in `value_series` and `contributions_series`)

```json
{ "date": "YYYY-MM-DD", "value": 20559.52 }
```

- **`value_series`**: daily portfolio total value (≈ 700 points, 2024-08-04 → today)
- **`contributions_series`**: daily cumulative net contributions (`net_amounts`). Step-line aligned by date with `value_series`. Last value ≈ 17999.99 (net of tax). Use this to draw the "Aportaciones" comparison line.

---

### `MonthlyReturnRow` (elements of `monthly_returns` list)

One object per calendar year. `months_pct` / `months_eur` only contain keys for months that have data (absent months → render as blank in table).

```json
{
  "year": 2024,
  "months_pct": {
    "8": 0.034754,
    "9": 0.014446,
    "10": -0.007513,
    "11": 0.02,
    "12": 0.021
  },
  "months_eur": {
    "8": 350.0,
    "9": 142.0,
    "10": -76.0,
    "11": 210.0,
    "12": 230.0
  },
  "total_pct": 0.072171,
  "total_eur": 856.0,
  "benchmark_pct": 0.019
}
```

| Field | Type | Description |
|---|---|---|
| `year` | int | Calendar year |
| `months_pct` | dict[int, float\|null] | TWR return per month (key = month 1–12) |
| `months_eur` | dict[int, float\|null] | EUR P&L per month (null if series data missing) |
| `total_pct` | float\|null | Compounded annual TWR: `product(1+monthly)−1` |
| `total_eur` | float\|null | Sum of monthly EUR P&L |
| `benchmark_pct` | float\|null | Compounded annual benchmark return |

**Note:** `monthly_returns` is `null` for multi-account (non-aggregatable). Current incomplete month (July 2026) is absent (not in history yet).

---

### `DrawdownOut` (on `drawdown` key)

```json
{
  "max_drawdown": -0.1005,
  "max_drawdown_eur": -1356.93,
  "start_date": "2025-02-20",
  "end_date": "2025-04-08"
}
```

| Field | Type | Description |
|---|---|---|
| `max_drawdown` | float | Fraction, negative (e.g. −0.1005 = −10.05%) |
| `max_drawdown_eur` | float | EUR amount, negative |
| `start_date` | str | YYYY-MM-DD — start of max drawdown period |
| `end_date` | str | YYYY-MM-DD — end (trough) of max drawdown period |

`drawdown` is `null` for multi-account and when `drawdowns` key is absent in the Indexa response.

---

### `CashInvestedSplit` (on `cash_invested` key)

```json
{
  "cash_amount": 67.16,
  "instruments_amount": 20492.36,
  "instruments_cost": 18000.0,
  "total_amount": 20559.52
}
```

Reflects `portfolios[0]` (newest daily snapshot — Indexa returns newest-first).

---

## Live Values (owner account, 2026-07-13)

| Field | Value |
|---|---|
| `total_value` | 20,559.52 € |
| `aportaciones` | 18,000.00 € |
| `retenciones` | −0.01 € |
| `rentabilidad_eur` | +2,559.53 € |
| `rentabilidad_pct` | 0.2133 (money-weighted, ~21.33%) |
| `twr_total` | 0.2373 (+23.73%) |
| `twr_annual` | 0.1162 (annualised TWR) |
| `xirr` | 0.1050 |
| `sharpe_ratio` | 1.325 |
| `value_series` length | ≈ 709 points |
| `contributions_series` length | ≈ 716 points |
| `monthly_returns` length | 3 years (2024, 2025, 2026) |
| `drawdown.max_drawdown` | −10.05% |
| `drawdown` period | 2025-02-20 → 2025-04-08 |

---

## Date Format

All dates in all series and drawdown: **`YYYY-MM-DD`** (ISO 8601).  
`ValuePoint.date` and `DrawdownOut.start_date`/`end_date` are all 10-character ISO strings.

---

## API Source Paths (Indexa `/accounts/{n}/performance`)

| Our field | Indexa path |
|---|---|
| `value_series` | `data["return"]["total_amounts"]` (YYYYMMDD keys, reformatted) |
| `contributions_series` | `data["net_amounts"]` (YYYYMMDD keys, reformatted) |
| `total_value` | `data["portfolios"][0]["total_amount"]` (newest-first) |
| `cash_invested` | `data["portfolios"][0]` fields |
| `monthly_returns` | `data["history"]` (cumulative TWR multipliers) + `data["benchmark"]` |
| `drawdown` | `data["drawdowns"]` (integer YYYYMMDD dates) |
| `sharpe_ratio` | `data["sharpe_ratio"]` (top-level) |
| `aportaciones` | `data["return"]["inflows"]` |
| `retenciones` | `data["return"]["tax_outflows"]` (already negative) |
| `rentabilidad_eur` | `data["return"]["pl"]` |
| `rentabilidad_pct` | `data["return"]["money_return"]` |
| `money_return_annual` | `data["return"]["money_return_annual"]` |


---

# Vision Build Contract — Investments Page Polish (3 Changes)
**Author:** Wanda (UX/UI) · **Date:** 2026-07-14  
**CSS:** `frontend/src/index.css` (already appended) · **For:** Vision (Frontend Engineer)  
**Builds on:** `wanda-investments-redesign.md` (prior contract — read that first)

---

## 0. Summary

| # | Change | CSS added | JSX impact |
|---|--------|-----------|------------|
| 1 | Compact summary card (no stretch) | `.inv-top-row` `align-items: start` | None — layout fix only |
| 2 | Metrics strip: TWR / MWR / Volatility | `.inv-metrics-strip`, `.inv-metric*` | Add strip inside `.inv-summary-card` |
| 3 | Second donut: by instrument | `.inv-donuts-row`, `.inv-donut-compact-legend`, `.inv-donut-legend-*`, `--inv-p0…p11` | Replace single donut slot with two-card grid |

---

## 1. Change 1 — Summary Card Height Fix

**What changed in CSS:** `.inv-top-row` now has `align-items: start` (was `stretch`).  
**JSX change needed:** None. Cards are no longer forced to equal heights, so the summary card shrinks to fit its content + the metrics strip.

---

## 2. Change 2 — Metrics Strip JSX

Place this **inside** `.inv-summary-card`, **after** the last `.inv-summary-row` (after Retenciones):

```tsx
{/* Metrics strip: TWR / MWR / Volatility */}
<div className="inv-metrics-strip">

  {/* TWR — Time-Weighted Return (annualised) */}
  <div className="inv-metric">
    <span className="inv-metric-label">{t.invMetricTwr}</span>
    <span className="inv-metric-sublabel">{t.invMetricSubAnnual}</span>
    <span className={`inv-metric-value ${
      (portfolio.returns?.twr_annual ?? 0) >= 0
        ? 'inv-metric-value--pos'
        : 'inv-metric-value--neg'
    }`}>
      {portfolio.returns?.twr_annual != null
        ? `${portfolio.returns.twr_annual >= 0 ? '+' : ''}${(portfolio.returns.twr_annual * 100).toFixed(1)} %`
        : '—'}
    </span>
  </div>

  {/* MWR — Money-Weighted Return (XIRR / annualised) */}
  <div className="inv-metric">
    <span className="inv-metric-label">{t.invMetricMwr}</span>
    <span className="inv-metric-sublabel">{t.invMetricSubXirr}</span>
    <span className={`inv-metric-value ${
      (portfolio.returns?.xirr ?? 0) >= 0
        ? 'inv-metric-value--pos'
        : 'inv-metric-value--neg'
    }`}>
      {portfolio.returns?.xirr != null
        ? `${portfolio.returns.xirr >= 0 ? '+' : ''}${(portfolio.returns.xirr * 100).toFixed(1)} %`
        : '—'}
    </span>
  </div>

  {/* Volatility — annualised, direction-neutral */}
  <div className="inv-metric">
    <span className="inv-metric-label">{t.invMetricVolatility}</span>
    <span className="inv-metric-sublabel">{t.invMetricSubAnnual}</span>
    <span className="inv-metric-value inv-metric-value--neutral">
      {portfolio.returns?.volatility != null
        ? `${(portfolio.returns.volatility * 100).toFixed(1)} %`
        : '—'}
    </span>
  </div>

</div>
```

**Data fields used:**
| Field | Source | Notes |
|-------|--------|-------|
| `portfolio.returns.twr_annual` | `returns.twr_annual` | float, e.g. 0.083 → 8.3 % |
| `portfolio.returns.xirr` | `returns.xirr` | float; same scale |
| `portfolio.returns.volatility` | `returns.volatility` | float; neutral (no pos/neg coloring) |

**New i18n keys (add to ES + EN + Dict interface):**

| Key | ES | EN |
|-----|----|----|
| `invMetricTwr` | `TWR` | `TWR` |
| `invMetricMwr` | `MWR` | `MWR` |
| `invMetricVolatility` | `Volatilidad` | `Volatility` |
| `invMetricSubAnnual` | `anualizada` | `annualised` |
| `invMetricSubXirr` | `TIR anualizada` | `annualised IRR` |

---

## 3. Change 3 — Two-Donut Layout JSX

### 3a. DOM structure

In `inv-top-row`, **replace** the single `<div className="card inv-chart-card inv-chart-card--allocation">` with:

```tsx
{/* Two donuts: asset class + instrument */}
<div className="inv-donuts-row">

  {/* Donut 1 — Allocation by asset class (existing logic, moved here) */}
  <div className="card">
    <h3 className="card-title">{t.invDonutAssetTitle}</h3>
    <div className="cat-chart-layout">
      <div className="cat-donut-wrap">
        {/* existing PieChart / ResponsiveContainer — unchanged */}
        <div className="cat-donut-center">
          <span className="cat-donut-label">{t.invDonutAssetTitle}</span>
          <span className="cat-donut-total">{formatCurrency(portfolio.total_value)}</span>
        </div>
      </div>
      <div className="cat-table-wrap">
        {/* existing .cat-table for asset classes — unchanged */}
      </div>
    </div>
  </div>

  {/* Donut 2 — Allocation by instrument (new) */}
  <div className="card">
    <h3 className="card-title">{t.invDonutInstrumentTitle}</h3>
    <div className="cat-chart-layout">
      <div className="cat-donut-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={instrumentSlices}
              cx="50%"
              cy="50%"
              innerRadius="58%"
              outerRadius="80%"
              dataKey="value"
              strokeWidth={1}
              stroke="var(--surface)"
            >
              {instrumentSlices.map((_, i) => (
                <Cell key={i} fill={INSTRUMENT_PALETTE[i % INSTRUMENT_PALETTE.length]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="cat-donut-center">
          <span className="cat-donut-label">{t.invDonutInstrumentTitle}</span>
          <span className="cat-donut-total">{formatCurrency(portfolio.total_value)}</span>
        </div>
      </div>
      {/* Compact legend — replaces full cat-table for instruments */}
      <div className="inv-donut-compact-legend">
        {instrumentSlices.map((item, i) => (
          <div key={item.name} className="inv-donut-legend-item">
            <span
              className="inv-donut-legend-swatch"
              style={{ backgroundColor: INSTRUMENT_PALETTE[i % INSTRUMENT_PALETTE.length] }}
            />
            <span className="inv-donut-legend-name" title={item.name}>{item.name}</span>
            <span className="inv-donut-legend-pct">
              {((item.value / portfolio.total_value) * 100).toFixed(1)} %
            </span>
          </div>
        ))}
      </div>
    </div>
  </div>

</div>
```

### 3b. Data: `instrumentSlices`

Derive from `portfolio.holdings` (array already fetched):

```ts
const instrumentSlices = (portfolio.holdings ?? [])
  .filter(h => h.current_value > 0)
  .map(h => ({ name: h.fund_name ?? h.isin, value: h.current_value }))
  .sort((a, b) => b.value - a.value);   // largest slice first
```

### 3c. Instrument colour palette constant

Add near the top of `InvestmentsPage.tsx` (or a shared `investmentColors.ts`):

```ts
export const INSTRUMENT_PALETTE = [
  '#3b82f6',  // 0  blue
  '#22c55e',  // 1  green
  '#f59e0b',  // 2  amber
  '#ec4899',  // 3  pink
  '#8b5cf6',  // 4  violet
  '#06b6d4',  // 5  cyan
  '#f97316',  // 6  orange
  '#64748b',  // 7  slate
  '#84cc16',  // 8  lime
  '#e11d48',  // 9  rose
  '#0ea5e9',  // 10 sky
  '#d946ef',  // 11 fuchsia
] as const;
```

CSS also exposes them as `--inv-p0` … `--inv-p11` for swatch `backgroundColor: var(--inv-p0)` fallback, but the JS array is the primary source for Recharts `Cell` fills.

### 3d. New i18n keys

| Key | ES | EN |
|-----|----|----|
| `invDonutAssetTitle` | `Por clase de activo` | `By asset class` |
| `invDonutInstrumentTitle` | `Por instrumento` | `By instrument` |

---

## 4. Class Reference Table (all new classes)

| Class | File | Description |
|-------|------|-------------|
| `.inv-metrics-strip` | `index.css` | Flex row of 3 metric cells; `border-top` separator; lives at bottom of `.inv-summary-card` |
| `.inv-metric` | `index.css` | Single metric cell: flex-col, centered, `border-right` divider |
| `.inv-metric-label` | `index.css` | 10px uppercase label (e.g. "TWR") |
| `.inv-metric-sublabel` | `index.css` | 9px caption (e.g. "anualizada") |
| `.inv-metric-value` | `index.css` | 15px/700 numeric figure |
| `.inv-metric-value--pos` | `index.css` | `var(--income)` — positive return |
| `.inv-metric-value--neg` | `index.css` | `var(--expense)` — negative return |
| `.inv-metric-value--neutral` | `index.css` | `var(--text-muted)` — risk metric (volatility) |
| `.inv-donuts-row` | `index.css` | 1fr/1fr grid wrapper for the two donut cards; stacks ≤900px |
| `.inv-donut-compact-legend` | `index.css` | Flex-col list, max-height 200px scrollable, for instrument donut |
| `.inv-donut-legend-item` | `index.css` | One legend row: swatch + name + pct |
| `.inv-donut-legend-swatch` | `index.css` | 8×8px coloured square |
| `.inv-donut-legend-name` | `index.css` | Fund name, truncated with ellipsis |
| `.inv-donut-legend-pct` | `index.css` | Right-aligned percentage |
| `--inv-p0` … `--inv-p11` | `index.css` `:root` | 12 palette CSS custom properties for swatch fallback |

---

## 5. Full Updated Page Layout (after all 3 changes)

```tsx
<main className="dashboard">

  <div className="inv-account-header"> … </div>

  {/* Block 1 + both donuts — top row, cards at natural height */}
  <div className="inv-top-row">                         {/* align-items: start */}
    <div className="card inv-summary-card">
      {/* 4 summary rows */}
      <div className="inv-summary-row inv-summary-row--total"> … </div>
      <div className="inv-summary-row"> … </div>       {/* Rentabilidad */}
      <div className="inv-summary-row"> … </div>       {/* Aportaciones */}
      <div className="inv-summary-row"> … </div>       {/* Retenciones */}
      {/* Metrics strip */}
      <div className="inv-metrics-strip">
        <div className="inv-metric"> … </div>           {/* TWR */}
        <div className="inv-metric"> … </div>           {/* MWR */}
        <div className="inv-metric"> … </div>           {/* Volatilidad */}
      </div>
    </div>

    <div className="inv-donuts-row">
      <div className="card"> … </div>                   {/* Donut 1: asset class */}
      <div className="card"> … </div>                   {/* Donut 2: instrument */}
    </div>
  </div>

  <div className="card inv-evolution-card"> … </div>

  <div className="card returns-matrix-card"> … </div>

  <div className="card inv-holdings-card"> … </div>

</main>
```

---

## 6. Responsive Behaviour Summary

| Breakpoint | `inv-top-row` | `inv-donuts-row` | `inv-metrics-strip` |
|-----------|--------------|-----------------|---------------------|
| ≥ 901px | 1fr 1fr (side-by-side) | 1fr 1fr (two donuts) | 1 row, 3 equal cells |
| ≤ 900px | 1fr (stacked) | 1fr (stacked) | 1 row, 3 equal cells |
| ≤ 600px | 1fr | 1fr | 1 row, smaller type |

Mobile order (stacked): summary card → metrics strip → donut1 → donut2 → evolution → matrix → holdings.


---

# Vision Build Contract — Investments Polish 2 (3 Changes)
**Author:** Wanda (UX/UI) · **Date:** 2026-07-14  
**CSS:** `frontend/src/index.css` (already appended) · **For:** Vision (Frontend Engineer)  
**Builds on:** `wanda-investments-polish.md` (polish 1 — read first)

---

## 0. Summary

| # | Change | CSS added | JSX impact |
|---|--------|-----------|------------|
| 1 | Move returns matrix into left column gap | `.inv-left-col` | Wrap summary card + matrix in `.inv-left-col`; remove standalone matrix from below evolution card |
| 2 | Fix donut center label alignment | `.inv-donuts-row .cat-donut-wrap { height: 220px }` | **None** — CSS-only fix |
| 3 | Info-tip tooltips for TWR/MWR/Volatilidad | `.inv-metric-header`, `.inv-info-tip`, `.inv-info-bubble` | Add `inv-metric-header` div + tip button inside each `.inv-metric` |

---

## 1. Change 1 — Returns Matrix in Left Column

### Why
On wide screens the `.inv-summary-card` (left cell of `.inv-top-row`) is shorter than the right-column `.inv-donuts-row`, leaving an empty gap below the summary. Moving the returns matrix there fills that gap naturally.

### Implementation choice
The matrix has ≥15 columns (`min-width: 720px` on the `<table>`). In a half-viewport left column (~490–560px) it is narrower than 720px, so it scrolls horizontally inside its existing `.returns-matrix-wrap` container (`overflow-x: auto`). This is the cleanest option — all data stays accessible, and on mobile everything stacks to full-width anyway.

### New class
```css
/* Already in index.css */
.inv-left-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
```

### JSX structure — updated `InvestmentsPage.tsx`

```tsx
<main className="dashboard">

  <div className="inv-account-header"> … </div>

  {/* ── Top row ── */}
  <div className="inv-top-row">

    {/* LEFT column: summary card + returns matrix (NEW wrapper) */}
    <div className="inv-left-col">
      <div className="card inv-summary-card">
        {/* summary rows unchanged */}
        <div className="inv-metrics-strip">
          {/* TWR / MWR / Volatilidad — see Change 3 below */}
        </div>
      </div>

      {/* returns-matrix-card MOVED HERE from its former standalone position */}
      <div className="card returns-matrix-card">
        <div className="returns-matrix-header"> … </div>
        <div className="returns-matrix-wrap">
          <table className="returns-matrix"> … </table>
        </div>
        <p className="inv-drawdown-note"> … </p>
      </div>
    </div>

    {/* RIGHT column: two donuts (unchanged) */}
    <div className="inv-donuts-row">
      <div className="card"> … </div>   {/* asset-class donut */}
      <div className="card"> … </div>   {/* instrument donut */}
    </div>

  </div>

  {/* Evolution chart — full width, unchanged */}
  <div className="card inv-evolution-card"> … </div>

  {/* returns-matrix-card REMOVED from here — it is now in .inv-left-col above */}

  {/* Holdings table — unchanged */}
  <div className="card inv-holdings-card"> … </div>

</main>
```

### Responsive behaviour
| Breakpoint | `inv-top-row` | `inv-left-col` |
|-----------|--------------|---------------|
| ≥ 901px | 1fr 1fr | flex-col: summary → matrix (matrix scrolls H if needed) |
| ≤ 900px | 1fr (stacked) | full-width; summary → matrix → donuts → evolution → holdings |

---

## 2. Change 2 — Donut Center Label Fix (CSS-only)

**Problem:** `InvestmentsPage.tsx` passes `height={220}` to each `<ResponsiveContainer>` inside `.cat-donut-wrap`, but the shared CSS had `.cat-donut-wrap { height: 280px }`. The 60px mismatch pushed `.cat-donut-center` (which uses `position: absolute; inset: 0` on the 280px wrap) ~30px below the visual centre of the 220px ring.

**Fix already in CSS:**
```css
.inv-donuts-row .cat-donut-wrap {
  height: 220px;
  max-width: 220px;
}
```

**JSX change needed: None.** The existing `cat-donut-wrap` / `cat-donut-center` markup is correct. The scoped rule now makes the wrapper exactly match the RC height so `inset: 0` lands on centre.

---

## 3. Change 3 — Info-tip Tooltips for TWR / MWR / Volatilidad

### New classes (all in `index.css`)

| Class | Description |
|-------|-------------|
| `.inv-metric-header` | Flex row — holds `.inv-metric-label` + `.inv-info-tip` side-by-side |
| `.inv-info-tip` | Circular 14px "?" button; `position: relative` (bubble anchors here) |
| `.inv-info-bubble` | Absolute tooltip bubble; shown on `:hover` / `:focus-visible` of `.inv-info-tip` |

### Markup pattern (inside each `.inv-metric`)

```tsx
<div className="inv-metric">
  {/* label row: uppercase name + info icon */}
  <div className="inv-metric-header">
    <span className="inv-metric-label">{t.invMetricTwr}</span>
    <button
      className="inv-info-tip"
      type="button"
      aria-label={t.invMetricTwrInfo}
    >
      ?
      <span className="inv-info-bubble">{t.invMetricTwrInfo}</span>
    </button>
  </div>
  <span className="inv-metric-sublabel">{t.invMetricSubAnnual}</span>
  <span className={`inv-metric-value ${
    (portfolio.returns?.twr_annual ?? 0) >= 0
      ? 'inv-metric-value--pos'
      : 'inv-metric-value--neg'
  }`}>
    {portfolio.returns?.twr_annual != null
      ? `${portfolio.returns.twr_annual >= 0 ? '+' : ''}${(portfolio.returns.twr_annual * 100).toFixed(1)} %`
      : '—'}
  </span>
</div>
```

Repeat the same pattern for MWR and Volatilidad (use the `aria-label` + bubble text from the i18n keys below).

### Behaviour
- **Desktop hover:** bubble appears above the "?" icon
- **Keyboard:** Tab to the button → `:focus-visible` shows bubble
- **Mobile tap:** tap sets focus → bubble appears; tap elsewhere → focus leaves → bubble hides
- `pointer-events: none` on the bubble prevents accidental mouse-leave flicker

### i18n keys — add to ES + EN + Dict interface

| Key | ES | EN |
|-----|----|----|
| `invMetricTwrInfo` | `Rentabilidad ponderada por tiempo (TWR). Mide el rendimiento de la cartera eliminando el efecto de aportaciones y reintegros; compara gestores en igualdad de condiciones.` | `Time-Weighted Return (TWR). Measures portfolio performance independently of the timing and size of contributions or withdrawals; useful for comparing managers on equal terms.` |
| `invMetricMwrInfo` | `Rentabilidad ponderada por dinero (MWR / TIR). Tu rentabilidad real teniendo en cuenta cuándo y cuánto aportaste; refleja el impacto de tus decisiones de inversión.` | `Money-Weighted Return (MWR / IRR). Your actual return accounting for when and how much you contributed; reflects the impact of your own investment timing decisions.` |
| `invMetricVolInfo` | `Volatilidad anualizada. Variabilidad histórica de los rendimientos diarios. A mayor volatilidad, mayor incertidumbre a corto plazo y mayor riesgo percibido.` | `Annualised volatility. Historical variability of daily returns. Higher volatility means greater short-term uncertainty and perceived risk.` |

**Use `invMetricVolInfo` for Volatilidad** (the existing `invMetricVolatility` / `invMetricSubAnnual` keys remain; only add the `…Info` keys).

---

## 4. Full Class Reference (all new in this contract)

| Class | File | Description |
|-------|------|-------------|
| `.inv-left-col` | `index.css` | Flex-col wrapper for left cell of `.inv-top-row` |
| `.inv-metric-header` | `index.css` | Flex row — label + tip button |
| `.inv-info-tip` | `index.css` | 14px circular "?" button with relative positioning |
| `.inv-info-bubble` | `index.css` | Absolute tooltip bubble; hidden/shown by tip hover/focus |

---

## 5. Final Page Layout (after all Polish 1 + Polish 2 changes)

```
<main className="dashboard">
  .inv-account-header
  .inv-top-row (1fr 1fr → 1fr ≤900px)
    .inv-left-col (flex-col)                          ← NEW
      .card.inv-summary-card
        .inv-summary-row × 4
        .inv-metrics-strip
          .inv-metric (.inv-metric-header + sublabel + value) × 3   ← UPDATED
      .card.returns-matrix-card                       ← MOVED from below
    .inv-donuts-row (1fr 1fr → 1fr ≤900px)
      .card (asset-class donut)
      .card (instrument donut)
  .card.inv-evolution-card
  .card.inv-holdings-card
</main>
```


---

# Vision Build Contract — Investments Page Redesign (Indexa Layout)
**Author:** Wanda (UX/UI) · **Date:** 2026-07-14  
**CSS:** `frontend/src/index.css` (already appended) · **For:** Vision (Frontend Engineer)

---

## 0. Summary of Changes

| What changes | Old element | New element |
|---|---|---|
| Summary box | `kpi-grid` (5 `kpi-card`s) | `inv-summary-card` — 4 compact rows |
| Top-row layout | `inv-charts-row` (3fr/2fr) | `inv-top-row` (1fr/1fr) |
| Evolution chart | `inv-chart-card--value` inside `inv-charts-row` | `inv-evolution-card` — full-width, with period + toggle |
| Donut | Right cell of `inv-charts-row` | Right cell of `inv-top-row` (JSX unchanged; just move into new grid) |
| Returns | `inv-returns-card` (simple list) | `returns-matrix-card` — month × year matrix |

**New state variables needed:** `evPeriod`, `evMode`, `matrixMode`  
**New Recharts import:** `LineChart`, `Line` (replace `AreaChart`/`Area` or add)

---

## 1. New Page Layout (populated state)

```tsx
<main className="dashboard">

  {/* Account header — unchanged */}
  <div className="inv-account-header"> … </div>

  {/* Block 1 + allocation donut — new top row */}
  <div className="inv-top-row">
    <div className="card inv-summary-card"> … </div>                     {/* Block 1 */}
    <div className="card inv-chart-card inv-chart-card--allocation"> … </div> {/* donut — JSX unchanged */}
  </div>

  {/* Block 2 — Evolution chart, full-width */}
  <div className="card inv-evolution-card"> … </div>

  {/* Block 3 — Monthly returns matrix, full-width */}
  <div className="card returns-matrix-card"> … </div>

  {/* Holdings table — unchanged */}
  <div className="card inv-holdings-card"> … </div>

</main>
```

**Remove:** `kpi-grid` block (5 kpi-cards), `inv-charts-row` wrapper (and its `inv-chart-card--value` child).

---

## 2. Block 1 — Summary Card JSX

```tsx
<div className="card inv-summary-card">

  {/* Valor total — hero number */}
  <div className="inv-summary-row inv-summary-row--total">
    <span className="inv-summary-label">{t.invSummaryValorTotal}</span>
    <span className="inv-summary-value inv-summary-value--big">
      {formatCurrency(portfolio.total_value)}
    </span>
  </div>

  {/* Rentabilidad — € amount + % in one cell */}
  <div className="inv-summary-row">
    <span className="inv-summary-label">{t.invSummaryRentabilidad}</span>
    <span className={`inv-summary-value ${
      (portfolio.returns?.pl ?? 0) >= 0 ? 'inv-summary-value--pos' : 'inv-summary-value--neg'
    }`}>
      {portfolio.returns?.pl != null
        ? `${portfolio.returns.pl >= 0 ? '+' : ''}${formatCurrency(portfolio.returns.pl)}` +
          (portfolio.returns.money_return != null
            ? ` (${portfolio.returns.money_return >= 0 ? '+' : ''}${(portfolio.returns.money_return * 100).toFixed(1)} %)`
            : '')
        : '—'}
    </span>
  </div>

  {/* Aportaciones */}
  <div className="inv-summary-row">
    <span className="inv-summary-label">{t.invSummaryAportaciones}</span>
    <span className="inv-summary-value">
      {portfolio.returns?.inflows != null
        ? `+${formatCurrency(portfolio.returns.inflows)}`
        : '—'}
    </span>
  </div>

  {/* Retenciones — tax_outflows is a positive number; display as negative */}
  <div className="inv-summary-row">
    <span className="inv-summary-label">{t.invSummaryRetenciones}</span>
    <span className={`inv-summary-value ${
      (portfolio.returns?.tax_outflows ?? 0) > 0 ? 'inv-summary-value--neg' : ''
    }`}>
      {portfolio.returns?.tax_outflows != null
        ? portfolio.returns.tax_outflows > 0
          ? `−${formatCurrency(portfolio.returns.tax_outflows)}`
          : formatCurrency(0)
        : '—'}
    </span>
  </div>

</div>
```

**Data fields (from `InvestmentPortfolio.returns`):**
| UI label | Field | Notes |
|---|---|---|
| Valor total | `portfolio.total_value` | Top-level; fixed by Shuri (`portfolios[0]`) |
| Rentabilidad € | `returns.pl` | P&L in EUR |
| Rentabilidad % | `returns.money_return` | Decimal → × 100 for %. Display: `money_return`, not `twr_total` (Indexa's "Rentabilidad" = money-weighted) |
| Aportaciones | `returns.inflows` | Gross deposits |
| Retenciones | `returns.tax_outflows` | Positive float; display as `−value` |

---

## 3. Block 2 — Evolution Card JSX

### 3a. State variables (add to component):

```tsx
type EvolutionPeriod = '1M' | '3M' | '6M' | '1A' | string | 'Todo';
type EvolutionMode   = 'eur' | 'pct';

const [evPeriod, setEvPeriod] = useState<EvolutionPeriod>('Todo');
const [evMode,   setEvMode]   = useState<EvolutionMode>('eur');
```

### 3b. Dynamic year list (useMemo):

```tsx
const evolutionYears = useMemo((): string[] => {
  if (!portfolio?.value_series?.length) return [];
  // value_series dates are YYYY-MM-DD after Shuri's fix
  const firstYear = parseInt(portfolio.value_series[0].date.slice(0, 4), 10);
  const lastYear  = new Date().getFullYear();
  return Array.from({ length: lastYear - firstYear + 1 }, (_, i) => String(firstYear + i));
}, [portfolio]);
```

### 3c. Fixed period labels:

```tsx
const FIXED_PERIODS: Array<{ id: EvolutionPeriod; label: string }> = [
  { id: '1M',  label: t.invPeriod1M },
  { id: '3M',  label: t.invPeriod3M },
  { id: '6M',  label: t.invPeriod6M },
  { id: '1A',  label: t.invPeriod1A },
];
```

### 3d. Chart data (useMemo):

```tsx
const evolutionData = useMemo(() => {
  if (!portfolio?.value_series?.length) return [];

  // Build contributions lookup from net_amounts_series
  // net_amounts_series: array of { date: string /* YYYY-MM-DD */, value: number }
  const contribMap = new Map(
    (portfolio.net_amounts_series ?? []).map(pt => [pt.date, pt.value])
  );

  const now = new Date();
  const cutoff: Date | null = (() => {
    if (evPeriod === '1M') return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
    if (evPeriod === '3M') return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
    if (evPeriod === '6M') return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
    if (evPeriod === '1A') return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    return null; // 'Todo' or year string
  })();

  const filtered = portfolio.value_series.filter(pt => {
    if (evPeriod !== 'Todo' && evPeriod.length === 4) return pt.date.startsWith(evPeriod);
    if (cutoff) return new Date(pt.date) >= cutoff;
    return true;
  });

  if (evMode === 'pct') {
    // Normalize: (value / value[0] - 1) × 100
    const base = filtered[0]?.value ?? 1;
    const baseC = contribMap.get(filtered[0]?.date) ?? 1;
    return filtered.map(pt => ({
      date:          new Date(pt.date).toLocaleDateString(locale, { month: 'short', year: '2-digit' }),
      value:         base > 0 ? +((pt.value / base - 1) * 100).toFixed(2) : 0,
      contributions: (() => {
        const c = contribMap.get(pt.date);
        return c != null && baseC > 0 ? +((c / baseC - 1) * 100).toFixed(2) : null;
      })(),
    }));
  }

  return filtered.map(pt => ({
    date:          new Date(pt.date).toLocaleDateString(locale, { month: 'short', year: '2-digit' }),
    value:         pt.value,
    contributions: contribMap.get(pt.date) ?? null,
  }));
}, [portfolio, evPeriod, evMode, locale]);
```

### 3e. JSX tree:

```tsx
<div className="card inv-evolution-card">

  <div className="inv-evolution-header">
    <h3 className="card-title">{t.invEvolutionTitle}</h3>
    <div className="inv-evolution-controls">

      {/* Period selector */}
      <div className="inv-period-selector">
        {FIXED_PERIODS.map(p => (
          <button
            key={p.id}
            className={`inv-period-btn${evPeriod === p.id ? ' inv-period-btn--active' : ''}`}
            onClick={() => setEvPeriod(p.id)}
          >{p.label}</button>
        ))}
        {evolutionYears.map(y => (
          <button
            key={y}
            className={`inv-period-btn${evPeriod === y ? ' inv-period-btn--active' : ''}`}
            onClick={() => setEvPeriod(y)}
          >{y}</button>
        ))}
        <button
          className={`inv-period-btn${evPeriod === 'Todo' ? ' inv-period-btn--active' : ''}`}
          onClick={() => setEvPeriod('Todo')}
        >{t.invPeriodTodo}</button>
      </div>

      {/* €/% toggle */}
      <div className="inv-toggle">
        <button
          className={`inv-toggle-btn${evMode === 'eur' ? ' inv-toggle-btn--active' : ''}`}
          onClick={() => setEvMode('eur')}
        >{t.invToggleEur}</button>
        <button
          className={`inv-toggle-btn${evMode === 'pct' ? ' inv-toggle-btn--active' : ''}`}
          onClick={() => setEvMode('pct')}
        >{t.invTogglePct}</button>
      </div>

    </div>
  </div>

  {evolutionData.length === 0 ? (
    <div className="state-box">
      <span className="icon">📈</span>
      <span>{t.noDataPeriod}</span>
    </div>
  ) : (
    <>
      <div className="inv-evolution-chart-wrap">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={evolutionData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tickFormatter={evMode === 'eur'
                ? (v: number) => `${(v / 1000).toFixed(0)}k€`
                : (v: number) => `${v.toFixed(1)}%`}
              tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
              axisLine={false}
              tickLine={false}
              width={52}
            />
            <Tooltip
              contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
              labelStyle={{ color: 'var(--text)' }}
              itemStyle={{ color: 'var(--text)' }}
              formatter={(value: number, name: string) => [
                evMode === 'eur' ? formatCurrency(value) : `${value.toFixed(2)}%`,
                name === 'value' ? t.invLegendPortfolio : t.invLegendContributions,
              ]}
            />
            {/* Tu cartera — primary colour, solid */}
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--primary)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: 'var(--primary)' }}
              connectNulls
            />
            {/* Aportaciones — muted, dashed step-line */}
            <Line
              type="stepAfter"
              dataKey="contributions"
              stroke="var(--text-muted)"
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
              activeDot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="inv-chart-legend">
        <span className="inv-chart-legend-item">
          <span className="inv-chart-legend-swatch" style={{ background: 'var(--primary)' }} />
          <span>{t.invLegendPortfolio}</span>
        </span>
        <span className="inv-chart-legend-item">
          <span className="inv-chart-legend-swatch"
            style={{ background: 'var(--text-muted)', backgroundImage: 'repeating-linear-gradient(90deg, var(--text-muted) 0 5px, transparent 5px 8px)' }} />
          <span>{t.invLegendContributions}</span>
        </span>
      </div>
    </>
  )}

</div>
```

**Recharts note:** Import `LineChart` and `Line` from `recharts`. You may keep `AreaChart`/`Area` imports if still needed elsewhere; otherwise swap them.

---

## 4. Block 3 — Monthly Returns Matrix JSX

### 4a. State variable:

```tsx
type MatrixMode = 'pct' | 'eur';
const [matrixMode, setMatrixMode] = useState<MatrixMode>('pct');
```

### 4b. Data shape expected from Shuri (`portfolio.monthly_returns`):

```ts
type MonthlyReturn = {
  year:           number;        // e.g. 2024
  month:          number;        // 1 = Jan … 12 = Dec
  portfolio_pct:  number | null; // monthly TWR return, decimal (0.0347 = +3.47%)
  portfolio_eur:  number | null; // monthly P&L in EUR
  benchmark_pct:  number | null; // same structure
  benchmark_eur:  number | null;
};
```

Shuri derives this from `data["history"]` (cumulative TWR multipliers, monthly) and `data["benchmark"]`.

### 4c. Drawdown data shape (`portfolio.drawdown`):

```ts
type DrawdownInfo = {
  max_drawdown:     number; // e.g. -0.10050  (already negative)
  max_drawdown_eur: number; // e.g. -1356.93  (already negative)
  start_date:       string; // YYYY-MM-DD
  end_date:         string; // YYYY-MM-DD
};
```

### 4d. JSX tree:

```tsx
{portfolio.monthly_returns && portfolio.monthly_returns.length > 0 && (() => {
  const MONTHS = [
    t.invMonthENE, t.invMonthFEB, t.invMonthMAR, t.invMonthABR,
    t.invMonthMAY, t.invMonthJUN, t.invMonthJUL, t.invMonthAGO,
    t.invMonthSEP, t.invMonthOCT, t.invMonthNOV, t.invMonthDIC,
  ];

  // Group rows by year
  const yearMap = new Map<number, MonthlyReturn[]>();
  for (const r of portfolio.monthly_returns) {
    if (!yearMap.has(r.year)) yearMap.set(r.year, []);
    yearMap.get(r.year)!.push(r);
  }
  const years = Array.from(yearMap.keys()).sort();

  // Format a single cell value
  const fmtCell = (v: number | null, mode: MatrixMode): string => {
    if (v == null) return '';
    if (mode === 'pct') {
      const s = (v * 100).toFixed(2);
      return v >= 0 ? `+${s}%` : `${s}%`;
    }
    return v >= 0 ? `+${formatCurrency(v)}` : formatCurrency(v);
  };

  // CSS class for a cell value
  const cellCls = (v: number | null, extra = ''): string => {
    const base = `returns-matrix-cell${extra ? ` ${extra}` : ''}`;
    if (v == null) return `${base} returns-matrix-cell--empty`;
    if (v > 0)    return `${base} returns-matrix-cell--pos`;
    if (v < 0)    return `${base} returns-matrix-cell--neg`;
    return base;
  };

  // Annual totals (geometric product for % ; simple sum for €)
  const annualPct = (rows: MonthlyReturn[]): number | null => {
    const valid = rows.filter(r => r.portfolio_pct != null);
    if (!valid.length) return null;
    return valid.reduce((acc, r) => acc * (1 + r.portfolio_pct!), 1) - 1;
  };
  const annualEur = (rows: MonthlyReturn[]): number | null => {
    const valid = rows.filter(r => r.portfolio_eur != null);
    if (!valid.length) return null;
    return valid.reduce((acc, r) => acc + r.portfolio_eur!, 0);
  };
  const benchPct = (rows: MonthlyReturn[]): number | null => {
    const valid = rows.filter(r => r.benchmark_pct != null);
    if (!valid.length) return null;
    return valid.reduce((acc, r) => acc * (1 + r.benchmark_pct!), 1) - 1;
  };

  return (
    <div className="card returns-matrix-card">

      <div className="returns-matrix-header">
        <h3 className="card-title">{t.invMatrixTitle}</h3>
        <div className="inv-toggle">
          <button
            className={`inv-toggle-btn${matrixMode === 'pct' ? ' inv-toggle-btn--active' : ''}`}
            onClick={() => setMatrixMode('pct')}
          >{t.invTogglePct}</button>
          <button
            className={`inv-toggle-btn${matrixMode === 'eur' ? ' inv-toggle-btn--active' : ''}`}
            onClick={() => setMatrixMode('eur')}
          >{t.invToggleEur}</button>
        </div>
      </div>

      <div className="returns-matrix-wrap">
        <table className="returns-matrix">
          <thead>
            <tr>
              <th></th>
              {MONTHS.map((m, i) => <th key={i}>{m}</th>)}
              <th className="returns-matrix-cell--total">{t.invMatrixTotal}</th>
              <th className="returns-matrix-cell--bench">{t.invMatrixBenchmark}</th>
            </tr>
          </thead>
          <tbody>
            {years.map(year => {
              const rows  = yearMap.get(year)!;
              const byMon = new Map(rows.map(r => [r.month, r]));
              const tot   = matrixMode === 'pct' ? annualPct(rows) : annualEur(rows);
              const bench = benchPct(rows); // benchmark: % only
              return (
                <tr key={year}>
                  <td className="returns-matrix-year">{year}</td>
                  {Array.from({ length: 12 }, (_, i) => {
                    const row = byMon.get(i + 1);
                    const v = row
                      ? matrixMode === 'pct' ? row.portfolio_pct : row.portfolio_eur
                      : null;
                    return <td key={i} className={cellCls(v)}>{fmtCell(v, matrixMode)}</td>;
                  })}
                  <td className={cellCls(tot, 'returns-matrix-cell--total')}>
                    {fmtCell(tot, matrixMode)}
                  </td>
                  <td className={cellCls(bench, 'returns-matrix-cell--bench')}>
                    {bench != null ? fmtCell(bench, 'pct') : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Max-drawdown note */}
      {portfolio.drawdown && (
        <p className="inv-drawdown-note">
          {t.invDrawdownNote(
            `${(Math.abs(portfolio.drawdown.max_drawdown) * 100).toFixed(1)}%`,
            formatCurrency(Math.abs(portfolio.drawdown.max_drawdown_eur)),
            new Date(portfolio.drawdown.start_date).toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
            new Date(portfolio.drawdown.end_date).toLocaleDateString(locale, { day: '2-digit', month: '2-digit', year: 'numeric' }),
          )}
        </p>
      )}

    </div>
  );
})()}
```

---

## 5. CSS Class Reference

All classes are in `frontend/src/index.css`. Read the Indexa Redesign block appended at the end.

### Layout

| Class | Purpose |
|---|---|
| `.inv-top-row` | `1fr 1fr` grid for summary + donut; stacks at ≤900px |
| `.inv-summary-card` | Block 1 card shell; flex-column |
| `.inv-evolution-card` | Block 2 card shell; flex-column, full-width |
| `.returns-matrix-card` | Block 3 card shell; **`max-width: 1100px`** ultrawide fix |

### Block 1 — Summary

| Class | Purpose |
|---|---|
| `.inv-summary-row` | flex row: label left, value right; `border-bottom` |
| `.inv-summary-row--total` | extra padding for the total row (hero separator) |
| `.inv-summary-label` | 13px muted left cell |
| `.inv-summary-value` | 15px/600 tabular-nums right cell |
| `.inv-summary-value--big` | 26px/800 — hero Valor total number |
| `.inv-summary-value--pos` | `var(--income)` green |
| `.inv-summary-value--neg` | `var(--expense)` red |

### Block 2 — Evolution

| Class | Purpose |
|---|---|
| `.inv-evolution-header` | flex row: title + controls; wraps on mobile |
| `.inv-evolution-controls` | groups period selector + toggle |
| `.inv-period-selector` | sunken track container; `flex-wrap: wrap` for mobile |
| `.inv-period-btn` | individual period button |
| `.inv-period-btn--active` | primary bg + white text |
| `.inv-toggle` | 2-option toggle container (same style as period selector) |
| `.inv-toggle-btn` / `--active` | same as period buttons |
| `.inv-evolution-chart-wrap` | 360px height → `ResponsiveContainer height="100%"` |
| `.inv-chart-legend` | centered flex legend row below chart |
| `.inv-chart-legend-item` | swatch + label pair |
| `.inv-chart-legend-swatch` | 24×3px line-style swatch |

### Block 3 — Matrix

| Class | Purpose |
|---|---|
| `.returns-matrix-header` | title + toggle row |
| `.returns-matrix-wrap` | `overflow-x: auto` scroll wrapper |
| `.returns-matrix` | `<table>` — `min-width: 720px`, `border-collapse: collapse` |
| `.returns-matrix-year` | year column cell — left-aligned, bold |
| `.returns-matrix-cell` | base cell (no extra rules) |
| `.returns-matrix-cell--pos` | green tint + bold |
| `.returns-matrix-cell--neg` | red tint + bold |
| `.returns-matrix-cell--empty` | `var(--text-muted)` |
| `.returns-matrix-cell--total` | bold + left border |
| `.returns-matrix-cell--bench` | muted text |
| `.inv-drawdown-note` | 12px muted text, border-top |

---

## 6. i18n Keys (add to `es.ts`, `en.ts`, `index.ts` Dict)

### Block 1 — Summary

| Key | TypeScript type | ES | EN |
|---|---|---|---|
| `invSummaryValorTotal` | `string` | `'Valor total'` | `'Total value'` |
| `invSummaryRentabilidad` | `string` | `'Rentabilidad'` | `'Return'` |
| `invSummaryAportaciones` | `string` | `'Aportaciones'` | `'Contributions'` |
| `invSummaryRetenciones` | `string` | `'Retenciones'` | `'Withholdings'` |

### Block 2 — Evolution + period/toggle (shared with Block 3)

| Key | TypeScript type | ES | EN |
|---|---|---|---|
| `invEvolutionTitle` | `string` | `'Evolución de la cuenta'` | `'Account evolution'` |
| `invPeriod1M` | `string` | `'1M'` | `'1M'` |
| `invPeriod3M` | `string` | `'3M'` | `'3M'` |
| `invPeriod6M` | `string` | `'6M'` | `'6M'` |
| `invPeriod1A` | `string` | `'1A'` | `'1Y'` |
| `invPeriodTodo` | `string` | `'Todo'` | `'All'` |
| `invToggleEur` | `string` | `'€'` | `'€'` |
| `invTogglePct` | `string` | `'%'` | `'%'` |
| `invLegendPortfolio` | `string` | `'Tu cartera'` | `'Your portfolio'` |
| `invLegendContributions` | `string` | `'Aportaciones'` | `'Contributions'` |

### Block 3 — Matrix

| Key | TypeScript type | ES | EN |
|---|---|---|---|
| `invMatrixTitle` | `string` | `'Tabla de rentabilidades'` | `'Returns table'` |
| `invMonthENE` | `string` | `'ENE'` | `'JAN'` |
| `invMonthFEB` | `string` | `'FEB'` | `'FEB'` |
| `invMonthMAR` | `string` | `'MAR'` | `'MAR'` |
| `invMonthABR` | `string` | `'ABR'` | `'APR'` |
| `invMonthMAY` | `string` | `'MAY'` | `'MAY'` |
| `invMonthJUN` | `string` | `'JUN'` | `'JUN'` |
| `invMonthJUL` | `string` | `'JUL'` | `'JUL'` |
| `invMonthAGO` | `string` | `'AGO'` | `'AUG'` |
| `invMonthSEP` | `string` | `'SEP'` | `'SEP'` |
| `invMonthOCT` | `string` | `'OCT'` | `'OCT'` |
| `invMonthNOV` | `string` | `'NOV'` | `'NOV'` |
| `invMonthDIC` | `string` | `'DIC'` | `'DEC'` |
| `invMatrixTotal` | `string` | `'TOTAL'` | `'TOTAL'` |
| `invMatrixBenchmark` | `string` | `'BENCHMARK'` | `'BENCHMARK'` |
| `invDrawdownNote` | `(pct: string, eur: string, start: string, end: string) => string` | `` (pct, eur, start, end) => `Pérdida máxima soportada: −${pct} (−${eur}), entre ${start} y ${end}.` `` | `` (pct, eur, start, end) => `Max drawdown: −${pct} (−${eur}), from ${start} to ${end}.` `` |

Note: `invDrawdownNote` receives pre-formatted strings (absolute values). The `−` sign is part of the template.

---

## 7. Backend Types Needed (coordinate with Shuri)

Add to `InvestmentPortfolio` (or `NormalizedPerformance`):

```ts
// Existing — extend returns object:
returns?: {
  // … existing fields …
  pl: number;              // P&L in EUR  (data["return"]["pl"])
  money_return: number;    // Money-weighted return decimal  (data["return"]["money_return"])
  inflows: number;         // Gross deposits  (data["return"]["inflows"])
  tax_outflows: number;    // Withheld taxes, positive  (data["return"]["tax_outflows"])
};

// New top-level fields:
net_amounts_series?: Array<{ date: string; value: number }>;  // cumulative contributions step-series
monthly_returns?: MonthlyReturn[];  // from data["history"] + data["benchmark"]
drawdown?: {
  max_drawdown: number;      // e.g. -0.10050 (negative)
  max_drawdown_eur: number;  // e.g. -1356.93 (negative)
  start_date: string;        // YYYY-MM-DD
  end_date: string;          // YYYY-MM-DD
};
```

---

## 8. What to Keep / Remove in InvestmentsPage.tsx

**Remove:**
- `kpi-grid` div and its 5 `kpi-card` children
- `inv-charts-row` wrapper div
- `inv-chart-card--value` div (and its `AreaChart` content)
- `inv-returns-card` div (and its `returns-table` content)

**Keep unchanged:**
- `inv-account-header` strip
- `inv-chart-card--allocation` div (donut chart) — just moves into `.inv-top-row`
- `inv-holdings-card` div

**AreaChart vs LineChart:** The evolution chart now uses `LineChart + Line` instead of `AreaChart + Area`. Remove `AreaChart`, `Area` from imports if no longer used elsewhere. Add `LineChart`, `Line`.

---

## 9. Null / Loading Behaviour

- `portfolio.monthly_returns == null || length === 0` → skip Block 3 entirely (or show `.state-box` inside `.returns-matrix-card`)
- `portfolio.drawdown == null` → omit `.inv-drawdown-note`
- `portfolio.net_amounts_series == null` → `contribMap` is empty → `contributions: null` for all points → contributions line simply absent from chart (Recharts `connectNulls` won't draw anything, which is correct)
- While loading: use the existing `.state-box` pattern inside each card

---

*End of contract. CSS is live in `index.css`. Build and verify with `cd frontend && npm run build`.*


---

# Vision Build Contract — Returns Table (Tabla de Rentabilidades)
**Author:** Wanda (UX/UI) · **Date:** 2026-07-14 · **For:** Vision (Frontend Engineer)

---

## 1. Placement on the Page

Add the returns card **between `inv-charts-row` and the holdings card** (`inv-holdings-card`). Full-width — no side-by-side with another element.

```
[inv-account-header]
[kpi-grid  ·  5 cards]
[inv-charts-row]          ← evolution chart (3fr) + allocation donut (2fr)
[.card.inv-returns-card]  ← NEW — full-width returns table  ◀
[.card.inv-holdings-card] ← holdings table (unchanged)
```

---

## 2. JSX Tree (exact class names)

```tsx
<div className="card inv-returns-card">
  <h3 className="card-title">{t('invReturnsTitle')}</h3>
  <div className="returns-table">

    {/* Última semana */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsWeek')}</span>
      <span className={`returns-value ${pct(returns.twr_last_week)}`}>
        {fmt(returns.twr_last_week)}
      </span>
    </div>

    {/* Último mes */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsMonth')}</span>
      <span className={`returns-value ${pct(returns.twr_last_month)}`}>
        {fmt(returns.twr_last_month)}
      </span>
    </div>

    {/* Último año */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsYear')}</span>
      <span className={`returns-value ${pct(returns.twr_last_year)}`}>
        {fmt(returns.twr_last_year)}
      </span>
    </div>

    {/* Rentabilidad acumulada (TWR total) */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsTotal')}</span>
      <span className={`returns-value ${pct(returns.twr_total)}`}>
        {fmt(returns.twr_total)}
      </span>
    </div>

    {/* Rentabilidad anualizada (TWR) */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsAnnual')}</span>
      <span className={`returns-value ${pct(returns.twr_annual)}`}>
        {fmt(returns.twr_annual)}
      </span>
    </div>

    {/* TIR / XIRR */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsXirr')}</span>
      <span className={`returns-value ${pct(returns.xirr)}`}>
        {fmt(returns.xirr)}
      </span>
    </div>

    {/* Volatilidad — always neutral color (risk metric, not gain/loss) */}
    <div className="returns-row">
      <span className="returns-label">{t('invReturnsVolatility')}</span>
      <span className="returns-value returns-value--neutral">
        {returns.volatility != null ? `${(returns.volatility * 100).toFixed(2)}%` : '—'}
      </span>
    </div>

  </div>
</div>
```

---

## 3. Helper functions (suggested)

```ts
// fmt: decimal → "+1.23%" string, or "—" for null
function fmt(v: number | null | undefined): string {
  if (v == null) return '—';
  const pct = (v * 100).toFixed(2);
  return v >= 0 ? `+${pct}%` : `${pct}%`;
}

// pct: decimal → CSS modifier class
function pct(v: number | null | undefined): string {
  if (v == null) return '';
  if (v > 0) return 'returns-value--pos';
  if (v < 0) return 'returns-value--neg';
  return ''; // exactly zero: default text color
}
```

---

## 4. i18n Keys (add to ES + EN)

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

---

## 5. CSS Classes Defined (all in `frontend/src/index.css`)

| Class | Purpose |
|-------|---------|
| `.inv-returns-card` | Hook on the `.card` shell — no extra rules, scope for future tweaks |
| `.returns-table` | `flex-direction: column` container of rows |
| `.returns-row` | `flex; space-between` — label + value pair; `border-bottom: 1px solid var(--border)`; last-child: no border |
| `.returns-label` | 13px muted left cell |
| `.returns-value` | 14px/700 tabular-nums right cell — default `var(--text)` |
| `.returns-value--pos` | `var(--income)` green — positive return |
| `.returns-value--neg` | `var(--expense)` red — negative return |
| `.returns-value--neutral` | `var(--text-muted)` — volatility (risk metric, not directional) |

---

## 6. Evolution Chart Emphasis

`inv-value-chart-wrap` height bumped **260px → 300px** (already applied in `index.css`). No JSX change needed — `ResponsiveContainer height="100%"` fills the wrapper automatically.

---

## 7. Null / loading behavior

- Backend returns `null` for a metric that can't be computed → render `—` (en-dash).  
- While portfolio data is loading, show the `.state-box` spinner over the entire card (reuse existing `state-box` pattern inside `.inv-returns-card`).
- No skeleton rows needed — the card itself shows the spinner.

---

## 8. Data source

All values come from `portfolio.returns` object:  
`twr_total`, `twr_last_week`, `twr_last_month`, `twr_last_year`, `twr_annual`, `xirr`, `volatility` — all **decimals** (e.g. `0.0423` = 4.23%). Multiply × 100 before display.

---

## 2026-07-15T06:51:14Z — Fidelity ESPP "Statement-Import" Connector — Feasibility Probe & Architecture

**Coordinators:** Fury (Lead/Architect), Banner (Data/AI), Shuri (Backend)  
**Contributors:** Romanoff (Security flagged), Vision/Wanda (UX noted for Phase 1)  
**Status:** FEASIBILITY CONFIRMED — 3-Phase Plan Draft; awaiting owner scope decisions (Phase 1 details)  
**Context:** Owner requested import capability for quarterly Fidelity ESPP (MSFT) statements (PDF) with daily market-based valuation in EUR. Team conducted feasibility probe: PDF parseable, pricing viable, DB schema designed.

---

## Executive Verdict: ¿Es viable?

**Sí, completamente viable.** ESPP statement import + market-priced holdings is a standard pattern (not novel). The key insight: this requires a new **provider type** (`statement_import`) coexisting with the existing `live_api` type (Indexa). No architectural blocker; all three critical pieces (PDF extraction, market price source, DB persistence) have concrete solutions.

---

## 1. Architecture: Two Provider Types Coexist

### Discovery

The existing `InvestmentProvider` ABC is implicitly designed for live-API connectors (token validation, portfolio fetch, performance metrics). Fidelity ESPP doesn't have an API — it's a PDF-based statement import + market-priced holdings pattern.

**Solution:** Extend the provider abstraction minimally:
- Add `provider_type: str` attribute (`"live_api"` | `"statement_import"`)
- New optional methods: `import_statement(parsed_data, connection_id, db)` and `refresh_price_cache(tickers)`
- `service.py` routes by `provider_type`: live-API calls token-decrypt-fetch; statement-import reads lots from DB + fetches current price

**Output:** Both types produce identical `NormalizedPortfolio` → frontend and aggregation unchanged.

### Generalization

The pattern (statement-import + market-priced holdings) is reusable:
- Any broker without API (CSV/PDF/Excel statements)
- Stock plans (RSU, options) from any employer
- Manual holdings ("I own X shares of Y")
- The "market-priced holding" piece (ticker → daily price → current value) is generic

---

## 2. PDF Extraction — Fidelity ESPP Statement

### Probe Result: ✅ Fully Parseable

- **Text layer:** Real text (not scanned/OCR) generated from stable Fidelity template
- **Pages:** Typically 8–10 pages; target sections: Holdings detail (page 4), Activity/Lots (page 5), Stock Plans metadata (page 8)
- **Fields present & locatable:** Ticker, shares held (cumulative), price at period end, cost basis, per-lot purchase date, price, quantity, ESPP plan metadata
- **Layout:** Stable machine-generated template (Helvetica headers, fixed x-positions for columns) — low risk of format drift

### Recommended Approach: Hybrid (Structured Parse + LLM)

| Approach | Pros | Contras |
|----------|------|---------|
| Pure regex/x-position | No LLM cost; deterministic | Fragile if layout changes; hard to maintain |
| **Hybrid** ← recommended | Extract clean text locally; LLM structured output; review step in wizard = safety net | Small LLM cost (~$0.01–0.05/PDF); owner imports ~4/year so negligible |

The review step (user confirms extracted holdings before saving) mitigates errors.

### New Modules Needed (Banner's Scope)

```
src/finlytics/extraction/
├── espp_schema.py          # ESPPLot + ESPPHoldingSnapshot Pydantic models
├── espp_prompts.py         # build_espp_system_prompt() + build_espp_user_prompt()
└── espp_extractor.py       # extract_espp_holdings(pdf_source) → ESPPHoldingSnapshot
```

**Schema structure (no real values):**
```python
class ESPPLot(BaseModel):
  purchase_date: date
  shares: Decimal              # ≥ 3 decimal places (fractional shares confirmed)
  price_per_share_usd: Decimal
  cost_basis_usd: Decimal      # computed: shares × price

class ESPPHoldingSnapshot(BaseModel):
  statement_period_start: date
  statement_period_end: date
  offering_period_start: date
  offering_period_end: date
  plan_type: str               # e.g. "Section 423 Qualified"
  payroll_deduction_pct: Decimal
  ticker: str                  # "MSFT"
  shares_held: Decimal         # cumulative total
  price_at_close_usd: Decimal
  market_value_usd: Decimal
  cost_basis_total_usd: Decimal
  unrealized_gain_loss_usd: Decimal
  lots: list[ESPPLot]          # per-purchase entries
  contributions_usd: Decimal   # payroll sum for period
```

### Edge Cases & Mitigations

1. **Multi-currency:** Statement is 100% USD; USD→EUR conversion applied externally with daily FX rate.
2. **Fractional shares:** Confirmed present (≥3 decimals); use `Decimal` type always.
3. **Multiple lots per purchase:** A single quarterly ESPP purchase can generate 4+ "Conversion" rows in Activity section, each with distinct price and quantity — extractor must collect all.
4. **Accumulativity:** Holdings section (page 4) shows cumulative total shares; Activity (page 5) shows only this period's deposits. Both needed for complete model.
5. **Dividends & withholding:** Present in statement but not part of Phase 1 objective.

### Effort Estimate (Banner)

~2.75 days: schema (0.5d) + prompts (0.5d) + extractor (0.5d) + PII redaction expansion (0.25d) + tests (1d).

---

## 3. Market Data & Persistence — Backend

### Price Source Decision

**Primary: Stooq** (HTTP GET, CSV response, no auth)
```
GET https://stooq.com/q/d/l/?s=msft.us&d1=YYYYMMDD&d2=YYYYMMDD&i=d  → Date,Open,High,Low,Close,Volume
GET https://stooq.com/q/d/l/?s=eurusd.us&d1=YYYYMMDD&d2=YYYYMMDD&i=d  → FX rate
```
- Fiable para 1 fetch/día sobre 1 ticker. Sin límite de tasa documentado a esta frecuencia. Cero dependencias de auth.

**Fallback: yfinance** (Python lib, no API key)
```python
import yfinance as yf
msft = yf.Ticker("MSFT").history(period="5d")["Close"].iloc[-1]
```
- If Stooq returns error/empty → yfinance as second line.

**Future:** If source requirements evolve, abstraction allows pivot to Alpha Vantage, Finnhub, etc. (25–60 calls/day free tiers).

### DB Schema (Shuri's Scope)

#### `espp_lots` — Tax-lot style tracking

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `connection_id` | FK → investment_connections | |
| `import_run_id` | FK → import_runs | Traces back to source statement |
| `purchase_date` | DATE NOT NULL | ESPP purchase date |
| `shares` | NUMERIC(18,8) NOT NULL | Shares bought (fractional OK) |
| `purchase_price_usd` | NUMERIC(18,4) NOT NULL | Price paid per share |
| `cost_basis_usd` | NUMERIC(18,4) NOT NULL | Total cost (shares × price) |
| `dedup_hash` | VARCHAR(64) UNIQUE | SHA-256 of natural key for idempotence |
| `created_at` | TIMESTAMPTZ | |

Index: `(connection_id, purchase_date)` for valuation queries.

#### `price_cache` — Daily close + FX

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `ticker` | VARCHAR(20) NOT NULL | "MSFT" |
| `price_date` | DATE NOT NULL | |
| `close_price_usd` | NUMERIC(18,4) | |
| `fx_eur_usd` | NUMERIC(18,6) | EUR/USD (1 EUR = X USD) |
| `close_price_eur` | NUMERIC(18,4) | Converted: close_price_usd × fx_eur_usd |
| `source` | VARCHAR(30) | "stooq" | "yfinance" |
| `fetched_at` | TIMESTAMPTZ | |

Constraint UNIQUE: `(ticker, price_date)` — idempotent backfill.

### Refresh Strategy: On-Request + DB Cache

**No background scheduler** (simpler than APScheduler). Flujo en `GET /api/investments/portfolio`:
1. Query `price_cache` for MSFT, most recent row.
2. If `price_date` = today (or last business day) → use cached value.
3. If stale or missing → fetch from Stooq (HTTP ~50ms) → insert `price_cache` row.
4. If Stooq fails → return last known price with `price_stale: true` flag (graceful degradation).
5. Compute: `current_value_eur = SUM(lots.shares) × close_price_eur`.

**Advantages:**
- Zero schedulers; survives Docker restarts (cache in PG, not in-memory).
- Max 1 HTTP call to Stooq per day per ticker.
- Portfolio never completely fails (stale price is better than null).

### Idempotence

Same pattern as transactions: SHA-256 of natural key `(connection_id, purchase_date, shares, purchase_price_usd)`. Inserción with `ON CONFLICT (dedup_hash) DO NOTHING`. Re-import of same PDF → no duplicate rows; counter incremented instead.

**Critical normalization:** Fidelity PDFs may use European number format (comma decimal). Always normalize to float before hashing: `float(str(value).replace(",", ".")` with fixed precision.

### Migration & Integration

**Alembic migration 0014** (design, not yet written):
- Create `espp_lots` and `price_cache` tables.
- **Make `investment_connections.token_enc` NULLABLE** — Indexa continues `NOT NULL` at app layer; Fidelity ESPP omits token.
- No breaking changes to existing live-API providers.

**Provider ABC extensions** (Shuri):
- Add `provider_type: str = "live_api"` (override `"statement_import"` in Fidelity).
- Add `async def import_statement(parsed_data, connection_id, db) → int` (number of lots inserted).
- Add `async def refresh_price_cache(tickers) → None` (optional hook).

**`service.py` logic:**
- Registry: `plugin_id → provider_instance` dict (not hardcoded Indexa).
- Branch by `provider_type`:
- `live_api`: decrypt token → call API → return portfolio.
- `statement_import`: read lots from DB → fetch price → compute portfolio.

---

## 4. Three-Phase Plan (Vertical Slices)

### Phase 1: Import PDF → Save Lots → Display Holdings

**Objective:** Upload Fidelity ESPP statement → see holdings and cost basis.

| Task | Agent |
|------|-------|
| PDF parser + extractors | Banner |
| DB tables + migration | Shuri |
| POST endpoint (`/investments/fidelity/import`) | Shuri |
| FidelityESPPProvider (`provider_type="statement_import"`) | Shuri |
| Register plugin in registry (backend + frontend) | Shuri + Vision |
| Upload wizard (file picker + review extracted data + confirm) | Wanda + Vision |
| Validate PDF privacy handling | Romanoff |
| Unit tests + idempotence | Barton |

**Demo:** "Upload PDF → see holdings with total shares and cost basis."

### Phase 2: Daily Price → Current Value + Gain/Loss

**Objective:** See current value in EUR, updated daily, with gain/loss metrics.

| Task | Agent |
|------|-------|
| Market data service (Stooq primary + yfinance fallback) | Shuri |
| `price_cache` table + on-request fetch | Shuri |
| Portfolio computation: lots × price × FX | Shuri |
| Daily refresh (post–market close) | Rocket (if scheduler added) |
| Fidelity holdings view (KPIs: current value, gain/loss, %) | Vision |
| Valuation + FX tests | Barton |

**Demo:** "See that my MSFT ESPP holdings are worth €X today (+Y% gain)."

### Phase 3: Historical Evolution + Multi-Statement

**Objective:** See investment growth over time; import multiple statements.

| Task | Agent |
|------|-------|
| Backfill MSFT price history (from first lot date) | Shuri |
| Value series: lots × historical price → time series | Shuri |
| Evolution chart (reuse Indexa component) | Vision |
| Multi-statement import + cumulative lots | Shuri + Banner |
| Import history view (uploaded statements, dates) | Wanda + Vision |
| Series + multi-import tests | Barton |

**Demo:** "See a chart of how my MSFT ESPP has grown since first purchase."

---

## 5. Open Questions for Owner

1. **Statement acumulativity:** Does each PDF show all holdings cumulative (replace prior state) or only period deposits (accumulate)?
2. **Currency display:** Show EUR (converted, consistent with Indexa) or USD native + EUR converted side-by-side?
3. **Price timeliness:** Previous-day close sufficient, or need intraday (~15 min delay)?
4. **ESPP discount tracking:** Track the ~15% discount separately from market gain (fiscal relevance)?
5. **Disposals:** Will you ever sell shares (FIFO/LIFO logic) or accumulate-only (simpler model)?
6. **PDF format changes:** If Fidelity updates layout, the review step in the wizard is the safety net. Acceptable?

---

## 6. Privacy & Security Flags for Romanoff

⚠️ PII present in statements: full name, postal address, **participant number** (pattern: `I` + 8 digits = employee ID). 

**Requirements:**
1. **Redact** full name, address, participant number **before any LLM call** — extract locally, parse text, mask PII, then call LLM.
2. **Never store original PDF** in database; only structured extracted data.
3. **Participant number pattern:** Expand `redact_pii()` to match and mask this identifier.
4. Validate that the flow (parse local → redact → LLM with sanitized text) meets security policy.

---

## 7. Risk Summary

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Fidelity PDF layout change | Low–Medium | Parser breaks | Hybrid parse+LLM + review step in wizard |
| yfinance endpoint rotation (Yahoo scraping) | Low | Price fetch fails | Stooq primary; yfinance fallback; abstraction for future swap |
| Multi-lot per purchase edge case | Low | Incorrect total shares | Extractor tested against real statement; review step catches errors |
| Fractional share precision loss | Very Low | Rounding error | Enforce `Decimal` type; fixed-point arithmetic |

---

## Summary Table

| Aspect | Answer |
|--------|--------|
| **Viable?** | ✅ Yes |
| **Insensate?** | ❌ No — standard pattern |
| **New provider type needed?** | ✅ Yes — `statement_import` coexists with `live_api` |
| **Phases** | 3 (import → price → evolution) |
| **DB tables** | `espp_lots`, `price_cache`, migration 0014 |
| **Price source** | Stooq primary + yfinance fallback (no auth) |
| **Extraction strategy** | Hybrid parse + LLM structured output |
| **Effort (design)** | ~2.75d Banner + ~3–4d Shuri + UX/tests in Phase 1 |
| **Owner blockers?** | Scope decisions: Phase 1 depth, sell logic, currency display |


---

## 2026-07-15T09:39:34+02:00 — RECONCILIATION: Fidelity ESPP CSV Refinement Wave

**Purpose:** Consolidate findings from Fury (architecture), Romanoff (security), and Banner (CSV probe). CRITICAL CORRECTION applied.

**CRITICAL CORRECTION — CSV currency:**
Earlier entries (Shuri/first-wave Fury) assumed CSV inputs would be in USD. Banner's empirical probe of the REAL "View open lots.csv" file reveals the footer states EUR. **All values are already in EUR** — cost basis, per-share prices, value fields. Therefore:
- NormalizedLot.currency = "EUR" (hardcoded for MSFT ESPP, not USD)
- Phase 1 (CSV parse + display) requires NO FX conversion; cost basis is final.
- FX conversion is needed ONLY in Phase 2 (live USD market price → EUR valuation). Use USD_EUR lookup only for Phase-2 daily revaluation, not for cost basis.
- This simplifies Phase 1 considerably — no multi-currency math until live prices enter.

**Idempotency refinement — duplicate DO lots:**
Banner identified that multiple dividend-reinvestment (DO) lots can have identical (date, quantity, cost_basis_per_share) tuples. Dedup strategy requires:
- File-level: sha256(file_bytes) for gross dedup (skip re-processing identical CSV)
- Lot-level: sha256(ticker|date|quantity|cost_per_share|share_source|ordinal_within_group) to handle duplicate tuples stably

The ordinal index (0-based within identical groups in CSV order) ensures stable dedup across re-exports.

**Outcome:** CSV-first MVP confirmed. PDF importer deprioritized. Awaiting owner sign-off on Phase 1 UI preference (KPI cards vs table vs both) and revaluation frequency (on-demand vs hourly).

---

# Refinamiento Arquitectónico: Fidelity ESPP — CSV-First + Input Adapters

**Autor:** Fury (Lead/Architect)  
**Fecha:** 2026-07-15T08:51:14+02:00  
**Status:** PROPUESTA — pendiente aprobación del owner  
**Contexto:** El owner respondió a las preguntas de scoping de la arquitectura inicial. Nuevas decisiones: accumulate-only, prev-close pricing, sin descuento ESPP, generic-ready, y MUY IMPORTANTE: puede entregar un CSV de current shares en lugar del PDF.

---

## A. Decisión MVP: CSV es el smallest-thing-that-works

### Veredicto: CSV-first. PDF como Phase posterior (si se necesita).

**Justificación:**

| Criterio | CSV | PDF + LLM |
|----------|-----|-----------|
| Complejidad de parse | Determinista (stdlib Python) | LLM structured output + review |
| PII | Ninguna (sólo datos financieros) | Nombre, dirección, participant number |
| Dependencias nuevas | Ninguna | LLM prompts, redaction, pdfplumber |
| Tiempo de implementación | ~1 día parser + tests | ~2.75 días (Banner) + redaction |
| Riesgo de error | Casi nulo | Layout drift, hallucination |
| Costo operativo | €0 | ~€0.01-0.05 por PDF (despreciable, pero no cero) |

**La pregunta del lead: ¿Cuál es la cosa más pequeña que funciona?**

Si el owner puede exportar un CSV con sus shares actuales, obtenemos la misma información financiera core (ticker, shares, opcionalmente cost basis) sin LLM, sin PII, sin parseo frágil. El PDF es un camino más rico (per-lot purchase dates, offering periods) pero NO es necesario para el objetivo primario: "saber cuánto vale mi ESPP hoy en EUR."

**Decisión:** Phase 1 = CSV adapter. Phase futura = PDF adapter (sólo si el CSV no cubre el detalle que quiere per-lot).

---

## B. Diseño Multi-Input-Source: Input Adapters → Modelo Normalizado

### Pipeline conceptual

```
┌─────────────────────┐     ┌──────────────────────┐     ┌───────────────────┐
│  INPUT ADAPTERS     │     │  NORMALIZED MODEL    │     │  VALUATION        │
│                     │     │                      │     │                   │
│  ┌───────────────┐  │     │  holding_lots table  │     │  shares × price   │
│  │ CSV Adapter   │──┼────▶│  - ticker            │────▶│  × FX rate        │
│  └───────────────┘  │     │  - shares            │     │  = value_eur      │
│                     │     │  - purchase_date     │     │                   │
│  ┌───────────────┐  │     │  - purchase_price    │     │  NormalizedPortfolio
│  │ PDF/LLM       │──┼────▶│  - cost_basis        │     │  (misma salida que│
│  │ Adapter       │  │     │  - currency          │     │   Indexa)         │
│  └───────────────┘  │     │  - source_type       │     │                   │
│                     │     │  - dedup_hash        │     │                   │
│  ┌───────────────┐  │     │                      │     │                   │
│  │ Manual Entry  │──┼────▶│                      │     │                   │
│  │ (futuro)      │  │     │                      │     │                   │
│  └───────────────┘  │     └──────────────────────┘     └───────────────────┘
└─────────────────────┘
```

### Contrato del Input Adapter

Cada adapter debe producir una lista de `NormalizedLot`:

```
NormalizedLot:
  ticker: str           # "MSFT"
  shares: Decimal       # fractional OK
  purchase_date: date | None   # si lo tiene
  purchase_price: Decimal | None  # price per share (moneda original)
  cost_basis: Decimal | None      # total cost
  currency: str         # "USD"
  source_type: str      # "csv" | "pdf" | "manual"
```

El modelo NO es específico de ESPP ni de MSFT — cualquier holding cotizado encaja.

### Ventajas de esta abstracción

1. **Swappable:** Si el CSV cubre todo, nunca necesitamos el PDF adapter.
2. **Extensible:** Un futuro broker (e.g., Interactive Brokers CSV export) → nuevo adapter, misma tabla.
3. **Testable:** Cada adapter se testea en aislamiento contra su formato; valuation se testea contra lots mockeados.

---

## C. Generic-Ready: Qué hacemos genérico AHORA vs diferir

### Genérico AHORA (barato, son campos):

| Aspecto | Implementación |
|---------|---------------|
| Ticker como campo (no hardcode "MSFT") | `holding_lots.ticker VARCHAR(20)` |
| Currency como campo | `holding_lots.currency VARCHAR(3)` |
| price_cache keyed by ticker | `UNIQUE(ticker, price_date)` ya diseñado |
| FX par derivado de currency del lot vs EUR | lookup `{currency}_EUR` |
| source_type en cada lot | Para saber de dónde vino |
| Provider plugin_id genérico | Ya existe en investment_connections |

**Costo: ~0 extra.** Son literalmente campos VARCHAR en vez de hardcodear.

### Diferir (YAGNI hasta que haya 2º caso real):

| Aspecto | Razón para diferir |
|---------|-------------------|
| Multi-broker plumbing (broker-specific parsers registry) | MSFT es el único caso; un `if` es suficiente ahora |
| Disposals / sell logic (FIFO/LIFO) | Owner confirma: nunca vende MSFT |
| Dividend reinvestment tracking | No pedido |
| Tax lot matching / wash sale rules | No aplica en España igual |
| Multi-user multi-broker routing | Single-user app |
| Background scheduler para price refresh | On-request + cache es suficiente |

### Sobre el sketch `espp_lots` de Shuri

La tabla `espp_lots` del diseño original ya es genérica en su estructura — sólo necesita:
1. **Renombrar** `espp_lots` → `holding_lots` (o mantener `espp_lots` como alias semántico si preferimos).
2. **Agregar `currency VARCHAR(3) DEFAULT 'USD'`** (ya implícito en el `_usd` suffix de las columnas, pero hacerlo explícito permite GBP/JPY futuros).
3. **Agregar `source_type VARCHAR(20) DEFAULT 'pdf'`** → para distinguir CSV vs PDF origin.

El campo `ticker` NO necesita cambio — ya es VARCHAR genérico.  
La `price_cache` ya es genérica (keyed by ticker).

**Cambio mínimo:** Renaming + 2 columnas. Schema esencialmente válido.

---

## D. Reutilización del flujo de imports.py existente

### Lo que existe (bank statement flow):

```
POST /api/imports/preview  → parse + LLM extract → PreviewOut (user reviews)
POST /api/imports/confirm  → persist transactions
```

Patrón: upload → parse → preview → user confirms → persist. Idempotencia via dedup_hash.

### Cómo reutilizar para Fidelity:

| Patrón existente | Adaptación para Fidelity |
|-----------------|--------------------------|
| Two-step flow (preview → confirm) | ✅ Mismo concepto: upload CSV → preview lots → confirm save |
| SHA-256 dedup_hash | ✅ Reusar para lots: hash(connection_id, ticker, purchase_date, shares, price) |
| `ImportRun` tracking | ✅ Adaptar: crear `investment_import_runs` (o reusar ImportRun con type field) |
| `_parse_file(bytes, ext)` | ⚠️ Parcialmente: CSV/PDF parsing sí. Pero output es lots, no transactions |
| UPLOAD_DIR (mounted volume) | ⚠️ PDF: decisión de Romanoff (en paralelo). CSV: no necesita almacenarse |
| LLM extraction | ❌ No aplica a CSV. Aplica sólo si se hace PDF adapter en fase posterior |

### Decisión de reutilización:

**Reusar el PATRÓN (preview → confirm + dedup), pero NO las funciones exactas.**

Razón: el output type es diferente (`ExtractedTransaction` vs `NormalizedLot`). Crear endpoints propios en el router de investments:
- `POST /api/investments/fidelity/import/preview` → parse CSV → return lots for review
- `POST /api/investments/fidelity/import/confirm` → persist lots + create import run

Pero seguir la misma disciplina:
1. File upload → parse in memory
2. Return structured preview (user can edit/delete rows)
3. User confirms → persist
4. Dedup hash prevents re-import of same lots
5. Track import run for auditability

### Consistencia con el plugin model:

- Frontend: nueva entrada en `PLUGIN_VIEW_REGISTRY` → `'fidelity-espp': { icon: '📊', name: 'Fidelity ESPP', component: lazy(() => import('./views/FidelityView')) }`
- Backend: `FidelityProvider` implementa `InvestmentProvider` con `provider_type = "statement_import"`
- Connection: row en `investment_connections` con `plugin_id = "fidelity-espp"`, `token_enc = NULL` (no hay API token)
- Routing en service.py: branch por `provider_type` para computar portfolio desde lots + market price

---

## E. Plan por Fases Actualizado

### Phase 1: CSV Import → Lots en DB → Portfolio básico (sin precio live)

**Objetivo:** "Subir CSV → ver mis shares de MSFT con cost basis."

| Tarea | Agente |
|-------|--------|
| CSV adapter (parse → NormalizedLot[]) | Shuri |
| Tabla `holding_lots` + `investment_import_runs` (migration 0014) | Shuri |
| Endpoints preview/confirm (`/investments/fidelity/import/*`) | Shuri |
| `FidelityProvider` (statement_import type) | Shuri |
| Registrar plugin en registry backend + frontend | Shuri + Vision |
| Upload wizard (file picker → preview lots → confirm) | Vision + Wanda |
| Unit tests parser + idempotencia | Barton |

**Demo:** "Subo un CSV → veo 'MSFT: X shares, cost basis $Y'."  
**Sin LLM, sin PII, sin price fetching.** Puro parse + DB + display estático.

### Phase 2: Precio diario → Valor actual en EUR + Gain/Loss

**Objetivo:** "Ver cuánto valen mis acciones HOY en EUR."

| Tarea | Agente |
|-------|--------|
| Market data service (Stooq + yfinance fallback) | Shuri |
| Tabla `price_cache` + on-request fetch | Shuri |
| Cálculo: lots × prev-close × FX → value_eur | Shuri |
| KPIs en FidelityView (valor actual, gain/loss, %) | Vision |
| Tests de valuation + FX | Barton |

**Demo:** "Mis MSFT ESPP valen €X hoy (+Y% ganancia total)."

### Phase 3: Serie histórica + gráfico de evolución

**Objetivo:** "Ver cómo ha crecido mi inversión desde la primera compra."

| Tarea | Agente |
|-------|--------|
| Backfill precio MSFT desde first lot date | Shuri |
| Value series: lots × historical price → time series | Shuri |
| Gráfico de evolución (reusar componente de Indexa) | Vision |
| Tests de series | Barton |

**Demo:** "Gráfico mostrando mi inversión creciendo desde 2019."

### Phase 4 (OPCIONAL): PDF Adapter para detalle por lote

**Sólo si el CSV no da suficiente detalle per-lot.**

| Tarea | Agente |
|-------|--------|
| PDF parser + LLM extraction | Banner |
| PII redaction expandida | Banner + Romanoff |
| PDF adapter que produce NormalizedLot[] | Banner + Shuri |
| Tests contra PDF de ejemplo | Barton |

**Demo:** "Subo el PDF del quarterly statement → veo cada lote con su fecha de compra."

---

## F. Preguntas abiertas para el owner (antes de construir)

### Sobre el CSV (CRÍTICAS para Phase 1):

1. **¿Qué columnas tiene el CSV que exportas?** — Ej: ¿tiene `date, shares, price, total_cost`? ¿O sólo `ticker, total_shares`? Esto define si Phase 1 tiene per-lot detail o sólo posición agregada.

2. **¿El CSV tiene cost basis per lot o sólo total shares?** — Si sólo tiene "500 shares de MSFT", no podemos calcular gain/loss hasta Phase 2 con precio actual. Si tiene cost basis, podemos mostrar gain/loss desde Phase 1.

3. **¿Podrías pegar un ejemplo anonimizado del CSV (2-3 filas)?** — Para diseñar el parser exacto.

### Sobre el display (para Vision/Wanda):

4. **¿Cómo quieres ver el "valor actual"?** — Opciones:
   - KPI cards estilo Indexa (valor, gain/loss, %)
   - Tabla simple de holdings
   - ¿Ambos?

5. **¿EUR only o EUR + USD side-by-side?** — Indexa es EUR-native. MSFT es USD-native. ¿Mostrar sólo la conversión EUR, o también el valor USD?

### Sobre scope futuro:

6. **¿El PDF importer lo necesitas realmente, o el CSV cubre todo?** — Si puedes exportar CSV cada quarter con detalle por lote, el PDF adapter puede que nunca se necesite. Simplifica mucho el proyecto.

7. **¿Tienes otros tickers en mente para "prepared for more things"?** — No para implementar ahora, pero saber si serían otros ESPPs, RSUs, acciones compradas por tu cuenta, ETFs... influye en cómo nombramos las cosas.

---

## Nota: Privacidad (PDF path)

Romanoff está evaluando en paralelo si podemos almacenar el PDF y bajo qué condiciones. El path CSV tiene **cero concern de PII** — no contiene nombres, direcciones ni identificadores personales. Esta es otra razón fuerte para CSV-first.

---

## Resumen de cambios vs arquitectura anterior

| Antes (PDF-first) | Ahora (CSV-first) |
|---|---|
| Phase 1 = PDF + LLM + redaction | Phase 1 = CSV deterministic parse |
| Banner (AI) necesario Phase 1 | Banner NO necesario hasta Phase 4 |
| PII handling en Phase 1 | Zero PII en Phase 1 |
| ~2.75d extractor + tests | ~1d parser + tests |
| `espp_lots` hardcoded | `holding_lots` genérico (ticker, currency como campos) |
| Sell logic TBD | Confirmed: accumulate-only (simplifica) |
| Price: intraday? | Confirmed: prev-day close (simplicísimo) |
| Discount tracking? | Confirmed: NO (defer indefinitely) |

---

# ESPP PDF Storage & Privacy Review — Fidelity Statement

**Fecha:** 2026-07-15T08:51:14+02:00  
**Autor:** Romanoff (Security/Privacy Engineer)  
**Estado:** RECOMENDACIÓN — pendiente de decisión del owner

---

## 1. Comportamiento actual — Evidencia del código

### One-shot endpoint (`POST /api/imports`, `create_import`)
- `file_bytes = await file.read()` — bytes en memoria
- Se llama a `_persist_import_run(session, ..., source_pdf=file_bytes)`
- Dentro de `_persist_import_run` (líneas 116–125 de `api/imports.py`): el PDF **SE ESCRIBE A DISCO** en `settings.upload_dir` = `/app/data/uploads/{account_slug}_{YYYYMM}.pdf`
- **Los extractos bancarios SÍ se persisten al volumen montado hoy mismo.**

### Preview/confirm (`POST /api/imports/preview` + `/confirm`)
- Preview: `file_bytes` se usa solo para parsear; `_persist_import_run` **no se llama** → PDF descartado en memoria
- Confirm: recibe JSON (sin fichero); el PDF ya no existe en ningún lado

### Configuración y volumenes
- `config.py` línea 66: `upload_dir: str = "/app/data/uploads"` — configuración activa, no vestigial
- `docker-compose.yml` línea 28: `${FINLYTICS_DATA_DIR:-./data}:/app/data` — los PDFs aterrizan en `./data/uploads/` en el host
- `.gitignore` línea 38: `/data/` cubierto ✅ — los PDFs nunca entran en git, confirmado con comentario explícito en el gitignore

### `parser.py` y `redaction.py`
- `parse_statement(source: bytes)` — completamente en memoria, sin escrituras a disco propias
- `redact_pii()` cubre hoy: IBANs, PANs, números de cuenta largos
- `redact_pii()` **NO cubre** (aún): nombre completo, dirección postal, número de participante (`I` + 8 dígitos)
- La redacción se aplica solo en el boundary del LLM (`extractor.py`), no en storage

---

## 2. Respuesta a la pregunta del owner

### 2.1 Paridad con extractos bancarios
El owner tiene razón en cuestionar la regla dogmática. **Los extractos bancarios ya se persisten.** Vía el one-shot endpoint, el PDF original se escribe a `./data/uploads/`. Guardar el ESPP PDF en el mismo directorio es **paridad exacta** con el comportamiento actual — no es una nueva superficie de riesgo.

### 2.2 Threat model real — Self-hosted, monousuario

| Amenaza | Extracto bancario (hoy) | ESPP PDF | Diferencial real |
|---------|------------------------|----------|-----------------|
| Host comprometido | Acceso completo a `./data/` | Ídem | Ninguno: quien tiene la máquina tiene todo |
| Backups que incluyan `./data/` | Sí incluido | Ídem | Responsabilidad del usuario |
| Commit accidental a git | `/data/` en `.gitignore` ✅ | Ídem | Ninguno — cubierto |
| Incluido en imagen Docker | No (bind-mount, no `COPY`) | Ídem | Ninguno |
| PII adicional vs. extracto bancario | Nombre + IBAN + transacciones | +Dirección postal + Employee ID (`I`+8 dígitos) + datos plan ESPP | **Moderado:** añade datos de empleo/RRHH vinculados al empleador |

El riesgo incremental frente a los extractos bancarios ya almacenados es **moderado, no severo**. La diferencia material es que el extracto Fidelity vincula explícitamente al usuario con su empleador y plan de compensación variable. En un despliegue self-hosted monousuario sobre volumen local, esto es aceptable. No hay más actores que el propio usuario.

---

## 3. Recomendación ranqueada

### (a) ✅ MI ELECCIÓN — Guardar en el volumen, igual que los extractos bancarios
- **Argumento principal:** parity. La app ya hace esto con extractos bancarios. Hay que ser consistente.
- `/data/` está protegido por `.gitignore` — los PDFs nunca entran en git.
- El PDF no se incluye en la imagen Docker (bind-mount).
- Riesgo aceptable en self-hosted monousuario.
- **Condición no negociable que lo acompaña:** la redacción pre-LLM de la Sección 4 debe implementarse siempre, independientemente de esta decisión de storage.
- **Recomendación operativa:** si el usuario hace backups automáticos a nube (iCloud, Google Drive, OneDrive) del directorio que contiene `./data/`, debe saber que los PDFs estarán en ese backup. No es un blocker, pero sí es algo que el usuario debe conocer.

### (b) Guardar con redacción previa de cabecera PII antes de escribir a disco
- Se redactan nombre/dirección/employee-ID del texto antes de reescribir el PDF (o se guarda solo el texto redactado, no el PDF binario original).
- Mayor carga de ingeniería; valor marginal en self-hosted monousuario.
- Indicado si el scope crece a multi-usuario o a un servicio compartido.

### (c) CSV en lugar de PDF
- Si el owner proporciona un CSV de solo posiciones actuales, el debate desaparece casi por completo.
- El CSV no contiene nombre, dirección, ni employee ID. Ver Sección 5 para la comparativa completa.
- **Limitación:** un CSV de posiciones actuales no incluye lotes históricos (precio de compra por lote, fechas individuales). Si se necesita historial para cálculo de coste base y plusvalías, el PDF sigue siendo necesario.

### (d) Solo en memoria, sin persistencia
- Máxima privacidad, pero rompe la paridad con extractos bancarios.
- Innecesario en el contexto self-hosted actual.

---

## 4. La frontera OpenAI — Requisito no negociable (separable de storage)

Esta decisión es **independiente** de si se guarda o no el PDF. Independientemente del storage, el flujo de extracción ESPP enviará texto al LLM. El `redact_pii()` actual **no cubre** los campos de cabecera del extracto Fidelity.

**Antes de cualquier llamada LLM con texto del extracto ESPP, deben redactarse:**

1. **Número de participante** — patrón `\b[A-Z]\d{6,9}\b` (patrón confirmado en el SKILL de brokerage-statement-parsing)
2. **Nombre completo** — presente en las primeras líneas de la cabecera de página 1
3. **Dirección postal** — presentes en la cabecera de página 1, después del nombre

**Estrategia pragmática:** las páginas 4, 5 y 8 contienen los datos financieros que el LLM necesita (holdings, lotes, ESPP metadata). La cabecera con PII personal está concentrada en la página 1. Una aproximación limpia: redactar las primeras N líneas de la página 1 (donde siempre están nombre y dirección) antes del LLM call, y aplicar el regex de participant number en todo el texto.

**Esta redacción debe implementarse en `redact_pii()` o en un wrapper específico para ESPP antes de que Banner construya la integración.**

---

## 5. CSV vs. PDF — Comparativa PII

| Campo | PDF completo (Fidelity statement) | CSV shares-only |
|-------|-----------------------------------|-----------------|
| Nombre completo | ✅ Presente | ❌ Ausente |
| Dirección postal | ✅ Presente | ❌ Ausente |
| Número de empleado (`I`+8 dígitos) | ✅ Presente | ❌ Ausente |
| Ticker / símbolo bursátil | ✅ Presente | ✅ Presente |
| Shares totales actuales | ✅ Presente | ✅ Presente |
| Precio de cierre del período | ✅ Presente | Opcional |
| Lotes individuales (fecha, precio, qty) | ✅ Presente | ❌ Ausente |
| Coste base por lote | ✅ Presente | ❌ Ausente |
| Período de oferta ESPP + % deducción | ✅ Presente | ❌ Ausente |

**Conclusión:** Si el owner solo necesita "cuántas acciones tengo y cuánto valen hoy", el CSV es suficiente y minimiza drásticamente el PII. Si se necesita el historial de lotes para cálculo de plusvalías, coste base por lote, o visualización del plan ESPP, el PDF es necesario y la opción (a) es la recomendada.

**El path CSV sidesteps casi todo este debate de privacidad.** Para un MVP de inversiones que solo muestre posición actual y valor en EUR, empezar con CSV es la opción más limpia.

---

## 6. Resumen ejecutivo

| Pregunta | Respuesta |
|----------|-----------|
| ¿Los extractos bancarios ya se persisten al volumen? | **Sí**, vía `_persist_import_run` con `source_pdf=file_bytes` |
| ¿`/data/` está en `.gitignore`? | **Sí**, línea 38 con comentario explícito |
| ¿Guardar el ESPP PDF es paridad con extractos bancarios? | **Sí**, misma protección, mismo directorio |
| ¿El riesgo incremental es severo en self-hosted monousuario? | **No**, moderado — datos de empleo vinculados al empleador |
| ¿Qué es no negociable independientemente del storage? | Redacción pre-LLM de nombre/dirección/employee-ID |
| ¿El CSV sidestea el debate? | **Sí, casi por completo**, a costa de perder historial de lotes |

---

# Fidelity "View open lots" CSV — Probe Findings

**Autor:** Banner (Data/AI Engineer)  
**Fecha:** 2026-07-15T09:24:54+02:00  
**Status:** FINDINGS — para Fury (arquitectura), Shuri (schema), Romanoff (PII review)  
**Contexto:** El owner puede exportar un CSV de "View open lots" desde Fidelity en lugar del PDF. Este documento recoge los hallazgos del probe real del fichero.

---

## 1. Estructura del CSV

**Fichero:** `View open lots.csv` (export manual desde Fidelity, nombre con espacios — usar glob al parsear)

| Propiedad | Valor |
|-----------|-------|
| Línea 1 | Cabecera (sin preamble) |
| Filas de datos | **61 lotes fiscales individuales** |
| Separador de campos | Coma `,` (CSV estándar) |
| Separador decimal | Punto `.` (notación americana) |
| Separadores de miles | **Ninguno** |
| Signos `$` | **Ninguno** |
| Campos con comillas | **Ninguno** |
| Valores ausentes | Guión literal `-` |
| Penúltima línea | Línea vacía (solo `,`) — ignorar |
| Última línea (footer) | `The values are displayed in EUR` — **strip antes de parsear** |

---

## 2. Columnas (verbatim, 11 total)

| # | Nombre columna | Tipo Python | Formato | Unidades | Notas |
|---|---------------|-------------|---------|----------|-------|
| 1 | `Date acquired` | `date` | `Mon-DD-YYYY` | — | Fecha settlement del lote; `datetime.strptime(v, "%b-%d-%Y")` |
| 2 | `Quantity` | `Decimal` | 4 decimales | acciones | Compartidas fraccionales; nunca negativo |
| 3 | `Cost basis` | `Decimal` | 2 decimales | **EUR** | Coste total del lote en EUR |
| 4 | `Cost basis/share` | `Decimal` | 2 decimales | **EUR/acción** | Coste por acción; ya convertido a EUR en fecha de adquisición |
| 5 | `Value` | `Decimal` | 2 decimales | **EUR** | Valor de mercado a fecha del export (volátil — no almacenar) |
| 6 | `Gain/loss` | `Decimal` | 2 decimales | **EUR** | P&L no realizado; puede ser negativo |
| 7 | `Sale availability date` | `date \| None` | `Mon-DD-YYYY` o `-` | — | `-` en todos los lotes observados |
| 8 | `Transfer availability date` | `date \| None` | `Mon-DD-YYYY` o `-` | — | `-` en todos los lotes observados |
| 9 | `Grant date` | `date \| None` | `Mon-DD-YYYY` o `-` | — | Solo lotes SP: = inicio del período de oferta ESPP |
| 10 | `Share source` | `str` | `"SP"` o `"DO"` | — | `SP`=ESPP purchase trimestral, `DO`=Dividend reinvestment |
| 11 | `Holding period` | `str` | `"Short"` o `"Long"` | — | Periodo fiscal de retención |

**⚠️ CORRECCIÓN CRÍTICA a arquitectura Fury:**  
El footer confirma `EUR`. `Cost basis/share` NO es el precio USD de compra — es ya el equivalente EUR (convertido por Fidelity al tipo de cambio de la fecha de adquisición). El campo `NormalizedLot.currency` debe ser `"EUR"`, no `"USD"`.

---

## 3. Presencia de campos necesarios para el MVP

| Campo objetivo | Columna CSV | Presente | Notas |
|----------------|-------------|----------|-------|
| Ticker/símbolo | — | ❌ | No hay columna ticker. Hardcodear `MSFT` para MVP |
| Fecha adquisición | `Date acquired` | ✅ | Por lote, formato `Mon-DD-YYYY` |
| Acciones | `Quantity` | ✅ | Por lote, 4 decimales |
| Coste total | `Cost basis` | ✅ | EUR, 2 decimales |
| Coste por acción | `Cost basis/share` | ✅ | EUR, 2 decimales |
| Precio actual | — | ❌ (derivable) | No columna explícita; derivar: `Value / Quantity` a fecha export |
| Valor actual | `Value` | ✅ | EUR; volatile — no almacenar como campo permanente |
| Ganancia/pérdida | `Gain/loss` | ✅ | EUR; recomputar diariamente con precio live |
| Corto/largo plazo | `Holding period` | ✅ | `"Short"` / `"Long"` |
| Tipo de lote | `Share source` | ✅ | `"SP"` / `"DO"` |
| Inicio oferta ESPP | `Grant date` | ✅ (solo SP) | = offering_period_start para lotes ESPP |

**Conclusión: el CSV SOLO es suficiente** para el objetivo MVP + Phases 2-3. Σ(Quantity) = shares totales; cost basis por lote para gain/loss; fechas para serie histórica.

---

## 4. Fecha "as-of"

**No hay fecha "as-of" explícita en el fichero.** Los valores `Value` y `Gain/loss` reflejan el precio de mercado en el momento del export, pero la fecha no se registra en el CSV. El importer debe:
- Capturar el `import_timestamp` como referencia temporal para la snapshot de valor
- O bien ignorar `Value`/`Gain/loss` del CSV (recomputar desde precio live en Phase 2)

---

## 5. Tipos de lote

| Tipo | `Share source` | Frecuencia | Cantidad típica | `Grant date` |
|------|----------------|------------|-----------------|--------------|
| ESPP purchase | `SP` | 1/trimestre, fin de trimestre | Mayor (~5–15 shares) | ✅ = inicio del período de oferta |
| Dividend reinvestment | `DO` | Varios/mes, días 1/2/15/16/17 | Menor (~0.55–1.1 shares) | `-` |

**Lotes duplicados:** múltiples lotes DO en la misma fecha pueden tener valores idénticos `(Date acquired, Quantity, Cost basis/share)`. La clave `(date, quantity, price)` **no es única**. Ver sección 7 para la estrategia de idempotencia.

---

## 6. CSV vs PDF — Veredicto

| Criterio | CSV | PDF + LLM |
|----------|-----|-----------|
| Parse | Determinista, `csv.DictReader` stdlib | pdfplumber + LLM structured output |
| PII | **Ninguna** (0 identifiers de identidad) | Nombre, dirección, participant ID |
| Cobertura lotes | **Todos los lotes históricos** (~18 trimestres SP + DO) | Solo el período del statement (1 quarter) |
| Moneda declarada | EUR (footer) | USD (Fidelity US) |
| Ticker en fichero | ❌ No (hardcodear) | ✅ Explícito |
| Fecha "as-of" explícita | ❌ No | ✅ Statement period end |
| Campos extra (plan, payroll %) | ❌ No | ✅ Sí |
| Esfuerzo Banner | **~1 día** | ~3 días |
| Riesgo de error | Casi nulo | Layout drift, hallucination |
| Dependencias nuevas | Ninguna | LLM, pdfplumber, redaction |

### ✅ RECOMENDACIÓN: CSV como input primario — diferir PDF indefinidamente

El CSV supera al PDF en todos los ejes que importan para el MVP:
- Más lotes históricos (todos, no solo el último quarter)
- Sin PII de identidad → sin necesidad de redacción
- Parse 100% determinista → sin LLM, sin riesgo de alucinaciones
- ~1 día de esfuerzo vs ~3 días

Los únicos campos que el PDF añade (plan name, payroll deduction %, offering period formal, contributions totales) NO son necesarios para el objetivo "cuánto valen mis MSFT hoy en EUR". Phase 4 (PDF adapter) es probablemente **obsoleta**.

---

## 7. Mapping CSV → NormalizedLot (Shuri's model)

```
NormalizedLot:
  ticker          ← hardcode "MSFT" (no hay columna en CSV)
  shares          ← `Quantity`           (Decimal, 4 decimales)
  purchase_date   ← `Date acquired`      (parse: strptime(v, "%b-%d-%Y"))
  purchase_price  ← `Cost basis/share`   (Decimal, EUR, 2 decimales)
  cost_basis      ← `Cost basis`         (Decimal, EUR, 2 decimales)
  currency        ← hardcode "EUR"       (footer: "The values are displayed in EUR")
  source_type     ← hardcode "csv"
  holding_period  ← `Holding period`     ("Short" | "Long")
  share_source    ← `Share source`       ("SP" | "DO")
  grant_date      ← `Grant date`         (date | None; "-" → None)
```

**Campos del CSV a NO almacenar en la tabla de lotes:**
- `Value` — volátil (cambia diariamente con precio de mercado), recomputar en Phase 2
- `Gain/loss` — derivado de `Value - Cost basis`, recomputar en Phase 2
- `Sale/Transfer availability date` — `-` en todos los lotes observados; almacenar como nullable si se quiere

---

## 8. Clave de idempotencia

**Problema:** Lotes DO duplicados (mismo date/quantity/price) → clave simple no es única.

**Estrategia recomendada — dos niveles:**

### Nivel fichero (dedup grueso)
```python
file_hash = sha256(file_bytes).hexdigest()
```
Si mismo hash → skip completo. Evita re-procesar el mismo CSV.

### Nivel lote (dedup fino, para accumulate-only)
```python
# ordinal = índice 0-based dentro de lotes con idénticos
# (date_acquired, share_source, quantity_str, cost_basis_per_share_str)
# en el orden en que aparecen en el CSV

dedup_hash = sha256(
    f"{ticker}|{date_acquired.isoformat()}|{quantity}|{cost_basis_per_share}|{share_source}|{ordinal}"
    .encode()
).hexdigest()
```

Justificación: accumulate-only → los lotes existentes nunca desaparecen; los nuevos siempre se añaden al final del CSV. El `ordinal` dentro del grupo es estable entre re-exports del mismo conjunto.

---

## 9. Esfuerzo estimado

| Tarea | Enfoque | Días (Banner) |
|-------|---------|--------------|
| CSV importer determinista | `csv.DictReader` + Decimal + date parse + footer strip | **~1 día** |
| Tests (fixture anónima, validación columnas, idempotencia) | pytest fixtures | ~0.5 día |
| PDF + LLM adapter | pdfplumber + prompt + extractor + redaction | ~3 días |
| **CSV total** | | **~1.5 días** |
| **PDF total** | | **~3+ días** |

**El CSV no necesita a Banner para Phase 1** (Fury ya asignó el CSV adapter a Shuri). Banner entra en Phase 4 si se construye el PDF adapter.

---

## 10. PII — Flag para Romanoff

| Campo/dato | Tipo PII | Presencia en CSV |
|------------|----------|-----------------|
| Nombre del titular | PII directo | ❌ Ausente |
| Dirección | PII directo | ❌ Ausente |
| Número de cuenta Fidelity | Identifier financiero | ❌ Ausente |
| Participant number (I + 8 dígitos) | Identifier laboral | ❌ Ausente |
| Cantidades de acciones y valores EUR | Datos financieros personales | ✅ Presentes — no exponer |
| Fechas de adquisición + cost basis | Datos financieros personales | ✅ Presentes — no exponer |

**Conclusión para Romanoff:** El CSV tiene riesgo de privacidad **significativamente menor** que el PDF. No contiene identificadores directos de identidad. Los datos financieros personales (acciones, valores) deben tratarse con las mismas protecciones que las transacciones bancarias (no logear, no enviar a terceros), pero no requieren redacción activa antes de su procesamiento.


## Fidelity ESPP — Closing Design Round (2026-07-15)

**Coordinators:** Fury (Lead/Architect), Shuri (Backend), Vision (Frontend)  
**Status:** FINAL DESIGN CONVERGED — awaiting owner sign-off on 6 final questions  
**Context:** Closing refinement round. Currency-of-record = EUR (FINAL). CSV-first MVP confirmed. Endpoint contracts agreed (Vision ↔ Shuri).

---

### A. Currency-of-Record Decision: EUR (FINAL)

- **CSV to owner:** Export in EUR (as already configured)
- **Cost basis stored per lot:** EUR — final value, never recalculated
- **Daily current value:** Σ(shares) × MSFT_close_USD(today) × EUR/USD(today) — derived live
- **Gain/loss:** current_value_EUR − Σ(cost_basis_EUR) — captures stock + FX combined
- **Fallback (if USD only):** Detect CSV footer → store USD + mark currency="USD" → requires historical FX per lot for cost basis in EUR (complexity avoided by requesting EUR)

**Rationale:** Owner thinks in EUR (payroll-FX reality). Cost basis EUR = exactly what left the paycheck. Storing USD is a dead-end (would need historical FX per lot to show EUR cost basis anyway).

---

### B. End-to-End Flow (Numbered Narrative)

1. **Export:** Owner opens Fidelity NetBenefits → "View open lots" → Export CSV (in EUR). Gets file with ~61+ lots (cumulative; grows each quarter).

2. **Upload:** Uploads CSV in app (Finlytics → Inversiones → Fidelity ESPP → "Importar CSV" button). UI shows 3-step wizard.

3. **Preview (deterministic parse):**
   - POST /api/investments/fidelity/import/preview
   - Calculates sha256(file_bytes) → if identical to prior import, warns "already imported" and stops
   - Parses with csv.DictReader: 11 columns, footer strip, date parse (%b-%d-%Y), Decimal
   - Per lot: calculates dedup_hash = sha256(MSFT|date|quantity|cost_per_share|share_source|ordinal)
   - Returns list of new lots (not in DB) + summary of existing (no changes)
   - Frontend: editable table of new lots. Owner reviews and confirms.

4. **Confirm (persist):**
   - POST /api/investments/fidelity/import/confirm
   - Inserts new lots into holding_lots with ON CONFLICT (dedup_hash) DO NOTHING
   - Creates investment_import_run (file_hash, timestamp, lots_added count)
   - Response: summary of imported

5. **Current value (auto-daily, Phase 2):**
   - On each visit to Fidelity page (or once/day on first visit):
   - GET /api/investments/portfolio?plugin=fidelity-espp
   - Backend: queries price_cache for MSFT. If price_date < last_business_day → fetch Stooq (fallback yfinance) → upsert
   - Computes: current_value = Σ(lot.shares) × close_price_usd × fx_eur_usd
   - Computes: gain_loss = current_value − Σ(lot.cost_basis)
   - Returns KPIs: current value EUR, cost basis total EUR, gain/loss EUR, gain/loss %
   - Frontend: KPI cards + lots table with "current value" column recalculated

6. **Historical series (Phase 3):**
   - Endpoint: GET /api/investments/fidelity/evolution?period=ALL (or 1Y, YTD, etc.)
   - Backend:
     - shares_held(date) = step function: sum of lot.shares where lot.purchase_date ≤ date
     - alue(date) = shares_held(date) × MSFT_close_USD(date) × FX_EUR_USD(date)
     - invested(date) = Σ cost_basis_EUR of lots with purchase_date ≤ date (step function)
     - Backfill: on endpoint creation, fetch MSFT + FX history from min(purchase_date) to today → bulk insert into price_cache. Once; then extends daily
   - Returns: [{ date, value_eur, invested_eur }] — daily (business day) granularity
   - Frontend: area/line chart like Indexa — value line + contributions line. Period selector.

---

### C. Final Phases

**Phase 1:** CSV → Lots → Static display (demoable)
- CSV parser + holding_lots table + investment_import_runs table (migration 0014)
- Preview/confirm endpoints
- FidelityProvider (statement_import)
- Plugin registered frontend + backend
- Upload wizard (3 steps: upload → preview table → confirm)
- Value shown = snapshot from CSV (with disclaimer "as of import date")
- Static KPIs: total shares, total cost basis EUR, snapshot value

**Phase 2:** Daily price → Current value EUR live + Gain/Loss
- Market data service (Stooq primary + yfinance fallback)
- price_cache table (migration 0015 or merged with 0014)
- On-request fetch + DB cache (no scheduler)
- Calculation: Σ shares × MSFT_USD × FX = value EUR
- Live KPIs: current value EUR, gain/loss EUR, gain/loss %
- Lots table with "current value" column
- Flag price_stale: true if fetch fails → UI shows "price from yesterday"

**Phase 3:** Historical evolution + chart (Indexa-style)
- Backfill MSFT + EUR/USD from min(lot.purchase_date) to today (Stooq accepts long ranges)
- Time-series endpoint (value + invested per date)
- Evolution chart: value line EUR + invested line EUR
- Period selector: 1M / 3M / 6M / YTD / 1Y / ALL
- Hover tooltip with value + day gain

---

### D. Database Schema (Final)

**espp_lots table:**
- id (PK autoincrement), connection_id (FK), import_run_id (FK)
- 	icker, purchase_date, grant_date (null for DO), shares, cost_basis, cost_basis_per_share
- source_currency ("EUR" or "USD"), share_source ("SP" or "DO"), holding_period
- dedup_hash UNIQUE (SHA-256 of natural key + ordinal)
- created_at (TIMESTAMPTZ default now())
- Index: (connection_id, purchase_date)

**investment_import_runs table:**
- id (PK autoincrement), connection_id (FK)
- source_filename, ile_hash UNIQUE (SHA-256 of raw bytes)
- imported_at (TIMESTAMPTZ default now()), source_currency
- 
um_lots_parsed, 
um_lots_inserted, 
um_lots_skipped
- Index: (connection_id)

**price_history table:**
- id (PK autoincrement)
- 	icker, price_date
- close_usd, x_eur_usd, close_eur (derived: close_usd × fx_eur_usd)
- source ("stooq" | "yfinance" | "csv_snapshot")
- etched_at (TIMESTAMPTZ default now())
- Constraint: UNIQUE (ticker, price_date)

---

### E. Endpoint Contracts (Vision ↔ Shuri)

**1. GET /api/investments/fidelity/kpis** (Phase 1+2+3)
- Returns: { total_shares, invested_eur, current_value_eur, gain_loss_eur, gain_loss_pct, msft_price_usd, usd_eur_rate, last_price_date (ISO), price_stale, as_of_date (ISO) }
- Phase 1: current_value_eur: null, gain_loss_eur: null, gain_loss_pct: null when no price yet
- Phase 2+: populated with live market data

**2. GET /api/investments/fidelity/evolution** (Phase 3)
- Returns: { value_series: [{ date (ISO), value }], contributions_series: [{ date (ISO), value }] }
- Dates as raw ISO "YYYY-MM-DD" (never pre-formatted)
- alue_series: daily portfolio value (shares × price × FX)
- contributions_series: cumulative cost basis step-line (one point per new lot)

**3. GET /api/investments/fidelity/lots** (Phase 3)
- Returns: array of lots with id, purchase_date (ISO), shares, cost_basis_per_share_eur, cost_basis_total_eur, current_value_eur (null until Phase 2), gain_loss_eur, gain_loss_pct, share_source ("SP"|"DO"), grant_date (ISO or null)

---

### F. Open Questions for Owner (Final 6)

1. **Gain: "EUR reality" or "pure stock %"?**  
   Gain/loss combines stock movement + FX effect. Show EUR combined (recommended) or also USD % separately?

2. **Evolution periods: what range?**  
   Show 1M / 3M / 6M / YTD / 1Y / All? Or simplify to YTD / 1Y / All?

3. **Historical granularity: daily enough?**  
   ~1,250 points for 5+ years. Daily (recommended) or weekly?

4. **Lots SP vs DO: distinguish visually?**  
   ~20 ESPP purchases (SP) vs ~40 dividend (DO). Color/group/filter or mixed by date?

5. **Price source without SLA: acceptable?**  
   Stooq + yfinance free, no guarantee. Show last known price with "stale" warning if they fail?

6. **Confirm EUR for CSV?**  
   Export CSV in EUR as configured now. If Fidelity stops offering EUR, we detect and handle USD.

---

### G. Notes for Implementation

- **Shuri** detailing: price_cache schema, backfill strategy, series math, idempotent re-import
- **Vision** detailing: FidelityView component, chart library, KPI cards layout, period UX
- **Fury** (providing this) does NOT duplicate. This doc = what + why; Shuri/Vision = how
- **Banner** not needed until/if Phase 4 PDF adapter (probably never)
- **Romanoff** already validated: CSV = zero PII concern. Done.

---

**No real financial values or identity PII in decisions.md.**  
Currency-of-record FINAL = EUR (Fury).  
Endpoint contract kpis/evolution/lots agreed (Shuri ↔ Vision).

---

## FEEDBACK BATCH 2 — 2026-07-15 (COMPLETED)

**Status:** Completed in Docker; repo code uncommitted pending owner sign-off.

**Agents:** Vision (frontend), Shuri (backend/combined-overview), Rocket (Docker rebuild), Wanda (UX recommendation).

**Deliverables:**

1. **AnalyticsPage Tendencias title** — moved OUT of filter bar into page header (tx-page-header/tx-page-title). ✅ Vision implemented.
2. **Layout.tsx Investments nav** — restored as EXPANDABLE with Indexa/Fidelity sub-items. Routes: `/investments/indexa-capital`, `/investments/fidelity-espp`. Parent still → combined overview. ✅ Vision implemented.
3. **4 Settings groups** — now individually COLLAPSIBLE (buttons + aria-expanded + carets). ✅ Vision implemented; build 0 errors.
4. **Combined-overview provider-card** — id/route now use REAL plugin_ids (indexa-capital/fidelity-espp) so cards link correctly. ✅ Shuri implemented; tests 1120 passed.
5. **Generic-broker + crypto-exchange removed** — from _PLUGIN_REGISTRY. Connectors no longer shows "coming soon". ✅ Shuri implemented; tests updated.
6. **Wanda recommendation: Inicio-vs-Finanzas content split** — PROPOSAL only, awaiting owner decision (see section below).

**Docker:** rebuilt (docker-compose.local.yml), no new migration (head 0015), endpoints verified, new frontend chunks served, running :7777.

---

## 🎨 PROPOSAL: Recomendación: Inicio vs Finanzas — Diferenciación de Pantallas

**Autora:** Wanda (UX/UI Designer)  
**Fecha:** 2026-07-15  
**Estado:** Propuesta — pendiente decisión del owner

### 1. ¿Para qué sirve cada pantalla?

| Pantalla | Propósito | Analogía |
|----------|-----------|----------|
| **Inicio** (`/`) | **Cuadro de mando personal** — snapshot cross-domain (gastos + inversiones) del estado financiero actual. Responde a: *"¿cómo estoy?"* en 3 segundos. | La pantalla de bloqueo del iPhone: lo justo para saber si algo requiere atención. |
| **Finanzas** (`/finances`) | **Centro de operaciones de gasto** — análisis enfocado de ingresos/gastos con filtros completos. Responde a: *"¿en qué me he gastado el dinero este mes?"* con capacidad de drill-down. | La app del banco abierta en la sección de movimientos. |

**Principio clave:** Inicio NO es un dashboard de finanzas reducido. Inicio es el *hub* que abarca TODO (gastos + inversiones). Finanzas es la herramienta de análisis de cash-flow.

### 2. Recomendación: **MOVER + REEMPLAZAR** (ni duplicar, ni simplemente quitar)

**Dirección concreta:**

1. **MOVER a Finanzas:** SpendingByCategory, TopMerchants, CategoryMovers, SpendingHeatmap, y GlobalFilterBar. Finanzas se convierte en el dashboard de análisis de gasto *completo*.

2. **REEMPLAZAR en Inicio:** Sustituir los widgets movidos por contenido cross-domain:
   - KPIs simplificados del mes actual (sin filtros) — gasto del mes, ingreso del mes, neto
   - Nuevo widget de patrimonio/inversiones (valor total de cartera + variación)
   - Accesos rápidos a secciones

3. **NO DUPLICAR:** Cada widget debe tener UN hogar.

**Justificación:** Con la app creciendo a gastos + inversiones, Inicio necesita ser el punto de encuentro de ambos mundos. Hacerlo cross-domain le da un propósito único e insustituible.

### 3. Propuesta de layout — Inicio ideal

```
KPIs del mes (julio 2026) — Gastos, Ingresos, Neto, Ahorro
Patrimonio inversiones — Valor total, ganancia/pérdida, desglose por proveedor
Accesos rápidos — Finanzas, Inversiones, Tendencias, Ajustes
```

### 4. Finanzas ideal propuesto

Con los widgets movidos:
- GlobalFilterBar — filtros
- KpiCards — con filtros aplicados
- SpendingByCategory (donut) + TopMerchants (side by side)
- SpendingHeatmap — full width
- CategoryMovers — full width

### 5. Necesidades de datos / endpoints nuevos

| Necesidad | Endpoint | Estado |
|-----------|----------|--------|
| KPIs mes actual en Inicio | `getOverview({ from, to })` | ✅ Ya existe |
| Patrimonio inversiones en Inicio | `GET /api/investments/combined-overview` | ✅ Ya existe |
| CategoryMovers en Finanzas | `getByCategory()` | ✅ Ya existe |
| SpendingHeatmap en Finanzas | `getHeatmap()` | ✅ Ya existe |

**🎉 No se necesita NINGÚN endpoint nuevo.** Solo:
1. Nuevo componente React `InvestmentSnapshotCard` (compact) para Inicio
2. Reorganizar qué componentes renderiza cada página

### 6. Riesgos y consideraciones

- **Inicio queda "ligero":** Intencionado. Mobile-first = menos scroll, más foco.
- **Pérdida de interactividad en Inicio:** Sin filtros, Inicio es solo lectura. Esto es una feature (reduce carga cognitiva). Para interactuar → Finanzas.
- **Accesos rápidos pueden parecer innecesarios con el sidebar:** En desktop sí. En mobile, donde el sidebar está colapsado, son muy útiles como primer punto de contacto.

### 7. Resumen ejecutivo

> **Inicio = Vistazo rápido cross-domain (gastos del mes + inversiones + shortcuts)**
> **Finanzas = Análisis completo de cash-flow con filtros**
> **Dirección: MOVER widgets de análisis a Finanzas, REEMPLAZAR en Inicio con contenido cross-domain. No duplicar.**
> **Backend: 0 endpoints nuevos necesarios.**

---

## Wanda Decision Drop — Accent Palette Presets (2026-07-16)

**Status:** Implemented after owner approval

### Approved approach

Finlytics now exposes user-selectable accent palettes in **Ajustes → Aplicación → Apariencia**. Presets offered:

- Classic Blue — current default, preserving the existing look
- Emerald
- Violet
- Amber / Warm
- High-Contrast

### Token mechanism

Palette selection sets `data-palette` on `document.documentElement` and swaps only accent tokens in `frontend/src/index.css`:

- `--primary`
- `--primary-rgb`
- `--primary-hover`
- `--primary-bright`
- `--primary-contrast`

Hard-coded blue accent rgba usages now derive from `rgba(var(--primary-rgb), alpha)`, so hover/soft/ring states follow the selected palette. Light/dark theme remains an independent axis via `data-theme`; palette overrides compose with both themes.

### Persistence

Palette persistence follows the existing theme pattern in `ThemeContext`: local React state + `localStorage`. The new key is `finlytics_accent_palette`. `frontend/index.html` applies `data-palette` before React mounts, mirroring the existing `data-theme` FOUC-prevention script.

### Guardrail

Financial semantic colors are not palette-driven. Income/positive green, expense/negative red, category colors, chart colors, and investment instrument palettes remain intact regardless of accent selection.

---

## Merchant Normalization — Slice 1 Implementation & Locked Decisions (2026-07-16)

**Status:** Implemented, Slice 1 complete

**Author:** Shuri  

### Approved schema

- New `merchants` table: canonical display name, unique normalized key, optional default category, JSON-array default tags, active flag, notes, timestamps.
- New `merchant_aliases` table: owner/system/suggested aliases with deterministic match types `exact`, `normalized`, `contains`, `prefix`, `regex`, priority, active flag, notes, timestamps.
- `transactions` keeps raw `merchant` untouched and gains nullable `canonical_merchant_id` plus nullable `merchant_resolution_source`.
- Migration: `alembic/versions/0016_add_merchant_normalization.py`, chained from head `0015_add_portfolio_cache.py`.
- Dedup invariant: `merchant` and `canonical_merchant_id` remain outside `dedup_hash`; dedup remains account/date/amount/description plus optional detail.

### Resolver

Deterministic only, no fuzzy auto-matching:
1. exact alias text match;
2. normalized equality against active canonical merchant keys and alias keys;
3. priority-ordered pattern aliases: prefix, contains, regex.

Normalization: uppercase, trim, collapse whitespace, strip punctuation and diacritics.

### Locked decisions (owner-approved)

1. `default_category_behavior = fill_if_missing`: default category/tags apply only when a transaction lacks category/tags; extractor/user values are never overridden.
2. `auto_create = manual_review`: unknown raw merchants are not auto-created and remain unmatched.
3. `apply_historical = apply_all`: alias changes trigger re-resolution across all historical transactions.
4. `topmerchants_unmatched = mixed_fallback`: `/summary/by-merchant` uses canonical display names when resolved and raw merchant text when unmatched.
5. `matching_aggressiveness = deterministic_only`: no fuzzy matching in Slice 1.

### Minor defaults

- Deleting a canonical merchant means soft deactivation (`active=false` via PATCH), not hard delete.
- Regex aliases are allowed in the API; UI exposure is reserved for a later slice.

### Implementation artifacts

**Backend:** `src/finlytics/db/merchant_normalization.py` (390 lines, deterministic resolver) + `src/finlytics/api/merchants.py` (prefix /merchants, auth-gated).  
**Tests:** `tests/test_merchant_normalization.py` + `tests/api/test_merchants.py` (full suite: 1156 passed, 2 skipped).  
**Endpoints:** GET/POST `/merchants`, PATCH `/merchants/{id}`, POST/DELETE `/merchants/{id}/aliases`, GET `/merchants/unmatched`, POST `/merchants/backfill`.

---


