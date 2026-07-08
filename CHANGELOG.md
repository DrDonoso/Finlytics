# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

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

