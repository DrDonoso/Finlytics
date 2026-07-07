# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

## [20260707.03] - 2026-07-07

- rules table (migration 0008) + Rule model + /api/rules CRUD (regex + skip_ai validation)
- apply_rules matcher: contains/starts_with/exact/regex, sign/account/currency filters, first-match by priority
- pre_match_rules pre-LLM extraction (BBVA/Indexa date+amount) with safety-net fallback to the LLM
- import pipeline: pre_match -> conditional LLM on remaining text -> apply_rules -> merge/sort
- Settings > Reglas CRUD page, "Regla" preview badge, "Crear regla" from preview/transaction rows
- ExtractedTransaction.matched_rule_id/name; ~160 new tests


## [20260707.02] - 2026-07-07

- Initial commit

