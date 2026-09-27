import { describe, expect, it } from 'vitest'
import { formatCurrency, formatPercent } from '../i18n'

// Intl separates the symbol with a no-break (or narrow no-break) space.
const plain = (s: string) => s.replace(/[\u00a0\u202f]/g, ' ')

describe('formatCurrency', () => {
  it('never prints a negative zero', () => {
    expect(plain(formatCurrency(-0, 'es'))).toBe('0,00 €')
    expect(plain(formatCurrency(-0.004, 'en'))).toBe('€0.00')
  })

  it('keeps the sign once the amount rounds to a cent', () => {
    expect(plain(formatCurrency(-0.005, 'es'))).toBe('-0,01 €')
    expect(plain(formatCurrency(-1234.5, 'en'))).toBe('-€1,234.50')
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
