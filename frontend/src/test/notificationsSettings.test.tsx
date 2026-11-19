import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import type { NotificationPreference, PushConfig, PushSubscriptionPayload, PushTestResult } from '../api/types'
import { ToastProvider } from '../contexts/ToastContext'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'
import NotificationsSettingsPage from '../pages/NotificationsSettingsPage'
import { PushProvider } from '../push/PushContext'
import { base64UrlBytes } from '../push/support'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    loading: false, initialized: true, authenticated: true, username: 'owner',
    onSetupSuccess: vi.fn(), onLoginSuccess: vi.fn(), onLogout: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

// The server's push key, and the one it had before a new AUTH_SECRET.
const KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U'
const OLD_KEY = 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM'
const ENDPOINT = 'https://web.push.apple.com/QGuQyavXutnMH'
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1'

class FakeSubscription {
  readonly endpoint: string
  readonly options: { applicationServerKey: ArrayBuffer | null }
  readonly unsubscribe: () => Promise<boolean>

  constructor(browser: FakeBrowser, endpoint: string, key: string) {
    this.endpoint = endpoint
    this.options = { applicationServerKey: base64UrlBytes(key).buffer }
    this.unsubscribe = vi.fn(async () => {
      browser.subscription = null
      return true
    })
  }

  toJSON() {
    return { endpoint: this.endpoint, expirationTime: null, keys: { p256dh: 'BBrowserKey', auth: 'AuthSecret' } }
  }
}

interface FakeBrowserOptions {
  /** `Notification.permission` before asking. */
  permission?: NotificationPermission
  /** What the user answers when asked. */
  answer?: NotificationPermission
  /** The key of a subscription the browser already has. */
  subscribedWith?: string
}

/** A browser with service workers and the Push API (jsdom has neither). */
class FakeBrowser {
  subscription: FakeSubscription | null = null
  readonly notification: { permission: NotificationPermission; requestPermission: () => Promise<NotificationPermission> }
  readonly subscribe = vi.fn(async ({ applicationServerKey }: { applicationServerKey: Uint8Array }) => {
    const key = btoa(String.fromCharCode(...applicationServerKey)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    this.subscription = new FakeSubscription(this, `${ENDPOINT}-${key.slice(-6)}`, key)
    return this.subscription
  })
  readonly register = vi.fn(async () => this.registration)
  readonly registration = {
    pushManager: { getSubscription: async () => this.subscription, subscribe: this.subscribe },
  }

  constructor({ permission = 'default', answer = 'granted', subscribedWith }: FakeBrowserOptions = {}) {
    if (subscribedWith) this.subscription = new FakeSubscription(this, ENDPOINT, subscribedWith)
    const notification = {
      permission,
      requestPermission: vi.fn(async () => {
        notification.permission = answer
        return answer
      }),
    }
    this.notification = notification
    vi.stubGlobal('Notification', notification)
    vi.stubGlobal('PushManager', {})
    vi.stubGlobal('isSecureContext', true)
    Object.defineProperty(navigator, 'serviceWorker', {
      configurable: true,
      value: { register: this.register, ready: Promise.resolve(this.registration), getRegistration: async () => this.registration },
    })
  }
}

function fakeBrowser(options: FakeBrowserOptions = {}): FakeBrowser {
  return new FakeBrowser(options)
}

let config: PushConfig
let preferences: NotificationPreference[]
let testResult: PushTestResult
let sent: {
  registered: PushSubscriptionPayload[]
  removed: unknown[]
  tested: unknown[]
  chosen: unknown[]
}

/** FastAPI does not parse the browser's text/plain body as JSON. */
function notJson(request: Request) {
  return request.headers.get('Content-Type') !== 'application/json'
    ? HttpResponse.json({ detail: 'Expected a JSON request body.' }, { status: 422 })
    : null
}

const server = setupServer(
  http.get('/api/push', () => HttpResponse.json(config)),
  http.put('/api/push/subscription', async ({ request }) => {
    const refused = notJson(request)
    if (refused) return refused
    sent.registered.push(await request.json() as PushSubscriptionPayload)
    return new HttpResponse(null, { status: 204 })
  }),
  http.post('/api/push/unsubscribe', async ({ request }) => {
    const refused = notJson(request)
    if (refused) return refused
    sent.removed.push(await request.json())
    return new HttpResponse(null, { status: 204 })
  }),
  http.post('/api/push/test', async ({ request }) => {
    const refused = notJson(request)
    if (refused) return refused
    sent.tested.push(await request.json())
    return HttpResponse.json(testResult)
  }),
  http.get('/api/notifications/preferences', () => HttpResponse.json(preferences)),
  http.patch('/api/notifications/preferences', async ({ request }) => {
    const refused = notJson(request)
    if (refused) return refused
    const change = await request.json() as NotificationPreference
    sent.chosen.push(change)
    preferences = preferences.map(p => (p.source === change.source ? change : p))
    return HttpResponse.json(preferences)
  }),
  http.get('/api/notifications/channels', () => HttpResponse.json([])),
  http.get('/api/notifications/import-summary-settings', () => HttpResponse.json({
    enabled: false, channel_id: null, language: 'en', ai_available: true,
  })),
  http.get('/api/notifications/import-summaries', () => HttpResponse.json([])),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  config = { public_key: KEY }
  preferences = [{ source: 'statement', enabled: true }, { source: 'espp', enabled: true }]
  testResult = { ok: true, error: null }
  sent = { registered: [], removed: [], tested: [], chosen: [] }
  localStorage.setItem('finlytics_lang', 'en')
})
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
  vi.unstubAllGlobals()
  Reflect.deleteProperty(navigator, 'serviceWorker')
  Reflect.deleteProperty(navigator, 'userAgent')
})

