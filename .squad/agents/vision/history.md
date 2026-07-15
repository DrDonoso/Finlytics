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

