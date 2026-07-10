# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

## [20260710.02] - 2026-07-10

- Trim the overloaded home: remove the embedded full transactions table; move the heavy analytical charts (spending over time, by account, cashflow Sankey) to a new "Trends" view at /analytics.
- Add a Top-merchants donut and a GitHub-style daily spending heatmap with adaptive cell size (large for a single month, small for a year).
- Click-to-filter across the home: category, merchant and day are pinnable filters shown as removable chips; clicking any chart filters the rest.
- Constant unfiltered "current net" KPI in the header; a "View transactions" button that carries the active filters to /transactions.
- Date-picker year navigation; logo/title links to Home; show "clear filters" when the date range changes; reserve chart heights to avoid layout shift.
- New GET /api/summary/by-merchant (expenses grouped by merchant, excludes null/empty merchant) and GET /api/summary/by-day (daily expense/income/net).
- Add an exact-date `day` filter to _apply_filters and thread `merchant` + `day` cross-filters through the summary endpoints so clicking a chart filters the rest (each chart never self-filters its own dimension).
- New tests bring the suite to 832 passed / 2 skipped.
- Preview rows re-run the duplicate check when an identity field (date, amount, description) is edited, debounced 400ms with stale-response protection; the "Duplicada" badge and count now update live.
- Replaced the stuck/empty confirm-phase progress bar with the same spinner used during PDF extraction.
- Import preview now flags DUPLICATE rows (dimmed + "Duplicada" badge + per-group count) via a new POST /api/imports/check-duplicates endpoint that reuses the dedup hash (so flags match what confirm would skip; also flags intra-batch repeats).
- Rule form: the "apply to N" action is now a checkbox; Save becomes "Guardar y aplicar" when checked (saves the rule then applies it to matching transactions). Count copy fixed to "Aplicar a N transacciones" with singular/plural and the "transacciones" accent typo corrected.
- Confirm-phase progress bar is now visible and advances (was invisible: undefined --accent -> --primary) with a per-file spinner/counter; import preview tag suggestions are ordered by usage (tx_count desc).
- fix(import): spinner on the active file and replace the stuck progress bar
- feat(import): batch-import multiple statement PDFs at once


## [20260710] - 2026-07-10

- feat(import): one-click file selection and a styled, localized file picker
- feat(accounts): identify accounts by IBAN detected on import
- feat(auth): add "remember me" for long-lived persistent sessions
- fix(auth): pass AUTH_SECRET to the container so sessions survive restarts


## [20260709] - 2026-07-09

- fix(statements): make empty month cells clearly non-interactive
- feat(statements): restrict month picker to months with data + persistent import
- feat(ui): custom date-picker calendar and clearer empty-month styling
- style(import): mark required file and account fields with an asterisk
- fix(import): require a file and a non-empty trimmed account
- feat(settings): accounts management page with tx counts and delete
- fix(transactions): omit empty query params so the default list loads
- refactor(ui): move delete-month action into the transactions table header
- Rules: RuleFormModal shows a live "applies to N current transactions" count and an "apply to existing" action. Backend adds POST /api/rules/preview and /api/rules/apply (+ /api/rules/{id}/apply), reusing the import-time rule matcher so results are consistent.
- Extractos: account selector (shown when more than one account); the delete-month control is now a small icon-only button in the corner.
- Transactions: default view (no filter) shows the latest transactions, date descending, instead of a pre-applied month range.
- feat(ui): redesign date-range fields and add custom month picker
- feat(statements): add monthly Extractos view with per-month delete
- fix(extraction): derive statement year from period title, not issue date
- docs: add root README and standardize OpenAI wording
- feat(dashboard): add month-over-month period comparison
- Tag filter becomes a searchable typeahead showing the top-5 most-used tags when there are many
- New tags and categories get a color derived from their name, with a swatch color picker and a live preview
- App logo added: browser-tab favicon, top bar, and the with-text logo on the login screen
- The extracted detail is shown under each description in the import preview and the transactions table
- Rule editor redesigned into Identity / Conditions / Actions sections, collapsible, with an amount filter and the active toggle moved to the top-left and to the first column of the rules table
- Rules can match on an optional detail condition (e.g. detail contains "octopus") to separate charges that share the same title
- Rules can filter by amount magnitude (e.g. only charges over 1000)
- Transaction detail is persisted and included in the de-duplication key so distinct charges are no longer merged
- Parser now separates the bold concept (e.g. "Adeudo a su cargo") from the non-bold detail line (e.g. "Octopus Energy" vs a community address), so look-alike charges can be told apart
- Extracted transactions gain a `detail` field carrying that sub-line
- Descriptions are normalized to readable text instead of raw uppercase, unspaced bank tokens
- Extraction is processed in chunks so large statements no longer exceed the model output limit (fixes a 502 on full-month imports)
- feat(ui): move Reglas to a top-level menu item
- rules table (migration 0008) + Rule model + /api/rules CRUD (regex + skip_ai validation)
- apply_rules matcher: contains/starts_with/exact/regex, sign/account/currency filters, first-match by priority
- pre_match_rules pre-LLM extraction (BBVA/Indexa date+amount) with safety-net fallback to the LLM
- import pipeline: pre_match -> conditional LLM on remaining text -> apply_rules -> merge/sort
- Settings > Reglas CRUD page, "Regla" preview badge, "Crear regla" from preview/transaction rows
- ExtractedTransaction.matched_rule_id/name; ~160 new tests
- Initial commit


## [20260708.02] - 2026-07-08

- Tag filter becomes a searchable typeahead showing the top-5 most-used tags when there are many
- New tags and categories get a color derived from their name, with a swatch color picker and a live preview
- App logo added: browser-tab favicon, top bar, and the with-text logo on the login screen
- The extracted detail is shown under each description in the import preview and the transactions table
- Rule editor redesigned into Identity / Conditions / Actions sections, collapsible, with an amount filter and the active toggle moved to the top-left and to the first column of the rules table
- Rules can match on an optional detail condition (e.g. detail contains "octopus") to separate charges that share the same title
- Rules can filter by amount magnitude (e.g. only charges over 1000)
- Transaction detail is persisted and included in the de-duplication key so distinct charges are no longer merged
- Parser now separates the bold concept (e.g. "Adeudo a su cargo") from the non-bold detail line (e.g. "Octopus Energy" vs a community address), so look-alike charges can be told apart
- Extracted transactions gain a `detail` field carrying that sub-line
- Descriptions are normalized to readable text instead of raw uppercase, unspaced bank tokens
- Extraction is processed in chunks so large statements no longer exceed the model output limit (fixes a 502 on full-month imports)


## [20260708] - 2026-07-08

- feat(ui): move Reglas to a top-level menu item


## [20260707.03] - 2026-07-07

- rules table (migration 0008) + Rule model + /api/rules CRUD (regex + skip_ai validation)
- apply_rules matcher: contains/starts_with/exact/regex, sign/account/currency filters, first-match by priority
- pre_match_rules pre-LLM extraction (BBVA/Indexa date+amount) with safety-net fallback to the LLM
- import pipeline: pre_match -> conditional LLM on remaining text -> apply_rules -> merge/sort
- Settings > Reglas CRUD page, "Regla" preview badge, "Crear regla" from preview/transaction rows
- ExtractedTransaction.matched_rule_id/name; ~160 new tests


## [20260707.02] - 2026-07-07

- Initial commit

