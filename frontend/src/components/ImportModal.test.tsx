/**
 * An oversized statement is refused by the server with 413. The modal used to
 * fall through to the generic "unexpected error" text, which gives no hint that
 * the file is simply too big.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import ImportModal from './ImportModal'
import { ToastProvider } from '../contexts/ToastContext'
import type { PreviewResponse } from '../api/types'
import es from '../i18n/es'

afterEach(() => {
  vi.unstubAllGlobals()
})

function pdf(name: string): File {
  return new File(['%PDF'], name, { type: 'application/pdf' })
}

function tooLarge(): Promise<Response> {
  return Promise.resolve(new Response(
    JSON.stringify({ detail: 'File exceeds the 20 MB upload limit.' }),
    { status: 413, statusText: 'Payload Too Large' },
  ))
}

it('explains the size limit when the server rejects a statement with 413', async () => {
  // The second preview never settles, so the modal stays on the per-file
  // progress list where extraction errors are shown.
  const fetchMock = vi.fn()
    .mockImplementationOnce(tooLarge)
    .mockReturnValueOnce(new Promise(() => {}))
  vi.stubGlobal('fetch', fetchMock)

  render(
    <ImportModal
      accounts={[]}
      categories={[]}
      allTags={[]}
      onClose={() => {}}
      onSuccess={() => {}}
      initialFiles={[pdf('huge.pdf'), pdf('next.pdf')]}
    />,
    { wrapper: ToastProvider },
  )

  expect(await screen.findByText(es.error413)).toBeInTheDocument()
})

it('shows why every statement failed instead of an empty account step', async () => {
  // It used to jump to "Identify accounts" with nothing to identify, whose
  // Continue led to a disabled "import 0 transactions" and no error in sight.
  vi.stubGlobal('fetch', vi.fn().mockImplementation(tooLarge))
  const onClose = vi.fn()
  const onSuccess = vi.fn()

  render(
    <ImportModal
      accounts={[]}
      categories={[]}
      allTags={[]}
      onClose={onClose}
      onSuccess={onSuccess}
      initialFiles={[pdf('huge.pdf')]}
    />,
    { wrapper: ToastProvider },
  )

  expect(await screen.findByRole('heading', { name: es.batchSummaryFailedTitle })).toBeInTheDocument()
  expect(screen.getByText(es.batchSummaryFileError('huge.pdf', es.error413))).toBeInTheDocument()
  expect(screen.queryByText(es.batchResolveTitle)).not.toBeInTheDocument()

  const footerClose = screen.getAllByRole('button', { name: es.toastClose })
    .find(button => button.classList.contains('btn-primary'))
  await userEvent.click(footerClose!)

  // Nothing reached the server, so there is no "0 new transactions" toast.
  expect(onClose).toHaveBeenCalledOnce()
  expect(onSuccess).not.toHaveBeenCalled()
})

it('re-checks duplicates once typing settles, against the edited rows', async () => {
  // The debounce is armed on the first keystroke and fires after the last one,
  // so it has to read the rows through a ref that follows every commit.
  const preview: PreviewResponse = {
    account_ref: 'Main',
    filename: 'may.pdf',
    transactions: [{
      transaction_date: '2024-05-02', amount: -93.4, currency: 'EUR', description: 'Mercadona',
      raw_line: null, category: 'Groceries', category_confidence: 0.9, account_ref: 'Main',
      balance_after: null, tags: [], merchant: 'Mercadona',
    }],
    statement_year: 2024,
    year_detected: true,
    matched_account_id: 1,
    matched_account_name: 'Main',
    quality: {
      summary: { error_count: 0, warning_count: 0, info_count: 0, flagged_row_count: 0 },
      signals: [],
      row_flags: [],
    },
  }
  const checked: { account_name: string; transactions: { description: string }[] }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/imports/preview') return new Response(JSON.stringify(preview))
    if (url === '/api/imports/check-duplicates') {
      checked.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify({ is_duplicate: [false] }))
    }
    return new Response('{}', { status: 404, statusText: 'Not Found' })
  }))

  render(
    <ImportModal
      accounts={[]}
      categories={[]}
      allTags={[]}
      onClose={() => {}}
      onSuccess={() => {}}
      initialFiles={[pdf('may.pdf')]}
    />,
    { wrapper: ToastProvider },
  )

  await userEvent.click(await screen.findByRole('button', { name: es.modalBtnContinue }))
  expect(checked).toHaveLength(1)

  await userEvent.type(await screen.findByLabelText(es.previewColDesc), ' Madrid')

  await waitFor(() => expect(checked).toHaveLength(2))
  expect(checked[1].account_name).toBe('Main')
  expect(checked[1].transactions.map(tx => tx.description)).toEqual(['Mercadona Madrid'])

  // One check for the whole burst, not one per keystroke.
  await act(() => new Promise(resolve => setTimeout(resolve, 500)))
  expect(checked).toHaveLength(2)
})

it.each(['Escape', 'close button', 'backdrop'])('sends the opening balance and refreshes imported data on %s', async dismissal => {
  // With no accounts, a statement without an IBAN always creates one, but the
  // confirm path only read its balance once "new account" had been toggled.
  const preview: PreviewResponse = {
    account_ref: null,
    filename: 'june.pdf',
    transactions: [{
      transaction_date: '2024-06-03', amount: -20, currency: 'EUR', description: 'Bakery',
      raw_line: null, category: 'Groceries', category_confidence: 0.9, account_ref: '',
      balance_after: null, tags: [], merchant: 'Bakery',
    }],
    statement_year: 2024,
    year_detected: true,
    matched_account_id: null,
    matched_account_name: null,
    quality: {
      summary: { error_count: 0, warning_count: 0, info_count: 0, flagged_row_count: 0 },
      signals: [],
      row_flags: [],
    },
  }
  const confirmed: { account_name: string; opening_balance?: number }[] = []
  const onClose = vi.fn()
  const onSuccess = vi.fn()
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/imports/preview') return new Response(JSON.stringify(preview))
    if (url === '/api/imports/check-duplicates') return new Response(JSON.stringify({ is_duplicate: [false] }))
    if (url === '/api/imports/confirm') {
      confirmed.push(JSON.parse(String(init?.body)))
      return new Response(JSON.stringify({ import_run_id: 1, num_parsed: 1, num_inserted: 1, num_duplicates: 0 }))
    }
    return new Response('{}', { status: 404, statusText: 'Not Found' })
  }))

  render(
    <ImportModal
      accounts={[]}
      categories={[]}
      allTags={[]}
      onClose={onClose}
      onSuccess={onSuccess}
      initialFiles={[pdf('june.pdf')]}
    />,
    { wrapper: ToastProvider },
  )

  await userEvent.type(await screen.findByPlaceholderText(es.modalAccountPlaceholder), 'Savings')
  await userEvent.type(screen.getByLabelText(es.importOpeningBalanceLabel), '1.234,56')
  await userEvent.click(screen.getByRole('button', { name: es.modalBtnContinue }))
  await userEvent.click(await screen.findByRole('button', { name: es.batchConfirmAllBtn(1) }))

  await waitFor(() => expect(confirmed).toHaveLength(1))
  expect(confirmed[0].account_name).toBe('Savings')
  expect(confirmed[0].opening_balance).toBe(1234.56)
  const close = screen.getAllByRole('button', { name: es.modalClose })
    .find(button => button.classList.contains('modal-close'))!
  await waitFor(() => expect(close).toBeEnabled())
  if (dismissal === 'Escape') {
    fireEvent.keyDown(document, { key: 'Escape' })
  } else if (dismissal === 'close button') {
    await userEvent.click(close)
  } else {
    const dialog = screen.getByRole('dialog')
    fireEvent.pointerDown(dialog)
    fireEvent.pointerUp(dialog)
    fireEvent.click(dialog)
  }
  expect(onSuccess).toHaveBeenCalledExactlyOnceWith({
    import_run_id: 0, num_parsed: 1, num_inserted: 1, num_duplicates: 0,
  })
  expect(onClose).not.toHaveBeenCalled()
})
