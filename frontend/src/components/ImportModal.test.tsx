/**
 * An oversized statement is refused by the server with 413. The modal used to
 * fall through to the generic "unexpected error" text, which gives no hint that
 * the file is simply too big.
 */
import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import ImportModal from './ImportModal'
import es from '../i18n/es'

afterEach(() => {
  vi.unstubAllGlobals()
})

function pdf(name: string): File {
  return new File(['%PDF'], name, { type: 'application/pdf' })
}

it('explains the size limit when the server rejects a statement with 413', async () => {
  // The second preview never settles, so the modal stays on the per-file
  // progress list where extraction errors are shown.
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: 'File exceeds the 20 MB upload limit.' }),
      { status: 413, statusText: 'Payload Too Large' },
    ))
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
