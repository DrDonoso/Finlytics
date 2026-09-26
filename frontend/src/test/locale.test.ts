/**
 * The UI language becomes an Intl locale in exactly one place, `i18n/index.ts`.
 * A tag inlined anywhere else is how the English UI ended up printing
 * "1.234,56 €" beside "€1,234.56": nothing throws, it only reads wrong.
 */
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob<string>(
  ['../**/*.{ts,tsx}', '!../**/*.test.{ts,tsx}', '!../test/**', '!../i18n/index.ts'],
  { query: '?raw', import: 'default', eager: true },
)

const INLINE_TAG = /['"`](?:es-ES|en-GB|en-US)['"`]/

describe('locale tags', () => {
  it('scans the source tree', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(50)
  })

  it('are only defined in i18n/index.ts', () => {
    const offenders = Object.entries(sources)
      .filter(([, text]) => INLINE_TAG.test(text))
      .map(([path]) => path)
    expect(offenders).toEqual([])
  })
})
