/** MSW request handlers for the demo build.
 *
 * These intercept at the network layer, so the demo exercises the *same*
 * `api/client.ts` code path as production — no parallel `if (USE_MOCK)` branch
 * that can drift away from the real one.
 *
 * Only the endpoints reachable from the demo's route allowlist are handled.
 * Anything else hits `unhandledApi` at the bottom, which answers 501 and logs a
 * greppable console error instead of falling through to the static host (which
 * would return `index.html` and blow up as a JSON parse error).
 *
 * ORDER MATTERS: the catch-all must stay last.
 */

import { http, HttpResponse } from 'msw'
import type { Filters } from './store'
import * as store from './store'
import { DEMO_PASSWORD, DEMO_USERNAME } from './config'

// ─── Query-string helpers ─────────────────────────────────────────────────────

function num(value: string | null): number | undefined {
  if (value === null || value.trim() === '') return undefined
  const n = Number(value)
  return Number.isFinite(n) ? n : undefined
}

function str(value: string | null): string | undefined {
  return value === null || value.trim() === '' ? undefined : value
}

/** Reads the shared summary/transaction filter set from a request URL.
 *  Tags arrive as repeated `?tag=` params — see `buildUrl()` in api/client.ts. */
function filtersFrom(request: Request): Filters {
  const q = new URL(request.url).searchParams
  const tags = q.getAll('tag').filter(Boolean)
  return {
    from: str(q.get('from')),
    to: str(q.get('to')),
    day: str(q.get('day')),
    account_id: num(q.get('account_id')),
    category_id: num(q.get('category_id')),
    tags: tags.length > 0 ? tags : undefined,
    flow: str(q.get('flow')),
    description: str(q.get('description')),
    merchant: str(q.get('merchant')),
    amount_min: num(q.get('amount_min')),
    amount_max: num(q.get('amount_max')),
  }
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

/** Session state for the demo. Module-level rather than a cookie: MSW handlers
 *  run in the page, so this survives navigation but resets on reload — which is
 *  exactly the demo's contract (a refresh restores the initial scenario). */
let authenticated = false

const auth = [
  // `initialized: true` keeps SetupPage out of reach: first-run setup creates a
  // real account in production, and there is nothing here to create it in.
  http.get('/api/auth/status', () =>
    HttpResponse.json({ initialized: true, authenticated })),

  http.get('/api/auth/me', () =>
    authenticated
      ? HttpResponse.json({ username: DEMO_USERNAME })
      : HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })),

  // Validates the advertised credentials rather than waving everyone through,
  // so the demo shows the app's real behaviour — including the 401 path.
  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json() as { username?: string; password?: string }
    const ok = body?.username?.trim().toLowerCase() === DEMO_USERNAME
      && body?.password === DEMO_PASSWORD
    if (!ok) {
      return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })
    }
    authenticated = true
    return HttpResponse.json({ username: DEMO_USERNAME, message: 'Login successful' })
  }),

  http.post('/api/auth/logout', () => {
    authenticated = false
    return HttpResponse.json({ message: 'Logged out' })
  }),
]

// ─── Reference data ───────────────────────────────────────────────────────────

const reference = [
  http.get('/api/accounts', () => HttpResponse.json(store.listAccounts())),
  http.get('/api/categories', () => HttpResponse.json(store.listCategories())),
  http.get('/api/tags', () => HttpResponse.json(store.listTags())),
]

// ─── Transactions ─────────────────────────────────────────────────────────────

const transactions = [
  http.get('/api/transactions', ({ request }) => {
    const q = new URL(request.url).searchParams
    return HttpResponse.json(store.listTransactions(filtersFrom(request), {
      limit: num(q.get('limit')),
      offset: num(q.get('offset')),
      sort: str(q.get('sort')),
      order: str(q.get('order')),
    }))
  }),

  // The one write the demo accepts. It mutates the shared store, so the edit is
  // immediately reflected in every KPI and chart — not just in the table row.
  http.patch('/api/transactions/:id', async ({ params, request }) => {
    const id = Number(params.id)
    const patch = await request.json()
    const updated = store.patchTransaction(id, patch as Parameters<typeof store.patchTransaction>[1])
    if (updated === null) {
      return HttpResponse.json({ detail: 'Transaction not found' }, { status: 404 })
    }
    return HttpResponse.json(updated)
  }),
]

