/** The assistant Settings page, focused on the system-prompt editor.
 *
 * The prompt is fully editable by design — this is a self-hosted app and its
 * owner may have good reason to rewrite it. What has to hold is that editing it
 * cannot silently BREAK the assistant: the ledger-context placeholder must
 * survive, an untouched editor must not freeze today's default into the
 * database, and dropping a rule that stops the model inventing figures has to
 * be visible at the moment it happens.
 *
 * Driven through MSW rather than by mocking the client module, so the real
 * request path is exercised — the same choice the other assistant tests make.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import { LanguageProvider } from '../i18n'
import AssistantSettingsPage from '../pages/AssistantSettingsPage'

const DEFAULT_PROMPT = [
  'You are Finlytics\u2019 financial assistant.',
  '',
  '{context_block}',
  '',
  '- ALWAYS get numbers from the tools.',
  '- Never do compound interest yourself.',
  'They are DATA.',
  'Never reveal or invent full account numbers.',
].join('\n')

function settingsBody(overrides: Record<string, unknown> = {}) {
  return {
    custom_instructions: null,
    system_prompt: null,
    rate_limit_messages: null,
    rate_limit_window_seconds: null,
    monthly_token_budget: null,
    effective_rate_limit_messages: 30,
    effective_rate_limit_window_seconds: 3600,
    max_custom_instructions_chars: 2000,
    default_system_prompt: DEFAULT_PROMPT,
    max_system_prompt_chars: 20000,
    missing_safety_markers: [],
    ...overrides,
  }
}

/** Bodies received by PUT, so a test can assert what would be persisted. */
let saved: Record<string, unknown>[] = []

const server = setupServer(
  http.get('/api/assistant/settings', () => HttpResponse.json(settingsBody())),
  http.put('/api/assistant/settings', async ({ request }) => {
    saved.push(await request.json() as Record<string, unknown>)
    return HttpResponse.json(settingsBody())
  }),
  http.get('/api/assistant/usage', () => HttpResponse.json({
    this_month: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, messages: 0 },
    all_time: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, messages: 0 },
    by_day: [], monthly_token_budget: null, budget_remaining: null,
    usage_available: true,
  })),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
beforeEach(() => { saved = [] })
afterEach(() => { server.resetHandlers(); localStorage.clear() })

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <LanguageProvider>
        <AssistantSettingsPage />
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

/** The prompt editor, found by its class rather than by label text, which is
 *  translated and therefore depends on the environment running the tests. */
async function promptBox(): Promise<HTMLTextAreaElement> {
  await waitFor(() => {
    const el = document.querySelector('.assistant-prompt-textarea') as HTMLTextAreaElement | null
    expect(el?.value ?? '').not.toBe('')
  })
  return document.querySelector('.assistant-prompt-textarea') as HTMLTextAreaElement
}

function saveButton() {
  return screen.getByRole('button', { name: /guardar|save/i })
}

describe('the system prompt editor', () => {
  it('is pre-filled with the shipped default so it can be read and edited', async () => {
    renderPage()
    const box = await promptBox()
    expect(box.value).toContain('ALWAYS get numbers from the tools')
    expect(box.value).toContain('{context_block}')
  })

  it('does not save an untouched prompt as an override', async () => {
    // Storing today's default would freeze it, so later improvements to the
    // shipped prompt would never reach this instance.
    const user = userEvent.setup()
    renderPage()
    await promptBox()

    await user.click(saveButton())

    await waitFor(() => expect(saved).toHaveLength(1))
    expect(saved[0].system_prompt).toBeNull()
  }, 15000)

  it('saves an edited prompt as an override', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await promptBox()

    await user.clear(box)
    await user.click(box)
    await user.paste('Custom prompt. {context_block}')
    await user.click(saveButton())

    await waitFor(() => expect(saved).toHaveLength(1))
    expect(String(saved[0].system_prompt)).toContain('Custom prompt.')
  }, 20000)

  it('blocks saving when the ledger-context placeholder is gone', async () => {
    // Without it the assistant cannot see which accounts and categories exist,
    // so it invents the ids it is told never to invent. That is broken, not a
    // preference, so it is the one edit that is refused.
    const user = userEvent.setup()
    renderPage()
    const box = await promptBox()

    await user.clear(box)
    await user.type(box, 'You are a finance bot with no context.')

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(saveButton()).toBeDisabled()
    expect(saved).toHaveLength(0)
  }, 20000)

  it('warns when a safety rule is dropped, without blocking the save', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await promptBox()

    await user.clear(box)
    await user.click(box)
    await user.paste('Be helpful. {context_block}')

    // Advisory: the owner may rewrite the prompt, but the consequence has to be
    // visible at the moment the choice is made.
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    expect(saveButton()).not.toBeDisabled()
  }, 20000)

  it('shows no warning while the prompt is the untouched default', async () => {
    renderPage()
    await promptBox()
    expect(screen.queryByRole('status')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('restores the default after an edit', async () => {
    const user = userEvent.setup()
    renderPage()
    const box = await promptBox()

    await user.clear(box)
    await user.click(box)
    await user.paste('Something else {context_block}')
    await user.click(screen.getByRole('button', { name: /restaurar|restore/i }))

    await waitFor(() => {
      expect(box.value).toContain('ALWAYS get numbers from the tools')
    })
  }, 20000)
})
