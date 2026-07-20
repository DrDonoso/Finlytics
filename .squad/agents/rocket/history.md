# Rocket — DevOps & Infrastructure

**Owner:** DrDonoso  
**Latest:** 2026-07-16 — Migration head 0015_add_portfolio_cache. 0016 (merchant normalization) reverted. Docker healthy :7777.

For full history, see `history-archive.md`

## 2026-07-20T12:27:03Z: Orchestration Summary

Finanzas/Extractos rework (Vision 3 deliverables) orchestrated by Scribe. Decisions merged, orchestration logs written, git stage staged for selective .squad/ commit only. No app code staging needed — changes already in HEAD (5b934c5).

---

## Learnings

- 2026-07-20: **Finanzas/Extractos rework commit + push (PASS).** Commit `55dee66` — `feat(finanzas/extractos): drill-down transactions table + month-over-month comparison in Extractos`. 9 files staged (types.ts, TransactionsTable.tsx, en/es/index i18n, index.css, FinancesOverviewPage.tsx, StatementsPage.tsx, comparison.ts). Non-fast-forward on push resolved with `git pull --no-rebase origin main` (merged auto-changelog `de70618`); pushed `de70618..5b934c5 main -> main`. Deploy run `29735247108` — `in_progress`. Account: DrDonoso.

- 2026-07-20: **Finanzas arrow removal + Extractos MoM KPI docker rebuild (PASS).** Change: removed KPI variation arrows from Finanzas page; added month-over-month variation to Extractos KPIs — frontend-only, no backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 905 kB chunk warning (pre-existing/OK), CSS `white-space` warning (pre-existing/OK), built in 4.20s.
  2. `docker compose -f docker-compose.local.yml build` — layers 12–14 (frontend/dist copy + entrypoint) invalidated; all Python/pip layers cache-hit. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated; db already healthy (6 days), pgdata volume persisted.
  4. `ps` — api up (10 s), db healthy (5 days).
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  7. API logs — clean startup: alembic at head (no new migrations), seed 0 inserted/0 recolored, notification loop at 300s, no tracebacks.
  - Stack left UP at :7777.

- 2026-07-20: **CategoryMovers reorganization + Finanzas KPI delta fix docker rebuild (PASS).** Change: "Mayores cambios" (CategoryMovers) moved from Finanzas to Extractos; Finanzas KPI delta comparison basis fixed — frontend-only, no backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 905 kB chunk warning (pre-existing/OK), CSS `white-space` warning (pre-existing/OK), built in 14.34s.
  2. `docker compose -f docker-compose.local.yml build` — layers 12–14 (frontend/dist copy + entrypoint) invalidated; all Python/pip layers cache-hit. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated; db already healthy (6 days), pgdata volume persisted.
  4. `ps` — api up (20 s), db healthy (5 days).
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  7. API logs — clean startup: alembic at head (no new migrations), seed 0 inserted/0 recolored, notification loop at 300s, no tracebacks.
  - Stack left UP at :7777.

- 2026-07-20: **Finanzas drill-down transactions table docker rebuild (PASS).** Change: Finanzas page now has a drill-down transactions table (category/merchant/day clicks filter it) + active-filter chips — frontend-only, no backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 904 kB chunk warning (pre-existing/OK), CSS `white-space` warning (pre-existing/OK), built in 27.99s.
  2. `docker compose -f docker-compose.local.yml build` — layers 12–14 (frontend/dist copy + entrypoint) invalidated; all Python/pip layers cache-hit. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated; db already healthy (6 days), pgdata volume persisted.
  4. `ps` — api up (10 s), db healthy (5 days).
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  7. API logs — clean startup: alembic at head (no new migrations), seed 0 inserted/0 recolored, notification loop at 300s, no tracebacks.
  - Stack left UP at :7777.

- 2026-07-20: **CSS-only fix docker rebuild (PASS).** Change: nav chevron hover no longer paints a background box (`index.css`). Frontend-only, no backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 902 kB chunk warning (pre-existing/OK), CSS `white-space` warning (pre-existing/OK), built in 4.35s.
  2. `docker compose -f docker-compose.local.yml build` — layers 12/14 (frontend/dist copy) + 13-14 invalidated; rest from cache. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated (9 s); db already healthy (5 days), pgdata volume persisted.
  4. `ps` — api up (7 s), db healthy.
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  - Stack left UP at :7777.

- 2026-07-20: **Frontend formatting fixes docker rebuild (PASS).** Picked up three frontend-only changes: euro amounts showing 2 decimals (Dashboard + InvestmentSnapshotCard formatters), FinancesOverviewPage all-time "Neto histórico", and nav Finanzas/Inversiones chevron toggle-only split. No backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 902 kB chunk warning (pre-existing/OK), built in 4.71s.
  2. `docker compose -f docker-compose.local.yml build` — only layers 12/14 (frontend/dist copy) + 13-14 invalidated; rest from cache. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated; db already healthy (5 days), pgdata volume persisted.
  4. `ps` — api up (seconds), db healthy.
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  7. API logs — clean startup (`alembic upgrade head` at head, no new migrations), notification loop at 300s, no tracebacks.
  - Stack left UP at :7777.

