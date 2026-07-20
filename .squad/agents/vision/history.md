## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

---

## 2026-07-20T09:02:18+02:00: Transaction Detail / Edit Modal (mobile-only)

### Learnings

**`useIsMobile` hook** (`frontend/src/hooks/useIsMobile.ts`):
- Uses `window.matchMedia('(max-width: 600px)')` + `addEventListener('change', ...)` for live updates on resize.
- Returns a boolean that initialises synchronously on first render from `matchMedia(...).matches`.
- 600px matches the app's existing mobile breakpoint used throughout `index.css`.

**`TransactionDetailModal`** (`frontend/src/components/TransactionDetailModal.tsx`):
- Full-screen sheet (uses existing `.modal-backdrop` / `.modal` chassis; slides up from bottom on mobile via the pre-existing `@media (max-width:600px)` rule that sets `align-items: flex-end`).
- Stacked label/value field layout via `.tx-detail-field` rows. Read-only fields (date, account) at top; editable fields below.
- **Reuses inline-edit logic exactly**: same `EditData` shape, same `updateTransaction()` call, same `signedAmount` formula, same `CategorySelect` + `TagEditor` props pattern.
- `onSaved(updated)` callback received from `TransactionsTable` — parent maps the updated item into its `data.items` and calls `onEditSuccess?.()`, keeping a single source of truth.
- Escape key and backdrop click both close the modal.
- `tx.id` change in `useEffect` dep resets the form when the parent opens a new transaction.

**Mobile-only enforcement in `TransactionsTable`**:
- `useIsMobile()` hook drives a conditional: `onClick` on read-mode `<tr>` only fires `setDetailTx(tx)` when `isMobile` is true. On desktop nothing happens.
- Action buttons (`⚙+` and `✎`) call `e.stopPropagation()` so tapping them on mobile does NOT also open the detail modal.
- `tr.tr-mobile-tappable` CSS class applied only when `isMobile`; provides `cursor: pointer` + `:active` highlight at ≤600px.

---

## 2026-07-20T10:11:41+02:00: Euro decimals, Finanzas historic net, nav chevron split

### Learnings

**`fmtEur` decimals fix** (`InvestmentSnapshotCard.tsx` + `Dashboard.tsx`):
- Both files had a local euro formatter with `maximumFractionDigits: 0`. Fixed both to `minimumFractionDigits: 2, maximumFractionDigits: 2` so all euro amounts on Inicio (investment snapshot card values, accounts-table neto histórico column, Neto total KPI, average monthly expense) show cents consistently.
- `formatEur` exported from `client.ts` (line ~417) uses bare `Intl.NumberFormat` which defaults to 2 decimal places — no change needed there.

**Finanzas "neto histórico" KPI** (`FinancesOverviewPage.tsx`):
- Data source: `getByAccount()` with no params → all-time per-account summaries. Sum of `row.net` = all-time cumulative net (same computation as Dashboard.tsx `accountNetTotal`).
- Mounted once in `useEffect([], [])` — period filter changes do NOT re-fetch, keeping it period-independent.
- Displayed using `.finances-historic-net-kpi` inside `dashboard-header-actions`, with `margin-right: auto` to push the two action buttons to the right. Label reuses `t.dashboardAccountsNet` ('Neto histórico' / 'Historical net') — no new i18n keys needed.
- Colors via existing `inv-kpi-card__value--pos` / `inv-kpi-card__value--neg` classes.

**Nav chevron split** (`Layout.tsx`):
- Finanzas and Inversiones: single `<button>` replaced with `.sidebar-section-header` wrapper `<div>` containing two sibling buttons — valid HTML, no nested buttons.
- Main button (`.sidebar-section-btn`): navigates to `/finances` or `/investments` only. `flex: 1` via `.sidebar-section-header .sidebar-section-btn` selector.
- Arrow button (`.sidebar-section-arrow-btn`): toggles `financesExpanded` / `investmentsExpanded` only. Has its own `active` class for color parity when on the page.
- Ajustes section and settings sub-group toggles left unchanged (toggle-only, no navigation — was already correct).
- For Inversiones: arrow button renders only when `connectedPlugins.length > 0` (condition preserved).

---

## 2026-07-20T10:11:41+02:00: Inicio UI Polish — Euro decimals, all-time net, nav split

**Euro decimals:** Fixed InvestmentSnapshotCard.tsx and Dashboard.tsx local formatters to display 2 decimals (was 0). All Inicio amounts now consistent EUR formatting.

**Finanzas "Neto histórico":** Added all-time account net fetch (getByAccount() no params) in FinancesOverviewPage.tsx. Displayed in dashboard-header-actions with margin-right: auto spacing. Reuses existing i18n key.

**Nav chevron split:** Replaced single nav+toggle button in Finanzas/Inversiones headers with .sidebar-section-header wrapper + two sibling buttons (.sidebar-section-btn nav-only, .sidebar-section-arrow-btn toggle-only). Valid HTML, preserved active state.

**Validation:** 
pm run build passes.

**Merged to:** decisions.md (Vision — Inicio euro decimals, all-time net, nav chevron split).