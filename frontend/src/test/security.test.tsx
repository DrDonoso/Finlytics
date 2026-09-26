/** The Security settings page: password change and "sign out other devices".
 *
 * Driven through MSW so the real client path runs, including which failures
 * reach the global 401 handler: a wrong current password must NOT sign the
 * user out (it is a 400 for that reason), while an ended session must.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { registerOn401Handler } from '../api/client'
import { LanguageProvider } from '../i18n'
import SecurityPage from '../pages/SecurityPage'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ username: 'drdonoso' }),
}))

let passwordBodies: unknown[] = []
let logoutOthersCalls = 0
const on401 = vi.fn()

const server = setupServer(
  http.post('/api/auth/password', async ({ request }) => {
    passwordBodies.push(await request.json())
    return HttpResponse.json({ message: 'Password changed' })
  }),
  http.post('/api/auth/logout-others', () => {
    logoutOthersCalls += 1
    return HttpResponse.json({ message: 'Other sessions signed out' })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => {
  server.close()
  registerOn401Handler(() => {})
})
beforeEach(() => {
  passwordBodies = []
  logoutOthersCalls = 0
  on401.mockReset()
  registerOn401Handler(on401)
  localStorage.setItem('finlytics_lang', 'en')
})
afterEach(() => {
  server.resetHandlers()
  localStorage.clear()
})

function renderPage() {
  return render(<LanguageProvider><SecurityPage /></LanguageProvider>)
}

async function submitPasswordForm(current: string, next: string, confirm = next) {
  const user = userEvent.setup()
  await user.type(screen.getByLabelText('Current password'), current)
  await user.type(screen.getByLabelText('New password'), next)
  await user.type(screen.getByLabelText('Repeat the new password'), confirm)
  await user.click(screen.getByRole('button', { name: 'Change password' }))
}

describe('changing the password', () => {
  it('sends the current and new password, then clears the form', async () => {
    renderPage()
    await submitPasswordForm('old-password', 'a-new-password')

    expect(await screen.findByRole('status')).toHaveTextContent('Password changed.')
    expect(passwordBodies).toEqual([
      { current_password: 'old-password', new_password: 'a-new-password' },
    ])
    expect(screen.getByLabelText('Current password')).toHaveValue('')
    expect(screen.getByLabelText('New password')).toHaveValue('')
    expect(screen.getByLabelText('Repeat the new password')).toHaveValue('')
  })

  it('checks the confirmation before sending anything', async () => {
    renderPage()
    await submitPasswordForm('old-password', 'a-new-password', 'a-new-passwrod')

    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.')
    expect(passwordBodies).toEqual([])
  })

  it('checks the minimum length before sending anything', async () => {
    renderPage()
    await submitPasswordForm('old-password', 'short')

    expect(screen.getByRole('alert')).toHaveTextContent('at least 8 characters')
    expect(passwordBodies).toEqual([])
  })

  it('reports a wrong current password without signing the user out', async () => {
    server.use(http.post('/api/auth/password', () =>
      HttpResponse.json({ detail: 'Current password is incorrect' }, { status: 400 })))
    renderPage()
    await submitPasswordForm('not-my-password', 'a-new-password')

    expect(await screen.findByRole('alert')).toHaveTextContent('The current password is incorrect.')
    expect(on401).not.toHaveBeenCalled()
    expect(screen.getByLabelText('New password')).toHaveValue('a-new-password')
  })

  it('says how long to wait once attempts are exhausted', async () => {
    server.use(http.post('/api/auth/password', () =>
      HttpResponse.json(
        { detail: 'Too many attempts' },
        { status: 429, headers: { 'Retry-After': '180' } },
      )))
    renderPage()
    await submitPasswordForm('not-my-password', 'a-new-password')

    expect(await screen.findByRole('alert')).toHaveTextContent('wait 3 minutes')
  })

  it('signs out when the session itself has ended', async () => {
    server.use(http.post('/api/auth/password', () =>
      HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })))
    renderPage()
    await submitPasswordForm('old-password', 'a-new-password')

    await waitFor(() => expect(on401).toHaveBeenCalledTimes(1))
  })
})

describe('signing out other devices', () => {
  it('asks the server to end every other session', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Sign out of other devices' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Signed out of all other devices.')
    expect(logoutOthersCalls).toBe(1)
  })

  it('reports a failure instead of claiming success', async () => {
    server.use(http.post('/api/auth/logout-others', () =>
      HttpResponse.json({ detail: 'boom' }, { status: 500 })))
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('button', { name: 'Sign out of other devices' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Unexpected error. Please try again.')
    expect(screen.queryByRole('status')).toBeNull()
  })
})
