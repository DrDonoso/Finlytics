# Finlytics Decision Log

## Vision — Backup wizard section icons

**Date:** 2026-07-17T14:09:26+02:00  
**Owner:** DrDonoso  
**Scope:** Frontend backup wizard UI polish.

### Decision

Add a consistent icon before every Backup wizard export section label, reusing existing sidebar menu icons where an exact navigation mapping exists.

### Icon mapping

- Transacciones / Transactions: 📋 (sidebar Transactions icon)
- Inversiones / Investments: 💰 (sidebar Investments icon)
- Cuentas / Accounts: 🏦
- Categorías / Categories: 🗂️
- Etiquetas / Tags: 🏷️
- Reglas / Rules: 🧩

### Implementation notes

Icons are inline UI decoration in `BackupPage.tsx`, not i18n strings. The import result summary headings also use the same mapping for consistency.

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. Vite emitted only the existing chunk-size warning.

---

## Shuri — Backup v2 selective rules/investments

**Date:** 2026-07-17T13:29:35+02:00  
**Owner:** DrDonoso  
**Scope:** Backend backup export/import contract.

### Decision

Backup schema version 2 extends the portable JSON backup with deterministic rules and investment data. The investment connection export includes the stored encrypted Indexa token ciphertext (`token_enc`) exactly as saved in the database; backup code never decrypts or logs it.

### Export API

`GET /api/backup/export` accepts optional boolean section query params:

- `accounts`
- `categories`
- `tags`
- `transactions`
- `rules`
- `investments`

No params means all sections are included for backward compatibility. If any section flag is supplied, only sections explicitly set truthy are emitted. The `Content-Disposition` attachment filename behavior remains unchanged.

### Import behavior

`POST /api/backup/import` accepts both v1 and v2 documents and restores whichever sections are present:

- Existing v1 account/category/tag/transaction semantics remain unchanged.
- Rules upsert by `name`.
- Investment connections upsert by `(current user, plugin_id)` and write `token_enc` verbatim.
- ESPP lots insert idempotently via `dedup_hash`.
- Price history upserts by `(ticker, price_date)`.
- Portfolio cache and raw investment import audit runs remain excluded because they are regenerable/not required by the current ESPP model.

### Summary fields added

- `rules_created`, `rules_updated`
- `investment_connections_created`, `investment_connections_updated`
- `espp_lots_inserted`, `espp_lots_duplicates`
- `price_history_inserted`, `price_history_duplicates`

### Validation

Added backup tests for selective export, default v2 export including rules/investments, v1 import compatibility, idempotent v2 import, and round-trip export/import.

---

## Shuri — Statement previous-month reminder

**Date:** 2026-07-17T13:07:15+02:00  
**Owner:** DrDonoso  
**Scope:** Backend statements API for Home per-account warnings.

### Decision

Add `GET /api/statements/reminder` to report which accounts are missing the previous completed calendar month's bank statement.

### Rule

- Previous month is the last completed calendar month relative to the server date.
- Grace is 0 days: the check applies from day 1 of the new month.
- An account is watched only if it has at least one statement month on or before the previous month.
- A watched account is missing when the previous month is absent from its statement months.
- Accounts with no history, or whose only history is the current month, are not flagged.

### Response

```json
{
  "year": 2026,
  "month": 6,
  "missing_account_ids": [1, 5]
}
```

The backend returns numeric year/month only; the frontend owns localized month labels.

### Implementation

- `StatementReminderOut` in `src/finlytics/api/schemas.py`.
- Pure `compute_statement_reminder(today, per_account_months)` in `src/finlytics/api/statements.py`.
- Endpoint enumerates `queries.get_accounts()` and reuses `queries.get_statement_months(session, account_id=...)` per account.

### Validation

- `C:\Python314\python.exe -m pytest tests\api\test_statements.py -q` → 24 passed.
- `C:\Python314\python.exe -m pytest -q` → 1167 passed, 2 skipped, 12 warnings.

---

## Vision — Backup wizard

