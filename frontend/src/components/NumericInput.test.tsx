/**
 * NumericInput keeps the typed text and flags a malformed value only once the
 * field has been left, so a half-typed number is never reported as an error.
 */
import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import NumericInput from './NumericInput'
import { parseAmount } from '../utils/parseNumber'

function Harness({ initial = '', onValue = vi.fn() }: { initial?: string; onValue?: (n: number) => void }) {
  const [text, setText] = useState(initial)
  const value = parseAmount(text)
  const malformed = text.trim() !== '' && !Number.isFinite(value)
  return (
    <>
      <label htmlFor="amount">Amount</label>
      <NumericInput
        id="amount"
        value={text}
        onChange={next => {
          setText(next)
          onValue(parseAmount(next))
        }}
        error={malformed ? 'Enter a valid number' : null}
      />
      <button type="button">Other</button>
    </>
  )
}

function field() {
  return screen.getByRole('textbox', { name: 'Amount' })
}

describe('NumericInput', () => {
  it('keeps the text exactly as typed', async () => {
    const user = userEvent.setup()
    const onValue = vi.fn()
    render(<Harness onValue={onValue} />)

    await user.type(field(), '1.234,5')

    expect(field()).toHaveValue('1.234,5')
    expect(onValue).toHaveBeenLastCalledWith(1234.5)
  })

  it('does not flag a malformed value before the field is left', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(field(), '1.2.3')

    expect(screen.queryByText('Enter a valid number')).not.toBeInTheDocument()
    expect(field()).not.toHaveAttribute('aria-invalid')
  })

  it('flags a malformed value on blur and links the message to the field', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(field(), '1.2.3')
    await user.tab()

    const message = screen.getByText('Enter a valid number')
    expect(field()).toHaveAttribute('aria-invalid', 'true')
    expect(field()).toHaveAttribute('aria-describedby', message.id)
    expect(field()).toHaveClass('form-input--error')
  })

  it('clears the error as soon as the text becomes valid', async () => {
    const user = userEvent.setup()
    render(<Harness initial="abc" />)

    await user.click(field())
    await user.tab()
    expect(screen.getByText('Enter a valid number')).toBeInTheDocument()

    await user.clear(field())
    await user.type(field(), '42')

    expect(screen.queryByText('Enter a valid number')).not.toBeInTheDocument()
    expect(field()).not.toHaveAttribute('aria-invalid')
    expect(field()).not.toHaveAttribute('aria-describedby')
  })

  it('shows no error for an empty field', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.click(field())
    await user.tab()

    expect(screen.queryByText('Enter a valid number')).not.toBeInTheDocument()
  })

  it('reveals the error without a blur once showError is set', () => {
    render(
      <>
        <label htmlFor="amount">Amount</label>
        <NumericInput id="amount" value="1.2.3" onChange={vi.fn()} error="Enter a valid number" showError />
      </>,
    )

    expect(screen.getByText('Enter a valid number')).toBeInTheDocument()
    expect(field()).toHaveAttribute('aria-invalid', 'true')
  })

  it('forwards disabled to the input', () => {
    render(
      <>
        <label htmlFor="amount">Amount</label>
        <NumericInput id="amount" value="" onChange={vi.fn()} disabled />
      </>,
    )

    expect(field()).toBeDisabled()
  })
})
