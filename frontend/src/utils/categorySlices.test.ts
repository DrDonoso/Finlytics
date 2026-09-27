import { describe, expect, it } from 'vitest'

import { TOP_SLICES, splitTopSlices } from './categorySlices'

const items = (n: number) => Array.from({ length: n }, (_, i) => i)

describe('splitTopSlices', () => {
  it('draws every item when there are no more than the top slices', () => {
    expect(splitTopSlices(items(TOP_SLICES))).toEqual({ head: items(TOP_SLICES), rest: [] })
  })

  it('never folds a tail of one item into the rest slice', () => {
    const { head, rest } = splitTopSlices(items(TOP_SLICES + 1))
    expect(head).toHaveLength(TOP_SLICES + 1)
    expect(rest).toEqual([])
  })

  it('folds a longer tail and keeps the largest items first', () => {
    const { head, rest } = splitTopSlices(items(TOP_SLICES + 3))
    expect(head).toEqual(items(TOP_SLICES))
    expect(rest).toEqual([TOP_SLICES, TOP_SLICES + 1, TOP_SLICES + 2])
  })

  it('handles an empty list', () => {
    expect(splitTopSlices([])).toEqual({ head: [], rest: [] })
  })
})