- 2026-07-17: App log timestamps use a deep-copied uvicorn `LOGGING_CONFIG` with `%(asctime)s ` prepended to `default` and `access` formatters, `datefmt = %Y-%m-%d %H:%M:%S`, and the root logger routed through uvicorn's `default` handler so `finlytics.*` loggers propagate without duplicate lines. Alembic timestamps are configured in `alembic.ini` `[formatter_generic]`; entrypoint messages prefix `date '+%Y-%m-%d %H:%M:%S'`; `seed.py` prepends the same `datetime.now().strftime(...)` value to its top-level print.

- 2026-07-17: **Notifications + Telegram docker verify (PASS).** Local stack (docker-compose.local.yml) builds and boots cleanly with the notifications feature. Verified sequence:
  1. `cd frontend && npm run build` — succeeded (895 kB chunk warning is pre-existing/OK).
  2. `docker compose -f docker-compose.local.yml build` — 13-stage Dockerfile.local built, finlytics 0.1.0 wheel installed.
  3. `docker compose -f docker-compose.local.yml up -d` — api + db both up; db healthy.
  4. Alembic on startup: `Running upgrade 0015 -> 0016, Add notifications tables: notifications, notification_channels, notification_deliveries.` — migration applied.
  5. `Notification loop started (interval=300s)` logged at startup — no tracebacks.
  6. `GET /health` → `{"status":"ok"}` (HTTP 200).
  7. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401** (router registered and auth-gated; not 404).
  - **Env vars needed by the feature** (all have safe defaults; none required for container boot):
    - `NOTIFICATIONS_LOOP_ENABLED` (default `true`) — set `false` to disable the background loop.
    - `NOTIFICATIONS_EVAL_INTERVAL_SECONDS` (default `300`) — detector cycle cadence.
    - `TELEGRAM_SEND_ENABLED` (default `true`) — global kill-switch for Telegram sends.
    - `FINLYTICS_ENCRYPTION_KEY` (already required) — used by Telegram channel token encrypt/decrypt.
  - Stack left UP at :7777 as requested.

- 2026-07-20: **Mobile-UX round docker rebuild (PASS).** Picked up Wanda (mobile KPI layout CSS) + Vision (mobile transaction detail modal, `useIsMobile` hook, i18n) — frontend-only changes, no backend/migration changes.
  1. `cd frontend && npm run build` — 902 modules, 901 kB chunk warning (pre-existing/OK), built in 5.16s.
  2. `docker compose -f docker-compose.local.yml build` — only layers 12/14 (frontend/dist copy) + 13-14 invalidated; rest from cache. Clean.
  3. `docker compose -f docker-compose.local.yml up -d` — api recreated; db already healthy, pgdata volume persisted.
  4. `ps` — api + db up; db healthy.
  5. `GET /health` → `{"status":"ok"}` (HTTP 200).
  6. `GET /api/notifications/unread-count` (no cookie) → **HTTP 401**.
  7. `SELECT count(*) FROM notifications WHERE source='seed'` → **4** (pgdata survived).
  8. API logs — clean startup, no tracebacks, notification loop at 300s running.
  - Stack left UP at :7777.

---

## 2026-07-20T10:41:54+02:00: UI fixes commit + push — euro decimals, historic net, nav chevron

**Commit:** `8c049ef` — `fix(ui): euro decimals on Inicio, historic net on Finanzas, nav chevron`  
**Files:** `InvestmentSnapshotCard.tsx`, `Dashboard.tsx`, `FinancesOverviewPage.tsx`, `Layout.tsx`, `index.css` (5 files, +98/-27)  
**Push result:** SUCCESS — non-fast-forward resolved with `git pull --no-rebase origin main` (merged auto-changelog `6ab9ea5`); pushed `6ab9ea5..92ac3ec main -> main`.  
**Account:** DrDonoso (active via `gh auth switch`).  
**Deploy run:** `29728964427` — `in_progress` at push time.  
**`.squad/` files:** left uncommitted for Scribe (3 history.md files modified).

---

## 2026-07-20T09:55:40+02:00: Full feature push — notifications + Telegram + mobile UX + backup-wizard-v2

**Status:** 3 thematic commits pushed to `main`. Deploy workflow triggered (run 29726359341, in_progress).

**Commit SHAs:**
- `08f3962` — `feat(notifications): backend — detectors, orchestrator, API, Telegram channel` (20 files, +3559/-14)
- `acc34b1` — `feat(frontend): notifications center, Telegram wizard, mobile responsive fixes` (18 files, +2172/-114)
- `86340c8` — `feat(backup): backup wizard v2` (3 files, +899/-118)
- `875abd0` — merge commit integrating CI changelog (`0429011 docs: update changelog for 20260717.05 [skip ci]`) that the remote gained after our local commits were made.

**Push result:** SUCCESS — `0429011..875abd0 main -> main`. Branch up to date with `origin/main`.

**Account:** DrDonoso (active via `gh auth switch`). `git config user.name` = `drdonoso`.

**Note:** Remote was 1 commit ahead (auto-changelog [skip ci]) at push time. Resolved with `git merge origin/main --no-edit` (no rebase, no force-push).

---

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.

---

## 2026-07-20T08:41:54Z: Docker rebuild — UI polish round

**Changes:** Rebuilt with Vision's (euro decimals, all-time net, nav split) + Wanda's (arrow hover) frontend fixes.

**Build:** 
pm run build 902 modules, 5.16s. docker compose build clean; Python layers cache-hit. Stack verified UP.

**Deployed:** Commit 8c049ef (fix(ui)) to main as DrDonoso. CI triggered.

**Merged to:** decisions.md (Rocket Rebuild — Mobile-UX Round).