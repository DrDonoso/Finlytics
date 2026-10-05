import { describe, expect, it } from 'vitest'
import { formatCompactCurrency, formatCurrency, formatPercent } from '../i18n'

// Intl separates the symbol with a no-break (or narrow no-break) space.
const plain = (s: string) => s.replace(/[\u00a0\u202f]/g, ' ')

describe('formatCurrency', () => {
  it('formats USD explicitly without changing the default EUR behavior', () => {
    expect(plain(formatCurrency(1234.5, 'en', 'USD'))).toBe('US$1,234.50')
    expect(plain(formatCurrency(1234.5, 'es', 'USD'))).toBe('1234,50 US$')
    expect(plain(formatCurrency(-0.004, 'en', 'USD'))).toBe('US$0.00')
    expect(plain(formatCurrency(1234.5, 'en'))).toBe('€1,234.50')
  })
  it('never prints a negative zero', () => {
    expect(plain(formatCurrency(-0, 'es'))).toBe('0,00 €')
    expect(plain(formatCurrency(-0.004, 'en'))).toBe('€0.00')
  })

  it('keeps the sign once the amount rounds to a cent', () => {
    expect(plain(formatCurrency(-0.005, 'es'))).toBe('-0,01 €')
    expect(plain(formatCurrency(-1234.5, 'en'))).toBe('-€1,234.50')
  })
})

describe('formatCompactCurrency', () => {
  it('abbreviates in the UI language', () => {
    expect(plain(formatCompactCurrency(1234, 'es'))).toBe('1,23 mil €')
    expect(plain(formatCompactCurrency(1234, 'en'))).toBe('€1.23k')
    expect(plain(formatCompactCurrency(1234567, 'es'))).toBe('1,23 M €')
    expect(plain(formatCompactCurrency(-1500, 'es'))).toBe('-1,5 mil €')
  })

  it('keeps small amounts instead of rounding them to 0k', () => {
    expect(plain(formatCompactCurrency(450, 'es'))).toBe('450 €')
    expect(plain(formatCompactCurrency(999, 'en'))).toBe('€999')
  })

  it('never prints a negative zero', () => {
    expect(plain(formatCompactCurrency(-0, 'es'))).toBe('0 €')
    expect(plain(formatCompactCurrency(-0.001, 'en'))).toBe('€0')
  })
})

describe('formatPercent', () => {
  it('never prints a negative zero', () => {
    expect(plain(formatPercent(-0.04, 'es'))).toBe('0,0 %')
  })

  it('follows the locale and the unit', () => {
    expect(plain(formatPercent(12.5, 'es', { signed: true }))).toBe('+12,5 %')
    expect(formatPercent(0.254, 'en', { unit: 'fraction' })).toBe('25.4%')
  })
})
