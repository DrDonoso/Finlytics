/**
 * Amortization schedule table.
 *
 * The table claims an instalment is paid only when a real charge was matched
 * to it. A due date in the past proves time passed, not payment, so those rows
 * stay unmarked — the app should never assert money it cannot see.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import MortgageScheduleTable from '../components/MortgageScheduleTable'
import { LanguageProvider } from '../i18n'
import type { MortgageScheduleRow, MortgageScheduleYear } from '../api/types'

function row(
  date: string,
  status: MortgageScheduleRow['status'],
  charged: number | null = null,
): MortgageScheduleRow {
  return {
    period_index: Number(date.slice(8, 10)),
    date,
    opening_balance: 200000,
    payment: 843.21,
    interest: 500,
    principal: 343.21,
    prepayment: 0,
    fee: 0,
    closing_balance: 199656.79,
    annual_rate: 3,
    projected: false,
    status,
    charged,
  }
}

const MONTHS = [
  row('2024-01-01', 'paid', 843.21),
  row('2024-02-02', 'elapsed'),
  row('2024-03-03', 'pending'),
]

function year(overrides: Partial<MortgageScheduleYear> = {}): MortgageScheduleYear {
  return {
    year: 2024,
    payment: 2529.63,
    interest: 1500,
    principal: 1029.63,
    prepayment: 0,
    closing_balance: 198970.37,
    months_total: 3,
    months_paid: 1,
    months_elapsed: 2,
    months: MONTHS,
    ...overrides,
  }
}

async function renderTable(linked: boolean) {
  render(
    <LanguageProvider>
      <MortgageScheduleTable years={[year()]} linked={linked} loading={false} error={null} />
    </LanguageProvider>,
  )
  await userEvent.click(screen.getByRole('button', { name: /2024/ }))
}

describe('MortgageScheduleTable', () => {
  it('marks only the instalment backed by a real charge', async () => {
    await renderTable(true)

    const paid = screen.getByText('01/01/2024').closest('tr')!
    const elapsed = screen.getByText('02/02/2024').closest('tr')!

    expect(within(paid).getByRole('img', { hidden: true })).toBeTruthy()
    expect(within(elapsed).queryByRole('img', { hidden: true })).toBeNull()
  })

  it('sets the paid amount as the marker title', async () => {
    await renderTable(true)

    const paid = screen.getByText('01/01/2024').closest('tr')!
    expect(within(paid).getByTitle(/843,21/)).toBeTruthy()
  })

  it('counts paid instalments per year when linked', async () => {
    await renderTable(true)
    expect(screen.getByText('1/3 paid')).toBeTruthy()
  })

  it('falls back to elapsed instalments when there is nothing to match against', async () => {
    await renderTable(false)
    expect(screen.getByText('2/3 elapsed')).toBeTruthy()
  })

  it('does not dim past instalments when unlinked', async () => {
    /* Every past row is 'elapsed' without a link, so styling them as
       unconfirmed would grey out the whole history and leave the projection
       looking more solid than the part that already happened. */
    await renderTable(false)

    const elapsed = screen.getByText('02/02/2024').closest('tr')!
    expect(elapsed.className).not.toContain('is-elapsed')
  })

  it('dims an unconfirmed instalment sitting between confirmed ones', async () => {
    await renderTable(true)

    const elapsed = screen.getByText('02/02/2024').closest('tr')!
    expect(elapsed.className).toContain('is-elapsed')
  })

  it('does not claim a payment count for years the ledger does not reach', async () => {
    /* A mortgage normally predates the oldest imported statement. Reporting
       "0/12 paid" there states the instalments went unpaid, when the truth is
       that nothing is known about them. */
    render(
      <LanguageProvider>
        <MortgageScheduleTable
          years={[year({ year: 2020, months_paid: 0, months_elapsed: 3 }), year()]}
          linked={true}
          chargesFrom="2024-01-01"
          loading={false}
          error={null}
        />
      </LanguageProvider>,
    )

    expect(screen.queryByText('0/3 paid')).toBeNull()
    expect(screen.getByText('1/3 paid')).toBeTruthy()
  })
})
