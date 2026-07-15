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

### 2026-07-15 — Fidelity ESPP Visualization Plan — Reuse Audit + KPI + Evolution Chart (design only, no code)

**Fecha:** 2026-07-15T09:56:45+02:00  
**Tarea:** Ronda de cierre de refinamiento de diseño para el conector Fidelity ESPP MSFT. Sin código.  
**Plan completo en:** `.squad/decisions/inbox/vision-fidelity-espp-visualization.md`

---

#### Reuse Audit — Qué pasa de Indexa a Fidelity sin cambios

Los siguientes elementos del `IndexaView.tsx` y sus CSS asociados se reutilizan **íntegramente** en el nuevo `FidelityView.tsx`:

- **`PluginViewWrapper.tsx`:** Sin cambio alguno. FidelityView monta igual por lazy import.
- **`PLUGIN_VIEW_REGISTRY` en `registry.ts`:** Solo añadir una entrada `'fidelity-espp'`.
- **CSS `inv-*` completo:** `inv-summary-card`, `inv-summary-row`, `inv-summary-value`, `inv-evolution-card`, `inv-evolution-header`, `inv-evolution-controls`, `inv-period-selector`, `inv-period-btn`, `inv-toggle`, `inv-toggle-btn`, `inv-evolution-chart-wrap`, `inv-chart-legend`, `inv-top-row`, `inv-left-col`, `inv-account-header`, `inv-holdings-table-wrap` — todos reutilizables sin cambio CSS.
- **useMemo `evolutionData`:** misma lógica (contribMap, cutoff período, evMode eur/pct, normalización desde start).
- **useMemo `evolutionDomain`:** idéntico.
- **`formatDDMMYYYY`, `niceStep/niceFloor/niceCeil`, `formatRelativeTime`:** copiar (o extraer a `src/utils/dates.ts`).
- **States `evPeriod` / `evMode`:** mismos tipos, misma lógica.
- **`FIXED_PERIODS`:** adaptar a 1M / 3M / 1A (quitar 6M) + años dinámicos desde primer lote + "Todo".
- **Patrón `investmentsFetch` + `auth_required` = plugin state ≠ logout global:** mantener idéntico.
- **Loading / error / empty states:** `.state-box`, `.state-box.error`, `.investments-empty` con CTA al wizard.
- **Tipos `InvestmentConnection`, `ValuePoint`:** reutilizar sin modificar.

**Lo que se OMITE de Indexa (no aplica a cartera mono-holding):**
- Donut de asset class y donut de instrumentos (100% MSFT = sin información en un donut)
- Returns matrix mensual (no aplica a acción cotizada)
- Métricas TWR/MWR/Volatilidad (diferir a Phase 4)

---

#### KPI Cards — 4 cards, sin vanity metrics

1. **Acciones totales MSFT** — `total_shares` con 3 decimales + "MSFT", subtexto con nº de lotes
2. **Invertido** — `invested_eur` (coste base total EUR, ya EUR del CSV — sin conversión FX en Phase 1)
3. **Valor actual** — `current_value_eur` grande; subtexto muestra precio USD × FX usado; "—" en Phase 1
4. **Ganancia / Pérdida** — `gain_loss_eur` + `gain_loss_pct` en dos líneas, colored; "—" en Phase 1

Indicador `price_stale`: si `price_stale === true`, banner ⚠️ en `inv-account-header` con color amber (nueva clase `inv-account-header__updated--stale` — Wanda). No bloquea la UI.

---

#### Evolution Chart — Idéntico a Indexa, con estas diferencias

- Línea 1 "Tu cartera MSFT": valor de mercado diario, `var(--primary)` sólido
- Línea 2 "Invertido": coste base acumulado step-after dashed, `var(--text-muted)` — responde visualmente "¿cuánto gané sobre lo que puse?"
- Period selector: `1M | 3M | 1A | [años] | Todo` (default "Todo")
- `ResponsiveContainer height={360}` — NUNCA `height="100%"` (bug vision-42)
- XAxis `dataKey="date"` raw ISO + `tickFormatter` — nunca pre-formatear en el array
- Tooltip `labelFormatter` = `formatDDMMYYYY`
- Extensión Phase 3 (backlog): dos líneas contributions (SP en azul, DO en verde) si el owner quiere distinguirlas

---

#### Endpoint shapes pedidas a Shuri

**`GET /api/investments/fidelity/kpis`**
→ `{ total_shares, invested_eur, current_value_eur, gain_loss_eur, gain_loss_pct, msft_price_usd, usd_eur_rate, last_price_date (ISO), price_stale, as_of_date (ISO) }`  
Phase 1: `current_value_eur: null, gain_loss_*: null` — frontend muestra "—".

**`GET /api/investments/fidelity/evolution`**
→ `{ value_series: ValuePoint[], contributions_series: ValuePoint[] }` — idéntico al shape de Indexa. Fechas siempre `"YYYY-MM-DD"` raw ISO. `contributions_series` sparse (un punto por lote nuevo = step-after natural).

**`GET /api/investments/fidelity/lots`** (Phase 3)
→ `{ lots: [{ id, purchase_date (ISO), shares, cost_basis_per_share_eur, cost_basis_total_eur, current_value_eur?, gain_loss_eur?, gain_loss_pct?, share_source: "SP"|"DO", grant_date? }] }`

---

#### Tabla de lotes — Phase 3, no MVP

Merece estar en Phase 3 (fecha | fuente SP/DO | shares | coste/share | coste total | valor actual | ganancia €+%). Requiere `price_cache` por lote funcional (Shuri). En Phase 1/2: no se muestra. Sin paginación para MVP (61 lotes caben en scroll).

---

#### Phasing UI

| Fase | UI disponible |
|---|---|
| Phase 1 | KPIs con shares + invested reales; "—" para valor/ganancia; sin gráfico |
| Phase 2 | KPIs completos + `price_stale` indicator; sin gráfico |
| Phase 3 | Gráfico de evolución + tabla de lotes |

Transición transparente: FidelityView detecta campos `null` y adapta el render — no requiere redeploy entre fases.

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

## Learnings

### 2026-07-15 — Fidelity ESPP Full Frontend Implementation

**Fecha:** 2026-07-15T10:20:50+02:00  
**Tarea:** Implementación completa del frontend Fidelity ESPP contra el contrato de endpoint acordado.  

---

#### Estructura final de componentes y archivos

