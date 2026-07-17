# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

## [20260717.02] - 2026-07-17

- uvicorn + app: custom log_config in __main__.py (built from uvicorn LOGGING_CONFIG + a root logger so finlytics.* module logs are timestamped too)
- alembic: alembic.ini [formatter_generic]
- entrypoint: date-prefixed echoes in docker-entrypoint.sh
- seed: timestamped print in seed.py
- Merge rocket-log-timestamps decision into decisions.md (inbox→main)
- Write orchestration log: Rocket log-timestamps + Coordinator deploy
- Write session log: brief summary of log-timestamps feature
- Verify: decisions.md no items >7d old; all history.md <15360 bytes


## [20260717] - 2026-07-17

- Appearance: 5 selectable accent palettes (Classic/Emerald/Violet/Amber/High-Contrast) via CSS custom properties, persisted in localStorage, light/dark aware.
- Charts: income/expense semantic colors are now palette-aware (tonal variants per palette) while preserving meaning; category identity colors untouched.
- Import: deterministic Import Quality Report on the preview (low-confidence/missing category, missing merchant, zero amount, date mismatch, duplicates) with live client-side recompute, flagged-only filter, and unified PreviewTypeahead selectors (localized category labels).
- Inicio: removed import + view-transactions buttons and the month selector; global KPIs (Neto total = accounts net + investments, historical savings rate, average monthly net, with tooltips); clickable Accounts table (Neto + avg monthly spend) deep-linking to Finanzas by account; investments snapshot providers link to their detail screens.
- Icons: centralized Indexa/Fidelity platform icons as bundled SVG logos.
- Merged vision-preview-expand-typeahead.md from decisions/inbox/ into decisions.md
- Created orchestration-log/2026-07-16T11-51-05Z-vision.md (vision spawn execution + coordinator deploy)
- Created log/2026-07-16T11-51-05Z-preview-expand-typeahead.md (session summary)
- Condensed banner/history.md and rocket/history.md to stubs, archived previous versions
- Verified: decisions.md, orchestration-log, session-log created; no app source staged
- Added decision entry recording merchant normalization feature removal per owner request
- Merchant Normalization (Slice 1 backend + Slice 2 UI) reverted; DB downgraded 0016 -> 0015
- Retained color palettes and palette-aware charts (Wanda's work)
- Updated Shuri and Vision history.md with reversal notes
- Created orchestration and session logs with verification details
- Summarized Shuri and Vision history.md to meet size thresholds
- Merged wanda-palette-aware-charts and vision-merchant-ui-slice2 decisions into decisions.md
- Cleared decisions/inbox/ (2 files archived)
- Documented with orchestration logs (wanda, vision, coordinator) and session log
- Condensed 5 large agent history files for archival (banner, fury, rocket, shuri, vision)


## [20260716.02] - 2026-07-16

- Rewrite README with Inicio hub, Finanzas (heatmap + drill-down) and full Investments section (Indexa live-API + Fidelity ESPP)
- Document the dual data-flow (bank statements + investments) and refresh the tech stack (Fernet, Yahoo Chart API, plugin architecture)
- Add the two-Dockerfile convention (Dockerfile / Dockerfile.local) and FINLYTICS_ENCRYPTION_KEY to DEPLOY.md
- Document migrations head (0015), connector architecture (live-API vs statement-import) and Fernet token encryption in AGENTS.md
- Update frontend/README.md with the current directory structure and component/page list
- Correct the license note to MIT


## [20260716] - 2026-07-16

- Pagina About disponible en Settings > Application con info de la imagen desplegada
- GET /api/version expone {version, image_tag, built_at} consumido por el frontend
- Workflow de deploy inyecta CalVer IMAGE_TAG + BUILD_DATE como build-args al construir la imagen Docker
- Licencia MIT (LICENSE) anadida al repositorio
- .dockerignore corregido para incluir frontend/dist/ en la imagen de produccion


## [20260715.02] - 2026-07-15

- Restore full multi-stage Dockerfile (Node 20 frontend-builder stage + Python runtime); CI/prod are self-contained again
- Revert .dockerignore: re-add frontend/dist/ so the dist is never sent to the Docker build context
- Remove Node.js + frontend pre-build steps from docker-deploy.yml; the Dockerfile handles it
- Add Dockerfile.local (host-prebuilt frontend) + update docker-compose.local.yml to use it; workaround for npm 10 crash-in-Docker on owner's machine
- Add AGENTS.md documenting the two-Dockerfile convention


## [20260715] - 2026-07-15

- Fidelity ESPP CSV connector: import wizard, ESPP lots, daily Yahoo Finance pricing + FX conversion, evolution chart, KPIs (unrealized gain, ESPP discount, current value)
- ESPP purchase reminder: tracks upcoming ESPP purchase dates and surfaces alerts in dashboard
- Indexa Capital portfolio cache (migration 0015): reduces API calls, stores snapshot with TTL
- Combined investments overview: unified landing page with per-provider donuts and aggregate KPIs
- Nav restructure: Finanzas group (gastos/analytics), Inversiones standalone section, Inicio hub
- Inicio hub + InvestmentSnapshotCard: at-a-glance portfolio value widget on dashboard
- Data-driven import source picker (ImportSourcePicker.tsx): registry-driven connector selection UI
- Adaptive drill-down spending heatmap (SpendingHeatmap.tsx): click-through from month to category
- Settings reorganised into 4 groups; i18n strings updated (en + es)
- Migrations 0014 (fidelity_espp tables) and 0015 (portfolio_cache table)
- CI fix: docker-deploy.yml now pre-builds the React frontend on the runner (setup-node + npm ci + npm run build) before docker build, so frontend/dist exists without committing it
- Feature: SpendingHeatmap clickable drill-down with global date filter integration
- Props: onDayClick/selectedDay → onSelectPeriod(from,to) + onResetPeriod
- Zoom affordance: "‹ Ampliar rango" reset button (visible during drill)
- A11y: role=button, tabIndex, Enter/Space keyboard support
- CSS: cursor:pointer + :focus-visible on all clickable cells + .hm-reset-btn
- i18n: Added heatmapZoomOut key (es/en)
- Build: 0 TypeScript errors
- decisions.md: prepended batch 5 entry (heatmap redesign 3-mode fix + ESPP reminder endpoint + banner + cadence analysis)
- orchestration-log: 4 agent logs (2026-07-15T160800Z)
- log: session summary
- agents/*/history.md: updated with recent work
- Add batch 4 status to decisions.md (Shuri months endpoint, Vision i18n & month selection, Rocket rebuild)
- Update vision/history.md with three frontend owner-feedback fixes (FIX 1: i18n, FIX 2: month selection, FIX 3: Finanzas link)
- Clean up barton history (remove pre-7-day entries, duplicate sections)
- Add orchestration logs for shuri, vision, rocket (gitignored, disk only)
- Add session log for feedback batch 4 (gitignored, disk only)
- Merge Vision feedback (Inicio/Finanzas split, ImportSourcePicker, InvestmentSnapshotCard) into decisions.md
- Clean up decision inbox (vision-inicio-finanzas-import-picker.md moved to decisions.md)
- Archive check: all dated entries recent (2026-07-14 to 2026-07-15), within 7-day window — skip archival
- History summarization: large files (banner, barton, rocket, shuri, vision) have recent 2026-07-15 entries with existing archives — no action needed
- Orchestration logs written (shuri, vision, rocket) — disk-only, gitignored
- Session log: feedback batch 3 summary — disk-only, gitignored
- Decisions: merged wanda-inicio-vs-finanzas-recommendation.md from inbox
- Decisions: added FEEDBACK BATCH 2 status (vision, shuri, rocket, wanda deliverables)
- Histories: vision, wanda updated with recent work logs
- AnalyticsPage Tendencias title moved to page header
- Investments nav made expandable with sub-items (indexa-capital, fidelity-espp)
- Settings 4-group collapsible toggles implemented
- Combined-overview cards now use real plugin_ids
- Generic-broker + crypto-exchange stubs removed
- Wanda recommendation: Inicio-vs-Finanzas content differentiation (PROPOSAL)
- Merged 4 inbox files into decisions.md: wanda nav-restructure spec, shuri indexa-cache, shuri combined-overview endpoint, vision nav+overview implementation
- Added UX batch integration status line (nav Finanzas group, combined investments overview, indexa 24h cache, settings 4-group)
- Deleted inbox files (gitignored, disk-only)
- Created 6 orchestration logs (wanda, shuri×2, vision×2, rocket) — ISO 8601 UTC
- Created session log for UX batch
- Checked history files for archiving (banner/barton/vision contain entries 2026-07-09 to 2026-07-14; older content already archived)
- Updated decisions.md, agents/vision/history.md, agents/wanda/history.md
- Merged ADR: Yahoo Chart API (browser UA, query1→query2 fallback)
- Status: 1088 tests passing; repo code uncommitted (owner testing)
- Orchestration logs: agents (shuri, vision, rocket) round A & B
- Decisions: 265341 bytes (no archiving needed; all entries recent)
- Inbox: 1 file processed; deleted
- Shuri Wave 1–A (foundation), Wave 2 (endpoints)
- Banner Wave 1–B (parser), contract fix
- Vision Wave 3 (frontend)
- Fury architecture + 2 reviews (REJECT → APPROVE)
- Romanoff privacy review (PASS)
- Barton QA + integration tests (69 new tests, 1069 total)
- Rocket DevOps (Docker compose, npm-in-Docker workaround)
- Future planning (nav reorganization, settings refactor)
- Romanoff: Fidelity ESPP CSV import privacy review (PASS)
- Vision: Full Fidelity frontend implementation learnings
- Merged three agent design decisions (Fury, Shuri, Vision) into decisions.md
- Currency-of-record finalized as EUR; endpoint contracts agreed
- Archived older entries from vision/history.md and wanda/history.md (>15KB gate)
- Preserved recent entries (2026-07-15) in main history files
- Merged fury-fidelity-espp-refinement.md, romanoff-espp-pdf-storage-privacy.md, banner-fidelity-openlots-csv.md into decisions.md
- Added reconciliation note: critical correction to currency assumption (CSV values in EUR, not USD; FX only for Phase 2 live prices)
- Updated idempotency strategy for duplicate DO lots (ordinal-within-group in dedup hash)
- Deleted 3 processed inbox files (fury-fidelity-espp-refinement.md, romanoff-espp-pdf-storage-privacy.md, banner-fidelity-openlots-csv.md)
- Updated shuri/history.md, vision/history.md, wanda/history.md with CSV refinement findings and UI preference heads-up
- Added archive pointers to history files for readability
- decisions.md: merged architecture, extraction probe, and backend design (§2026-07-15T06:51:14Z) - New provider type (statement_import) coexists with live_api (Indexa) - PDF fully parseable; hybrid parse+LLM recommended (~2.75 days effort) - Stooq primary + yfinance fallback for pricing; on-request fetch + DB cache - New tables: espp_lots, price_cache; token_enc NULLABLE migration 0014 - Three-phase plan: import → price → evolution - Open questions for owner: accumulativity, currency, price timeliness, ESPP discount, disposal logic
- orchestration-log/: per-agent logs (Fury, Banner, Shuri) documenting contributions
- log/: session summary for Fidelity ESPP feasibility probe
- agents/{romanoff,vision,wanda}/history.md: cross-agent heads-up notes - Romanoff: PII redaction for participant number pattern (I + 8 digits) - Vision: frontend components for upload wizard - Wanda: CSS design for file picker, holdings review, buttons


## [20260714] - 2026-07-14

- Show real Indexa portfolio value, contributions, time-weighted (TWR) and money-weighted (XIRR) returns and annualized volatility
- Add an account evolution chart (portfolio vs contributions) with period selector (1M/3M/6M/1Y/years/all) and EUR/% toggle
- Add a monthly returns matrix (month x year) with a benchmark column and a max-drawdown note
- Add asset-class and per-instrument allocation donuts
- Make the holdings table sortable by every column, add a units (participaciones) column, and add info tooltips on gain/loss columns
- Compact "total value" summary box: value, return, contributions and tax withholdings, with TWR/MWR/volatility metrics
- Fix total value showing 0, de-duplicate holdings by ISIN, and fix a 500 error on the portfolio endpoint (benchmark dict handling)
- Merge 7 inbox files into decisions.md (fury plan/review, romanoff security, shuri backend, wanda design, vision frontend, barton findings)
- Resolve inbox (7 files deleted)
- Create orchestration logs for all agents (fury, romanoff, shuri, wanda, vision, barton, rocket) with ISO 8601 UTC timestamps
- Create session log summarizing Phase 2 completion
- decisions.md now 111,277 bytes (Phase 2 architecture + implementation details + security verification + test results)
- Connect an Indexa Capital account via a read-only token through a 4-step wizard (Ajustes -> Conectores)
- Encrypted token storage (Fernet via FINLYTICS_ENCRYPTION_KEY), one connection per account, scoped fail-closed
- Investments page shows live data: value/invested/P&L KPIs, TWR & XIRR, value-over-time chart, asset-allocation donut, holdings table
- New endpoints: validate/connect/list/disconnect connections + aggregated portfolio; dynamic plugin status
- Wire FINLYTICS_ENCRYPTION_KEY through docker-compose; center the manage-connectors CTA label
- Investments nav item + /investments page: KPI placeholders and a holdings empty state with a "manage connectors" CTA
- Plugin catalog under Settings -> Conectores (/settings/connectors) listing coming-soon connectors (Indexa Capital, broker, crypto)
- Backend GET /api/investments/plugins static registry plus normalized InvestmentHolding/InvestmentPortfolio schemas for future phases
- Bilingual ES/EN, dark mode, responsive; API tests included
- Merge 5 inbox decision files into decisions.md (fury, shuri, wanda, vision, barton)
- Delete merged inbox files (no duplicates)
- Create orchestration logs for each agent (2026-07-14T07-52-49Z)
- Create session log: Investments skeleton Phase 1 shipped
- Decision archive gate: 0 bytes → 19369 bytes (under 20480 threshold)
- Inbox processed: 6 files merged & deleted
- No history files summarized (all < 15360 bytes)
- Test results: 43 smoke suite + 6 new investments tests passing


## [20260713] - 2026-07-13

- Replace the Docker-managed `uploads` volume with a bind mount of ${FINLYTICS_DATA_DIR:-./data} to /app/data, and set UPLOAD_DIR to /app/data/uploads, so original statement PDFs live on the host.
- Dockerfile creates /app/data/uploads (owned by uid 1000); .env.example documents FINLYTICS_DATA_DIR (plus the Linux uid-1000 host-perms note); gitignore the local ./data dir.
- Store each imported statement's original PDF on disk under UPLOAD_DIR (/app/data/uploads) as {Account}_{YYYYMM}.pdf (sanitized, latest wins); the relative path is recorded on ImportRun.source_path (migration 0012).
- The PDF is captured at import-confirm time; a failed file write never aborts the import.
- New GET /api/statements/originals and GET /api/statements/original/{id} back a "Download original" button on the /statements month header.


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

