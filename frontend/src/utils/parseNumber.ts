// Reads a number typed in either convention, Spanish (1.234,56) or English
// (1,234.56). Anything malformed is NaN rather than a guess, so a typo blocks
// the form instead of silently saving a different figure.

const IGNORED = /[\s\u00a0\u202f€%]/g
const FIRST_GROUP = /^\d{1,3}$/
const LATER_GROUP = /^\d{3}$/

function validGroups(groups: string[]): boolean {
  return FIRST_GROUP.test(groups[0]) && groups.slice(1).every(group => LATER_GROUP.test(group))
}

function parseLocaleNumber(raw: string, loneSeparatorMayGroup: boolean): number {
  const cleaned = raw.replace(IGNORED, '').replace(/\u2212/g, '-')
  const sign = cleaned.startsWith('-') ? -1 : 1
  const body = /^[+-]/.test(cleaned) ? cleaned.slice(1) : cleaned
  if (!/^[\d.,]+$/.test(body) || !/\d/.test(body)) return Number.NaN

  const lastDot = body.lastIndexOf('.')
  const lastComma = body.lastIndexOf(',')
  if (lastDot === -1 && lastComma === -1) return sign * Number(body)

  if (lastDot !== -1 && lastComma !== -1) {
    const decimalIndex = Math.max(lastDot, lastComma)
    const decimal = body[decimalIndex]
    const integer = body.slice(0, decimalIndex)
    if (integer.includes(decimal)) return Number.NaN
    const groups = integer.split(decimal === '.' ? ',' : '.')
    if (!validGroups(groups)) return Number.NaN
    return sign * Number(`${groups.join('')}.${body.slice(decimalIndex + 1)}`)
  }

  const parts = body.split(lastDot !== -1 ? '.' : ',')
  if (parts.length > 2) {
    return validGroups(parts) ? sign * Number(parts.join('')) : Number.NaN
  }
  const [integer, fraction] = parts
  if (loneSeparatorMayGroup && fraction.length === 3 && /^[1-9]\d{0,2}$/.test(integer)) {
    return sign * Number(integer + fraction)
  }
  return sign * Number(`${integer || '0'}.${fraction}`)
}

/** Euro amounts: a lone separator followed by exactly three digits is grouping, so `1.234` is 1234. */
export function parseAmount(raw: string): number {
  return parseLocaleNumber(raw, true)
}

/** Rates, years and counts: a lone separator is always the decimal, so `2,125` is 2.125. */
export function parseDecimal(raw: string): number {
  return parseLocaleNumber(raw, false)
}

// ─── Form helpers ────────────────────────────────────────────────────────────

export type NumberParser = (raw: string) => number

export function isBlank(value: string): boolean {
  return value.trim() === ''
}

/** The parsed value, or `fallback` when the field was left empty. Malformed text stays NaN. */
export function parseOr(value: string, parse: NumberParser, fallback: number): number {
  return isBlank(value) ? fallback : parse(value)
}

/** The parsed value, or null when the field is empty or malformed. */
export function parseOptional(value: string, parse: NumberParser): number | null {
  const n = parse(value)
  return Number.isFinite(n) ? n : null
}

/** True only for text that was typed and does not parse; an empty field is not malformed. */
export function isMalformed(value: string, parse: NumberParser): boolean {
  return !isBlank(value) && !Number.isFinite(parse(value))
}

/** For live previews, which must not render NaN while a field is half-typed. */
export function finiteOrZero(n: number): number {
  return Number.isFinite(n) ? n : 0
}