| Archivo | Tipo | Descripción |
|---|---|---|
| `frontend/src/investments/views/FidelityView.tsx` | **NUEVO** | Vista principal Fidelity ESPP (~380 líneas) |
| `frontend/src/investments/registry.ts` | editado | Añadida entrada `'fidelity-espp'` (icono 💼, lazy import) |
| `frontend/src/api/types.ts` | editado | 7 nuevas interfaces: `FidelityKpis`, `FidelityEvolution`, `FidelityLot`, `FidelityLots`, `FidelityImportPreviewLot`, `FidelityImportPreview`, `FidelityImportConfirmResult` |
| `frontend/src/api/client.ts` | editado | 5 nuevas funciones: `getFidelityKpis`, `getFidelityEvolution`, `getFidelityLots`, `fidelityImportPreview`, `fidelityImportConfirm` |
| `frontend/src/i18n/index.ts` | editado | 30 nuevas claves en `Dict` (prefijo `fidelity*`) |
| `frontend/src/i18n/es.ts` | editado | 30 traducciones ES |
| `frontend/src/i18n/en.ts` | editado | 30 traducciones EN |
| `frontend/src/index.css` | editado | `inv-account-header__updated--stale` (amber), `fid-source-badge--sp/--do`, `kpi-sub--pos/--neg` |

---

#### Wiring de endpoints

- `GET /api/investments/fidelity/kpis` → `getFidelityKpis()` → state `kpis`
- `GET /api/investments/fidelity/evolution` → `getFidelityEvolution()` → state `evolution`
- `GET /api/investments/fidelity/lots` → `getFidelityLots()` → state `lots`
- `POST /api/investments/fidelity/import/preview` (multipart) → `fidelityImportPreview(file)`
- `POST /api/investments/fidelity/import/confirm` (multipart) → `fidelityImportConfirm(file)`

Los tres primeros se llaman en `Promise.all` al montar. En caso de error cualquiera, se muestra error state. El confirm envía el mismo archivo CSV de nuevo (multipart, el backend re-parsea e inserta).

---

#### Reutilización de Indexa

- **CSS `inv-*`:** `inv-account-header`, `inv-evolution-card`, `inv-evolution-header`, `inv-evolution-controls`, `inv-period-selector`, `inv-period-btn`, `inv-evolution-chart-wrap`, `inv-chart-legend`, `inv-holdings-card`, `inv-holdings-table-wrap`, `inv-holdings-table`, `inv-pnl--pos/--neg` — todos reutilizados sin cambio CSS.
- **`kpi-grid` / `kpi-card` / `kpi-label` / `kpi-value` / `kpi-sub`:** reutilizados para las 4 KPI cards.
- **Helpers:** `formatDDMMYYYY`, `niceStep`, `niceFloor`, `niceCeil` — copiados directamente de IndexaView.
- **`evolutionData` useMemo:** misma lógica base (contribMap, cutoff período) pero con **carry-forward** de contributions (Fidelity tiene series sparse por lote, no diaria).
- **Modal pattern:** `modal-backdrop`, `modal`, `modal-header`, `modal-body`, `modal-footer`, `inv-wizard__body`, `inv-wizard__success`, `inv-wizard__error-banner` — reutilizados del patrón IndexaWizard.
- **`investmentsFetch` pattern:** `apiFetch` + `_on401` handler — mismo patrón, no logout global.

---

#### Decisiones de implementación

1. **Implementación full en una fase:** El task pedía KPIs + chart + lots + import wizard en un solo PR. La vista detecta campos `null` y muestra "—" transparentemente.
2. **Carry-forward contributions:** La `contributions_series` es sparse (un punto por lote). El `useMemo` evolutionData lleva forward el último valor conocido para que el gráfico `stepAfter` sea correcto sin `connectNulls` gaps.
3. **`isEmpty` condition:** `lots.length === 0 && kpis === null` — si el backend devuelve kpis pero no hay lotes, se muestran las KPI cards (con "—") en lugar del empty state.
4. **No toggle €/%:** Chart siempre en EUR (mono-activo). Sin estado `evMode`.
5. **Period selector:** 1M / 3M / 1A / años dinámicos / Todo (sin 6M vs Indexa).
6. **Nav sub-item:** Automático vía `PLUGIN_VIEW_REGISTRY` — Layout.tsx ya lo gestiona cuando el backend devuelva conexión `fidelity-espp` activa. No requirió tocar Layout.tsx.

---

#### Resultado de build

`npm run build` → `tsc --noEmit && vite build` → **0 errores TypeScript, 0 warnings CSS**.  
`FidelityView-*.js` = 15.25 kB (lazy chunk, correcto). Pre-existing chunk-size warning presente.

### 2026-07-15 — Fidelity Connectors-page entry point

**Fecha:** 2026-07-15T12:05:21+02:00  
**Tarea:** Añadir el entry point de Fidelity ESPP en la página de Connectors para que el owner pueda iniciar la importación de CSV.

**Aprendizaje clave:** Para plugins de tipo statement-import (sin token/OAuth), el flujo correcto es un `Link` directo a la ruta `/investments/<plugin-id>`, **sin** abrir ningún wizard de credenciales (no IndexaWizard). La FidelityView en esa ruta ya contiene el upload wizard del CSV.

**Cambios realizados:**
- `frontend/src/pages/ConnectorsPage.tsx` — añadido `import { Link }` de react-router-dom + función `renderFidelityEsppCard` + branch `plugin.id === 'fidelity-espp'` en `plugins.map` antes del fallback coming-soon.
- `frontend/src/i18n/index.ts` — nueva clave `fidelityImportCta: string`
- `frontend/src/i18n/es.ts` — `fidelityImportCta: 'Importar CSV'`
- `frontend/src/i18n/en.ts` — `fidelityImportCta: 'Import CSV'`

**Comportamiento de la card:**
- Sin conexión activa → card con `<Link className="btn-primary" to="/investments/fidelity-espp">Importar CSV</Link>` (botón habilitado, navega directamente)
- Con conexión activa (`status === 'active'`) → `connector-card--connected` + badge ✓ + Link "Resumen" + botón desconectar

**Build:** `npm run build` → 0 errores TS, 0 warnings CSS. Exit code 0.

### 2026-07-15 — Three frontend owner-feedback fixes

**Fecha:** 2026-07-15T17:27:48+02:00  
**Tarea:** FIX 1 (connector descriptions i18n), FIX 2 (Inicio KPIs last-month-with-data + label/nav), FIX 3 (Finanzas ver-transacciones button).

---

#### FIX 1 — Connector plugin descriptions localized

**Problema:** `InvestmentPlugin.description` viene del backend en inglés; se renderizaba cruda en ConnectorsPage.tsx.

