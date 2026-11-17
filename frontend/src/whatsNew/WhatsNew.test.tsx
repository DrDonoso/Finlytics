import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { createQueryClient } from '../api/queryClient'
import { LanguageProvider } from '../i18n'
import { NOTES } from './notes'
import { WhatsNew } from './WhatsNew'

let seen: string[] | null = null
let posts: string[][] = []

const server = setupServer(
  http.get('/api/whats-new', () => HttpResponse.json({ seen })),
  http.post('/api/whats-new/seen', async ({ request }) => {
    const { ids } = (await request.json()) as { ids: string[] }
    posts.push(ids)
    return HttpResponse.json({ seen: ids })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => {
  posts = []
  seen = null
})

const ALL_IDS = NOTES.map((note) => note.id)

function renderNews(allOpen = false) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <LanguageProvider>
        <MemoryRouter>
          <WhatsNew allOpen={allOpen} onAllOpenChange={() => {}} />
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

describe('WhatsNew', () => {
  it('marks every note as read without a dialog for a new user', async () => {
    renderNews()
    await waitFor(() => expect(posts).toEqual([ALL_IDS]))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows what is unread and marks it as read when the dialog closes', async () => {
    seen = []
    renderNews()
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveTextContent(NOTES[0].en.title)
    expect(posts).toEqual([])
    await userEvent.click(screen.getByRole('button', { name: 'Got it!' }))
    await waitFor(() => expect(posts).toEqual([ALL_IDS]))
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('stays quiet when everything is read', async () => {
    seen = ALL_IDS
    renderNews()
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(posts).toEqual([])
  })

  it('lists every note on request', async () => {
    seen = ALL_IDS
    renderNews(true)
    expect(await screen.findByRole('dialog')).toHaveTextContent(NOTES[0].en.title)
  })
})
