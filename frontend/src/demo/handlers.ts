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
import { answerFor } from './assistantAnswers'
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

  // Fidelity ESPP — read-only. The CSV import endpoints stay unhandled: they
  // take a file upload and would write, which the demo does not do.
  http.get('/api/investments/fidelity/kpis', () => HttpResponse.json(store.esppKpis())),
  http.get('/api/investments/fidelity/evolution', () => HttpResponse.json(store.esppEvolution())),
  http.get('/api/investments/fidelity/lots', () => HttpResponse.json(store.esppLots())),
  http.get('/api/investments/fidelity/reminder', () => HttpResponse.json(store.esppReminder())),
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

// ─── Finance assistant ────────────────────────────────────────────────────────
//
// There is no model here, so the answers are scripted (see assistantAnswers.ts)
// and the stream is faked with delays. The panel is the most sellable thing in
// the app; leaving it out of the demo, or leaving it visibly broken, would be
// worse than scripting it — as long as the fallback is honest about what it is.

interface DemoConversation {
  id: number
  title: string
  created_at: string
  updated_at: string
  messages: {
    id: number
    role: 'user' | 'assistant'
    content: string
    tool_calls: { name: string; arguments: string; ok: boolean }[] | null
    created_at: string
  }[]
}

// Module-level like `authenticated`: survives navigation, resets on reload,
// which is the demo's contract everywhere else too.
const conversations = new Map<number, DemoConversation>()
let nextConversationId = 1
let nextMessageId = 1

/** Delay between streamed chunks. Long enough to read as typing, short enough
 *  that a visitor does not think it has hung. */
const TOKEN_DELAY_MS = 18
const TOOL_DELAY_MS = 420

function sseFrame(event: string, payload: unknown): Uint8Array {
  return new TextEncoder().encode(
    `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`,
  )
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

/** Split an answer into word-sized chunks so it arrives like real token output. */
function chunksOf(text: string): string[] {
  return text.split(/(\s+)/).filter(chunk => chunk !== '')
}

const assistant = [
  http.get('/api/assistant/status', () =>
    HttpResponse.json({ enabled: true, reason: null })),

  http.get('/api/assistant/suggestions', () =>
    HttpResponse.json({
      suggestions: [
        'assistant.suggestion.spendingLastMonth',
        'assistant.suggestion.biggestCategory',
        'assistant.suggestion.compareQuarters',
        'assistant.suggestion.subscriptions',
        'assistant.suggestion.whereToCut',
        'assistant.suggestion.investProjection',
      ],
    })),

  http.get('/api/assistant/conversations', () =>
    HttpResponse.json(
      [...conversations.values()]
        // The list endpoint returns headers only; the underscore marks the
        // destructured `messages` as deliberately discarded.
        .map(({ messages: _messages, ...header }) => header)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    )),

  http.post('/api/assistant/conversations', () => {
    const now = new Date().toISOString()
    const conversation: DemoConversation = {
      id: nextConversationId++,
      title: '',
      created_at: now,
      updated_at: now,
      messages: [],
    }
    conversations.set(conversation.id, conversation)
    const { messages: _messages, ...header } = conversation
    return HttpResponse.json(header, { status: 201 })
  }),

  http.get('/api/assistant/conversations/:id', ({ params }) => {
    const conversation = conversations.get(Number(params.id))
    if (!conversation) {
      return HttpResponse.json({ detail: 'Conversation not found' }, { status: 404 })
    }
    return HttpResponse.json(conversation)
  }),

  http.delete('/api/assistant/conversations/:id', ({ params }) => {
    conversations.delete(Number(params.id))
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/assistant/conversations/:id/messages', async ({ params, request }) => {
    const conversation = conversations.get(Number(params.id))
    if (!conversation) {
      return HttpResponse.json({ detail: 'Conversation not found' }, { status: 404 })
    }

    const body = await request.json() as { content?: string }
    const question = (body?.content ?? '').trim()
    const answer = answerFor(question)

    const now = new Date().toISOString()
    conversation.messages.push({
      id: nextMessageId++,
      role: 'user',
      content: question,
      tool_calls: null,
      created_at: now,
    })
    if (!conversation.title) {
      conversation.title = question.length > 60 ? `${question.slice(0, 59)}…` : question
    }
    conversation.updated_at = now

    const stream = new ReadableStream({
      async start(controller) {
        for (const tool of answer.tools) {
          controller.enqueue(sseFrame('tool', tool))
          await sleep(TOOL_DELAY_MS)
        }
        for (const chunk of chunksOf(answer.text)) {
          controller.enqueue(sseFrame('token', { text: chunk }))
          await sleep(TOKEN_DELAY_MS)
        }

        const stored = {
          id: nextMessageId++,
          role: 'assistant' as const,
          content: answer.text,
          tool_calls: answer.tools.map(t => ({ name: t.name, arguments: '{}', ok: true })),
          created_at: new Date().toISOString(),
        }
        conversation.messages.push(stored)
        conversation.updated_at = stored.created_at

        controller.enqueue(
          sseFrame('done', { message_id: stored.id, title: conversation.title }),
        )
        controller.close()
      },
    })

    return new HttpResponse(stream, {
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
      },
    })
  }),
]

// ─── Mortgage ─────────────────────────────────────────────────────────────────
//
// The demo scenario includes a fixed-rate mortgage, so these serve the same
// payloads the API would. Writes stay unhandled: the demo is read-only.

const mortgage = [
  http.get('/api/mortgages', () => HttpResponse.json(store.mortgages())),
  http.get('/api/mortgages/net-worth', () => HttpResponse.json(store.mortgageNetWorth())),
  http.get('/api/mortgages/:id/overview', () => HttpResponse.json(store.mortgageOverview())),
  http.get('/api/mortgages/:id/schedule', () => HttpResponse.json(store.mortgageSchedule())),
  http.get('/api/mortgages/:id/charts', () => HttpResponse.json(store.mortgageCharts())),
  http.get('/api/mortgages/:id/reconciliation', () => HttpResponse.json(store.mortgageReconciliation())),
  http.post('/api/mortgages/:id/simulate', async ({ request }) => {
    const body = await request.json() as Parameters<typeof store.simulateMortgagePrepayment>[0]
    return HttpResponse.json(store.simulateMortgagePrepayment(body))
  }),
  http.get('/api/mortgages/:id', () => HttpResponse.json(store.mortgage())),
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
  ...assistant,
  ...mortgage,
  ...misc,
  unhandledApi,
]
