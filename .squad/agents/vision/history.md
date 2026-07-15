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