# Vision — Agent History

## Summary of Sessions (2026-07-20 to 2026-07-23)

**Major outcomes:**
- **Indexa Contributions Table** (2026-07-23): "Aportaciones y retiradas" table in IndexaView; Fecha·Importe·Acumulado columns with signed coloring, type badges; defensive optional handling; 7 i18n keys; reuse existing CSS. ✅ Build green, contribution_events exposed in API. Cross-ref: orchestration-log/2026-07-23T10-09-14Z-vision.md, log/2026-07-23T10-09-14Z-indexa-contributions.md
- **is_system badge en ledger** (2026-07-21): Badge "Sistema"/"System" en filas `is_system=true` del ledger. Totales de página ya vienen del backend (overview) — no había suma cliente que corregir. ✅ Build green.
- **Import-time opening balance** (2026-07-21): Campo "Saldo anterior" opcional en la fase resolve del ImportModal, para cuentas nuevas (IBAN y manual). 3 keys i18n, `opening_balance` en `ConfirmRequest`. ✅ Build green.
- **Old Account Onboarding** (2026-07-21): AccountCreateModal with collapsible opening-balance section; 18 i18n keys; raw fetch for 409/422 handling; mutable mock store. ✅ Build green.
- **Finanzas/Extractos refactor** (2026-07-20): Drill-down transactions table + active-filter chips; CategoryMovers moved to Extractos; KPI comparison fix (equal-length preceding period).
- **Mobile transaction detail** (2026-07-20): Mobile-only transaction edit modal; useIsMobile hook; TransactionsTable integration.
- **UI polish** (2026-07-20): Euro decimal fixes (2 places); all-time net KPI; nav chevron split (finance/investments).

**Session patterns:**
- Consistent use of existing modal patterns (.modal-backdrop, .modal, etc.)
- i18n in all three files (Dict, en.ts, es.ts)
- Raw fetch for status-dependent error handling (409/422)
- Mutable store patterns for mock consistency

---

## 2026-07-21T17:01:22+02:00: Badge "Sistema" en filas is_system=true

**Summary:** Marcado visual de filas sintéticas "Saldo inicial" (`is_system=true`) en TransactionsTable. Badge sutil `.tx-system-badge` (dashed border, text-muted, 10px) aparece debajo del texto de descripción. Totales de la página (`tx-totals`) ya vienen del endpoint `GET /api/summary/overview` que excluye `is_system` — no había suma cliente que corregir. Mock actualizado: 2 entradas `is_system: true` en RAW; `mockGetOverview`, `mockGetByCategory`, `mockGetByMonth`, `mockGetByAccount` filtran `!t.is_system`. npm run build ✅ 0 errores TS.

**Key files:** TransactionsTable.tsx, api/types.ts, api/mock.ts, i18n/{index,es,en}.ts, index.css.

**Pattern notes:**
- `Transaction.is_system?: boolean` — opcional para retrocompatibilidad con mocks sin la clave.
- Badge colocado FUERA de `.td-desc` (que tiene `overflow: hidden; text-overflow: ellipsis; white-space: nowrap`) para no quedar clippeado.
- Regla Shuri: "Badge visual → ledger row; Importe total → overview endpoint." — los totales de página NUNCA deben sumarse del cliente sobre filas visibles.
- Los 4 endpoints de resumen mock excluyen `is_system: true` para simular el comportamiento real del backend.

---



---

## 2026-07-23T11:32:01+02:00: Tabla "Aportaciones y retiradas" en IndexaView

**Summary:** Añadida tabla `contribution_events` al final del bloque conectado de IndexaView. El campo es opcional en el tipo (`contribution_events?: ContributionEvent[]`), por lo que el frontend es retrocompatible con backends sin el campo. Filas ordenadas más-reciente-primero (`.reverse()` sobre el array del backend que viene por fecha asc). Importe con signo y color (`inv-pnl--pos/neg`); badge tipo con clases ya existentes de asset-class (`--equity` azul para aportación, `--cash` gris para retirada). 7 claves i18n. Mock actualizado con 4 aportaciones + 1 retirada. npm run build ✅ 0 errores TS.

**Key files:** IndexaView.tsx, api/types.ts, api/mock.ts, i18n/{index,es,en}.ts.

**Pattern notes:**
- `contribution_events?: ContributionEvent[]` — campo opcional, evita romper si el backend no lo envía.
- El array del backend llega ordenado por fecha asc; se invierte con `.reverse()` sobre una copia `[...array]` para mostrar más reciente primero.
- Se reutilizan las clases `.inv-pnl--pos` / `.inv-pnl--neg` y `.inv-asset-class-badge--{class}` del holdings table — sin CSS nuevo.
- El formateo de fechas usa `formatDDMMYYYY()` (función local de IndexaView) para consistencia con el resto de la vista.
- El empty state protege tanto el caso array vacío como campo ausente (`portfolio?.contribution_events ?? []`).

## Learnings

- **contribution_events: campo opcional en el tipo** — `contribution_events?: ContributionEvent[]` evita romper si el backend no lo incluye todavía. Siempre defenderlo con `?? []`.
- **Reutilizar clases de holdings para la tabla de eventos** — `.inv-pnl--pos/neg`, `.inv-asset-class-badge--{class}`, `.inv-holdings-table-wrap`, `.inv-th-num` son genéricas del contexto de inversiones; reusarlas evita CSS nuevo.

