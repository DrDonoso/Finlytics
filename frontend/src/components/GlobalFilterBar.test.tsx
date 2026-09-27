import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import GlobalFilterBar from './GlobalFilterBar'
import type { GlobalFilters } from '../api/types'
import { presetRange } from '../utils'

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 0, 15))
})

afterEach(() => {
  vi.useRealTimers()
})

function renderBar(filters: GlobalFilters, onChange = vi.fn()) {
  const view = render(
    <GlobalFilterBar
      filters={filters}
      defaults={presetRange('lastMonth')}
      accounts={[]}
      categories={[]}
      tags={[]}
      onChange={onChange}
    />,
  )
  return { ...view, onChange, period: screen.getByLabelText('Periodo') as HTMLSelectElement }
}

it('shows the preset the user picked when another one has the same range', () => {
  const january = { ...presetRange('thisMonth'), tags: [] }
  const first = renderBar(january)
  expect(first.period.value).toBe('thisMonth')

  fireEvent.change(first.period, { target: { value: 'ytd' } })
  expect(first.onChange).toHaveBeenCalledWith({ ...january, ...presetRange('ytd'), day: undefined })
  expect(first.period.value).toBe('ytd')

  first.unmount()
  expect(renderBar(january).period.value).toBe('ytd')
})
