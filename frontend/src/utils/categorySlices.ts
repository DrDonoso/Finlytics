/** Slices a donut draws individually. The rest share one neutral slice: a sliver
 *  cannot be hovered, and twenty hues cannot all be told apart. */
export const TOP_SLICES = 6

/**
 * Splits items sorted largest-first into the ones drawn individually and the
 * tail folded into a single "rest" slice. A tail of one is never folded, since
 * that would only hide its name behind a vaguer label.
 */
export function splitTopSlices<T>(sorted: readonly T[], top: number = TOP_SLICES): { head: T[]; rest: T[] } {
  if (sorted.length <= top + 1) return { head: [...sorted], rest: [] }
  return { head: sorted.slice(0, top), rest: sorted.slice(top) }
}