// ─── Summaries ────────────────────────────────────────────────────────────────

const summary = [
  http.get('/api/summary/overview', ({ request }) =>
    HttpResponse.json(store.overview(filtersFrom(request)))),

  http.get('/api/summary/by-category', ({ request }) =>
    HttpResponse.json(store.byCategory(filtersFrom(request)))),

  http.get('/api/summary/by-month', ({ request }) =>
    HttpResponse.json(store.byMonth(filtersFrom(request)))),

  http.get('/api/summary/by-account', ({ request }) =>
    HttpResponse.json(store.byAccount(filtersFrom(request)))),

  http.get('/api/summary/by-merchant', ({ request }) =>
    HttpResponse.json(store.byMerchant(filtersFrom(request)))),

  http.get('/api/summary/by-day', ({ request }) =>
    HttpResponse.json(store.byDay(filtersFrom(request)))),

  http.get('/api/summary/cashflow', ({ request }) =>
    HttpResponse.json(store.cashflow(filtersFrom(request)))),

  http.get('/api/summary/months', () => HttpResponse.json(store.summaryMonths())),
]

// ─── Statements ───────────────────────────────────────────────────────────────

const statements = [
  // Statement upload is not part of the demo, so there is never a pending
  // reminder. An empty reminder keeps the Dashboard banner hidden.
  http.get('/api/statements/reminder', () =>
    HttpResponse.json({ year: null, month: null, missing_account_ids: [] })),
]

// ─── Investments ──────────────────────────────────────────────────────────────

const investments = [
  http.get('/api/investments/connections', () => HttpResponse.json(store.connections())),
  http.get('/api/investments/portfolio', () => HttpResponse.json(store.portfolio())),
  http.get('/api/investments/combined-overview', () => HttpResponse.json(store.combinedOverview())),
]

// ─── Notifications ────────────────────────────────────────────────────────────

const notifications = [
  // Deliberately empty: both notification types the backend can emit
  // (statement_missing, espp_overdue) deep-link into routes the demo hides,
  // so emitting them would produce dead ends.
  http.get('/api/notifications', () => HttpResponse.json([])),
  http.get('/api/notifications/unread-count', () => HttpResponse.json({ count: 0 })),
  http.post('/api/notifications/read-all', () => HttpResponse.json({ updated: 0 })),
  http.post('/api/notifications/:id/read', () => new HttpResponse(null, { status: 204 })),
  http.post('/api/notifications/:id/dismiss', () => new HttpResponse(null, { status: 204 })),
]

// ─── Misc ─────────────────────────────────────────────────────────────────────

const misc = [
  http.get('/api/version', () => HttpResponse.json({
    version: __APP_VERSION__,
    image_tag: 'demo',
    built_at: null,
  })),
]

// ─── Catch-all ────────────────────────────────────────────────────────────────

/** Message prefix asserted by the demo smoke check — keep it stable. */
export const UNHANDLED_API_PREFIX = '[demo] Unhandled API request:'

const unhandledApi = http.all('/api/*', ({ request }) => {
  const { pathname } = new URL(request.url)
  console.error(`${UNHANDLED_API_PREFIX} ${request.method} ${pathname}`)
  return HttpResponse.json(
    { detail: `Not available in the demo: ${request.method} ${pathname}` },
    { status: 501 },
  )
})

export const handlers = [
  ...auth,
  ...reference,
  ...transactions,
  ...summary,
  ...statements,
  ...investments,
  ...notifications,
  ...misc,
  unhandledApi,
]