**Solución:** Se añaden claves i18n `invPluginDescIndexa` y `invPluginDescFidelity` en `index.ts`, `es.ts` y `en.ts`. En `ConnectorsPage.tsx` se define un mapa estático `PLUGIN_DESC_KEYS: Partial<Record<string, keyof Dict>>` y la función `pluginDesc(plugin)` que retorna la clave localizada o hace fallback a `plugin.description` para plugins sin clave local. Se aplica a las 6 instancias donde se renderizaba la descripción (tarjeta conectada, error, no conectada de Indexa; conectada y no conectada de Fidelity; card genérico coming-soon).

**Patrón:** `PLUGIN_DESC_KEYS[plugin.id] ? (t[key] as string) : plugin.description` — el cast es seguro porque todas las claves de descripción son `string`.

**Archivos:** `i18n/index.ts`, `i18n/es.ts`, `i18n/en.ts`, `pages/ConnectorsPage.tsx`

---

#### FIX 2 — Inicio KPIs: último mes con datos + etiqueta + navegación

**Problema:** Dashboard.tsx mostraba el mes actual en curso (sin datos completos). El owner trabaja con finanzas del mes cerrado.

**Solución:**
- Se añade `getOverviewMonths(): Promise<string[]>` en `client.ts` → `GET /api/overview/months` → `["YYYY-MM", ...]` sorted ascending. Degradación suave a `[]` en cualquier error.
- Dashboard monta → llama `getOverviewMonths()` → defaultea a `months[months.length - 1]` (último mes con datos). Si la API falla o devuelve lista vacía, fallback al mes anterior al actual (via `defaultRange()`).
- Helper `monthRange(ym)`: "YYYY-MM" → `{ from, to }` para el primer/último día del mes.
- Helper `formatMonthLabel(ym, locale)`: "YYYY-MM" → "Junio 2026" via `Intl.DateTimeFormat` con capitalización del primer carácter.
- Navegación ‹/› constrained al array `availableMonths`; botones deshabilitados en los extremos.
- El mes seleccionado fuerza un nuevo fetch de `getOverview({ from, to })`.
- Los botones de navegación reutilizan las CSS classes `.month-nav-arrow` (ya existentes para StatementsPage) con dimensiones 32×32 inline para el contexto compacto.
- Se reutilizan las claves i18n `datePickerPrevMonth` / `datePickerNextMonth` como `aria-label`.

**⚠️ ASUNCIÓN:** Endpoint `GET /api/overview/months` documentado en la tarea como "likely" pero no encontrado en `shuri/history.md` ni en `decisions/inbox`. Se asumió shape `string[]` (YYYY-MM sorted ascending). Shuri debe implementar este endpoint para que FIX 2 funcione con datos reales; mientras tanto, el fallback al mes anterior garantiza UX operativa.

**Archivos:** `api/client.ts`, `pages/Dashboard.tsx`

---

#### FIX 3 — "Ver transacciones" en FinancesOverviewPage

**Problema:** Inicio tenía un botón "Ver transacciones →" que navegaba a `/transactions`, pero Finanzas no lo tenía.

**Solución:** Añadido `useNavigate` (react-router-dom) a `FinancesOverviewPage.tsx`. Se inserta un `<button className="btn-secondary">` con `{t.btnViewTransactions}` antes del botón de importación en `dashboard-header-actions`, mismo patrón exacto que Inicio.

**Archivos:** `pages/FinancesOverviewPage.tsx`

---

#### Build

`npm run build` → `tsc --noEmit && vite build` → **0 errores TypeScript, 0 warnings CSS**. Chunk-size warning pre-existente. Exit code 0.

## Learnings

### 2026-07-15 — Fidelity ESPP Visualization Plan — Reuse Audit + KPI + Evolution Chart (design only, no code)

**Fecha:** 2026-07-15T09:56:45+02:00  
**Tarea:** Ronda de cierre de refinamiento de diseño para el conector Fidelity ESPP MSFT. Sin código.  
**Plan completo en:** `.squad/decisions/inbox/vision-fidelity-espp-visualization.md`

---

#### Reuse Audit — Qué pasa de Indexa a Fidelity sin cambios

Los siguientes elementos del `IndexaView.tsx` y sus CSS asociados se reutilizan **íntegramente** en el nuevo `FidelityView.tsx`:

- **`PluginViewWrapper.tsx`:** Sin cambio alguno. FidelityView monta igual por lazy import.
- **`PLUGIN_VIEW_REGISTRY` en `registry.ts`:** Solo añadir una entrada `'fidelity-espp'`.
- **CSS `inv-*` completo:** `inv-summary-card`, `inv-summary-row`, `inv-summary-value`, `inv-evolution-card`, `inv-evolution-header`, `inv-evolution-controls`, `inv-period-selector`, `inv-period-btn`, `inv-toggle`, `inv-toggle-btn`, `inv-evolution-chart-wrap`, `inv-chart-legend`, `inv-top-row`, `inv-left-col`, `inv-account-header`, `inv-holdings-table-wrap` — todos reutilizables sin cambio CSS.
- **useMemo `evolutionData`:** misma lógica (contribMap, cutoff período, evMode eur/pct, normalización desde start).
- **useMemo `evolutionDomain`:** idéntico.
- **`formatDDMMYYYY`, `niceStep/niceFloor/niceCeil`, `formatRelativeTime`:** copiar (o extraer a `src/utils/dates.ts`).
- **States `evPeriod` / `evMode`:** mismos tipos, misma lógica.
- **`FIXED_PERIODS`:** adaptar a 1M / 3M / 1A (quitar 6M) + años dinámicos desde primer lote + "Todo".
- **Patrón `investmentsFetch` + `auth_required` = plugin state ≠ logout global:** mantener idéntico.
- **Loading / error / empty states:** `.state-box`, `.state-box.error`, `.investments-empty` con CTA al wizard.
- **Tipos `InvestmentConnection`, `ValuePoint`:** reutilizar sin modificar.

**Lo que se OMITE de Indexa (no aplica a cartera mono-holding):**
- Donut de asset class y donut de instrumentos (100% MSFT = sin información en un donut)
- Returns matrix mensual (no aplica a acción cotizada)
- Métricas TWR/MWR/Volatilidad (diferir a Phase 4)

---

#### KPI Cards — 4 cards, sin vanity metrics

1. **Acciones totales MSFT** — `total_shares` con 3 decimales + "MSFT", subtexto con nº de lotes
2. **Invertido** — `invested_eur` (coste base total EUR, ya EUR del CSV — sin conversión FX en Phase 1)
3. **Valor actual** — `current_value_eur` grande; subtexto muestra precio USD × FX usado; "—" en Phase 1
4. **Ganancia / Pérdida** — `gain_loss_eur` + `gain_loss_pct` en dos líneas, colored; "—" en Phase 1

