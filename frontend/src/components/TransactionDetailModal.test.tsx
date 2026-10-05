/**
 * The amount used to be a `type="number"` field read with `Number()`, so a
 * cleared box saved the transaction as 0 € and `1.234,56` could not be typed.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import type { Transaction } from '../api/types'
import { updateTransaction } from '../api/client'
import TransactionDetailModal from './TransactionDetailModal'
import es from '../i18n/es'

vi.mock('../api/client', () => ({ updateTransaction: vi.fn() }))

const update = vi.mocked(updateTransaction)

const tx: Transaction = {
  id: 1,
  transaction_date: '2025-01-15',
  amount: -42.5,
  currency: 'EUR',
  description: 'Shop',
  category: 'Groceries',
  account: 'Main',
  category_confidence: null,
  balance_after: null,
  tags: [],
  merchant: null,
}

beforeEach(() => {
  update.mockReset()
})

function setup() {
  const onSaved = vi.fn()
  render(
    <TransactionDetailModal
      tx={tx}
      sortedBaseCategories={[]}
      dbExtraCategories={[]}
      allTags={[]}
      categoryColorMap={{}}
      dynamicEs={{}}
      onClose={vi.fn()}
      onSaved={onSaved}
    />,
  )
  return {
    user: userEvent.setup(),
    onSaved,
    amount: screen.getByRole('textbox', { name: es.tableColAmount }),
    save: screen.getByRole('button', { name: es.tableSaveRow }),
  }
}

it('refuses to save a cleared amount instead of storing zero', async () => {
  const { user, amount, save } = setup()

  await user.clear(amount)
  await user.click(save)

  expect(screen.getByText(es.formInvalidNumber)).toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
})

it('refuses malformed text', async () => {
  const { user, amount, save } = setup()

  await user.clear(amount)
  await user.type(amount, '12abc')
  await user.click(save)

  expect(screen.getByText(es.formInvalidNumber)).toBeInTheDocument()
  expect(update).not.toHaveBeenCalled()
})

it('saves a grouped amount typed with a comma decimal, keeping the sign', async () => {
  update.mockResolvedValue({ ...tx, amount: -1234.56 })
  const { user, amount, save, onSaved } = setup()

  await user.clear(amount)
  await user.type(amount, '1.234,56')
  await user.click(save)

  expect(update).toHaveBeenCalledWith(1, expect.objectContaining({ amount: -1234.56 }))
  expect(onSaved).toHaveBeenCalledWith({ ...tx, amount: -1234.56 })
})

it('saves income when the sign is switched', async () => {
  update.mockResolvedValue({ ...tx, amount: 0.5 })
  const { user, amount, save } = setup()

  await user.selectOptions(
    screen.getByRole<HTMLSelectElement>('combobox', { name: es.txDetailSignLabel }),
    '+',
  )
  await user.clear(amount)
  await user.type(amount, '0,5')
  await user.click(save)

  expect(update).toHaveBeenCalledWith(1, expect.objectContaining({ amount: 0.5 }))
})
