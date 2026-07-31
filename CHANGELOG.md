# Changelog

All notable changes to Finlytics are documented here.

<!-- releases -->

## [20260731.05] - 2026-07-31

- fix(assistant): follow the UI language in the demo and the tool chips (#45)


## [20260731.04] - 2026-07-31

- fix(llm): stop sending temperature, which newer models reject outright (#44)


## [20260731.03] - 2026-07-31

- feat(assistant): read-only chat assistant over your own financial data (#43)


## [20260731.02] - 2026-07-31

- feat(notifications): route Telegram messages to a forum topic (#42)


## [20260731] - 2026-07-31

- refactor: write the whole codebase in English (#41)
- ci: serialise deploys so concurrent runs stop colliding on the CalVer tag (#40)


## [20260730.08] - 2026-07-30

- fix(logging): flatten user-controlled values before they enter log lines (#39)


## [20260730.07] - 2026-07-30

- fix(rules): bound user-authored rule regexes with a timeout (#38)


## [20260730.06] - 2026-07-30

- fix(notifications): rebuild the Telegram bot token from a fixed alphabet (#36)


## [20260730.05] - 2026-07-30

- The palette, typography and icons now derive from the logo instead of Tailwind's defaults. `slate-100`/`blue-600`/`green-500` shared nothing with the navy-to-teal logo, so the brand stopped at the favicon. Tokens are now `#123a6b -> #21639f -> #12b886`, and the red/green pair becomes teal/terracotta, which also survives colour blindness.
- ~380 emoji replaced by an in-house SVG icon set. Emoji render differently on every OS and inherit neither colour nor size, so the app looked like a different product depending on where it was opened. Geist and Geist Mono are self-hosted (82 KB) rather than loaded from a CDN, because a self-hosted finance app should not phone out to render its own UI.
- The login had no attempt limit: brute-forcing passwords was bounded only by bandwidth. It now allows 10 attempts per window, counted per IP and never per user - per user would let anyone lock a legitimate account out. The IP comes from the connection, not from `X-Forwarded-For`, which is forgeable.
- Reminders used the wrong day for two hours every night. `TIMEZONE` existed in the config and in docker-compose but was read nowhere, so the container evaluated dates in UTC while Madrid was two hours ahead.
- A failure reading investments also hid the bank net worth. One broken data source blanked another that was working; net worth is now computed from whatever resolves, and the missing part is marked as such.
- Stale responses could overwrite fresh ones: 22 of 26 effects were unguarded, so switching months quickly could leave the previous month on screen with no visible error. Requests now go through TanStack Query, where the params are part of the cache key.
- Three CSS rules never applied. `.batch-accordion-chevron.--open` and `.batch-detail-row.--done/--error` required a literal `--open` class while the markup emits the BEM form, so the accordion arrow never turned and detail rows were never coloured.
- The frontend had no linter and no tests while the backend had ruff and 1366 - that asymmetry is where the bugs above were hiding. It now has oxlint (ESLint is not installable here: typescript-eslint refuses TypeScript 7) and 65 tests, both gating CI, plus mypy over the query layer.
- `queries.py` (1175 lines) and `index.css` (7030 lines) split by domain. The query package re-exports through `__init__.py` so the `queries.get_x()` attribute access and the ~250 tests that patch it keep working untouched; the compiled CSS was compared rule by rule before and after and is byte-identical.
- Closed a high-severity CodeQL ReDoS alert in the tag-name emoji split. It was never exploitable in CPython (linear growth up to 8000 characters), but the ambiguous pattern was pointless in something a user types.


## [20260730.04] - 2026-07-30

- wrangler.jsonc documented the deploy command as optional. The docs do call it optional, but the setup form requires it. It now records `npx wrangler@4 deploy` - major pinned because wrangler is deliberately not a devDependency (npm ci also runs in the Docker builds, which never use it), so npx would otherwise pull whatever is latest and a wrangler 5 could break the deploy with no change on our side.
- docker-deploy.yml now ignores frontend/wrangler.jsonc. It is Cloudflare-only config that never reaches the Docker images, so editing it should not cut a release and republish both.


## [20260730.03] - 2026-07-30

- wrangler.jsonc documented the deploy command as optional. The docs do call it optional, but the setup form requires it. It now records `npx wrangler@4 deploy` - major pinned because wrangler is deliberately not a devDependency (npm ci also runs in the Docker builds, which never use it), so npx would otherwise pull whatever is latest and a wrangler 5 could break the deploy with no change on our side.
- docker-deploy.yml now ignores frontend/wrangler.jsonc. It is Cloudflare-only config that never reaches the Docker images, so editing it should not cut a release and republish both.


## [20260730.02] - 2026-07-30

- frontend/wrangler.jsonc for Cloudflare Workers. Pure static, no `main`, so no Worker code runs. `not_found_handling: single-page-application` is the SPA fallback for BrowserRouter routes, and is stricter than a blanket `/* -> /index.html` rewrite: a missing ASSET still returns a real 404 instead of HTML.
- `_redirects` and `_headers` emitted into dist-demo by a vite.config.ts plugin for Pages/Netlify. They are generated rather than committed under public/, because everything in public/ is copied into the PRODUCTION bundle too, where FastAPI serves the SPA and they would be dead weight.


## [20260730] - 2026-07-30

- demo/scenario.ts: seeded generator, 18 months of invented Spanish transactions plus an Indexa portfolio. Dates are relative to today because defaultRange() opens on the previous calendar month - fixed dates would show empty views a month later.
- demo/store.ts: one transaction list feeds the ledger, every aggregate and every tx_count, so an edit is reflected in the KPIs. Filter semantics mirror db/queries.py::_apply_filters (tag = ANY, amount range on absolute value).
- demo/handlers.ts: handlers for the allowlisted routes, plus a catch-all that answers 501 and logs "[demo] Unhandled API request:" so a new endpoint fails loudly instead of silently losing a screen.
- Reduced route surface (DemoRoutes): imports, statements, rules, backup, connectors, Telegram and Fidelity are unrouted and hidden from the sidebar.
- Banner on every page stating the data is fictional and resets on reload.


## [20260729.04] - 2026-07-29

- fix(frontend): restore react-router 8.3.0 and clean the lockfile
- [Release notes](https://github.com/github/codeql-action/releases)
- [Changelog](https://github.com/github/codeql-action/blob/main/CHANGELOG.md)
- [Commits](https://github.com/github/codeql-action/compare/v4...v4.37.1)
- [Release notes](https://github.com/docker/login-action/releases)
- [Commits](https://github.com/docker/login-action/compare/v4...v4.4.0)
- dependency-name: github/codeql-action dependency-version: 4.37.1 dependency-type: direct:production update-type: version-update:semver-minor dependency-group: github-actions-minor-patch
- dependency-name: docker/login-action dependency-version: 4.4.0 dependency-type: direct:production update-type: version-update:semver-minor dependency-group: github-actions-minor-patch
- ci(deploy): only rebuild when the image or compose file changes


## [20260729.03] - 2026-07-29

- fix(frontend): pin deps to versions served by the corporate mirror
- chore(deps): hold Dependabot version updates for 10 days


## [20260729.02] - 2026-07-29

- build(deps): react-router-dom -> react-router 8.3.0, closing GHSA-qwww-vcr4-c8h2


## [20260729] - 2026-07-29

- build(deps): postgres 16 -> 18-alpine, move the data mount


## [20260728.12] - 2026-07-28

- build(deps): vite 6.4.3 -> 8.1.5, fix malformed CSS rule it exposed


## [20260728.11] - 2026-07-28

- [Release notes](https://github.com/microsoft/TypeScript/releases)
- [Commits](https://github.com/microsoft/TypeScript/commits)
- dependency-name: typescript dependency-version: 7.0.2 dependency-type: direct:development update-type: version-update:semver-major


## [20260728.10] - 2026-07-28

- build(deps): vite 5.4.21 -> 6.4.3, closing 5 security advisories


## [20260728.09] - 2026-07-28

- react / react-dom / @types — react-dom 19 requires react 19 and the types must match the runtime. PR #16 is the proof this is the right unit.
- vite / @vitejs/* — the plugin declares a peer dependency on vite.


## [20260728.08] - 2026-07-28

- build(deps): recharts 2.15.4 -> 3.10.1, adapt Tooltip callback signatures


## [20260728.06] - 2026-07-28

- [Release notes](https://github.com/actions/checkout/releases)
- [Changelog](https://github.com/actions/checkout/blob/main/CHANGELOG.md)
- [Commits](https://github.com/actions/checkout/compare/v6...v7)
- [Release notes](https://github.com/actions/setup-python/releases)
- [Commits](https://github.com/actions/setup-python/compare/v6...v7)
- dependency-name: actions/checkout dependency-version: '7' dependency-type: direct:production update-type: version-update:semver-major dependency-group: github-actions
- dependency-name: actions/setup-python dependency-version: '7' dependency-type: direct:production update-type: version-update:semver-major dependency-group: github-actions


## [20260728.05] - 2026-07-28

- base-image bumps (node:20 -> node:26, python:3.12 -> 3.14)
- musl vs glibc — the frontend compiles inside node:alpine and esbuild/rollup ship platform-specific native binaries
- 'alembic upgrade head' and seed.py, which the entrypoint runs on boot
- the SPA actually being built and copied into the image
- /health returns ok
- /api/auth/status responds — a public route that queries the users table, so passing proves DB connectivity and that migrations completed
- /api/version returns 401 — auth is enforced in the shipped image, not just under pytest
- / serves the SPA (asserts div#root from frontend/index.html)
- alembic_version is non-empty and the categories table is seeded


## [20260728.04] - 2026-07-28

- [Release notes](https://github.com/remix-run/react-router/releases)
- [Changelog](https://github.com/remix-run/react-router/blob/react-router-dom@7.18.1/packages/react-router-dom/CHANGELOG.md)
- [Commits](https://github.com/remix-run/react-router/commits/react-router-dom@7.18.1/packages/react-router-dom)
- dependency-name: react-router-dom dependency-version: 7.18.1 dependency-type: direct:production update-type: version-update:semver-patch dependency-group: npm-minor-patch


## [20260728.03] - 2026-07-28

- ci: configure Dependabot properly, add CodeQL and dependency review
- pyproject.toml declared no license and no author, so a built wheel reported an unknown license. Adds PEP 639 license = 'MIT' + license-files, authors, readme, project URLs and trove classifiers (build-system bumped to setuptools>=77 for PEP 639 support). Verified: the wheel now emits 'License-Expression: MIT' and bundles dist-info/licenses/LICENSE.
- frontend/package.json: adds 'license': 'MIT' for consistency (the package is private, so npm did not require it).
- COPY README.md and LICENSE alongside pyproject.toml. Not needed for the build to succeed (verified: it builds fine without them), but without them the installed package carries no LICENSE file — and MIT requires the notice to be included in all copies, which includes the published Docker image.


## [20260728.02] - 2026-07-28

- Fix formatting in dependabot.yml


## [20260728] - 2026-07-28

- security: harden auth secret handling; apply Squad's documented state practices


## [20260723.02] - 2026-07-23

- fix(investments): version the portfolio cache to invalidate stale shapes
- decisions.md: 489,758 → 493,266 bytes
- Archived 9 entries older than 2026-07-16 (7 days prior)
- decisions-archive.md created with 10,547 bytes
- Merged 2 inbox files into decisions.md
- Inbox files deleted (.gitkeep retained)
- Deduplicated new entries
- 2026-07-23T10-48-27Z-shuri.md: Portfolio cache versioning implementation
- 2026-07-23T10-48-27Z-barton.md: 9 comprehensive tests + AsyncMock pattern
- 2026-07-23T10-48-27Z-fury.md: Architecture review + approval
- 2026-07-23T10-48-27Z-cache-versioning.md: Executive summary
- shuri/history.md: Added cache-versioning session ref
- barton/history.md: Added cache-versioning session ref + AsyncMock learning
- fury/history.md: Added cache-versioning session ref + invalidation learnings
- Decisions: 489,758 bytes → 493,266 bytes (after archive + inbox merge)
- Archive: 9 pre-7d entries → decisions-archive.md
- Inbox: 2 files → merged → cleaned
- Histories: All under 15,360 bytes (no summarization needed)
- shuri: 14,567 bytes
- barton: 6,862 bytes
- fury: 10,626 bytes


## [20260723] - 2026-07-23

- Backend: _derive_contribution_events + NormalizedContributionEvent; exposed as contribution_events on GET /api/investments/portfolio (chart series unchanged).
- Frontend: table in IndexaView with signed coloring, type badge, empty state.
- Tests: 30 new (deltas, withdrawal, multi-account, cache round-trip); suite 1356.


## [20260722] - 2026-07-22

- Store MSFT close_usd for every trading day, independent of FX (drop the msft-intersect-fx logic in topup and backfill; forward-fill FX).
- Convert the series to EUR at read time using a single latest EURUSD rate (live snapshot, fallback to last stored). Contributions are already EUR-native.
- period2 = today + 1 day so the current day''s bar is included.
- Auto gap-recovery: backfill when recent Fridays are missing; 90-day lookback.
- decisions.md: merged 3 inbox files (shuri, barton, fury FX-decouple entries)
- orchestration-log: 3 agent logs (shuri backend, barton QA, fury review)
- log: session summary
- cross-agent-pointers: coordination refs
- agent histories: updated with slice work
- deleted inbox files: shuri-fx-decouple.md, barton-fx-decouple-tests.md, fury-fx-decouple-review.md


## [20260721.02] - 2026-07-21

- Migration 0017: add transactions.is_system (default false) and backfill existing opening rows (import_runs.source_filename='manual:saldo-inicial').
- create_opening_balance_tx flags new opening transactions as is_system.
- Aggregations (overview, by category/merchant/month/day/account, cashflow) exclude is_system via a shared _apply_filters(exclude_system=True) parameter.
- The ledger (GET /api/transactions) keeps showing opening rows and exposes is_system; the frontend marks them with a subtle "Sistema" badge. Page totals come from the summary endpoint, so they stay consistent.
- Tests: 15 is_system tests (aggregations excluded, ledger includes, backfill flag); full suite 1290 passing.
- decisions.md: merged 4 inbox files (fury-is-system-review, shuri-is-system-ledger, shuri-is-system, vision-is-system-badge)
- Reconciled Option A (ledger-excludes) superseded by Option B (ledger-includes + badge)
- Marked is_system/KPI-exclusion as IMPLEMENTED + APPROVED (removed pending status)
- Created orchestration-log entries for Shuri, Vision, Barton, Fury (2026-07-21T16-59-22Z)
- Updated agent history files with cross-agent session references
- Summarized Fury history (15804 bytes -> condensed)
- Created session log: .squad/log/2026-07-21T16-59-22Z-is-system-kpi-exclusion.md


## [20260721] - 2026-07-21

- POST /api/accounts: create an account manually with an optional opening balance (creates a synthetic "Saldo inicial" transaction; no migration).
- Import flow: when a statement creates a NEW account, optionally capture the balance just before that statement. The opening date is inferred as the day before the earliest transaction in the statement.
- Merged 3 inbox decisions into decisions.md (Vision drill-down table, CategoryMovers redistribution, Finanzas variation removal)
- Deleted inbox files (decisions/inbox/*.md)
- Wrote orchestration logs for Vision (3 deliverables) and Rocket (rebuild + deploy verification)
- Wrote session log (Finanzas/Extractos rework overview)
- Updated agent history files with orchestration entry
- No summarization needed (Vision: 13.2 KB, Rocket: 11.4 KB, threshold: 15.4 KB)


## [20260720.03] - 2026-07-20

- feat(finanzas/extractos): drill-down transactions table + month-over-month comparison in Extractos
- Remove CategoryMovers from FinancesOverviewPage (was comparing whole multi-month range vs a single previous calendar month — meaningless).
- Add previousEqualRange(from, to) helper in utils/comparison.ts: preceding period of identical day-count, immediately before the range.
- FinancesOverviewPage KPI deltas now use previousEqualRange so a 6-month range compares against the 6 months before it, not just December.
- Add 'vs. periodo anterior' / 'vs. previous period' caption bar at the bottom of the Finanzas header card (kpisPrevPeriodLabel i18n key).
- Add CategoryMovers to StatementsPage (Extractos) with true month-over- month comparison: selected month vs previousCalendarMonth, both scoped to selAccountId. Refetches on month/account/import changes.
- Merged 2 inbox decisions into decisions.md
- Captured Vision fixes (euro decimals, all-time net, nav chevron split)
- Captured Wanda polish (arrow hover background removal)
- Wrote orchestration logs for Vision, Wanda, Rocket
- Updated agent histories
- No history summarization needed (all <15360 bytes)


## [20260720.02] - 2026-07-20

- fix(ui): euro decimals on Inicio, historic net on Finanzas, nav chevron


## [20260720] - 2026-07-20

- feat(backup): backup wizard v2
- feat(frontend): notifications center, Telegram wizard, mobile responsive fixes
- feat(notifications): backend — detectors, orchestrator, API, Telegram channel
- Vision: Conectores restructured (Inversiones/Notificaciones categories), TelegramWizard 4→3 steps, @BotFather link, chat_id validation UI
- Shuri: chat_id integer validator (^-?\d+$, HTTP 422), scripts/seed_notifications.py reusable tool (--push/--clear)
- Rocket (seed): 4 sample notifications seeded to live DB
- Rocket (rebuild): Docker images rebuilt with both Dockerfiles now COPY scripts/ (Ops fix for seed script availability)
- Wanda: Mobile donut CSS fix (max-width 220px→280px at ≤500px, fixes clipping on iPhone 14+ etc.)
- 5 orchestration logs (ISO 8601 UTC timestamps): Vision, Shuri, Rocket×2 (seed+rebuild), Wanda
- 1 session log: notifications-feedback-round summary
- docs: scribe archive backup-wizard-v2 spawn


## [20260717.05] - 2026-07-17

- backend: GET /api/statements/reminder returns { year, month, missing_account_ids } — accounts with prior statement history that are missing the previous completed calendar month (grace 0; established-this-month or no-history accounts are not flagged).
- frontend: a subtle warning marker with a localized portal tooltip ("Falta subir el extracto de {month}") next to each affected account in the Home accounts table.


## [20260717.04] - 2026-07-17

- backend: per-transaction allow_duplicate flag on ExtractedTransaction (carried through /api/imports/confirm). compute_dedup_hash() gains an optional disambiguator (None keeps existing hashes byte-identical); upsert_transactions() hashes a uuid disambiguator for allow_duplicate rows so they get a unique dedup_hash and INSERT instead of being skipped by ON CONFLICT.
- frontend: "No es duplicada / Not a duplicate" control beside the duplicate badge in the import preview; clears the flag, excludes the row from duplicate counts and the flagged-only filter, survives re-checks, and sends allow_duplicate in the confirm payload.


## [20260717.03] - 2026-07-17

- fix(i18n): show localized category label in PreviewTypeahead (rule form + preview)


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

- About page available under Settings > Application, showing the deployed image info
- GET /api/version exposes {version, image_tag, built_at}, consumed by the frontend
- Deploy workflow injects CalVer IMAGE_TAG + BUILD_DATE as build args when building the Docker image
- MIT license (LICENSE) added to the repository
- .dockerignore fixed so frontend/dist/ is included in the production image


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