Indicador `price_stale`: si `price_stale === true`, banner ⚠️ en `inv-account-header` con color amber (nueva clase `inv-account-header__updated--stale` — Wanda). No bloquea la UI.

---

#### Evolution Chart — Idéntico a Indexa, con estas diferencias

- Línea 1 "Tu cartera MSFT": valor de mercado diario, `var(--primary)` sólido
- Línea 2 "Invertido": coste base acumulado step-after dashed, `var(--text-muted)` — responde visualmente "¿cuánto gané sobre lo que puse?"
- Period selector: `1M | 3M | 1A | [años] | Todo` (default "Todo")
- `ResponsiveContainer height={360}` — NUNCA `height="100%"` (bug vision-42)
- XAxis `dataKey="date"` raw ISO + `tickFormatter` — nunca pre-formatear en el array
- Tooltip `labelFormatter` = `formatDDMMYYYY`
- Extensión Phase 3 (backlog): dos líneas contributions (SP en azul, DO en verde) si el owner quiere distinguirlas

---

#### Endpoint shapes pedidas a Shuri

**`GET /api/investments/fidelity/kpis`**
→ `{ total_shares, invested_eur, current_value_eur, gain_loss_eur, gain_loss_pct, msft_price_usd, usd_eur_rate, last_price_date (ISO), price_stale, as_of_date (ISO) }`  
Phase 1: `current_value_eur: null, gain_loss_*: null` — frontend muestra "—".

**`GET /api/investments/fidelity/evolution`**
→ `{ value_series: ValuePoint[], contributions_series: ValuePoint[] }` — idéntico al shape de Indexa. Fechas siempre `"YYYY-MM-DD"` raw ISO. `contributions_series` sparse (un punto por lote nuevo = step-after natural).

**`GET /api/investments/fidelity/lots`** (Phase 3)
→ `{ lots: [{ id, purchase_date (ISO), shares, cost_basis_per_share_eur, cost_basis_total_eur, current_value_eur?, gain_loss_eur?, gain_loss_pct?, share_source: "SP"|"DO", grant_date? }] }`

---

#### Tabla de lotes — Phase 3, no MVP

Merece estar en Phase 3 (fecha | fuente SP/DO | shares | coste/share | coste total | valor actual | ganancia €+%). Requiere `price_cache` por lote funcional (Shuri). En Phase 1/2: no se muestra. Sin paginación para MVP (61 lotes caben en scroll).

---

#### Phasing UI

| Fase | UI disponible |
|---|---|
| Phase 1 | KPIs con shares + invested reales; "—" para valor/ganancia; sin gráfico |
| Phase 2 | KPIs completos + `price_stale` indicator; sin gráfico |
| Phase 3 | Gráfico de evolución + tabla de lotes |

Transición transparente: FidelityView detecta campos `null` y adapta el render — no requiere redeploy entre fases.

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

## Learnings

### 2026-07-15 — Fidelity ESPP Full Frontend Implementation

**Fecha:** 2026-07-15T10:20:50+02:00  
**Tarea:** Implementación completa del frontend Fidelity ESPP contra el contrato de endpoint acordado.  

---

#### Estructura final de componentes y archivos

| Archivo | Tipo | Descripción |
|---|---|---|
| `frontend/src/investments/views/FidelityView.tsx` | **NUEVO** | Vista principal Fidelity ESPP (~380 líneas) |
| `frontend/src/investments/registry.ts` | editado | Añadida entrada `'fidelity-espp'` (icono 💼, lazy import) |
| `frontend/src/api/types.ts` | editado | 7 nuevas interfaces: `FidelityKpis`, `FidelityEvolution`, `FidelityLot`, `FidelityLots`, `FidelityImportPreviewLot`, `FidelityImportPreview`, `FidelityImportConfirmResult` |
| `frontend/src/api/client.ts` | editado | 5 nuevas funciones: `getFidelityKpis`, `getFidelityEvolution`, `getFidelityLots`, `fidelityImportPreview`, `fidelityImportConfirm` |
| `frontend/src/i18n/index.ts` | editado | 30 nuevas claves en `Dict` (prefijo `fidelity*`) |
| `frontend/src/i18n/es.ts` | editado | 30 traducciones ES |
| `frontend/src/i18n/en.ts` | editado | 30 traducciones EN |
| `frontend/src/index.css` | editado | `inv-account-header__updated--stale` (amber), `fid-source-badge--sp/--do`, `kpi-sub--pos/--neg` |

---

#### Wiring de endpoints

- `GET /api/investments/fidelity/kpis` → `getFidelityKpis()` → state `kpis`
- `GET /api/investments/fidelity/evolution` → `getFidelityEvolution()` → state `evolution`
- `GET /api/investments/fidelity/lots` → `getFidelityLots()` → state `lots`
- `POST /api/investments/fidelity/import/preview` (multipart) → `fidelityImportPreview(file)`
- `POST /api/investments/fidelity/import/confirm` (multipart) → `fidelityImportConfirm(file)`

Los tres primeros se llaman en `Promise.all` al montar. En caso de error cualquiera, se muestra error state. El confirm envía el mismo archivo CSV de nuevo (multipart, el backend re-parsea e inserta).

---

#### Reutilización de Indexa

- **CSS `inv-*`:** `inv-account-header`, `inv-evolution-card`, `inv-evolution-header`, `inv-evolution-controls`, `inv-period-selector`, `inv-period-btn`, `inv-evolution-chart-wrap`, `inv-chart-legend`, `inv-holdings-card`, `inv-holdings-table-wrap`, `inv-holdings-table`, `inv-pnl--pos/--neg` — todos reutilizados sin cambio CSS.
- **`kpi-grid` / `kpi-card` / `kpi-label` / `kpi-value` / `kpi-sub`:** reutilizados para las 4 KPI cards.
- **Helpers:** `formatDDMMYYYY`, `niceStep`, `niceFloor`, `niceCeil` — copiados directamente de IndexaView.
- **`evolutionData` useMemo:** misma lógica base (contribMap, cutoff período) pero con **carry-forward** de contributions (Fidelity tiene series sparse por lote, no diaria).
- **Modal pattern:** `modal-backdrop`, `modal`, `modal-header`, `modal-body`, `modal-footer`, `inv-wizard__body`, `inv-wizard__success`, `inv-wizard__error-banner` — reutilizados del patrón IndexaWizard.
- **`investmentsFetch` pattern:** `apiFetch` + `_on401` handler — mismo patrón, no logout global.