**Date:** 2026-07-17  
**Owner:** DrDonoso  
**Scope:** Frontend backup wizard aligned with backend v2.

### Decision

Turn the Backup page into a two-part wizard aligned with backend Backup v2.

### Implemented

- Export now exposes six localized checkboxes: transactions, accounts, categories, tags, rules, and investments.
- All export sections are selected by default; selected subsets are sent as boolean flags to `GET /api/backup/export` and downloaded as JSON.
- Import remains file-based but now requires choosing the JSON and then pressing Import, restoring every section present in the v1/v2 document.
- The result summary is grouped by section and includes the extended v2 counts for rules and investments: connections, Fidelity ESPP lots, and price history.
- The Investments export note calls out that Indexa's token is encrypted and only restorable with the same encryption key.

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. Vite emitted only the existing chunk-size warning.

---

## Vision — Home statement-missing warning

**Date:** 2026-07-17  
**Owner:** DrDonoso  
**Scope:** Home account warning marker for missing bank statements.

### Decision

Show a per-account warning marker in the Home/Inicio accounts table when `GET /api/statements/reminder` reports the account ID in `missing_account_ids`.

### Implementation

- Added typed `StatementReminder` and `getStatementReminder()` with a mock fallback returning no missing accounts.
- Dashboard fetches the reminder on mount and only renders markers when `year`, `month`, and a matching account ID are present.
- The marker is subtle, uses existing expense/warning design tokens, and opens a fixed-position portal tooltip.
- Tooltip text is localized through i18n and formats the reminder month as `YYYY-MM` via Dashboard's `formatMonthLabel`, e.g. `Junio 2026` / `June 2026`.

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. Vite emitted only the existing chunk-size warning.

---

## Vision — Inicio global metrics

**Date:** 2026-07-17  
**Owner:** DrDonoso  
**Scope:** Inicio dashboard frontend-only global metric refinements.

### Decision

Inicio now treats the KPI strip and Cuentas summary as all-time/global, with `getOverviewMonths()` used only to count months with data for monthly averages.

1. **Neto total:** sum of all-time per-account nets displayed by `getByAccount()` plus `getCombinedOverview().total_value_eur`.
2. **Tasa de ahorro:** historical savings rate = all-time `getOverview().net ÷ getOverview().total_income`; render `—` when cumulative income is zero or negative.
3. **Promedio mensual neto:** replaces `% crecimiento`; all-time `getOverview().net ÷ getOverviewMonths().months.length`, rendered as signed currency per month and colored by sign.
4. **Cuentas table:** columns are Cuenta, Neto histórico, and Gasto medio/mes. Monthly spend uses each account's all-time `expense ÷ months.length`; rows remain clickable to `/finances?account_id=ID`.

### Files touched

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/i18n/index.ts`
- `frontend/src/i18n/es.ts`
- `frontend/src/i18n/en.ts`

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. The existing Vite chunk-size warning remains expected.

---

## Vision — Inicio redesign and centralized investment logos

**Date:** 2026-07-16  
**Owner:** Vision  
**Scope:** Inicio (Dashboard) redesign + investments consistency + icon centralization.

### Decisions implemented

1. **Removed statement import controls from Inicio:** The Inicio "Ver transacciones" and "Importar" buttons and the whole import flow have been removed. Import remains available in Finanzas.
2. **Replaced header KPI block:** Inicio now displays an investments-style KPI strip with:
   - Neto total (all-time net from `getOverview()` without date range)
   - Tasa de ahorro (selected month net/income)
   - % crecimiento (selected month net vs previous available month)
   - Patrimonio inversiones (combined investments total value from `getCombinedOverview().total_value_eur`)
3. **Added accounts table:** Displays selected-month accounts data with net and transaction count, rows deep-link to `/finances?account_id=...`.
4. **Finanzas account filter initialization:** Now reads `account_id` from search params on mount and initializes `filters.account_id` from it.
5. **Investment provider links:** InvestmentSnapshotCard provider rows are now clickable links to provider detail routes.
6. **Centralized investment logos:** Investment connector logos are now centralized in `frontend/src/investments/registry.ts` as `/logos/indexa-capital.svg` and `/logos/fidelity-espp.svg`; consumers render `<img>` with a fallback.

### Files touched

- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/FinancesOverviewPage.tsx`
- `frontend/src/components/InvestmentSnapshotCard.tsx`
- `frontend/src/pages/InvestmentsLandingPage.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/pages/ConnectorsPage.tsx`
- `frontend/src/investments/registry.ts`
- `frontend/src/i18n/` (index, es, en files)
- `frontend/src/index.css`
- `frontend/public/logos/indexa-capital.svg` (new)
- `frontend/public/logos/fidelity-espp.svg` (new)

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. The existing Vite chunk-size warning remains expected.

