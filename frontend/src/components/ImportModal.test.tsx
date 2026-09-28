/**
 * An oversized statement is refused by the server with 413. The modal used to
 * fall through to the generic "unexpected error" text, which gives no hint that
 * the file is simply too big.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'

import ImportModal from './ImportModal'
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