---

#### Decisiones de implementación

1. **Implementación full en una fase:** El task pedía KPIs + chart + lots + import wizard en un solo PR. La vista detecta campos `null` y muestra "—" transparentemente.
2. **Carry-forward contributions:** La `contributions_series` es sparse (un punto por lote). El `useMemo` evolutionData lleva forward el último valor conocido para que el gráfico `stepAfter` sea correcto sin `connectNulls` gaps.
3. **`isEmpty` condition:** `lots.length === 0 && kpis === null` — si el backend devuelve kpis pero no hay lotes, se muestran las KPI cards (con "—") en lugar del empty state.
4. **No toggle €/%:** Chart siempre en EUR (mono-activo). Sin estado `evMode`.
5. **Period selector:** 1M / 3M / 1A / años dinámicos / Todo (sin 6M vs Indexa).
6. **Nav sub-item:** Automático vía `PLUGIN_VIEW_REGISTRY` — Layout.tsx ya lo gestiona cuando el backend devuelva conexión `fidelity-espp` activa. No requirió tocar Layout.tsx.

---

#### Resultado de build

`npm run build` → `tsc --noEmit && vite build` → **0 errores TypeScript, 0 warnings CSS**.  
`FidelityView-*.js` = 15.25 kB (lazy chunk, correcto). Pre-existing chunk-size warning presente.

### 2026-07-15 — Fidelity Connectors-page entry point

**Fecha:** 2026-07-15T12:05:21+02:00  
**Tarea:** Añadir el entry point de Fidelity ESPP en la página de Connectors para que el owner pueda iniciar la importación de CSV.

**Aprendizaje clave:** Para plugins de tipo statement-import (sin token/OAuth), el flujo correcto es un `Link` directo a la ruta `/investments/<plugin-id>`, **sin** abrir ningún wizard de credenciales (no IndexaWizard). La FidelityView en esa ruta ya contiene el upload wizard del CSV.

**Cambios realizados:**
- `frontend/src/pages/ConnectorsPage.tsx` — añadido `import { Link }` de react-router-dom + función `renderFidelityEsppCard` + branch `plugin.id === 'fidelity-espp'` en `plugins.map` antes del fallback coming-soon.
- `frontend/src/i18n/index.ts` — nueva clave `fidelityImportCta: string`
- `frontend/src/i18n/es.ts` — `fidelityImportCta: 'Importar CSV'`
- `frontend/src/i18n/en.ts` — `fidelityImportCta: 'Import CSV'`

**Comportamiento de la card:**
- Sin conexión activa → card con `<Link className="btn-primary" to="/investments/fidelity-espp">Importar CSV</Link>` (botón habilitado, navega directamente)
- Con conexión activa (`status === 'active'`) → `connector-card--connected` + badge ✓ + Link "Resumen" + botón desconectar

**Build:** `npm run build` → 0 errores TS, 0 warnings CSS. Exit code 0.

## Learnings

### 2026-07-15 — Fidelity UI Polish: File Picker + SP/DO Tooltips

**Fecha:** 2026-07-15T12:27:01+02:00  
**Tarea:** Dos fixes de polish en el wizard de Fidelity ESPP.

---

#### FIX 1 — Patrón de upload reutilizado: `backup-file-label`

El patrón estándar del proyecto para file pickers estilizados es el de **`BackupPage.tsx`** (`frontend/src/pages/BackupPage.tsx`):

```tsx
<label className="backup-file-label">
  <span className="btn-primary">Texto del botón</span>
  <input
    ref={fileInputRef}
    type="file"
    accept="..."
    className="backup-file-input"
    onChange={handleFileChange}
  />
</label>
```

- `.backup-file-label` — `display: inline-flex; cursor: pointer;` (en index.css ~2564)
- `.backup-file-input` — `position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none;` — input nativo visualmente oculto, accesible
- `.btn-primary` dentro de un `.backup-file-label` recibe border/color override para look outline (jerarquía export > import)
- Nombre del archivo seleccionado se muestra con `{file && <span className="kpi-sub">{file.name}</span>}` a la derecha
- `resetImport()` también resetea `fileInputRef.current.value = ''` para permitir re-selección del mismo archivo

**No usar `<input type="file">` raw en la UI del wizard** — siempre wrappar con este patrón.

---

#### FIX 2 — Tooltips SP/DO: `title` + `aria-label` en el badge

Enfoque elegido: atributo `title` nativo (tooltip del sistema) + `aria-label` en el `<span>` del badge.

```tsx
<span
  className={`fid-source-badge fid-source-badge--${lot.share_source.toLowerCase()}`}
  title={lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip}
  aria-label={lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip}
>
  {lot.share_source}
</span>
```

Claves i18n añadidas en `index.ts` / `es.ts` / `en.ts`:
- `fidelitySourceSpTooltip` → ES: "SP – Compra ESPP" / EN: "SP – ESPP purchase"
- `fidelitySourceDoTooltip` → ES: "DO – Dividendo reinvertido" / EN: "DO – Dividend reinvestment"

Aplicado en **ambos** lugares donde aparece el badge: tabla de lotes principal + tabla de preview del wizard de importación.

---

## Learnings

### 2026-07-15 — Fidelity lots table: tooltip portal, sortable columns, pagination (vision-37)

**Contexto:** Tres mejoras UX en `FidelityView.tsx` pedidas por David.

#### Tooltip patrón reutilizado (IndexaView `createPortal` + `openTip`)

Se descartó el atributo `title=` nativo (no visible para el dueño) y se migró al **patrón `openTip` de IndexaView** (`frontend/src/investments/views/IndexaView.tsx` ~línea 951):

```tsx
// Estado en el componente:
const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)

// En el badge (tabla de lotes Y preview de importación):
<span
  className={`fid-source-badge fid-source-badge--${lot.share_source.toLowerCase()}`}
  tabIndex={0}
  onMouseEnter={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: ..., x: r.left + r.width / 2, y: r.top }) }}
  onFocus={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ ... }) }}
  onMouseLeave={() => setOpenTip(null)}
  onBlur={() => setOpenTip(null)}
>
  {lot.share_source}
</span>

// Portal al final del componente (antes de </main>):
{openTip && createPortal(
  <div role="tooltip" style={{ position: 'fixed', left: openTip.x, top: openTip.y - 10, transform: 'translate(-50%, -100%)', zIndex: 4000, ... }}>
    {openTip.text}
  </div>,
  document.body,
)}
```

Ventaja: `position: fixed` en un portal escapa el `overflow: hidden` de la tabla; se ve siempre.

#### Columnas ordenables (FIX 2)

