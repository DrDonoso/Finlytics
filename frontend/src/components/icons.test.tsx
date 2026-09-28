import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { IconLoading } from './icons'

describe('IconLoading', () => {
  it('keeps spinning when a caller adds its own class', () => {
    const { container } = render(<IconLoading className="extra" />)
    const svg = container.querySelector('svg')

    expect(svg).toHaveClass('icon', 'icon-spin', 'extra')
  })
})
