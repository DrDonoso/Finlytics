/**
 * DateInput keeps its own text while the user types, and gives it up only when
 * the parent hands it a different date (a preset, Clear, the back button).
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import DateInput from './DateInput'

function field() {
  return screen.getByRole('textbox', { name: 'Desde' })
}

function renderInput(value: string, onChange = vi.fn(), className?: string) {
  const view = render(
    <DateInput value={value} lang="es" onChange={onChange} ariaLabel="Desde" className={className} />,
  )
  return {
    ...view,
    onChange,
    rerenderWith: (next: string, nextClassName?: string) =>
      view.rerender(
        <DateInput value={next} lang="es" onChange={onChange} ariaLabel="Desde" className={nextClassName} />,
      ),
  }
}

describe('DateInput', () => {
  it('shows the value in the local format', () => {
    renderInput('2024-03-05')
    expect(field()).toHaveValue('05/03/2024')
  })

  it('replaces half-typed text when the parent sends a new date', async () => {
    const user = userEvent.setup()
    const { rerenderWith } = renderInput('2024-03-05')

    await user.clear(field())
    await user.type(field(), '1/1/')
    rerenderWith('2024-06-30')

    expect(field()).toHaveValue('30/06/2024')
  })

  it('keeps half-typed text when the parent re-renders with the same date', async () => {
    const user = userEvent.setup()
    const { rerenderWith } = renderInput('2024-03-05')

    await user.clear(field())
    await user.type(field(), '1/1/')
    rerenderWith('2024-03-05', 'other-class')

    expect(field()).toHaveValue('1/1/')
  })

  it('commits a valid date on blur and restores the value after an invalid one', async () => {
    const user = userEvent.setup()
    const { onChange } = renderInput('2024-03-05')

    await user.clear(field())
    await user.type(field(), '31/12/2024')
    await user.tab()
    expect(onChange).toHaveBeenCalledExactlyOnceWith('2024-12-31')

    await user.clear(field())
    await user.type(field(), '31/02/2024')
    await user.tab()
    expect(onChange).toHaveBeenCalledOnce()
    expect(field()).toHaveValue('05/03/2024')
  })
})
