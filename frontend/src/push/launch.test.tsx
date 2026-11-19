import { QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import { NotificationsProvider } from '../contexts/NotificationsContext'
import { consumeLaunchIntent, takeLaunchIntent } from './launch'

let read: number[] = []

const server = setupServer(
  http.get('/api/notifications', () => HttpResponse.json([])),
  http.get('/api/notifications/unread-count', () => HttpResponse.json({ count: 0 })),
  http.post('/api/notifications/:id/read', ({ params }) => {
    read.push(Number(params.id))
    return new HttpResponse(null, { status: 204 })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => {
  server.resetHandlers()
  read = []
  consumeLaunchIntent()
})

function opened(href: string) {
  const history = { state: { from: 'push' }, replaceState: vi.fn() }
  takeLaunchIntent({ href } as Location, history as unknown as History)
  return history.replaceState
}

describe('the alerts a push notification told', () => {
  it('are taken out of the address, keeping the rest of it, and handed over once', () => {
    const replaceState = opened('https://finlytics.example/finances?account_id=3&notif=12,13,x,-1#top')
    expect(replaceState).toHaveBeenCalledWith({ from: 'push' }, '', '/finances?account_id=3#top')
    expect(consumeLaunchIntent()).toEqual([12, 13])
    expect(consumeLaunchIntent()).toEqual([])
  })

  it('leave an address without them untouched', () => {
    expect(opened('https://finlytics.example/finances?account_id=3')).not.toHaveBeenCalled()
    expect(consumeLaunchIntent()).toEqual([])
  })

  it('are marked as read once the user is in', async () => {
    opened('https://finlytics.example/?notif=5,6')
    const client = createQueryClient()
    render(
      <QueryClientProvider client={client}>
        <NotificationsProvider><div /></NotificationsProvider>
      </QueryClientProvider>,
    )
    await waitFor(() => expect(read.sort()).toEqual([5, 6]))
  })
})
