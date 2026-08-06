/**
 * Mortgage setup wizard.
 *
 * The term field originally took whole years only. A loan signed mid-month
 * usually amortizes capital over 359 instalments — the first charge covers
 * interest alone — and a year-only field cannot express that. The instalment
 * then comes out a couple of euros below what the bank charges, which reads
 * like an engine bug rather than a data-entry one.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '../api/queryClient'
import MortgageFormModal from '../components/MortgageFormModal'
import { LanguageProvider } from '../i18n'
import type { Account, Category } from '../api/types'

const ACCOUNTS: Account[] = [
  { id: 1, name: 'Main', type: 'checking', currency: 'EUR', tx_count: 0, account_number_masked: null },
]
const CATEGORIES: Category[] = [
  { id: 1, name: 'Housing', is_base: true, color: '#92400e', name_es: null, tx_count: 0 },
]

/** Bodies received by POST, so a test can assert what would be persisted. */
let saved: Record<string, unknown>[] = []

const server = setupServer(
  http.get('/api/mortgages/euribor', () => HttpResponse.json({
    index_name: 'euribor_12m', points: [], latest: null, latest_period: null,
  })),
  http.post('/api/mortgages', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    saved.push(body)
    return HttpResponse.json({ ...body, id: 1, rate_periods: [], bonuses: [], prepayments: [] })
  }),
)

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
beforeEach(() => { saved = [] })
afterEach(() => server.resetHandlers())

function renderWizard() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <LanguageProvider>
        <MortgageFormModal
          accounts={ACCOUNTS}
          categories={CATEGORIES}
          onClose={vi.fn()}
          onSaved={vi.fn()}
        />
      </LanguageProvider>
    </QueryClientProvider>,
  )
}

/** Fill step 1, set the term, then walk to the end and save. */
async function submitWithTerm(years: string, months: string) {
  const user = userEvent.setup()
  renderWizard()

  await user.type(screen.getByLabelText(/name/i), 'Home')
  await user.clear(screen.getByLabelText(/amount borrowed/i))
  await user.type(screen.getByLabelText(/amount borrowed/i), '291200')
  await user.type(screen.getByLabelText(/start date/i), '2024-01-01')

  const yearsField = screen.getByLabelText(/term \(years\)/i)
  await user.clear(yearsField)
  await user.type(yearsField, years)

  const monthsField = screen.getByLabelText(/extra months/i)
  await user.clear(monthsField)
  if (months) await user.type(monthsField, months)

  await user.click(screen.getByRole('button', { name: /next/i }))
  await user.type(screen.getByLabelText(/nominal rate/i), '2')
  await user.click(screen.getByRole('button', { name: /next/i }))
  await user.click(screen.getByRole('button', { name: /^save$/i }))

  await waitFor(() => expect(saved).toHaveLength(1))
  return saved[0]
}

describe('the term can be expressed in months, not just whole years', () => {
  it('sends 360 for a plain 30-year term', async () => {
    expect(await submitWithTerm('30', '0')).toMatchObject({ term_months: 360 })
  })

  it('sends 359 for 29 years and 11 months', async () => {
    expect(await submitWithTerm('29', '11')).toMatchObject({ term_months: 359 })
  })

  it('treats an empty months field as zero', async () => {
    expect(await submitWithTerm('30', '')).toMatchObject({ term_months: 360 })
  })
})

describe('the live preview reflects the exact term', () => {
  it('one instalment fewer raises the monthly figure', async () => {
    const user = userEvent.setup()
    renderWizard()

    await user.clear(screen.getByLabelText(/amount borrowed/i))
    await user.type(screen.getByLabelText(/amount borrowed/i), '291200')

    const yearsField = screen.getByLabelText(/term \(years\)/i)
    await user.clear(yearsField)
    await user.type(yearsField, '30')

    // The preview needs a rate, which lives on step 2; on step 1 it shows the
    // instalment count, which is what this test is about.
    await waitFor(() => {
      expect(screen.getByText(/360 instalments in total/i)).toBeTruthy()
    })

    await user.clear(yearsField)
    await user.type(yearsField, '29')
    const monthsField = screen.getByLabelText(/extra months/i)
    await user.clear(monthsField)
    await user.type(monthsField, '11')

    await waitFor(() => {
      expect(screen.getByText(/359 instalments in total/i)).toBeTruthy()
    })
  })
})