- Tipo `LotsSortCol = 'date' | 'source' | 'shares' | 'costPerShare' | 'totalCost' | 'currentValue' | 'gain' | 'gainPct'`
- Estado: `lotsSortCol` (default `'date'`) + `lotsSortDir` (default `'desc'`)
- `sortedLots` useMemo con `switch` tipado; nulls siempre al final sin importar la dirección (retorno incondicional `1` / `-1` antes del `dir *`)
- `handleLotsSortClick` resetea la página a 0 al cambiar de columna
- `LotsSortArrow` component interno igual que IndexaView (retorna `▲`/`▼` o null)
- Headers `th` con `inv-th-sortable`, `inv-th-sort-active`, `aria-sort`, `tabIndex={0}`, `onKeyDown`
- La columna "Ganancia" se **dividió en dos**: `fidelityColGain` (€) + `fidelityColGainPct` (%) — permite ordenar cada métrica por separado

#### Paginación (FIX 3)

- `LOTS_PAGE_SIZE = 15` — constante a nivel de módulo
- Estado `lotsPage` (número de página base-0), se resetea a 0 en cada cambio de sort
- `pageLots` useMemo = `sortedLots.slice(page * 15, (page+1) * 15)`
- Controles reutilizando la clase `.pagination` existente (CSS en `index.css` línea 751) + claves i18n `t.tablePrev` / `t.tableNext` / `t.tablePaginationInfo`
- Los controles solo se renderizan si `lotsPageCount > 1` (evita controles innecesarios con pocos lotes)

#### i18n añadido

- `fidelityColGain` → renombrado a "Ganancia €" / "Gain €"
- `fidelityColGainPct` → "Ganancia %" / "Gain %" (nuevo en `index.ts`, `es.ts`, `en.ts`)

**Build:** `npm run build` (tsc --noEmit + vite build) → 0 errores TypeScript ✅

---

### 2026-07-15 — Nav restructure + Finanzas overview + Investments combined + Settings 4-group + Tendencias title fix

**Fecha:** 2026-07-15T14:10:06+02:00
**Tarea:** Reestructuración completa de la navegación per spec de Wanda (`wanda-nav-restructure-overviews.md`).
**Spec implementada al 100%:** nav tree, 2 páginas overview, settings grouping, title fix.
**Paso 7 (Indexa cache):** omitido — `shuri-indexa-portfolio-cache.md` no existe aún.

#### Archivos modificados

| Archivo | Cambio |
|---|---|
| `frontend/src/components/Layout.tsx` | Nav restructurado: Finanzas expandible (💳 + acordeón), Inversiones directo (NavLink), Ajustes con 4 grupos. Eliminados imports de `getConnections`, `InvestmentConnection`, `PLUGIN_VIEW_REGISTRY` (ya no necesarios). |
| `frontend/src/App.tsx` | Añadida ruta `finances` → `FinancesOverviewPage`, import de `FinancesOverviewPage`. |
| `frontend/src/pages/FinancesOverviewPage.tsx` | **NUEVO** — página overview de Finanzas: GlobalFilterBar + KpiCards + SpendingByCategory + TopMerchants. Patrón de data-fetching idéntico a Dashboard pero sin heatmap/movers/globalOverview/importModal/toast. |
| `frontend/src/pages/InvestmentsLandingPage.tsx` | **RECONSTRUIDO** — combined overview: KPI strip (3 cards) + 2 donuts (Recharts, patrón cat-chart-layout) + provider cards. Consume `GET /api/investments/combined-overview`. |
| `frontend/src/pages/AnalyticsPage.tsx` | Title fix: `analytics-page-title` → `tx-page-title` (22px/700 = estándar). |
| `frontend/src/api/types.ts` | Añadidas 4 interfaces: `CombinedOverviewProviderSlice`, `CombinedOverviewAssetClassSlice`, `CombinedOverviewProvider`, `CombinedOverview`. |
| `frontend/src/api/client.ts` | Añadida `getCombinedOverview(): Promise<CombinedOverview>` + import del tipo. |
| `frontend/src/i18n/index.ts` | +10 claves: `navFinances`, `financesOverviewTitle`, `settingsGroupRules`, `settingsGroupSystem`, `settingsGroupApp`, `invCombinedTitle`, `invCombinedTotalValue`, `invCombinedTotalGain`, `invCombinedByProvider`, `invCombinedByAssetClass`. |
| `frontend/src/i18n/es.ts` | +10 traducciones ES. |
| `frontend/src/i18n/en.ts` | +10 traducciones EN. |
| `frontend/src/index.css` | +CSS nuevo: `.inv-kpi-strip`, `.inv-kpi-card` + subclases, `.inv-provider-cards`, `.inv-provider-card` + subclases. |

#### Decisiones técnicas

1. **`isOnFinances` multi-path check:** `['/finances', '/transactions', '/analytics', '/statements'].some(p => location.pathname.startsWith(p))` — abre el acordeón en cualquier sub-ruta del grupo.
2. **Layout.tsx simplificado:** Se eliminó el `useEffect` de `getConnections()` y toda la lógica de `connectedPlugins`. La nav de Inversiones ya no muestra sub-links de plugins — la navegación a detalle se hace desde InvestmentsLandingPage.
3. **FinancesOverviewPage:** Usa `previousCalendarMonth` para comparativa; pasa `refreshKey={0}` a TopMerchants (sin importación en esta página, el refreshKey es constante).
4. **InvestmentsLandingPage:** Error de endpoint = empty state (CTA a Conectores), igual que `providers.length === 0`. El endpoint no existe aún (Shuri lo construye), así que la página mostrará el empty state hasta que esté disponible.
5. **CSS `inv-kpi-card`:** No existía en index.css (Wanda lo referenció como "existente" pero no estaba). Creado con mismo patrón que `.kpi-card`.

#### Dependencia backend pendiente

- `GET /api/investments/combined-overview` — Shuri lo construye en paralelo con el shape definido en `wanda-nav-restructure-overviews.md §B`. Hasta entonces, `/investments` mostrará el empty state.

**Build:** `npm run build` → 0 errores TypeScript ✅ · Chunk-size warning pre-existente.

### 2026-07-15 — Combined overview nullability: crash en caso precio-no-disponible

**Fecha:** 2026-07-15T14:10:06+02:00  
**Tarea:** Bugfix nullability contract mismatch en `InvestmentsLandingPage` + `types.ts`.

#### Problema

