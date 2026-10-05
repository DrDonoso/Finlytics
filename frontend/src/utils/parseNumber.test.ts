/**
 * The numeric fields accept both conventions because the app is bilingual and
 * people paste figures from their bank. The dangerous outcome is not a
 * rejected value but a misread one, so malformed input must come back as NaN.
 */
import { describe, expect, it } from 'vitest'

import { finiteOrZero, isMalformed, parseAmount, parseDecimal, parseOptional, parseOr } from './parseNumber'

describe('parseAmount', () => {
  it.each([
    ['1.234,56', 1234.56],
    ['1,234.56', 1234.56],
    ['-1.234,56', -1234.56],
    ['1.234', 1234],
    ['250.000', 250000],
    ['1.234.567,89', 1234567.89],
    ['1,234,567', 1234567],
    ['0,250', 0.25],
    ['12,5', 12.5],
    ['120,50', 120.5],
    ['2,125', 2125],
    ['€ 1.234,56', 1234.56],
    ['1.234,56 €', 1234.56],
    ['1\u00a0234,56', 1234.56],
    ['1\u202f234,56', 1234.56],
    ['\u22125,00', -5],
    ['+5', 5],
    ['.5', 0.5],
    ['5.', 5],
    ['250000', 250000],
  ])('reads %j as %d', (input, expected) => {
    expect(parseAmount(input)).toBe(expected)
  })

  it.each(['', '  ', 'abc', ',', '.', '-', '1.2.3', '1,23,456', '1e3', '1,2.3', '1.234,5,6', '1..2', '+-5', '5-', '1234.567,8'])(
    'rejects %j',
    input => {
      expect(parseAmount(input)).toBeNaN()
    },
  )
})

describe('parseDecimal', () => {
  it('always reads a lone separator as the decimal', () => {
    expect(parseDecimal('2,125')).toBe(2.125)
    expect(parseDecimal('1.234')).toBe(1.234)
    expect(parseDecimal('0,25')).toBe(0.25)
  })

  it('still honours an explicit grouping separator', () => {
    expect(parseDecimal('1.234,5')).toBe(1234.5)
    expect(parseDecimal('1,234.5')).toBe(1234.5)
  })

  it('strips a percent sign and keeps negative spreads', () => {
    expect(parseDecimal('3,5 %')).toBe(3.5)
    expect(parseDecimal('-0,10')).toBe(-0.1)
  })

  it.each(['', 'abc', '1.2.3', '2,5,0', '1e3'])('rejects %j', input => {
    expect(parseDecimal(input)).toBeNaN()
  })
})

describe('form helpers', () => {
  it('falls back only for an empty field, never for a malformed one', () => {
    expect(parseOr('  ', parseDecimal, 12)).toBe(12)
    expect(parseOr('6', parseDecimal, 12)).toBe(6)
    expect(parseOr('abc', parseDecimal, 12)).toBeNaN()
  })

  it('maps empty and malformed optional fields to null', () => {
    expect(parseOptional('', parseAmount)).toBeNull()
    expect(parseOptional('1.2.3', parseAmount)).toBeNull()
    expect(parseOptional('0', parseAmount)).toBe(0)
    expect(parseOptional('350.000', parseAmount)).toBe(350000)
  })

  it('flags typed text that does not parse, but not an empty field', () => {
    expect(isMalformed('', parseDecimal)).toBe(false)
    expect(isMalformed('0,5', parseDecimal)).toBe(false)
    expect(isMalformed('0,5,', parseDecimal)).toBe(true)
  })

  it('keeps previews finite', () => {
    expect(finiteOrZero(Number.NaN)).toBe(0)
    expect(finiteOrZero(-3.5)).toBe(-3.5)
  })
})
