/**
 * The amount cell of the import preview. It used to commit every keystroke,
 * so clearing an income row stored 0 — which the sign select reads as an
 * expense — and the next digit turned the income into an expense.
 */
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import ImportPreviewTable, { type EditRow } from './ImportPreviewTable'
import { computeLiveImportQuality } from './importQuality'
import es from '../i18n/es'

type Patch = Partial<Omit<EditRow, '_key'>>

function row(key: number, amount: number): EditRow {
  return {
    _key: key,
    transaction_date: '2025-01-15',
    amount,
    currency: 'EUR',
    description: 'Test',
    raw_line: null,
    category: 'Groceries',
    category_confidence: 0.9,
    account_ref: 'ES00',
    balance_after: null,
    tags: [],
    merchant: 'Shop',
  }
}

function Harness({ initial, onPatch }: { initial: EditRow[]; onPatch: (key: number, patch: Patch) => void }) {
  const [rows, setRows] = useState(initial)
  return (
    <ImportPreviewTable
      rows={rows}
      accounts={[]}
      categories={[]}
      allTags={[]}
      suggestedColors={{}}
      onUpdateRow={(key, patch) => {
        onPatch(key, patch)
        setRows(prev => prev.map(r => (r._key === key ? { ...r, ...patch } : r)))
      }}
      onDeleteRow={vi.fn()}
      onAddBlankRow={vi.fn()}
      onCreateRule={vi.fn()}
      liveQuality={computeLiveImportQuality(rows, null, true)}
    />
  )
}

function setup(amount: number) {
  const onPatch = vi.fn<(key: number, patch: Patch) => void>()
  render(<Harness initial={[row(1, amount)]} onPatch={onPatch} />)
  return {
    user: userEvent.setup(),
    onPatch,
    input: screen.getByRole('textbox', { name: es.previewColAmount }),
    sign: screen.getByRole<HTMLSelectElement>('combobox', { name: es.txDetailSignLabel }),
    committed: () => onPatch.mock.calls.flatMap(([, patch]) => (patch.amount === undefined ? [] : [patch.amount])),
  }
}

it('keeps an income row positive while its amount is retyped', async () => {
  const { user, input, sign, committed } = setup(50)

  await user.clear(input)
  await user.type(input, '0,12')

  expect(committed()).toEqual([0.1, 0.12])
  expect(sign.value).toBe('+')
  expect(input).toHaveValue('0,12')
})

it('keeps an expense row negative', async () => {
  const { user, input, sign, committed } = setup(-30)

  await user.clear(input)
  await user.type(input, '45')

  expect(committed()).toEqual([-4, -45])
  expect(sign.value).toBe('-')
})

it('reads a Spanish-formatted amount', async () => {
  const { user, input, committed } = setup(50)

  await user.clear(input)
  await user.type(input, '1.234,56')

  const values = committed()
  expect(values[values.length - 1]).toBe(1234.56)
  expect(input).toHaveValue('1.234,56')
})

it('restores the stored amount when the field is left empty', async () => {
  const { user, input, onPatch } = setup(50)

  await user.clear(input)
  expect(input).toHaveAttribute('aria-invalid', 'true')
  await user.tab()

  expect(input).toHaveValue('50')
  expect(input).not.toHaveAttribute('aria-invalid')
  expect(onPatch).not.toHaveBeenCalled()
})
