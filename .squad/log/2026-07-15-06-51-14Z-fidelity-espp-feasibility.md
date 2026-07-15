# Session Log — Fidelity ESPP Feasibility Probe

**Date:** 2026-07-15T06:51:14Z  
**Topic:** Feasibility probe for Fidelity ESPP (MSFT) statement-import investment connector

## Summary

Three-agent feasibility probe completed. **Verdict: VIABLE.** 

Key insights:
- **Architecture:** New provider type `statement_import` coexists with existing `live_api` (Indexa). Minimal ABC changes required.
- **Extraction:** Fidelity ESPP statement is fully parseable (text layer, stable template). Hybrid parse+LLM recommended (~2.75 days effort).
- **Backend:** Price source (Stooq primary + yfinance fallback) confirmed viable. New DB tables (`espp_lots`, `price_cache`). On-request fetch + DB cache (no scheduler).

## Deliverables

1. **Decisions merged:** `decisions.md` now contains consolidated architecture, extraction probe, and backend design (§2026-07-15T06:51:14Z entry)
2. **Orchestration logs:** Per-agent logs created in `.squad/orchestration-log/` (Fury, Banner, Shuri)
3. **Skills documented:** `.squad/skills/brokerage-statement-parsing/SKILL.md`, `.squad/skills/market-data-cache/SKILL.md`

## Next Steps

1. Owner reviews scope decisions (Phase 1 detail: accumulativity, currency, price timeliness, ESPP discount tracking, disposal logic)
2. Romanoff validates PDF privacy flow & PII redaction requirements
3. Banner, Shuri, Wanda/Vision begin Phase 1 implementation (pending owner approval)

## Blockers for Implementation

- Owner decision on Phase 1 scope (all listed in decisions.md §5)
- Security policy sign-off (Romanoff) on PII handling
