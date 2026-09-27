import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'

import TagFilterSelect from './TagFilterSelect'
import type { Tag } from '../api/types'

// More tags than the toggle-pill threshold, so the typeahead renders.
const tags: Tag[] = Array.from({ length: 10 }, (_, i) => ({
  id: i + 1,
  name: `tag-${i + 1}`,
  color: '#4963de',
  emoji: null,
  tx_count: 10 - i,
}))

it('announces the highlighted suggestion through aria-activedescendant', () => {
  render(<TagFilterSelect availableTags={tags} selected={[]} onChange={() => {}} />)
  const input = screen.getByRole('combobox')
  expect(input).not.toHaveAttribute('aria-activedescendant')

  fireEvent.focus(input)
  fireEvent.keyDown(input, { key: 'ArrowDown' })

  const active = document.getElementById(input.getAttribute('aria-activedescendant') ?? '')
  expect(active).toHaveAttribute('role', 'option')
  expect(active).toHaveAttribute('aria-selected', 'true')
  expect(active).toHaveTextContent('tag-2')

  fireEvent.keyDown(input, { key: 'Escape' })
  expect(input).not.toHaveAttribute('aria-activedescendant')
})
