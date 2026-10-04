import { StrictMode, useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import Modal from './Modal'

// A field holding a draft claims Escape, as an open picker does.
function DraftField() {
  return (
    <input
      aria-label="Name"
      onKeyDown={e => {
        if (e.key === 'Escape' && e.currentTarget.value) e.preventDefault()
      }}
    />
  )
}

function AutoFocusFields() {
  return (
    <>
      <button type="button">First</button>
      <input
        aria-label="Name"
        // eslint-disable-next-line jsx-a11y/no-autofocus -- the behaviour under test
        autoFocus
      />
    </>
  )
}

function setup(disabled = false) {
  const onDismiss = vi.fn()
  render(
    <Modal onDismiss={onDismiss} disabled={disabled} label="Edit">
      <DraftField />
    </Modal>,
  )
  return {
    onDismiss,
    dialog: screen.getByRole('dialog', { name: 'Edit' }) as HTMLDialogElement,
    input: screen.getByLabelText('Name'),
  }
}

function clickFrom(pressed: Element, released: Element, clicked: Element) {
  fireEvent.pointerDown(pressed)
  fireEvent.pointerUp(released)
  fireEvent.click(clicked)
}

const nextTick = () => new Promise(resolve => setTimeout(resolve, 0))

describe('Modal', () => {
  it('opens as a modal dialog on mount and focuses its first field', () => {
    const { dialog, input } = setup()
    expect(dialog.open).toBe(true)
    expect(input).toHaveFocus()
  })

  it('dismisses on a click that starts and ends on the backdrop', () => {
    const { onDismiss, dialog } = setup()
    clickFrom(dialog, dialog, dialog)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('keeps the form when a selection is dragged out of a field and released outside', () => {
    const { onDismiss, dialog, input } = setup()
    clickFrom(input, dialog, dialog)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('ignores clicks inside the box', () => {
    const { onDismiss, input } = setup()
    clickFrom(input, input, input)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('needs a fresh press for every click', () => {
    const { onDismiss, dialog } = setup()
    clickFrom(dialog, dialog, dialog)
    fireEvent.click(dialog)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('dismisses on Escape', () => {
    const { onDismiss } = setup()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('leaves an Escape that an inner widget claimed', () => {
    const { onDismiss, input } = setup()
    fireEvent.change(input, { target: { value: 'draft' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('ignores both gestures while disabled', () => {
    const { onDismiss, dialog } = setup(true)
    clickFrom(dialog, dialog, dialog)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()
    expect(dialog.open).toBe(true)
  })

  it('lets a descendant autoFocus win over the first focusable element', () => {
    render(<Modal onDismiss={vi.fn()} label="Edit"><AutoFocusFields /></Modal>)
    expect(screen.getByLabelText('Name')).toHaveFocus()
  })

  it('stays open, with focus kept, under StrictMode', async () => {
    const onDismiss = vi.fn()
    render(
      <StrictMode>
        <Modal onDismiss={onDismiss} label="Edit"><AutoFocusFields /></Modal>
      </StrictMode>,
    )
    const dialog = screen.getByRole('dialog', { name: 'Edit' }) as HTMLDialogElement
    expect(screen.getByLabelText('Name')).toHaveFocus()
    await nextTick()
    expect(dialog.open).toBe(true)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('hands focus back to the element that opened it', () => {
    function Opener() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open</button>
          {open && (
            <Modal onDismiss={() => setOpen(false)} label="Edit">
              <input aria-label="Name" />
            </Modal>
          )}
        </>
      )
    }
    render(<Opener />)
    const opener = screen.getByRole('button', { name: 'Open' })
    opener.focus()
    fireEvent.click(opener)
    expect(screen.getByLabelText('Name')).toHaveFocus()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(opener).toHaveFocus()
  })

  it('reopens and dismisses when the browser closes it anyway', async () => {
    const { onDismiss, dialog } = setup()
    dialog.close()
    await waitFor(() => expect(onDismiss).toHaveBeenCalledTimes(1))
    expect(dialog.open).toBe(true)
  })

  it('stays open without dismissing when closed anyway while disabled', async () => {
    const { onDismiss, dialog } = setup(true)
    dialog.close()
    await waitFor(() => expect(dialog.open).toBe(true))
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('dismisses only the topmost of two nested modals', () => {
    const outer = vi.fn()
    const inner = vi.fn()
    render(
      <Modal onDismiss={outer} label="Outer">
        <button type="button">Outer action</button>
        <Modal onDismiss={inner} label="Inner">
          <input aria-label="Name" />
        </Modal>
      </Modal>,
    )
    const innerDialog = screen.getByRole('dialog', { name: 'Inner' })
    fireEvent.keyDown(document, { key: 'Escape' })
    clickFrom(innerDialog, innerDialog, innerDialog)
    expect(inner).toHaveBeenCalledTimes(2)
    expect(outer).not.toHaveBeenCalled()
  })
})
