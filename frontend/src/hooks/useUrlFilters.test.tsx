import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigationType } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TransactionsViewFilters } from '../api/types'
import { matchPreset, presetRange } from '../utils'
import { parseFilters, serializeFilters, useDebouncedFilter, useUrlFilters } from './useUrlFilters'

const APRIL = { from: '2025-04-01', to: '2025-04-30' }
const OPEN = { from: '', to: '' }

function parse(search: string, defaults = APRIL) {
  return parseFilters(new URLSearchParams(search), defaults)
}

describe('parseFilters', () => {
  it('falls back to the page default when the range is absent', () => {
    expect(parse('')).toEqual({ ...APRIL, tags: [] })
  })

  it('reads a present but empty end as an open end', () => {
    expect(parse('from=&to=')).toEqual({ from: '', to: '', tags: [] })
  })

  it('drops malformed values instead of throwing', () => {
    const f = parse('from=2025-02-30&to=garbage&account_id=0&category_id=1.5&flow=both&min=-3&max=abc&day=2025-13-01')
    expect(f).toEqual({ ...APRIL, tags: [] })
  })

  it('reads every filter key', () => {
    const f = parse('from=2024-01-01&to=2024-12-31&account_id=7&category_id=12&tag=rent&tag=home&tag=rent&tag=%20'
      + '&flow=expense&merchant=Mercadona&q=groceries&min=10&max=99.5&day=2024-06-15')
    expect(f).toEqual({
      from: '2024-01-01', to: '2024-12-31', account_id: 7, category_id: 12, tags: ['rent', 'home'],
      flow: 'expense', merchant: 'Mercadona', description: 'groceries', amount_min: 10, amount_max: 99.5,
      day: '2024-06-15',
    })
  })
})

describe('serializeFilters', () => {
  it('omits a range equal to the page default', () => {
    expect(serializeFilters({ ...APRIL, tags: [] }, APRIL).toString()).toBe('')
  })

  it('writes both ends of a customised range', () => {
    const params = serializeFilters({ from: '2025-01-01', to: '2025-04-30', tags: [] }, APRIL)
    expect(params.get('from')).toBe('2025-01-01')
    expect(params.get('to')).toBe('2025-04-30')
  })

  it('keeps an open range distinct from the default', () => {
    const params = serializeFilters({ from: '', to: '', tags: [] }, APRIL)
    expect(params.toString()).toBe('from=&to=')
    expect(parseFilters(params, APRIL)).toMatchObject(OPEN)
  })

  it('round-trips every filter', () => {
    const cases: [TransactionsViewFilters, typeof APRIL][] = [
      [{
        from: '2024-01-01', to: '', account_id: 3, category_id: 4, tags: ['a', 'b'], flow: 'income',
        merchant: 'Amazon', description: 'books', amount_min: 0, amount_max: 250, day: '2024-02-29',
      }, APRIL],
      [{ from: '2024-01-01', to: '', tags: [] }, OPEN],
      [{ from: '', to: '2024-01-31', tags: ['x'] }, OPEN],
    ]
    for (const [filters, defaults] of cases) {
      expect(parseFilters(serializeFilters(filters, defaults), defaults)).toEqual(filters)
    }
  })
})