function renderPage() {
  const client = createQueryClient()
  client.setDefaultOptions({ queries: { retry: false } })
  render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <ToastProvider>
          <PushProvider>
            <MemoryRouter>
              <NotificationsSettingsPage />
            </MemoryRouter>
          </PushProvider>
        </ToastProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

describe('push notifications on this device', () => {
  it('turns them on, sends a test and turns them off', async () => {
    const browser = fakeBrowser()
    const user = userEvent.setup()
    renderPage()

    const toggle = await screen.findByRole('checkbox', { name: en.pushSwitch })
    expect(toggle).not.toBeChecked()
    await user.click(toggle)

    expect(await screen.findByText(en.pushEnabled)).toBeInTheDocument()
    expect(browser.notification.requestPermission).toHaveBeenCalledOnce()
    expect(browser.register).toHaveBeenCalledWith('/sw.js')
    expect(browser.subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: base64UrlBytes(KEY) })
    const endpoint = browser.subscription?.endpoint
    expect(sent.registered).toEqual([{ endpoint, keys: { p256dh: 'BBrowserKey', auth: 'AuthSecret' }, locale: 'en' }])
    expect(localStorage.getItem('finlytics_push')).toBe('owner')
    expect(toggle).toBeChecked()

    await user.click(screen.getByRole('button', { name: en.pushTest }))
    expect(await screen.findByText(en.pushTestSent)).toBeInTheDocument()
    expect(sent.tested).toEqual([{ endpoint }])

    await user.click(toggle)
    await waitFor(() => expect(toggle).not.toBeChecked())
    expect(sent.removed).toEqual([{ endpoint }])
    expect(browser.subscription).toBeNull()
    expect(localStorage.getItem('finlytics_push')).toBeNull()
    expect(screen.queryByRole('button', { name: en.pushTest })).toBeNull()
  })

  it('says why a test did not go out', async () => {
    localStorage.setItem('finlytics_push', 'owner')
    fakeBrowser({ permission: 'granted', subscribedWith: KEY })
    testResult = { ok: false, error: 'unreachable' }
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('button', { name: en.pushTest }))
    expect(await screen.findByText(en.pushTestErrors.unreachable)).toBeInTheDocument()
  })

  it('stays off when the permission is refused, and then says where to allow them', async () => {
    fakeBrowser({ answer: 'denied' })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole('checkbox', { name: en.pushSwitch }))
    expect(await screen.findByText(en.pushStatus.denied)).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: en.pushSwitch })).toBeNull()
    expect(sent.registered).toEqual([])
  })

  it.each([
    ['unavailable', () => { fakeBrowser(); config = { public_key: null } }],
    ['insecure', () => { fakeBrowser(); vi.stubGlobal('isSecureContext', false) }],
    ['install', () => {
      vi.stubGlobal('isSecureContext', true)
      Object.defineProperty(navigator, 'userAgent', { configurable: true, value: IPHONE })
    }],
    ['unsupported', () => { vi.stubGlobal('isSecureContext', true) }],
  ] as const)('explains why they cannot be turned on here: %s', async (status, arrange) => {
    arrange()
    renderPage()
    expect(await screen.findByText(en.pushStatus[status])).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: en.pushSwitch })).toBeNull()
  })

  it('registers this device again on open, with a new subscription when the server’s key changed', async () => {
    localStorage.setItem('finlytics_push', 'owner')
    const browser = fakeBrowser({ permission: 'granted', subscribedWith: OLD_KEY })
    const old = browser.subscription
    renderPage()

    await waitFor(() => expect(sent.registered).toHaveLength(1))
    expect(old?.unsubscribe).toHaveBeenCalledOnce()
    expect(sent.removed).toEqual([{ endpoint: ENDPOINT }])
    expect(browser.subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: base64UrlBytes(KEY) })
    expect(sent.registered[0].endpoint).toBe(browser.subscription?.endpoint)
    expect(browser.notification.requestPermission).not.toHaveBeenCalled()
    expect(await screen.findByRole('checkbox', { name: en.pushSwitch })).toBeChecked()
  })

  it('leaves the registration alone when another user turned them on in this browser', async () => {
    localStorage.setItem('finlytics_push', 'someone-else')
    fakeBrowser({ permission: 'granted', subscribedWith: KEY })
    renderPage()

    expect(await screen.findByRole('checkbox', { name: en.pushSwitch })).not.toBeChecked()
    expect(sent.registered).toEqual([])
  })
})

describe('the alert types sent by push and Telegram', () => {
  it('saves each choice at once', async () => {
    const user = userEvent.setup()
    renderPage()

    const espp = await screen.findByRole('checkbox', { name: en.notifTypes.espp.label })
    const statement = screen.getByRole('checkbox', { name: en.notifTypes.statement.label })
    expect(espp).toBeChecked()
    expect(espp).toHaveAccessibleDescription(en.notifTypes.espp.description)

    await user.click(espp)
    await waitFor(() => expect(sent.chosen).toEqual([{ source: 'espp', enabled: false }]))
    await waitFor(() => expect(espp).not.toBeChecked())
    expect(statement).toBeChecked()
  })

  it('keeps the Telegram channel and the import summaries next to them', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: en.notifSettingsTelegramLabel })).toBeInTheDocument()
    expect((await screen.findAllByRole('button', { name: en.notifSettingsConnectBtn })).length).toBeGreaterThan(0)
    expect(await screen.findByRole('heading', { name: en.importSummaryTitle })).toBeInTheDocument()
  })
})
