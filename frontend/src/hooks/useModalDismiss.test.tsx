import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useModalDismiss } from './useModalDismiss'

function Harness({ onDismiss, disabled = false }: { onDismiss: () => void; disabled?: boolean }) {
  const backdrop = useModalDismiss(onDismiss, disabled)
  return (
    <div data-testid="backdrop" {...backdrop}>
      <div role="dialog" aria-label="Edit">
        <input
          aria-label="Name"
          onKeyDown={e => { if (e.key === 'Escape' && e.currentTarget.value) e.preventDefault() }}
        />
      </div>
    </div>
  )
}

function setup(disabled = false) {
  const onDismiss = vi.fn()
  render(<Harness onDismiss={onDismiss} disabled={disabled} />)
  return { onDismiss, backdrop: screen.getByTestId('backdrop'), input: screen.getByLabelText('Name') }
}

function clickFrom(pressed: Element, released: Element, clicked: Element) {
  fireEvent.pointerDown(pressed)
  fireEvent.pointerUp(released)
  fireEvent.click(clicked)
}

describe('useModalDismiss', () => {
  it('dismisses on a click that starts and ends on the backdrop', () => {
    const { onDismiss, backdrop } = setup()
    clickFrom(backdrop, backdrop, backdrop)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('stays open when a drag that began inside the dialog ends on the backdrop', () => {
    const { onDismiss, backdrop, input } = setup()
    // The browser dispatches the click on the common ancestor: the backdrop.
    clickFrom(input, backdrop, backdrop)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('stays open on a click inside the dialog', () => {
    const { onDismiss, input } = setup()
    clickFrom(input, input, input)
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('needs a fresh press for every click', () => {
    const { onDismiss, backdrop } = setup()
    clickFrom(backdrop, backdrop, backdrop)
    fireEvent.click(backdrop)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('dismisses on Escape', () => {
    const { onDismiss } = setup()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('leaves an Escape an inner widget already claimed', () => {
    const { onDismiss, input } = setup()
    fireEvent.change(input, { target: { value: 'draft' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('ignores both gestures while disabled', () => {
    const { onDismiss, backdrop } = setup(true)
    clickFrom(backdrop, backdrop, backdrop)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).not.toHaveBeenCalled()
  })

  it('marks the backdrop as presentational', () => {
    const { backdrop } = setup()
    expect(backdrop).toHaveAttribute('role', 'presentation')
    expect(screen.getByRole('dialog', { name: 'Edit' })).toBeInTheDocument()
  })
})