describe('date presets', () => {
  const MID_MAY = new Date(2025, 4, 15)

  it('builds calendar-month ranges', () => {
    expect(presetRange('thisMonth', MID_MAY)).toEqual({ from: '2025-05-01', to: '2025-05-31' })
    expect(presetRange('lastMonth', MID_MAY)).toEqual({ from: '2025-04-01', to: '2025-04-30' })
    expect(presetRange('3m', MID_MAY)).toEqual({ from: '2025-03-01', to: '2025-05-31' })
    expect(presetRange('ytd', MID_MAY)).toEqual({ from: '2025-01-01', to: '2025-05-31' })
    expect(presetRange('12m', MID_MAY)).toEqual({ from: '2024-06-01', to: '2025-05-31' })
    expect(presetRange('all', MID_MAY)).toEqual(OPEN)
  })

  it('crosses the year boundary in January', () => {
    expect(presetRange('lastMonth', new Date(2025, 0, 10))).toEqual({ from: '2024-12-01', to: '2024-12-31' })
  })

  it('recognises a preset and reports a custom range as none', () => {
    expect(matchPreset({ from: '2025-04-01', to: '2025-04-30' }, MID_MAY)).toBe('lastMonth')
    expect(matchPreset(OPEN, MID_MAY)).toBe('all')
    expect(matchPreset({ from: '2025-04-02', to: '2025-04-30' }, MID_MAY)).toBeUndefined()
  })

  it('keeps the picked preset when two ranges coincide', () => {
    const JAN = new Date(2026, 0, 15)
    const january = presetRange('ytd', JAN)
    expect(january).toEqual(presetRange('thisMonth', JAN))
    expect(matchPreset(january, JAN)).toBe('thisMonth')
    expect(matchPreset(january, JAN, 'ytd')).toBe('ytd')
    expect(matchPreset(january, JAN, 'lastMonth')).toBe('thisMonth')

    const DEC = new Date(2026, 11, 15)
    expect(matchPreset(presetRange('12m', DEC), DEC)).toBe('ytd')
    expect(matchPreset(presetRange('12m', DEC), DEC, '12m')).toBe('12m')
  })
})

function LocationProbe() {
  const location = useLocation()
  const navigationType = useNavigationType()
  return (
    <>
      <output data-testid="search">{location.search}</output>
      <output data-testid="nav">{navigationType}</output>
    </>
  )
}

function Harness() {
  const { filters, setFilters } = useUrlFilters(() => APRIL)
  const [description, setDescription] = useDebouncedFilter(filters, setFilters, 'description')
  return (
    <>
      <input aria-label="description" value={description} onChange={e => setDescription(e.target.value)} />
      <button
        type="button"
        onClick={() => {
          setFilters(f => ({ ...f, account_id: 3 }))
          setFilters(f => ({ ...f, tags: [...f.tags, 'rent'] }))
        }}
      >
        both
      </button>
      <button type="button" onClick={() => setFilters(f => ({ ...f }))}>same</button>
      <button type="button" onClick={() => setFilters({ ...APRIL, tags: [] })}>clear</button>
      <output data-testid="filters">{JSON.stringify(filters)}</output>
    </>
  )
}

function renderHarness(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Harness />
      <LocationProbe />
    </MemoryRouter>,
  )
}

const search = () => new URLSearchParams(screen.getByTestId('search').textContent ?? '')

describe('useUrlFilters', () => {
  afterEach(() => { vi.useRealTimers() })

  it('restores the filters from the URL', () => {
    renderHarness('/x?account_id=5&tag=home')
    expect(JSON.parse(screen.getByTestId('filters').textContent ?? '')).toEqual({ ...APRIL, account_id: 5, tags: ['home'] })
  })

  it('composes two updates made in the same tick and keeps unrelated params', () => {
    renderHarness('/x?keep=1')
    fireEvent.click(screen.getByRole('button', { name: 'both' }))
    const params = search()
    expect(params.get('account_id')).toBe('3')
    expect(params.getAll('tag')).toEqual(['rent'])
    expect(params.get('keep')).toBe('1')
    expect(screen.getByTestId('nav').textContent).toBe('REPLACE')
  })

  it('does not navigate when nothing changes', () => {
    renderHarness('/x?account_id=5')
    fireEvent.click(screen.getByRole('button', { name: 'same' }))
    expect(screen.getByTestId('nav').textContent).toBe('POP')
  })

  it('debounces a text filter and resyncs the box after an external clear', () => {
    vi.useFakeTimers()
    renderHarness('/x')
    const box = screen.getByRole('textbox', { name: 'description' })

    fireEvent.change(box, { target: { value: 'rent' } })
    act(() => { vi.advanceTimersByTime(299) })
    expect(search().get('q')).toBeNull()
    act(() => { vi.advanceTimersByTime(1) })
    expect(search().get('q')).toBe('rent')

    fireEvent.click(screen.getByRole('button', { name: 'clear' }))
    expect(search().get('q')).toBeNull()
    expect(box).toHaveValue('')
    act(() => { vi.advanceTimersByTime(1000) })
    expect(search().get('q')).toBeNull()
  })

  it('fills the box from a shared link', () => {
    renderHarness('/x?q=netflix')
    expect(screen.getByRole('textbox', { name: 'description' })).toHaveValue('netflix')
  })
})
