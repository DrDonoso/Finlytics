/** Guarantees of the react-query data layer that a component test would not
 *  notice by itself: a badge that disagrees with its dropdown, a count left over
 *  from an earlier keystroke, or one user's cached figures surviving into the
 *  next session. None of these throw — they just show the wrong number.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import type { NotificationOut } from '../api/types'
import RuleFormModal from '../components/RuleFormModal'
import { AuthProvider, useAuth } from '../contexts/AuthContext'
import { NotificationsProvider, useNotifications } from '../contexts/NotificationsContext'
import { LanguageProvider } from '../i18n'
import en from '../i18n/en'

const client = vi.hoisted(() => ({
  previewRule: vi.fn(),
  getNotifications: vi.fn(),
  getUnreadCount: vi.fn(),
  getAuthStatus: vi.fn(),
  getMe: vi.fn(),
  logout: vi.fn(),
  registerOn401Handler: vi.fn(),
}))

vi.mock('../api/client', async importOriginal => ({
  ...(await importOriginal<object>()),
  ...client,
}))

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.setItem('finlytics_lang', 'en')
})

afterEach(() => localStorage.clear())

function renderWithClient(ui: ReactNode, queryClient = createQueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>{ui}</LanguageProvider>
    </QueryClientProvider>,
  )
  return queryClient
}

describe('the notifications badge', () => {
  function notification(id: number, read = false): NotificationOut {
    return {
      id, source: 'test', type: 'test', severity: 'info',
      title_key: 'x', title_args: {}, body_key: null, body_args: null,
      action_link: null, created_at: '2026-01-01T00:00:00Z',
      read_at: read ? '2026-01-02T00:00:00Z' : null, dismissed_at: null,
    }
  }

  function Badge() {
    const { unreadCount, notifications } = useNotifications()
    return <span data-testid="badge">{unreadCount}/{notifications.length}</span>
  }

  it('refetches the list when the polled count disagrees with it', async () => {
    client.getNotifications
      .mockResolvedValueOnce([notification(1)])
      .mockResolvedValue([notification(1), notification(2)])
    client.getUnreadCount.mockResolvedValue({ count: 2 })

    renderWithClient(<NotificationsProvider><Badge /></NotificationsProvider>)

    // The badge follows the list, so it only moves once the dropdown has the new item too.
    await waitFor(() => expect(screen.getByTestId('badge')).toHaveTextContent('2/2'))
    expect(client.getNotifications).toHaveBeenCalledTimes(2)
  })

  it('does not refetch the list while the count agrees with it', async () => {
    client.getNotifications.mockResolvedValue([notification(1), notification(2, true)])
    client.getUnreadCount.mockResolvedValue({ count: 1 })

    renderWithClient(<NotificationsProvider><Badge /></NotificationsProvider>)

    await waitFor(() => expect(client.getUnreadCount).toHaveBeenCalled())
    await new Promise(r => setTimeout(r, 50))
    expect(screen.getByTestId('badge')).toHaveTextContent('1/2')
    // Listing runs every detector and writes to the database, so it is not what gets polled.
    expect(client.getNotifications).toHaveBeenCalledTimes(1)
  })
})

describe('the rule preview', () => {
  it('drops the previous count as soon as the conditions change', async () => {
    const pending = new Map<string, (value: { count: number }) => void>()
    client.previewRule.mockImplementation((rule: { description_value: string }) =>
      rule.description_value === 'amazon'
        ? Promise.resolve({ count: 5 })
        : new Promise(resolve => { pending.set(rule.description_value, resolve) }),
    )
    const user = userEvent.setup()
    renderWithClient(
      <RuleFormModal categories={[]} availableTags={[]} onSave={vi.fn()} onClose={vi.fn()} />,
    )

    const pattern = screen.getByPlaceholderText(en.rulesFieldDescValuePlaceholder)
    await user.type(pattern, 'amazon')
    expect(
      await screen.findByRole('checkbox', { name: en.rulesApplyCheckbox(5) }, { timeout: 3000 }),
    ).toBeInTheDocument()

    await user.type(pattern, 'x')
    // Offering to apply the rule to 5 transactions would now be a claim about a different rule.
    expect(screen.queryByRole('checkbox', { name: en.rulesApplyCheckbox(5) })).toBeNull()
    expect(screen.getByText(en.rulesPreviewLoading)).toBeInTheDocument()

    await waitFor(() => expect(pending.has('amazonx')).toBe(true), { timeout: 3000 })
    act(() => pending.get('amazonx')?.({ count: 2 }))
    expect(await screen.findByRole('checkbox', { name: en.rulesApplyCheckbox(2) })).toBeInTheDocument()
  })
})

describe('ending a session', () => {
  function Session() {
    const { authenticated, onLogout } = useAuth()
    return (
      <>
        <span data-testid="session">{authenticated ? 'in' : 'out'}</span>
        <button type="button" onClick={() => void onLogout()}>logout</button>
      </>
    )
  }

  async function renderSignedIn() {
    client.getAuthStatus.mockResolvedValue({ initialized: true, authenticated: true })
    client.getMe.mockResolvedValue({ username: 'owner' })
    client.logout.mockResolvedValue(undefined)

    const queryClient = renderWithClient(<AuthProvider><Session /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('in'))
    queryClient.setQueryData(['summary', 'overview'], { total_expense: 1234 })
    return queryClient
  }

  it('drops every cached response on logout', async () => {
    const user = userEvent.setup()
    const queryClient = await renderSignedIn()

    await user.click(screen.getByRole('button', { name: 'logout' }))

    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('out'))
    expect(queryClient.getQueryData(['summary', 'overview'])).toBeUndefined()
  })

  it('drops every cached response when the session expires', async () => {
    const queryClient = await renderSignedIn()
    const on401 = client.registerOn401Handler.mock.lastCall?.[0] as () => void

    act(() => on401())

    await waitFor(() => expect(screen.getByTestId('session')).toHaveTextContent('out'))
    expect(queryClient.getQueryData(['summary', 'overview'])).toBeUndefined()
  })
})
