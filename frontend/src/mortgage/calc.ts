/**
 * Client-side amortization helpers.
 *
 * Two consumers:
 *   - the setup wizard's live preview, so the user can check the instalment
 *     against their bank statement before saving;
 *   - the browser-only demo, which has no backend to compute a schedule.
 *
 * For a real instance the authoritative schedule always comes from the backend
 * engine; this mirrors its French-system arithmetic for a fixed rate.
 */

import type { MortgageRateType, MortgageScheduleRow } from '../api/types'

/** Constant instalment for the French system. */
export function frenchPayment(principal: number, annualRatePct: number, months: number): number {
  if (months <= 0 || principal <= 0) return 0
  const i = annualRatePct / 100 / 12
  if (i <= 0) return principal / months
  const factor = Math.pow(1 + i, months)
  return (principal * i * factor) / (factor - 1)
}

export interface PreviewInput {
  principal: number
  termMonths: number
  rateType: MortgageRateType
  fixedRate: number
  spread: number
  latestIndex: number
  fixedYears: number
}

export interface PreviewResult {
  payment: number
  totalInterest: number
  totalPaid: number
}

/**
 * Approximate the instalment and total interest for the wizard preview.
 *
 * For variable and mixed loans the future index is unknowable, so the latest
 * published Euribor is held flat — the same assumption the backend uses for
 * its projection.
 */
export function previewSchedule(input: PreviewInput): PreviewResult {
  const { principal, termMonths, rateType, fixedRate, spread, latestIndex, fixedYears } = input
  if (principal <= 0 || termMonths <= 0) return { payment: 0, totalInterest: 0, totalPaid: 0 }

  const variableRate = Math.max(latestIndex + spread, 0)
  const firstRate = rateType === 'variable' ? variableRate : fixedRate
  const payment = frenchPayment(principal, firstRate, termMonths)

  // Walk the schedule so mixed loans reprice at the tranche boundary.
  const switchMonth = rateType === 'mixed' ? Math.round(fixedYears * 12) : Infinity
  let balance = principal
  let interestTotal = 0
  let paidTotal = 0
  let current = payment
  let rate = firstRate

  for (let m = 0; m < termMonths && balance > 0; m++) {
    if (m === switchMonth) {
      rate = variableRate
      current = frenchPayment(balance, rate, termMonths - m)
    }
    const interest = balance * (rate / 100 / 12)
    let principalPart = current - interest
    let instalment = current
    if (principalPart >= balance || m === termMonths - 1) {
      principalPart = balance
      instalment = balance + interest
    }
    balance -= principalPart
    interestTotal += interest
    paidTotal += instalment
  }

  return { payment, totalInterest: interestTotal, totalPaid: paidTotal }
}

const RATE_LABEL_KEY: Record<MortgageRateType, 'mortgageRateFixed' | 'mortgageRateVariable' | 'mortgageRateMixed'> = {
  fixed: 'mortgageRateFixed',
  variable: 'mortgageRateVariable',
  mixed: 'mortgageRateMixed',
}

export function rateTypeLabelKey(type: MortgageRateType) {
  return RATE_LABEL_KEY[type]
}

// ─── Full schedule (fixed rate) ───────────────────────────────────────────────

export interface FixedSchedulePrepayment {
  /** ISO date (YYYY-MM-DD). */
  date: string
  amount: number
  mode: 'reduce_term' | 'reduce_payment'
  fee?: number
}

export interface FixedScheduleInput {
  principal: number
  annualRatePct: number
  termMonths: number
  /** ISO date of the first instalment. */
  startDate: string
  paymentDay: number
  prepayments?: FixedSchedulePrepayment[]
}

/** Round to cents the way the backend does, so both agree to the last euro. */
function cents(value: number): number {
  return Math.round(value * 100) / 100
}

/** Instalment date `offset` months after `start`, clamped to the month length. */
function instalmentDate(start: string, paymentDay: number, offset: number): string {
  const base = new Date(`${start}T00:00:00Z`)
  const total = base.getUTCMonth() + offset
  const year = base.getUTCFullYear() + Math.floor(total / 12)
  const month = ((total % 12) + 12) % 12
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const day = Math.min(Math.max(paymentDay, 1), lastDay)
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

/** How many instalments of `payment` clear `balance`; null when it never amortizes. */
function remainingPeriods(balance: number, i: number, payment: number): number | null {
  if (balance <= 0) return 0
  if (payment <= 0) return null
  if (i <= 0) return Math.ceil(balance / payment)
  if (payment <= balance * i) return null
  return Math.ceil(-Math.log(1 - (balance * i) / payment) / Math.log(1 + i))
}

/**
 * Build the full instalment table for a fixed-rate loan.
 *
 * Mirrors the backend: `reduce_term` keeps the instalment and shortens the loan,
 * `reduce_payment` keeps the term and reprices; the final instalment absorbs the
 * rounding residue so the balance closes at exactly zero.
 */
export function buildFixedSchedule(input: FixedScheduleInput): MortgageScheduleRow[] {
  const { principal, annualRatePct, termMonths, startDate, paymentDay } = input
  if (principal <= 0 || termMonths <= 0) return []

  const byMonth = new Map<string, FixedSchedulePrepayment[]>()
  for (const p of input.prepayments ?? []) {
    const key = p.date.slice(0, 7)
    byMonth.set(key, [...(byMonth.get(key) ?? []), p])
  }

  const i = annualRatePct / 100 / 12
  const rows: MortgageScheduleRow[] = []
  let balance = cents(principal)
  let scheduledEnd = termMonths
  let payment = cents(frenchPayment(balance, annualRatePct, scheduledEnd))

  for (let month = 0; month < scheduledEnd && month < 1200; month++) {
    const when = instalmentDate(startDate, paymentDay, month)
    const opening = balance
    const interest = cents(balance * i)
    let capital = cents(payment - interest)
    let actual = payment

    if (capital >= balance || month === scheduledEnd - 1) {
      capital = balance
      actual = cents(capital + interest)
    }
    balance = cents(balance - capital)

    let prepaid = 0
    let fees = 0
    for (const p of byMonth.get(when.slice(0, 7)) ?? []) {
      if (balance <= 0) break
      const applied = Math.min(cents(p.amount), balance)
      if (applied <= 0) continue
      balance = cents(balance - applied)
      prepaid += applied
      fees += cents(p.fee ?? 0)
      if (p.mode === 'reduce_payment') {
        payment = cents(frenchPayment(balance, annualRatePct, scheduledEnd - month - 1))
      } else {
        const left = remainingPeriods(balance, i, payment)
        if (left !== null) scheduledEnd = month + 1 + left
      }
    }

    rows.push({
      period_index: month + 1,
      date: when,
      opening_balance: opening,
      payment: actual,
      interest,
      principal: capital,
      prepayment: prepaid,
      fee: fees,
      closing_balance: balance,
      annual_rate: annualRatePct,
      projected: false,
      status: 'pending',
      charged: null,
    })

    if (balance <= 0) break
  }

  return rows
}
