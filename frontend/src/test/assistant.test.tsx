/**
 * Finance assistant panel behaviour.
 *
 * Runs against the demo's own MSW handlers rather than a bespoke mock: they
 * already implement the whole SSE contract, so this exercises the real
 * `streamAssistantMessage` reader — the part most likely to break — instead of
 * a stub that agrees with itself.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import AssistantLauncher from '../components/AssistantLauncher'
import AssistantPanel from '../components/AssistantPanel'
import { renderMarkdown } from '../components/AssistantMessage'
import { AssistantProvider } from '../contexts/AssistantContext'
import { handlers } from '../demo/handlers'
import { LanguageProvider } from '../i18n'

const server = setupServer(...handlers)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

function renderAssistant() {
  const client = createQueryClient()
  return render(
    <QueryClientProvider client={client}>
      <LanguageProvider>
        <AssistantProvider>
          <AssistantLauncher />
          <AssistantPanel />
        </AssistantProvider>
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

async function openPanel() {
  const user = userEvent.setup()
  renderAssistant()
  const launcher = await screen.findByRole('button', { name: /asistente|assistant/i })
  await user.click(launcher)
  await screen.findByRole('dialog')
  return user
}

describe('the launcher', () => {
  it('appears when the backend reports the assistant as enabled', async () => {
    renderAssistant()
    expect(await screen.findByRole('button', { name: /asistente|assistant/i })).toBeInTheDocument()
  })

  it('stays hidden when the assistant is unavailable', async () => {
    // A button whose only outcome is a 503 is worse than no button.
    server.use(
      http.get('/api/assistant/status', () =>
        HttpResponse.json({ enabled: false, reason: 'LLM not configured' })),
    )
    const { container } = renderAssistant()

    await waitFor(() => {
      expect(container.querySelector('.assistant-launcher')).toBeNull()
    })
  })
})

describe('the panel', () => {
  it('opens with the suggested prompts on an empty thread', async () => {
    await openPanel()
    const suggestions = await screen.findAllByRole('button', { name: /\?$/ })
    expect(suggestions.length).toBeGreaterThan(0)
  })

  it('closes on Escape', async () => {
    const user = await openPanel()
    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull()
    })
  })

  it('shows the question before any answer arrives', async () => {
    // The stream is held open so the only thing that can be rendering the
    // question is the optimistic turn — waiting for the server to echo it back
    // would make the composer look like it swallowed the message.
    let release: () => void = () => {}
    const held = new Promise<void>(resolve => { release = resolve })

    server.use(
      http.post('/api/assistant/conversations/:id/messages', () =>
        new HttpResponse(
          new ReadableStream({
            async start(controller) {
              await held
              controller.close()
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )),
    )

    const user = await openPanel()
    await user.type(screen.getByRole('textbox'), 'Cuanto gaste el mes pasado')
    void user.click(screen.getByRole('button', { name: /enviar|send/i }))

    expect(await screen.findByText('Cuanto gaste el mes pasado')).toBeInTheDocument()
    release()
  }, 15000)

  it('streams the answer in and keeps the exchange on screen', async () => {
    const user = await openPanel()

    await user.type(screen.getByRole('textbox'), 'Cuanto gaste el mes pasado')
    await user.click(screen.getByRole('button', { name: /enviar|send/i }))

    await waitFor(
      () => {
        // The demo's canned answer is built from the same store the dashboards
        // read, so a rendered reply proves the whole SSE path worked.
        expect(document.querySelectorAll('.assistant-msg--assistant').length).toBeGreaterThan(0)
      },
      { timeout: 5000 },
    )
    expect(screen.getByText('Cuanto gaste el mes pasado')).toBeInTheDocument()
  }, 15000)

  it('surfaces a stream error instead of failing silently', async () => {
    server.use(
      http.post('/api/assistant/conversations/:id/messages', () =>
        new HttpResponse(
          new TextEncoder().encode(
            'event: error\ndata: {"detail":"upstream is down"}\n\n',
          ),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )),
    )
    const user = await openPanel()

    await user.type(screen.getByRole('textbox'), 'hola')
    await user.click(screen.getByRole('button', { name: /enviar|send/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('upstream is down')
  }, 15000)

  it('shows a repeated question rather than mistaking it for the stored one', async () => {
    // Matching pending turns against the whole stored thread would filter this
    // second copy out against its own earlier one, leaving the thread looking
    // like nothing was sent for the entire time the answer streams.
    let releaseSecond: () => void = () => {}
    const secondHeld = new Promise<void>(resolve => { releaseSecond = resolve })
    let streamCall = 0

    const user = await openPanel()

    const send = async () => {
      const button = await screen.findByRole(
        'button', { name: /enviar|send/i }, { timeout: 8000 },
      )
      await user.type(screen.getByRole('textbox'), 'Cuanto gaste')
      await user.click(button)
    }

    // First turn: the demo handler answers and persists it.
    await send()
    await waitFor(
      () => expect(document.querySelectorAll('.assistant-msg--assistant').length)
        .toBeGreaterThan(0),
      { timeout: 8000 },
    )

    // Second turn: held open, so the assertion lands while it is streaming —
    // which is the only window in which the bug is visible.
    server.use(
      http.post('/api/assistant/conversations/:id/messages', () => {
        streamCall++
        return new HttpResponse(
          new ReadableStream({
            async start(controller) {
              controller.enqueue(new TextEncoder().encode(
                'event: token\ndata: {"text":"Streaming."}\n\n',
              ))
              await secondHeld
              controller.close()
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }),
    )

    await send()

    await waitFor(() => {
      expect(streamCall).toBe(1)
      const asked = [...document.querySelectorAll('.assistant-msg--user')]
        .filter(el => el.textContent?.includes('Cuanto gaste'))
      expect(asked).toHaveLength(2)
    }, { timeout: 8000 })

    releaseSecond()
  }, 30000)

  it('drops preamble text when a tool starts, matching what gets stored', async () => {
    // The backend clears any text emitted alongside a tool request before it
    // persists the answer. If the panel kept it, the visible reply would lose
    // its opening line the moment the stored copy arrived.
    //
    // The stream is held open so the assertion lands while the buffer is what
    // is on screen — this stub does not persist, so closing it would hand over
    // to an empty stored copy.
    let release: () => void = () => {}
    const held = new Promise<void>(resolve => { release = resolve })

    server.use(
      http.post('/api/assistant/conversations/:id/messages', () =>
        new HttpResponse(
          new ReadableStream({
            async start(controller) {
              const send = (frame: string) =>
                controller.enqueue(new TextEncoder().encode(frame))
              send('event: token\ndata: {"text":"Let me check that."}\n\n')
              send('event: tool\ndata: {"name":"get_spending_summary","label":"Calculating totals"}\n\n')
              send('event: token\ndata: {"text":"You spent 320,50 EUR."}\n\n')
              await held
              controller.close()
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )),
    )
    const user = await openPanel()

    await user.type(screen.getByRole('textbox'), 'hola')
    void user.click(screen.getByRole('button', { name: /enviar|send/i }))

    await waitFor(() => {
      expect(document.body.textContent).toContain('You spent 320,50 EUR.')
    }, { timeout: 5000 })
    expect(document.body.textContent).not.toContain('Let me check that.')

    release()
  }, 15000)

  it('a stopped turn does not clobber the next one', async () => {
    // The dangerous window is between a turn's stream finishing and its tail
    // completing: Stop() frees the composer immediately, so a replacement turn
    // can start while the old one is still awaiting its refetch. This parks the
    // first turn exactly there, then starts a second one on top of it.
    let releaseFirstStream: () => void = () => {}
    let releaseRefetch: () => void = () => {}
    let releaseSecond: () => void = () => {}
    const firstStreamHeld = new Promise<void>(r => { releaseFirstStream = r })
    const refetchHeld = new Promise<void>(r => { releaseRefetch = r })
    const secondHeld = new Promise<void>(r => { releaseSecond = r })
    let parkRefetch = false
    let streamCall = 0

    server.use(
      http.post('/api/assistant/conversations/:id/messages', () => {
        const isFirst = streamCall++ === 0
        return new HttpResponse(
          new ReadableStream({
            async start(controller) {
              controller.enqueue(new TextEncoder().encode(
                isFirst
                  ? 'event: token\ndata: {"text":"First answer."}\n\n'
                  : 'event: token\ndata: {"text":"Second answer."}\n\n',
              ))
              await (isFirst ? firstStreamHeld : secondHeld)
              controller.close()
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }),
      http.get('/api/assistant/conversations/:id', async ({ params }) => {
        if (parkRefetch) await refetchHeld
        return HttpResponse.json({
          id: Number(params.id), title: 'x',
          created_at: '', updated_at: '', messages: [],
        })
      }),
    )

    const user = await openPanel()

    await user.type(screen.getByRole('textbox'), 'first question')
    void user.click(screen.getByRole('button', { name: /enviar|send/i }))

    await waitFor(() => {
      expect(document.body.textContent).toContain('First answer.')
    }, { timeout: 5000 })

    // Let the first stream finish; its tail then parks on the refetch.
    parkRefetch = true
    releaseFirstStream()
    await new Promise(resolve => setTimeout(resolve, 100))

    await user.click(await screen.findByRole('button', { name: /detener|stop/i }))
    await user.type(screen.getByRole('textbox'), 'second question')
    void user.click(screen.getByRole('button', { name: /enviar|send/i }))

    await waitFor(() => {
      expect(document.body.textContent).toContain('Second answer.')
    }, { timeout: 5000 })

    // Now let the abandoned turn's tail run to completion.
    parkRefetch = false
    releaseRefetch()
    await new Promise(resolve => setTimeout(resolve, 400))

    // Its tail must not have wiped the live turn's buffer, nor freed the
    // composer and left Stop unable to cancel the request still in flight.
    expect(document.body.textContent).toContain('Second answer.')
    expect(screen.getByRole('button', { name: /detener|stop/i })).toBeInTheDocument()

    releaseSecond()
  }, 25000)
})

describe('the markdown renderer', () => {
  it('turns **bold** into a strong element', () => {
    const { container } = render(<div>{renderMarkdown('You spent **320,50 €**.')}</div>)
    expect(container.querySelector('strong')?.textContent).toBe('320,50 €')
  })

  it('groups consecutive dashes into one list', () => {
    const { container } = render(
      <div>{renderMarkdown('Top:\n- Groceries\n- Dining\n\nThat is all.')}</div>,
    )
    expect(container.querySelectorAll('ul')).toHaveLength(1)
    expect(container.querySelectorAll('li')).toHaveLength(2)
    expect(container.querySelectorAll('p')).toHaveLength(2)
  })

  it('never emits raw HTML from model output', () => {
    // LLM output is untrusted and can echo whatever a bank statement contained,
    // so a tag in the text must render as text.
    const { container } = render(
      <div>{renderMarkdown('<img src=x onerror="alert(1)">')}</div>,
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container.textContent).toContain('<img src=x')
  })
})