- **tx-totals usan overview endpoint** — Los bloques `.tx-totals` en TransactionsPage y FinancesOverviewPage obtienen sus cifras de `getOverview()` (backend), no de suma cliente. Esto significa que cualquier cambio en qué filas aparecen en el ledger no afecta los totales de página automáticamente — el backend ya maneja la exclusión.
- **td-desc tiene overflow:hidden** — Nunca añadir badges dentro de `.td-desc`: tienen `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`. Los sub-elementos (badges, sublines) deben ser hermanos, no hijos del div.
- **is_system: optional en el tipo** — Hacer el campo `is_system?: boolean` en vez de requerido evita actualizar los ~43 objetos del array RAW en mock.ts.


## 2026-07-21T13:31:05+02:00: Campo "Saldo anterior" en ImportModal

**Summary:** Added optional "Saldo anterior" field in the `resolve` phase of ImportModal for new accounts. Field renders below the account name input for both IBAN-detected new accounts (`newIbanEntries`) and manual new accounts (`noIbanNewMode`). Opening balance is sent as `opening_balance` in the `ConfirmRequest` payload; omitted for existing/matched accounts. Added 3 i18n keys. npm run build: ✅ 0 TS errors.

**Key files:** ImportModal.tsx, api/types.ts, i18n/index.ts, i18n/es.ts, i18n/en.ts.

**Pattern notes:**
- `NewIbanEntry` interface gained `openingBalance: string` (empty = omit).
- New state `noIbanOpeningBalance: Record<number, string>` for per-file manual accounts.
- `handleConfirmAll` reads opening balance from respective state; parses to float; omits when empty/NaN.
- `ConfirmRequest.opening_balance?: number | null` — only sent when new account + non-empty value.
- No mock changes needed: `mockConfirmImport` ignores extra fields gracefully.
- Hint/copy follows Fury's proposal: one field, no date asked, server infers date from first tx.

---

## 2026-07-21T11:30:13+02:00: Formulario "Nueva cuenta" con saldo inicial

**Summary:** Implemented AccountCreateModal with collapsible opening-balance section. Used raw fetch for 409/422 error handling. Added 18 i18n keys (EN/ES), mutable mock store, CSS styling. npm run build: ✅ 0 TS errors.

**Key files:** AccountsPage.tsx, client.ts, types.ts, index.css, i18n/*.ts.

**Pattern notes:**
- Modal follows existing .modal-backdrop/.modal structure; Escape closes it.
- Opening-balance section collapses with ▶/▼ toggle (disclosure button pattern).
- Validation: amount !== '' && date required when amount present.
- Client-side error display: 409 = duplicate name/IBAN, 422 = balance without date.
- Mutable mock store (_mockAccounts) for session persistence.

---

## 2026-07-20 Sessions Summary (collapsed)

**Finanzas drill-down + CategoryMovers refactor:** Added drill-down transactions table to Finanzas (filters by category/merchant/date range). Moved CategoryMovers from Finanzas → Extractos. Added equal-length preceding-period comparison for Finanzas KPIs (not just previous calendar month). Added active-filter chips row with "Clear all" button. i18n: drillDownActiveFilters, drillDownClearAll, kpisPrevPeriodLabel. Validation: npm run build ✅.

**Mobile transaction detail:** Implemented TransactionDetailModal (mobile-only). Uses useIsMobile hook (window.matchMedia 600px). Full-screen sheet pattern. Reuses inline-edit logic. On desktop, TransactionsTable rows are non-interactive; on mobile, click-to-open detail modal (stopPropagation on action buttons).

**Inicio UI polish:** Fixed euro decimal formatting (InvestmentSnapshotCard, Dashboard) from 0 to 2 decimals. Added "Neto histórico" all-time net KPI (getByAccount, no params, sum of rows). Split Finanzas/Inversiones nav buttons (.sidebar-section-header with two siblings: nav button + toggle arrow button).

**Previous sessions (pre-2026-07-20):** Notifications + Telegram (hybrid model, Fernet encryption); earlier drill-down/filtering work; investment features.

---


---

## Archived Detailed Entries (2026-07-20, collapsed for size)

*Original learnings and detailed notes for 2026-07-20 sessions (drill-down table, CategoryMovers, mobile detail modal, UI polish, navigation splits) are available in git history or on request. Key learnings documented in summary above.*




## Session: 2026-07-21 — is_system implementation (slice complete)

**Collaborators:** Shuri, Vision, Barton, Fury  
**Status:** ✅ IMPLEMENTED + APPROVED  
**Decisions:** .squad/decisions.md (merged from inbox), .squad/orchestration-log/  
**Session Log:** .squad/log/2026-07-21T16-59-22Z-is-system-kpi-exclusion.md

**Summary:** Full squad execution: migration 0017 (Shuri), frontend badge (Vision), 15 tests (Barton), architecture review (Fury). Owner approved OPTION B (ledger-visible, KPI-excluded). No defects. Ready for merge.

**Cross-agent refs:**
- Shuri: orchestration-log/2026-07-21T16-59-22Z-shuri.md
- Vision: orchestration-log/2026-07-21T16-59-22Z-vision.md
- Barton: orchestration-log/2026-07-21T16-59-22Z-barton.md
- Fury: orchestration-log/2026-07-21T16-59-22Z-fury.md

