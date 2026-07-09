# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

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