---

## Vision — Import Preview Bugfixes

**Date:** 2026-07-16T13:27:03+02:00  
**Owner:** DrDonoso  
**Scope:** Import preview table editing/filtering and category typeahead display.

### Decisions implemented

1. **Focus-aware flagged filter:** `ImportPreviewTable` tracks the row currently focused/edited. In `Solo marcadas` / `Flagged only` mode, visible rows are now `currently flagged OR focused row`, so live flag recomputation can update counts/badges without making the row disappear mid-edit. The row is allowed to leave the filtered view only after blur.
2. **Localized category display with canonical values:** Category editing now uses `PreviewTypeahead` with localized labels from `categoryLabel(canonical, lang, dynamicEs)` for the input and dropdown options. Matching/typing searches localized labels too, while selected values remain canonical for import payloads.
3. **Generic typeahead extension:** `PreviewTypeahead` gained optional label and input-normalization hooks. Merchant and account usages do not pass those hooks, so they keep raw-text behavior.

### Files touched

- `frontend/src/components/ImportPreviewTable.tsx`
- `frontend/src/components/PreviewTypeahead.tsx`
- `.squad/agents/vision/history.md`

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. The existing Vite chunk-size warning remains expected.

---

## Vision — Preview Live Quality Re-sync + Selector Restyle

**Date:** 2026-07-16T13:11:00+02:00  
**Owner:** DrDonoso  
**Scope:** Frontend import preview UI only.

### Decisions implemented

1. **Client-side live quality:** After preview extraction, `frontend/src/components/importQuality.ts` recomputes advisory quality from the edited rows on every render. The panel, row badges, duplicate count, and `Flagged only` filter all consume this single live result.
2. **No AI/backend reclassification:** `category_confidence` remains the original AI confidence. When the user changes category away from the originally extracted value, the category is treated as human-verified and low-confidence/generic/missing-category flags clear without a backend or AI call.
3. **Deterministic field fixes:** Merchant, amount, and date edits clear their respective warnings only by making the deterministic rule no longer match. Missing merchant keeps Banner's expense/card-like scope and salary/transfer/tax/fee/ATM exclusions.
4. **Duplicates:** Intra-batch duplicates are recomputed live from account/date/amount/description/detail. DB duplicates from `check-duplicates` remain shown; duplicate row counts are unioned so a row is not double-counted.
5. **Selector styling:** Preview merchant, account, and category selectors now use a shared typeahead styled from the existing `TagTypeahead` pattern, with fixed-position dropdowns that escape the scrollable table. Tags keep their chip styling; the other selectors use the same input/dropdown language without swatches.
6. **Non-blocking:** Quality and duplicate signals remain advisory only; confirm stays enabled except for the pre-existing zero-row guard.

### Files touched

- `frontend/src/components/importQuality.ts`
- `frontend/src/components/PreviewTypeahead.tsx`
- `frontend/src/components/ImportModal.tsx`
- `frontend/src/components/ImportPreviewTable.tsx`
- `frontend/src/components/CategorySelect.tsx`
- `frontend/src/index.css`

### Validation

`cd frontend && npm run build` passed with zero TypeScript errors. The existing Vite chunk-size warning remains expected.