`CombinedOverviewOut` (backend) devuelve `total_invested_eur`, `total_gain_loss_eur`, `total_gain_loss_pct` como `float | None` (null cuando el precio no está disponible / stale). `ProviderCardOut` devuelve `value_eur`, `gain_loss_eur`, `gain_loss_pct` como `float | None`. Los tipos de frontend los declaraban como `number` (no-null), y el componente llamaba directamente `.toFixed()` o `>= 0` sobre ellos → `TypeError: null.toFixed()` en producción cuando un proveedor no tiene precio disponible.

#### Fix

**`frontend/src/api/types.ts`:**
- `CombinedOverview.total_invested_eur`, `.total_gain_loss_eur`, `.total_gain_loss_pct` → `number | null`
- `CombinedOverviewProvider.value_eur`, `.gain_loss_eur`, `.gain_loss_pct` → `number | null`
- `total_value_eur`, los slices `value_eur`/`pct` de `CombinedOverviewProviderSlice`/`AssetClassSlice` → siguen siendo `number` (el backend los garantiza siempre).

**`frontend/src/pages/InvestmentsLandingPage.tsx` — 6 guards añadidos:**

| Uso | Guard |
|---|---|
| `gainLossCls` (línea ~85) | `total_gain_loss_eur == null` → clase `''` (neutral) |
| KPI `total_invested_eur` (línea ~117) | `== null` → `'—'` |
| KPI `total_gain_loss_eur` (línea ~122) | `== null` → `'—'` |
| KPI `total_gain_loss_pct` + `.toFixed()` (línea ~125) | `== null` → `'—'` |
| Provider card `value_eur` (línea ~289) | `== null` → `'—'` |
| Provider card `gain_loss_eur` / `gain_loss_pct` + `.toFixed()` (líneas ~291-293) | any null → `'—'` en bloque |
| Provider card `gainCls` (línea ~276) | `gain_loss_eur == null` → clase `''` (neutral) |

Los donuts y tablas de allocación usan `by_provider[].value_eur` y `by_asset_class[].value_eur` (siempre presentes) → **no afectados**.

**Build:** `npm run build` → `tsc --noEmit && vite build` → **0 errores TypeScript ✅** · Chunk-size warning pre-existente.

## Learnings

### 2026-07-15 — Owner feedback: tres fixes (Tendencias header, Inversiones sub-items, Settings colapsable)

**Fecha:** 2026-07-15T15:54:01+02:00

#### Tendencias page-header structure
El título de AnalyticsPage estaba dentro del dashboard-header wrapper junto con GlobalFilterBar, causando que apareciera renderizado DENTRO de la barra de filtros. Fix: eliminar el div dashboard-header, añadir <div className="tx-page-header"><h1 className="tx-page-title"> ANTES del GlobalFilterBar — patrón idéntico a TransactionsPage. Regla: el título siempre va en su propio header div, separado del toolbar/filter-bar.

#### Investments nav restaurado con sub-items
Inversiones volvió de NavLink directo a sección expandible (sidebar-section). El botón padre navega a /investments Y alterna expansión. Sub-items generados dinámicamente desde getConnections() filtrado por status==='active', cruzado con PLUGIN_VIEW_REGISTRY para icon+name. Ruta de sub-item: /investments/${conn.plugin_id}. Caret solo visible si hay plugins conectados. Imports: getConnections (api/client), PLUGIN_VIEW_REGISTRY (investments/registry), InvestmentConnection (api/types).

#### Grupos colapsables en Settings accordion
Convertidos los 4 grupos (Datos/Reglas/Sistema/App) de <span className="sidebar-group-label"> a <button className="sidebar-group-label sidebar-group-toggle"> con aria-expanded y sidebar-arrow. Estados: sgData/sgRules/sgSystem/sgApp (useState(true) — expandidos por defecto). CSS nuevo: .sidebar-group-toggle con display:flex, justify-content:space-between, width:100%, background:none, border:none, cursor:pointer. Build: 0 TS errors.

### 2026-07-15 — Inicio/Finanzas split + InvestmentSnapshotCard + ImportSourcePicker + batch fixes

**Fecha:** 2026-07-15T16:20:19+02:00  
**Tarea:** Batch de 5 items de feedback del owner (DrDonoso). Implementación de la propuesta MOVE+REPLACE de Wanda para Inicio vs Finanzas.

---

#### Items implementados

| # | Item | Cambios |
|---|---|---|
| 1 | Quitar "Resumen" de Fidelity en Connectors | `ConnectorsPage.tsx`: eliminado `<Link to="/investments/fidelity-espp">` en estado connected. Card connected muestra solo badge + desconectar. |
| 2 | Settings groups collapsed por defecto | `Layout.tsx`: `sgData/sgRules/sgSystem/sgApp` → `useState(false)` (antes `true`). |
| 3 | Split Inicio/Finanzas (MOVE+REPLACE) | Dashboard reescrito como hub cross-domain; FinancesOverviewPage ampliado con análisis completo. |
| 4 | Import en Finanzas | `FinancesOverviewPage.tsx` — añadidos `ImportLauncher` + `ImportModal` + `refreshKey` + `toast`. |
| 5 | Inicio Import → picker multi-fuente | Botón Importar abre `ImportSourcePicker` (data-driven vía `import_route`). |

---

#### Inicio (Dashboard.tsx) — ahora hub cross-domain

**Quitado:** `GlobalFilterBar`, `SpendingByCategory`, `TopMerchants`, `SpendingHeatmap`, `CategoryMovers`, todo estado de filtros, fetches de previous-period, unfiltered-overview, `getByCategory`.

**Añadido:**
- `currentMonthRange()` helper — siempre muestra el mes en curso (a diferencia de `defaultRange()` que devolvía el mes anterior).
- `InvestmentSnapshotCard` — nuevo componente abajo del dashboard-header.
- `ImportSourcePicker` — modal con fuentes de importación antes de abrir el file picker.

**Mantenido:** `KpiCards` (compact, sin `previousOverview` — vista simplificada), botón "Ver transacciones", botón "Importar" (ahora abre el picker).

---

#### Finanzas (FinancesOverviewPage.tsx) — análisis completo de cash-flow

**Añadido:** `SpendingHeatmap`, `CategoryMovers`, `ImportLauncher`, `ImportModal`, `refreshKey`, `toast`, botón "Importar" en `dashboard-header-actions`. El `refreshKey` dispara re-fetch de overview + byCategory al importar (igual que Dashboard).

**Mantenido:** `GlobalFilterBar`, `KpiCards` con `previousOverview`, `SpendingByCategory`, `TopMerchants` — con cross-filter completo.

---

#### Nuevos componentes

