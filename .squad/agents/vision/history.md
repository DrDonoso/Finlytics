# Vision — Agent History

## Summary of Sessions (2026-07-20 to 2026-07-21)

**Major outcomes:**
- **Import-time opening balance** (2026-07-21): Campo "Saldo anterior" opcional en la fase resolve del ImportModal, para cuentas nuevas (IBAN y manual). 3 keys i18n, `opening_balance` en `ConfirmRequest`. ✅ Build green.
- **Old Account Onboarding** (2026-07-21): AccountCreateModal with opening-balance modal; 18 i18n keys; raw fetch for 409/422 handling; mutable mock store. ✅ Build green.
- **Finanzas/Extractos refactor** (2026-07-20): Drill-down transactions table + active-filter chips; CategoryMovers moved to Extractos; KPI comparison fix (equal-length preceding period).
- **Mobile transaction detail** (2026-07-20): Mobile-only transaction edit modal; useIsMobile hook; TransactionsTable integration.
- **UI polish** (2026-07-20): Euro decimal fixes (2 places); all-time net KPI; nav chevron split (finance/investments).

**Session patterns:**
- Consistent use of existing modal patterns (.modal-backdrop, .modal, etc.)
- i18n in all three files (Dict, en.ts, es.ts)
- Raw fetch for status-dependent error handling (409/422)
- Mutable store patterns for mock consistency

---

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


