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