**`InvestmentSnapshotCard.tsx`** (`src/components/`)
- Llama `getCombinedOverview()` al montar.
- Estados: loading / error / empty (sin providers → "Sin inversiones conectadas" + Link a /investments) / populated (total_value_eur + breakdown por provider).
- Muestra "—" si `value_eur === null` (helper `fmtEur`).
- CSS: clases `inv-snapshot-*` añadidas al final de `index.css`.
- Link "Ver inversiones →" siempre visible en el header.

**`ImportSourcePicker.tsx`** (`src/components/`)
- Modal data-driven: fuente 1 siempre = extractos bancarios (llama `onStatements`), fuentes N = plugins con `import_route !== null` (fetches `getInvestmentPlugins()` y filtra).
- Navegación: `navigate(p.import_route!)` para rutas de plugins.
- Cierre por Escape, click en backdrop, o botón ✕.
- CSS: clases `import-picker-*` añadidas al final de `index.css`.

---

#### Tipo `InvestmentPlugin` — campo `import_route`

`api/types.ts`: añadido `import_route: string | null` (Shuri lo añade en backend en paralelo).
`api/mock.ts`: todos los entries existentes actualziados con `import_route: null`. Añadida entry `fidelity-espp` con `import_route: '/investments/fidelity-espp'` para que el mock refleje el comportamiento real.

---

#### i18n — 7 nuevas claves

`invSnapshotTitle`, `invSnapshotNoConnections`, `invSnapshotGoTo` (InvestmentSnapshotCard).
`importPickerTitle`, `importPickerStatements`, `importPickerStatementsDesc`, `importPickerClose` (ImportSourcePicker).

---

#### Principio clave aprendido

`defaultRange()` devuelve el **mes anterior** (no el actual). Para una vista fixed de "mes actual" hay que calcular el range con `currentMonthRange()` inline o extraerlo a utils.

---

#### Build

`npm run build` → `tsc --noEmit && vite build` → **0 errores TypeScript, 0 warnings CSS**. Chunk-size warning pre-existente presente.


## Learnings

### 2026-07-15 — Heatmap 3-mode redesign + ESPP upload-reminder banner

**Fecha:** 2026-07-15T18:23:00+02:00  
**Tareas:** (A) SpendingHeatmap redesign per Wanda's spec; (B) ESPP reminder banner per Shuri's endpoint.

---

#### A) SpendingHeatmap — 3 modos adaptativos

**Root-cause overflow fix:**
- .heatmap-card { min-width: 0; overflow: hidden } — impide que la card salga de la grid y cause scroll de página.
- .heatmap-outer { width: 100%; overflow-x: auto; ... } — ancla el scroll-wrapper al ancho de la card.

**Tres modos por 	otalDays:**
| Modo | Umbral | Estructura | Celda |
|------|--------|------------|-------|
| daily | ≤ 182 días | 7 filas × N semanas (GitHub calendar) | 14–20px adaptativo |
| compact | 183–547 días | Mismo calendario, scroll interno de card | 11px fijo |
| monthly | > 547 días | 12 col (meses) × Y filas (años) | 36px, sin scroll |

**Agregación mensual (modo C):** 100% frontend — DaySummary[] → Map<"YYYY-MM", number> con suma de gastos por mes.  
**Etiquetas de mes (modo C):** Generadas con Intl.DateTimeFormat({ month: 'short' }) para i18n.  
**Click en modo monthly:** Deshabilitado (sin ole="button" ni onClick) — Wanda lo indica explícitamente hasta que el filtro admita rangos de mes.  
**CSS:** --hm-month-cell: 36px, --hm-month-radius: 6px, .heatmap-month-grid-wrap, .heatmap-month-header, .hm-year-placeholder, .hm-month-col-label, .heatmap-month-row, .hm-year-label.

**Archivos modificados:** rontend/src/components/SpendingHeatmap.tsx, rontend/src/index.css

---

#### B) ESPP upload-reminder banner

**Endpoint:** GET /api/investments/fidelity/reminder → { overdue, expected_date, period_label, last_lot_date }.  
**Tipo:** FidelityReminderResponse añadido a pi/types.ts.  
**Función cliente:** getFidelityReminder() en pi/client.ts — sin mock fallback (falla silenciosamente).  
**Banner:** .espp-reminder-banner — amber, non-blocking, order-left: 4px solid #f59e0b, dark-mode aware.  
**Páginas:** Inicio (Dashboard.tsx) y Fidelity (FidelityView.tsx). Oculto cuando overdue === false.  
**i18n:** sppReminderBanner(periodLabel) + sppReminderAction en s.ts, n.ts, index.ts.  
**Link de acción:** <Link to="/investments/fidelity-espp"> (react-router-dom).  
**Fetch failure:** Silenciosa (.catch(() => {})), banner no aparece.

**Archivos modificados:** pi/types.ts, pi/client.ts, i18n/index.ts, i18n/es.ts, i18n/en.ts, pages/Dashboard.tsx, investments/views/FidelityView.tsx, index.css

**Build:** 
pm run build → 	sc --noEmit && vite build → **0 errores TypeScript ✅**

## Learnings
### 2026-07-15 — Heatmap drill-down (click → Finanzas global date range)

**Feature:** SpendingHeatmap clickable con zoom-in por clic en celda.

**Wiring click → global date filter:**
- Props onDayClick / selectedDay reemplazados por onSelectPeriod(from, to) + onResetPeriod?.
- Modo monthly (>18 meses): click celda → onSelectPeriod("YYYY-MM-01", lastDayOfMonth).
- Modo daily/compact: click celda → onSelectPeriod(date, date) (from=to=día).
- FinancesOverviewPage: guarda preZoomFilters antes del drill-down; handleResetPeriod lo restaura. Limpiar preZoomFilters al cambio manual de GlobalFilterBar.

**Zoom-out affordance:** Botón .hm-reset-btn ("‹ Ampliar rango" / "‹ Zoom out") en la cabecera del card, visible solo cuando onResetPeriod existe. Usa card-title--has-action para el layout flex.

**Accesibilidad:** ole="button", 	abIndex={0}, onKeyDown (Enter/Space) en todas las celdas activas de los 3 modos.

**CSS:** CSS cursor:pointer + :focus-visible habilitados también para celdas de monthly-grid (antes desactivadas). Nuevo .hm-reset-btn con design tokens.

**i18n:** Añadida clave heatmapZoomOut en es.ts / en.ts / index.ts.

**Archivos modificados:** components/SpendingHeatmap.tsx, pages/FinancesOverviewPage.tsx, i18n/es.ts, i18n/en.ts, i18n/index.ts, index.css

**Build:** npm run build → tsc --noEmit && vite build → **0 errores TypeScript ✅**
