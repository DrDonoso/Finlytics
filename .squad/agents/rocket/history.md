# Rocket — DevOps & Infrastructure

**Owner:** DrDonoso  
**Latest:** 2026-07-16 — Migration head 0015_add_portfolio_cache. 0016 (merchant normalization) reverted. Docker healthy :7777.

For full history, see `history-archive.md`

## Learnings

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

## 2026-07-17T13:04:32Z: Notifications + Telegram Feature Session Concluded

**Status:** All deliverables merged into decisions.md and squad log. Test results: 1239 passed, 2 skipped. Docker E2E: PASS. Orchestration logs written.

**Key outcome:** Hybrid notifications model + Telegram channel with Fernet encryption. Backend-owned state. No Critical findings.
