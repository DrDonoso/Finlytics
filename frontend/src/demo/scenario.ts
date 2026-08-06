/** Deterministic synthetic dataset for the public demo.
 *
 * Everything here is invented: account labels describe a purpose rather than a
 * bank, and every merchant name is fictional. No real person, IBAN, card number
 * or institution appears anywhere in this file.
 *
 * Two properties matter and are easy to break:
 *
 * 1. **Dates are relative to today.** `defaultRange()` (src/utils.ts) opens every
 *    filtered view on the *previous calendar month*, so a fixture with hardcoded
 *    dates would silently show empty charts a month after it was written. The
 *    scenario is regenerated from `new Date()` on every page load.
 *
 * 2. **Generation is seeded, not random.** A fixed seed keeps the demo
 *    reproducible and testable. Per-visitor randomisation would buy nothing —
 *    the data is synthetic either way — while making failures unrepeatable.
 */

import type {
  Account, Category, Tag, Transaction,
  CombinedOverview, ContributionEvent, FidelityEvolution, FidelityKpis, FidelityLot,
  FidelityLots, FidelityReminderResponse,
  InvestmentConnection, InvestmentHolding, InvestmentPortfolio,
  MonthlyReturnRow, ValuePoint,
  Mortgage, MortgageCharts, MortgageNetWorth, MortgageOverview,
  MortgageReconciliation, MortgageSchedule, MortgageScheduleRow,
  MortgageScheduleYear, MortgageSummary,
} from '../api/types'
import { buildFixedSchedule, frenchPayment } from '../mortgage/calc'
import { DEMO_MONTHS, DEMO_SEED } from './config'

// ─── Mortgage terms ───────────────────────────────────────────────────────────
//
// A plain fixed-rate Spanish mortgage. The instalment is derived from the terms
// rather than written down, so the recurring charge below and the amortization
// schedule can never drift apart.

const MORTGAGE_PRINCIPAL = 210_000
const MORTGAGE_RATE_PCT = 2.9
const MORTGAGE_TERM_MONTHS = 360
const MORTGAGE_PAYMENT_DAY = 3
/** Months before the current one that the loan was signed. */
const MORTGAGE_STARTED_MONTHS_AGO = 59
/** Months before the current one that the lump-sum overpayment landed. */
const MORTGAGE_PREPAID_MONTHS_AGO = 26
const MORTGAGE_PREPAYMENT = 12_000
const MORTGAGE_PROPERTY_VALUE = 295_000
const MORTGAGE_LENDER = 'Banco Vega'

const MORTGAGE_PAYMENT = Math.round(
  frenchPayment(MORTGAGE_PRINCIPAL, MORTGAGE_RATE_PCT, MORTGAGE_TERM_MONTHS) * 100,
) / 100

// ─── Seeded PRNG ──────────────────────────────────────────────────────────────

/** mulberry32 — small, fast, good enough for fixture generation. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

interface Rng {
  /** Float in [min, max). */
  float(min: number, max: number): number
  /** Amount in [min, max) rounded to cents. */
  money(min: number, max: number): number
  /** Integer in [min, max]. */
  int(min: number, max: number): number
  pick<T>(items: readonly T[]): T
  /** True with probability p. */
  chance(p: number): boolean
}

function makeRng(seed: number): Rng {
  const next = mulberry32(seed)
  const float = (min: number, max: number) => min + next() * (max - min)
  return {
    float,
    money: (min, max) => Math.round(float(min, max) * 100) / 100,
    int: (min, max) => Math.floor(float(min, max + 1)),
    pick: <T,>(items: readonly T[]): T => items[Math.floor(next() * items.length)],
    chance: (p: number) => next() < p,
  }
}

// ─── Date helpers ─────────────────────────────────────────────────────────────

function pad2(n: number): string { return String(n).padStart(2, '0') }

function isoDate(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

function daysInMonth(year: number, month0: number): number {
  return new Date(year, month0 + 1, 0).getDate()
}

/** Clamps `day` to the last day of the month so e.g. day 31 in February works. */
function dayInMonth(year: number, month0: number, day: number): string {
  return isoDate(new Date(year, month0, Math.min(day, daysInMonth(year, month0))))
}

/** Last Mon–Fri of the month — when ESPP purchases settle.
 *  Mirrors `_last_weekday_of_month` in `api/fidelity.py`. */
function lastWeekdayOfMonth(year: number, month0: number): Date {
  const d = new Date(year, month0, daysInMonth(year, month0))
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() - 1)
  return d
}

// ─── Reference data ───────────────────────────────────────────────────────────

/** Canonical base categories + palette, mirroring `seed.py` / `BASE_CATEGORIES`.
 *  `Transaction.category` always carries the canonical English name; the UI
 *  translates it via `categoryLabel()`. */
const CATEGORY_COLORS: ReadonlyArray<readonly [string, string]> = [
  ['Groceries', '#22c55e'], ['Dining', '#ef4444'], ['Transport', '#3b82f6'],
  ['Fuel', '#f97316'], ['Housing', '#92400e'], ['Utilities', '#0d9488'],
  ['Health', '#ec4899'], ['Insurance', '#8b5cf6'], ['Shopping', '#f43f5e'],
  ['Entertainment', '#eab308'], ['Subscriptions', '#6366f1'], ['Travel', '#0ea5e9'],
  ['Education', '#1d4ed8'], ['Income', '#10b981'], ['Transfers', '#94a3b8'],
  ['Investments', '#d97706'], ['Bank Fees', '#dc2626'], ['Taxes', '#475569'],
  ['Cash/ATM', '#84cc16'], ['Other', '#a78bfa'],
]

const ACCOUNT_MAIN = 'Cuenta Nómina'
const ACCOUNT_SAVINGS = 'Cuenta Ahorro'
const ACCOUNT_CARD = 'Tarjeta Crédito'

/** Tags are plain user data: unlike categories, `Tag` carries no `name_es`, so
 *  whatever is written here renders verbatim in both languages. English keeps
 *  them legible in the filter bar, where they sit right next to UI chrome and a
 *  Spanish word beside an English label reads as a missing translation rather
 *  than as data. */
const TAG_WATER = 'water'
const TAG_GAS = 'gas'
const TAG_INTERNET = 'internet'
const TAG_POWER = 'power'
const TAG_PHONE = 'phone'

/** Fictional merchants. Any resemblance to a real business is coincidental. */
const MERCHANTS = {
  groceries: ['Supermercado La Plaza', 'Frutería El Huerto', 'Mercado Central', 'Ultramarinos Sol'],
  dining: ['Cafetería Central', 'Restaurante La Parra', 'Bar El Rincón', 'Pizzería Vesubio', 'Taberna Los Olivos'],
  transport: ['Transporte Metropolitano', 'Taxi Ciudad', 'Tren Regional'],
  fuel: ['Gasolinera Vía Norte', 'Estación Servicio Sur'],
  health: ['Farmacia San Roque', 'Clínica Dental Sonrisa', 'Centro Médico Aurora'],
  shopping: ['Moda Urbana', 'Electrónica Delta', 'Librería Página 12', 'Deportes Cumbre'],
  entertainment: ['Cine Astoria', 'Teatro Municipal', 'Sala Aurora'],
  travel: ['Agencia Viajes Brújula', 'Hotel Costa Serena', 'Vuelos Aurora'],
} as const

interface Recurring {
  day: number
  description: string
  merchant: string | null
  category: string
  account: string
  min: number
  max: number
  tags?: string[]
  /** Probability the charge appears in a given month (1 = always). */
  frequency?: number
}

const RECURRING: readonly Recurring[] = [
  { day: 25, description: 'Nómina mensual', merchant: 'Consultora Nexo', category: 'Income', account: ACCOUNT_MAIN, min: 2380, max: 2610 },
  { day: MORTGAGE_PAYMENT_DAY, description: 'Cuota hipoteca', merchant: MORTGAGE_LENDER, category: 'Housing', account: ACCOUNT_MAIN, min: -MORTGAGE_PAYMENT, max: -MORTGAGE_PAYMENT },
  { day: 8, description: 'Factura electricidad', merchant: 'Eléctrica Peninsular', category: 'Utilities', account: ACCOUNT_MAIN, min: -92, max: -46, tags: [TAG_POWER] },
  { day: 12, description: 'Factura agua', merchant: 'Aguas Municipales', category: 'Utilities', account: ACCOUNT_MAIN, min: -34, max: -18, tags: [TAG_WATER] },
  { day: 15, description: 'Factura gas', merchant: 'Distribuidora Gas Vega', category: 'Utilities', account: ACCOUNT_MAIN, min: -61, max: -22, tags: [TAG_GAS] },
  { day: 5, description: 'Fibra y móvil', merchant: 'Telecom Aurora', category: 'Utilities', account: ACCOUNT_MAIN, min: -49.9, max: -49.9, tags: [TAG_INTERNET, TAG_PHONE] },
  { day: 2, description: 'Suscripción streaming', merchant: 'Streaming Nébula', category: 'Subscriptions', account: ACCOUNT_CARD, min: -13.99, max: -13.99 },
  { day: 7, description: 'Suscripción música', merchant: 'Música Onda', category: 'Subscriptions', account: ACCOUNT_CARD, min: -10.99, max: -10.99 },
  { day: 4, description: 'Cuota gimnasio', merchant: 'Gimnasio Impulso', category: 'Subscriptions', account: ACCOUNT_CARD, min: -34.9, max: -34.9 },
  { day: 18, description: 'Almacenamiento en la nube', merchant: 'Nube Datos Plus', category: 'Subscriptions', account: ACCOUNT_CARD, min: -2.99, max: -2.99 },
  { day: 26, description: 'Traspaso a ahorro', merchant: null, category: 'Transfers', account: ACCOUNT_MAIN, min: -300, max: -300 },
  { day: 27, description: 'Aportación cartera indexada', merchant: 'Indexa Capital', category: 'Investments', account: ACCOUNT_MAIN, min: -250, max: -250 },
  { day: 20, description: 'Seguro del hogar', merchant: 'Seguros Meridiano', category: 'Insurance', account: ACCOUNT_MAIN, min: -21.4, max: -21.4 },
  { day: 30, description: 'Comisión de mantenimiento', merchant: null, category: 'Bank Fees', account: ACCOUNT_MAIN, min: -4, max: -4, frequency: 0.35 },
]

// ─── Transaction generation ───────────────────────────────────────────────────

type NewTx = Omit<Transaction, 'id' | 'balance_after'>

function buildTransactions(rng: Rng, today: Date): Transaction[] {
  const rows: NewTx[] = []

  const push = (
    date: string, amount: number, description: string, category: string,
    account: string, merchant: string | null, tags: string[] = [],
  ) => {
    rows.push({
      transaction_date: date,
      amount: Math.round(amount * 100) / 100,
      currency: 'EUR',
      description,
      category,
      account,
      category_confidence: Math.round(rng.float(0.72, 0.99) * 100) / 100,
      tags,
      merchant,
    })
  }

  for (let back = DEMO_MONTHS - 1; back >= 0; back--) {
    const cursor = new Date(today.getFullYear(), today.getMonth() - back, 1)
    const year = cursor.getFullYear()
    const month0 = cursor.getMonth()
    const isCurrentMonth = back === 0
    // Only generate up to today for the in-progress month, so the demo never
    // shows transactions dated in the future.
    const lastDay = isCurrentMonth ? today.getDate() : daysInMonth(year, month0)

    for (const r of RECURRING) {
      if (r.day > lastDay) continue
      if (r.frequency !== undefined && !rng.chance(r.frequency)) continue
      push(
        dayInMonth(year, month0, r.day),
        r.min === r.max ? r.min : rng.money(r.min, r.max),
        r.description, r.category, r.account, r.merchant, r.tags ? [...r.tags] : [],
      )
    }

    const variable = (
      count: number, min: number, max: number,
      category: string, account: string, pool: readonly string[],
      describe: (merchant: string) => string,
    ) => {
      for (let i = 0; i < count; i++) {
        const day = rng.int(1, lastDay)
        const merchant = rng.pick(pool)
        push(dayInMonth(year, month0, day), rng.money(min, max), describe(merchant), category, account, merchant)
      }
    }

    const scale = isCurrentMonth ? Math.max(0.2, lastDay / daysInMonth(year, month0)) : 1
    const times = (n: number) => Math.max(1, Math.round(n * scale))

    variable(times(rng.int(7, 11)), -96, -14, 'Groceries', ACCOUNT_MAIN, MERCHANTS.groceries, m => `Compra en ${m}`)
    variable(times(rng.int(3, 7)), -48, -9, 'Dining', ACCOUNT_CARD, MERCHANTS.dining, m => `Consumición en ${m}`)
    variable(times(rng.int(2, 5)), -32, -1.8, 'Transport', ACCOUNT_MAIN, MERCHANTS.transport, m => `Billete ${m}`)
    variable(times(rng.int(1, 3)), -72, -38, 'Fuel', ACCOUNT_MAIN, MERCHANTS.fuel, m => `Repostaje en ${m}`)
    variable(times(rng.int(1, 3)), -85, -12, 'Shopping', ACCOUNT_CARD, MERCHANTS.shopping, m => `Compra en ${m}`)

    if (rng.chance(0.55)) variable(1, -68, -11, 'Health', ACCOUNT_MAIN, MERCHANTS.health, m => `Pago en ${m}`)
    if (rng.chance(0.45)) variable(1, -54, -9, 'Entertainment', ACCOUNT_CARD, MERCHANTS.entertainment, m => `Entrada ${m}`)
    if (rng.chance(0.18)) variable(1, -420, -95, 'Travel', ACCOUNT_CARD, MERCHANTS.travel, m => `Reserva ${m}`)
    if (rng.chance(0.30)) {
      const day = rng.int(1, lastDay)
      push(dayInMonth(year, month0, day), -rng.money(20, 100), 'Retirada en cajero', 'Cash/ATM', ACCOUNT_MAIN, null)
    }
    if (rng.chance(0.22)) {
      const day = rng.int(1, lastDay)
      push(dayInMonth(year, month0, day), -rng.money(58, 190), 'Matrícula curso online', 'Education', ACCOUNT_CARD, 'Academia Idiomas Lingua')
    }

    // The savings transfer and the card settlement land as income on their account.
    const transferDay = Math.min(26, lastDay)
    if (transferDay >= 26) push(dayInMonth(year, month0, 26), 300, 'Traspaso desde cuenta nómina', 'Transfers', ACCOUNT_SAVINGS, null)

    if (rng.chance(0.25) && lastDay >= 28) {
      push(dayInMonth(year, month0, 28), rng.money(90, 260), 'Devolución de impuestos', 'Taxes', ACCOUNT_MAIN, null)
    }
  }

  // Sort ascending to compute running balances, then hand back newest-first.
  rows.sort((a, b) => a.transaction_date.localeCompare(b.transaction_date))

  const openingBalance: Record<string, number> = {
    [ACCOUNT_MAIN]: 4200,
    [ACCOUNT_SAVINGS]: 8600,
    [ACCOUNT_CARD]: 0,
  }
  const running = { ...openingBalance }

  const withBalance: Transaction[] = rows.map((row, idx) => {
    running[row.account] = Math.round((running[row.account] + row.amount) * 100) / 100
    return { ...row, id: idx + 1, balance_after: running[row.account] }
  })

  return withBalance.reverse()
}

// ─── Investment portfolio (Indexa Capital connector) ──────────────────────────

/** Fund names are generic asset-class descriptions, not real product names. */
const HOLDING_TEMPLATES: ReadonlyArray<{
  name: string; ticker: string; asset_class: string; weight: number
}> = [
  { name: 'Renta Variable Global',     ticker: 'RVG',  asset_class: 'equity',       weight: 0.42 },
  { name: 'Renta Variable Europa',     ticker: 'RVE',  asset_class: 'equity',       weight: 0.16 },
  { name: 'Renta Variable Emergentes', ticker: 'RVEM', asset_class: 'equity',       weight: 0.10 },
  { name: 'Bonos Europeos',            ticker: 'BEU',  asset_class: 'fixed_income', weight: 0.18 },
  { name: 'Bonos Globales',            ticker: 'BGL',  asset_class: 'fixed_income', weight: 0.11 },
  { name: 'Efectivo',                  ticker: 'CASH', asset_class: 'cash',         weight: 0.03 },
]

const MONTHLY_CONTRIBUTION = 250
const INITIAL_INVESTMENT = 9000

interface PortfolioBundle {
  portfolio: InvestmentPortfolio
  connection: InvestmentConnection
}

function buildPortfolio(rng: Rng, today: Date): PortfolioBundle {
  const valueSeries: ValuePoint[] = []
  const contributionsSeries: ValuePoint[] = []
  const contributionEvents: ContributionEvent[] = []
  /** Month-by-month percentage return, reused for the monthly-returns table. */
  const monthlyPct: { year: number; month0: number; pct: number; eur: number }[] = []

  let invested = INITIAL_INVESTMENT
  let value = INITIAL_INVESTMENT

  for (let back = DEMO_MONTHS - 1; back >= 0; back--) {
    const cursor = new Date(today.getFullYear(), today.getMonth() - back, 1)
    const year = cursor.getFullYear()
    const month0 = cursor.getMonth()
    const isCurrentMonth = back === 0
    const pointDay = isCurrentMonth ? today.getDate() : daysInMonth(year, month0)
    const date = dayInMonth(year, month0, pointDay)

    if (back === DEMO_MONTHS - 1) {
      contributionEvents.push({
        date, amount: INITIAL_INVESTMENT, cumulative: INITIAL_INVESTMENT, type: 'contribution',
      })
    }

    // A mildly positive drift with realistic monthly dispersion.
    const monthReturn = rng.float(-0.038, 0.052)
    const before = value
    value = value * (1 + monthReturn)
    const gainEur = Math.round((value - before) * 100) / 100

    if (!isCurrentMonth || today.getDate() >= 27) {
      value += MONTHLY_CONTRIBUTION
      invested += MONTHLY_CONTRIBUTION
      contributionEvents.push({
        date: dayInMonth(year, month0, 27),
        amount: MONTHLY_CONTRIBUTION,
        cumulative: Math.round(invested * 100) / 100,
        type: 'contribution',
      })
    }

    value = Math.round(value * 100) / 100
    valueSeries.push({ date, value })
    contributionsSeries.push({ date, value: Math.round(invested * 100) / 100 })
    monthlyPct.push({ year, month0, pct: Math.round(monthReturn * 10000) / 10000, eur: gainEur })
  }

  const totalValue = value
  const gainLoss = Math.round((totalValue - invested) * 100) / 100
  const gainLossPct = invested > 0 ? gainLoss / invested : 0

  const holdings: InvestmentHolding[] = HOLDING_TEMPLATES.map(h => {
    const currentValue = Math.round(totalValue * h.weight * 100) / 100
    // Cost basis tracks the same weight against total invested, nudged per fund
    // so each row shows its own gain/loss instead of an identical percentage.
    const costBasis = Math.round(invested * h.weight * rng.float(0.93, 1.04) * 100) / 100
    const rowGain = Math.round((currentValue - costBasis) * 100) / 100
    return {
      plugin_id: 'indexa-capital',
      name: h.name,
      ticker: h.ticker,
      asset_class: h.asset_class,
      units: Math.round((currentValue / rng.float(9, 180)) * 1000) / 1000,
      current_value: currentValue,
      cost_basis: costBasis,
      currency: 'EUR',
      gain_loss: rowGain,
      gain_loss_pct: costBasis > 0 ? Math.round((rowGain / costBasis) * 10000) / 10000 : 0,
      last_updated: isoDate(today),
    }
  })

  // Monthly returns table, grouped by calendar year.
  //
  // UNITS: every *_pct here is a DECIMAL FRACTION (0.0234 = +2.34%). The backend
  // compounds them as ∏(1 + r) - 1 (investments/indexa.py) and IndexaView renders
  // them with `(v * 100).toFixed(2)`, so storing percentages would display them
  // multiplied by 100 again.
  //
  // KEYS: month numbers WITHOUT a leading zero. The backend keys these by int
  // and JSON stringifies them as "1".."12"; the matrix reads `String(i + 1)`.
  // Zero-padding silently blanks January through September — only 10/11/12 match.
  const byYear = new Map<number, MonthlyReturnRow>()
  for (const m of monthlyPct) {
    let row = byYear.get(m.year)
    if (!row) {
      row = { year: m.year, months_pct: {}, months_eur: {}, total_pct: 0, total_eur: 0, benchmark_pct: null }
      byYear.set(m.year, row)
    }
    const key = String(m.month0 + 1)
    row.months_pct[key] = m.pct
    row.months_eur[key] = m.eur
  }
  const monthlyReturns: MonthlyReturnRow[] = [...byYear.values()].map(row => {
    const pcts = Object.values(row.months_pct).filter((v): v is number => typeof v === 'number')
    const eurs = Object.values(row.months_eur).filter((v): v is number => typeof v === 'number')
    const compounded = pcts.reduce((acc, p) => acc * (1 + p), 1) - 1
    return {
      ...row,
      total_pct: Math.round(compounded * 10000) / 10000,
      total_eur: Math.round(eurs.reduce((a, b) => a + b, 0) * 100) / 100,
      // A slightly lagging benchmark, so the comparison column reads plausibly.
      benchmark_pct: Math.round(compounded * 0.92 * 10000) / 10000,
    }
  }).sort((a, b) => b.year - a.year)

  // Worst peak-to-trough stretch of the generated value series.
  let peak = valueSeries[0]?.value ?? 0
  let peakDate = valueSeries[0]?.date ?? isoDate(today)
  let maxDrawdown = 0
  let ddStart = peakDate
  let ddEnd = peakDate
  for (const point of valueSeries) {
    if (point.value > peak) { peak = point.value; peakDate = point.date }
    const dd = peak > 0 ? (point.value - peak) / peak : 0
    if (dd < maxDrawdown) { maxDrawdown = dd; ddStart = peakDate; ddEnd = point.date }
  }

  const cashValue = holdings.find(h => h.asset_class === 'cash')?.current_value ?? 0
  const instrumentsValue = Math.round((totalValue - cashValue) * 100) / 100

  const portfolio: InvestmentPortfolio = {
    total_value: totalValue,
    total_invested: invested,
    total_gain_loss: gainLoss,
    total_gain_loss_pct: Math.round(gainLossPct * 10000) / 10000,
    currency: 'EUR',
    plugins_connected: 1,
    last_updated: new Date(today.getTime() - 42 * 60 * 1000).toISOString(),
    // UNITS inside `returns`: rates are DECIMAL FRACTIONS, amounts are EUR.
    // IndexaView renders twr_annual / xirr / volatility / money_return with
    // `* 100`, and pl / aportaciones / retenciones as currency. `money_return`
    // is the money-weighted total RETURN (a rate) — the view prints it as the
    // percentage next to `pl`, so putting euros in it renders "+342773.0 %".
    returns: {
      twr_annual: Math.round(gainLossPct * 0.7 * 10000) / 10000,
      xirr: Math.round(gainLossPct * 0.82 * 10000) / 10000,
      pl: gainLoss,
      invested,
      twr_total: Math.round(gainLossPct * 10000) / 10000,
      money_return: Math.round(gainLossPct * 10000) / 10000,
      volatility: 0.0871,
      aportaciones: invested,
      retenciones: 0,
      rentabilidad_eur: gainLoss,
      rentabilidad_pct: Math.round(gainLossPct * 10000) / 10000,
      sharpe_ratio: 0.94,
    },
    value_series: valueSeries,
    contributions_series: contributionsSeries,
    monthly_returns: monthlyReturns,
    drawdown: {
      max_drawdown: Math.round(maxDrawdown * 10000) / 10000,
      max_drawdown_eur: Math.round(maxDrawdown * peak * 100) / 100,
      start_date: ddStart,
      end_date: ddEnd,
    },
    cash_invested: {
      cash_amount: cashValue,
      instruments_amount: instrumentsValue,
      instruments_cost: Math.round((invested - cashValue) * 100) / 100,
      total_amount: totalValue,
    },
    holdings,
    contribution_events: contributionEvents,
  }

  const connection: InvestmentConnection = {
    id: 1,
    plugin_id: 'indexa-capital',
    status: 'active',
    account_label_masked: 'ES••••••••••••••••4417',
    created_at: new Date(today.getFullYear() - 1, today.getMonth(), 14).toISOString(),
    last_synced_at: portfolio.last_updated,
  }

  return { portfolio, connection }
}

// ─── Fidelity ESPP (statement-import connector) ───────────────────────────────

/** ESPP purchases settle on the last weekday of Mar/Jun/Sep/Dec — the quarter
 *  ends `_ESPP_QUARTER_MONTHS` uses in `api/fidelity.py`. */
const ESPP_QUARTER_MONTHS = [2, 5, 8, 11] as const
const ESPP_QUARTERS = 12                 // three years of purchase history
const ESPP_CONTRIBUTION_EUR = 1150       // set aside per quarter
const ESPP_DISCOUNT = 0.10               // purchase-price discount on the close
const MSFT_START_USD = 305
const USD_TO_EUR = 0.92                  // `usd_eur_rate` multiplies USD to give EUR

interface EsppBundle {
  kpis: FidelityKpis
  evolution: FidelityEvolution
  lots: FidelityLots
  reminder: FidelityReminderResponse
  connection: InvestmentConnection
  /** Current market value, needed for the combined-overview totals. */
  currentValueEur: number
  investedEur: number
}

/** Weekly MSFT closes from `from` to `today`, as a sorted array. Weekly rather
 *  than daily keeps the payload small; the chart is still smooth. */
function buildPriceSeries(rng: Rng, from: Date, today: Date): { date: string; usd: number }[] {
  const series: { date: string; usd: number }[] = []
  let usd = MSFT_START_USD
  const cursor = new Date(from)
  while (cursor <= today) {
    // Mild upward drift with weekly dispersion.
    usd = Math.max(40, usd * (1 + rng.float(-0.031, 0.037)))
    series.push({ date: isoDate(cursor), usd: Math.round(usd * 100) / 100 })
    cursor.setDate(cursor.getDate() + 7)
  }
  // Always finish exactly on today so the KPI price is "as of" the current date.
  const last = series[series.length - 1]
  if (!last || last.date !== isoDate(today)) {
    series.push({ date: isoDate(today), usd: Math.round(usd * 100) / 100 })
  }
  return series
}

/** Last close at or before `iso`. */
function priceAt(series: { date: string; usd: number }[], iso: string): number {
  let found = series[0]?.usd ?? MSFT_START_USD
  for (const p of series) {
    if (p.date > iso) break
    found = p.usd
  }
  return found
}

function buildEspp(rng: Rng, today: Date): EsppBundle {
  // Quarter-end purchase dates, oldest first.
  const purchaseDates: Date[] = []
  for (let back = 0; back < ESPP_QUARTERS * 4; back++) {
    const cursor = new Date(today.getFullYear(), today.getMonth() - back, 1)
    if (!(ESPP_QUARTER_MONTHS as readonly number[]).includes(cursor.getMonth())) continue
    const settle = lastWeekdayOfMonth(cursor.getFullYear(), cursor.getMonth())
    if (settle <= today) purchaseDates.push(settle)
    if (purchaseDates.length >= ESPP_QUARTERS) break
  }
  purchaseDates.reverse()

  const firstDate = purchaseDates[0] ?? today
  const prices = buildPriceSeries(rng, firstDate, today)
  const currentUsd = prices[prices.length - 1].usd
  const currentEur = currentUsd * USD_TO_EUR

  const lots: FidelityLot[] = []
  let id = 1

  for (const [idx, when] of purchaseDates.entries()) {
    const iso = isoDate(when)
    const closeEur = priceAt(prices, iso) * USD_TO_EUR
    const perShare = closeEur * (1 - ESPP_DISCOUNT)
    const shares = Math.round((ESPP_CONTRIBUTION_EUR / perShare) * 1000) / 1000
    const costTotal = Math.round(shares * perShare * 100) / 100
    const value = Math.round(shares * currentEur * 100) / 100
    const gain = Math.round((value - costTotal) * 100) / 100
    lots.push({
      id: id++,
      purchase_date: iso,
      shares,
      cost_basis_per_share_eur: Math.round(perShare * 10000) / 10000,
      cost_basis_total_eur: costTotal,
      current_value_eur: value,
      gain_loss_eur: gain,
      gain_loss_pct: costTotal > 0 ? Math.round((gain / costTotal) * 10000) / 100 : 0,
      share_source: 'SP',
      // The grant window opens two quarters before the purchase settles.
      grant_date: isoDate(new Date(when.getFullYear(), when.getMonth() - 6, 1)),
    })

    // Dividends are reinvested as small DO lots, starting after the first buy.
    if (idx > 0) {
      const divDate = new Date(when.getFullYear(), when.getMonth(), Math.min(12, daysInMonth(when.getFullYear(), when.getMonth())))
      const divIso = isoDate(divDate)
      const divEur = priceAt(prices, divIso) * USD_TO_EUR
      const heldShares = lots.reduce((sum, l) => sum + l.shares, 0)
      const divShares = Math.round(((heldShares * 0.0018 * divEur) / divEur) * 1000) / 1000
      if (divShares > 0) {
        const divCost = Math.round(divShares * divEur * 100) / 100
        const divValue = Math.round(divShares * currentEur * 100) / 100
        const divGain = Math.round((divValue - divCost) * 100) / 100
        lots.push({
          id: id++,
          purchase_date: divIso,
          shares: divShares,
          cost_basis_per_share_eur: Math.round(divEur * 10000) / 10000,
          cost_basis_total_eur: divCost,
          current_value_eur: divValue,
          gain_loss_eur: divGain,
          gain_loss_pct: divCost > 0 ? Math.round((divGain / divCost) * 10000) / 100 : 0,
          share_source: 'DO',
          grant_date: null,
        })
      }
    }
  }

  const totalShares = Math.round(lots.reduce((s, l) => s + l.shares, 0) * 1000) / 1000
  const investedEur = Math.round(lots.reduce((s, l) => s + l.cost_basis_total_eur, 0) * 100) / 100
  const currentValueEur = Math.round(totalShares * currentEur * 100) / 100
  const gainLossEur = Math.round((currentValueEur - investedEur) * 100) / 100

  // Value/contribution series over the same weekly grid as the price walk.
  const valueSeries: ValuePoint[] = []
  const contributionsSeries: ValuePoint[] = []
  for (const point of prices) {
    const owned = lots
      .filter(l => l.purchase_date <= point.date)
      .reduce((s, l) => s + l.shares, 0)
    const contributed = lots
      .filter(l => l.purchase_date <= point.date && l.share_source === 'SP')
      .reduce((s, l) => s + l.cost_basis_total_eur, 0)
    valueSeries.push({
      date: point.date,
      value: Math.round(owned * point.usd * USD_TO_EUR * 100) / 100,
    })
    contributionsSeries.push({ date: point.date, value: Math.round(contributed * 100) / 100 })
  }

  const lastPurchase = purchaseDates[purchaseDates.length - 1]
  const quarterLabel = `Q${Math.floor(lastPurchase.getMonth() / 3) + 1} ${lastPurchase.getFullYear()}`

  const kpis: FidelityKpis = {
    total_shares: totalShares,
    invested_eur: investedEur,
    current_value_eur: currentValueEur,
    gain_loss_eur: gainLossEur,
    gain_loss_pct: investedEur > 0
      ? Math.round((gainLossEur / investedEur) * 10000) / 100
      : null,
    msft_price_usd: currentUsd,
    usd_eur_rate: USD_TO_EUR,
    last_price_date: prices[prices.length - 1].date,
    price_stale: false,
    as_of_date: isoDate(today),
  }

  // Never overdue: the most recent quarter's purchase is always in the dataset,
  // so the demo does not nag about an upload it cannot accept anyway.
  const reminder: FidelityReminderResponse = {
    overdue: false,
    expected_date: isoDate(lastPurchase),
    period_label: quarterLabel,
    last_lot_date: lots[lots.length - 1].purchase_date,
  }

  const connection: InvestmentConnection = {
    id: 2,
    plugin_id: 'fidelity-espp',
    status: 'active',
    account_label_masked: '••••••••1274',
    created_at: new Date(today.getFullYear() - 3, today.getMonth(), 9).toISOString(),
    last_synced_at: new Date(lastPurchase).toISOString(),
  }

  return {
    kpis,
    evolution: { value_series: valueSeries, contributions_series: contributionsSeries },
    lots: { lots: [...lots].sort((a, b) => b.purchase_date.localeCompare(a.purchase_date)) },
    reminder,
    connection,
    currentValueEur,
    investedEur,
  }
}

// ─── Combined investments overview ────────────────────────────────────────────

const ASSET_LABELS: Record<string, string> = {
  equity: 'Renta variable',
  fixed_income: 'Renta fija',
  espp_stock: 'Acciones ESPP',
  cash: 'Efectivo',
}

/** Consolidates both connectors, exactly as `GET /api/investments/combined-overview`
 *  does on the backend.
 *
 *  UNITS: every `pct` here is a PERCENTAGE (25.4 = 25.4%), matching
 *  `api/investments.py`, which multiplies by 100 for `by_provider.pct`,
 *  `by_asset_class.pct`, `providers[].gain_loss_pct` and `total_gain_loss_pct`.
 *  `InvestmentPortfolio.total_gain_loss_pct` is the odd one out — that one is a
 *  decimal fraction — so it has to be scaled on the way in. */
function buildCombined(portfolio: InvestmentPortfolio, espp: EsppBundle): CombinedOverview {
  const indexaValue = portfolio.total_value
  const indexaInvested = portfolio.total_invested ?? 0
  const indexaGain = portfolio.total_gain_loss ?? 0

  const totalValue = Math.round((indexaValue + espp.currentValueEur) * 100) / 100
  const totalInvested = Math.round((indexaInvested + espp.investedEur) * 100) / 100
  const totalGain = Math.round((totalValue - totalInvested) * 100) / 100
  /** Share of the total, as a percentage rounded to 2 decimals (backend parity). */
  const share = (v: number) => (totalValue > 0 ? Math.round((v / totalValue) * 10000) / 100 : 0)

  const byAssetClass = new Map<string, number>()
  for (const h of portfolio.holdings) {
    byAssetClass.set(h.asset_class, (byAssetClass.get(h.asset_class) ?? 0) + h.current_value)
  }
  byAssetClass.set('espp_stock', espp.currentValueEur)

  const esppGain = Math.round((espp.currentValueEur - espp.investedEur) * 100) / 100

  return {
    total_value_eur: totalValue,
    total_invested_eur: totalInvested,
    total_gain_loss_eur: totalGain,
    total_gain_loss_pct: totalInvested > 0
      ? Math.round((totalGain / totalInvested) * 1000000) / 10000
      : null,
    by_provider: [
      { provider: 'indexa', label: 'Indexa Capital', value_eur: indexaValue, pct: share(indexaValue) },
      { provider: 'fidelity', label: 'Fidelity ESPP', value_eur: espp.currentValueEur, pct: share(espp.currentValueEur) },
    ],
    by_asset_class: [...byAssetClass.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([assetClass, valueEur]) => ({
        asset_class: assetClass,
        label: ASSET_LABELS[assetClass] ?? assetClass,
        value_eur: Math.round(valueEur * 100) / 100,
        pct: share(valueEur),
      })),
    providers: [
      {
        id: 'indexa-capital',
        name: 'Indexa Capital',
        icon: '/logos/indexa-capital.svg',
        value_eur: indexaValue,
        gain_loss_eur: indexaGain,
        gain_loss_pct: indexaInvested > 0
          ? Math.round((indexaGain / indexaInvested) * 1000000) / 10000
          : null,
        route: '/investments/indexa-capital',
      },
      {
        id: 'fidelity-espp',
        name: 'Fidelity ESPP',
        icon: '/logos/fidelity-espp.svg',
        value_eur: espp.currentValueEur,
        gain_loss_eur: esppGain,
        gain_loss_pct: espp.investedEur > 0
          ? Math.round((esppGain / espp.investedEur) * 1000000) / 10000
          : null,
        route: '/investments/fidelity-espp',
      },
    ],
  }
}

// ─── Public scenario ──────────────────────────────────────────────────────────

export interface DemoScenario {
  accounts: Account[]
  categories: Category[]
  tags: Tag[]
  transactions: Transaction[]
  portfolio: InvestmentPortfolio
  connections: InvestmentConnection[]
  combined: CombinedOverview
  espp: {
    kpis: FidelityKpis
    evolution: FidelityEvolution
    lots: FidelityLots
    reminder: FidelityReminderResponse
  }
  mortgage: DemoMortgage
}

/** Every mortgage payload the API would serve, precomputed for the demo. */
export interface DemoMortgage {
  detail: Mortgage
  summary: MortgageSummary
  overview: MortgageOverview
  schedule: MortgageSchedule
  charts: MortgageCharts
  reconciliation: MortgageReconciliation
  netWorth: MortgageNetWorth
}

/** Builds the whole dataset. `tx_count` is left at 0 here — the store derives it
 *  from the live transaction list so it stays correct after an edit. */
export function buildScenario(today: Date = new Date()): DemoScenario {
  const rng = makeRng(DEMO_SEED)

  const accounts: Account[] = [
    { id: 1, name: ACCOUNT_MAIN,    type: 'checking', currency: 'EUR', tx_count: 0, account_number_masked: 'ES••••••••••••••••8102' },
    { id: 2, name: ACCOUNT_SAVINGS, type: 'savings',  currency: 'EUR', tx_count: 0, account_number_masked: 'ES••••••••••••••••6644' },
    { id: 3, name: ACCOUNT_CARD,    type: 'credit',   currency: 'EUR', tx_count: 0, account_number_masked: '••••••••••••3971' },
  ]

  const categories: Category[] = CATEGORY_COLORS.map(([name, color], idx) => ({
    id: idx + 1, name, is_base: true, color, name_es: null, tx_count: 0,
  }))

  const tags: Tag[] = [
    { id: 1, name: TAG_WATER,    color: '#3b82f6', emoji: '💧', tx_count: 0 },
    { id: 2, name: TAG_GAS,      color: '#f97316', emoji: '🔥', tx_count: 0 },
    { id: 3, name: TAG_INTERNET, color: '#8b5cf6', emoji: '📶', tx_count: 0 },
    { id: 4, name: TAG_POWER,    color: '#eab308', emoji: '💡', tx_count: 0 },
    { id: 5, name: TAG_PHONE,    color: '#ec4899', emoji: '📱', tx_count: 0 },
  ]

  const transactions = buildTransactions(rng, today)
  const { portfolio, connection: indexaConnection } = buildPortfolio(rng, today)
  const espp = buildEspp(rng, today)
  const combined = buildCombined(portfolio, espp)

  return {
    accounts,
    categories,
    tags,
    transactions,
    portfolio,
    connections: [indexaConnection, espp.connection],
    combined,
    espp: {
      kpis: espp.kpis,
      evolution: espp.evolution,
      lots: espp.lots,
      reminder: espp.reminder,
    },
    mortgage: buildMortgage(today, transactions, accounts, categories),
  }
}

// ─── Mortgage ─────────────────────────────────────────────────────────────────

/** ISO date `monthsAgo` months before `today`, on `day`. */
function isoMonthsAgo(today: Date, monthsAgo: number, day: number): string {
  const target = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - monthsAgo, 1))
  const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate()
  const d = Math.min(day, lastDay)
  return `${target.getUTCFullYear()}-${String(target.getUTCMonth() + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

/** Roll instalments up per calendar year, optionally keeping the monthly detail. */
function groupByYear(rows: MortgageScheduleRow[], includeMonths: boolean): MortgageScheduleYear[] {
  const years = new Map<number, MortgageScheduleYear>()
  for (const row of rows) {
    const year = Number(row.date.slice(0, 4))
    const bucket = years.get(year) ?? {
      year, payment: 0, interest: 0, principal: 0, prepayment: 0, closing_balance: 0, months: [],
    }
    bucket.payment += row.payment
    bucket.interest += row.interest
    bucket.principal += row.principal
    bucket.prepayment += row.prepayment
    bucket.closing_balance = row.closing_balance
    if (includeMonths) bucket.months.push(row)
    years.set(year, bucket)
  }
  return [...years.values()]
    .sort((a, b) => a.year - b.year)
    .map(y => ({
      ...y,
      payment: round2(y.payment),
      interest: round2(y.interest),
      principal: round2(y.principal),
      prepayment: round2(y.prepayment),
      closing_balance: round2(y.closing_balance),
    }))
}

/**
 * Build every mortgage payload from the same schedule the backend would compute.
 *
 * The reconciliation table is derived from the generated transactions, so the
 * "expected vs charged" comparison is genuine rather than a hardcoded match.
 */
function buildMortgage(
  today: Date,
  transactions: Transaction[],
  accounts: Account[],
  categories: Category[],
): DemoMortgage {
  const startDate = isoMonthsAgo(today, MORTGAGE_STARTED_MONTHS_AGO, MORTGAGE_PAYMENT_DAY)
  const prepaymentDate = isoMonthsAgo(today, MORTGAGE_PREPAID_MONTHS_AGO, MORTGAGE_PAYMENT_DAY)
  const todayIso = today.toISOString().slice(0, 10)

  const account = accounts.find(a => a.name === ACCOUNT_MAIN)
  const category = categories.find(c => c.name === 'Housing')

  const rows = buildFixedSchedule({
    principal: MORTGAGE_PRINCIPAL,
    annualRatePct: MORTGAGE_RATE_PCT,
    termMonths: MORTGAGE_TERM_MONTHS,
    startDate,
    paymentDay: MORTGAGE_PAYMENT_DAY,
    prepayments: [{ date: prepaymentDate, amount: MORTGAGE_PREPAYMENT, mode: 'reduce_term' }],
  })
  const baseline = buildFixedSchedule({
    principal: MORTGAGE_PRINCIPAL,
    annualRatePct: MORTGAGE_RATE_PCT,
    termMonths: MORTGAGE_TERM_MONTHS,
    startDate,
    paymentDay: MORTGAGE_PAYMENT_DAY,
  })

  const past = rows.filter(r => r.date <= todayIso)
  const upcoming = rows.find(r => r.date > todayIso) ?? rows[rows.length - 1]
  const outstanding = past.length > 0 ? past[past.length - 1].closing_balance : MORTGAGE_PRINCIPAL
  const amortized = round2(MORTGAGE_PRINCIPAL - outstanding)

  const totalInterest = round2(rows.reduce((s, r) => s + r.interest, 0))
  const interestPaid = round2(past.reduce((s, r) => s + r.interest, 0))
  const totalPaid = round2(rows.reduce((s, r) => s + r.payment + r.prepayment + r.fee, 0))
  const baselineInterest = round2(baseline.reduce((s, r) => s + r.interest, 0))

  const detail: Mortgage = {
    id: 1,
    name: 'Vivienda habitual',
    lender: MORTGAGE_LENDER,
    initial_principal: MORTGAGE_PRINCIPAL,
    start_date: startDate,
    term_months: MORTGAGE_TERM_MONTHS,
    payment_day: MORTGAGE_PAYMENT_DAY,
    rate_type: 'fixed',
    linked_account_id: account?.id ?? null,
    linked_category_id: category?.id ?? null,
    property_value: MORTGAGE_PROPERTY_VALUE,
    property_value_date: null,
    include_in_net_worth: true,
    notes: null,
    rate_periods: [{
      id: 1, start_month: 0, kind: 'fixed', fixed_rate: MORTGAGE_RATE_PCT,
      index_name: null, spread: null, review_months: null, review_lag_months: 2,
      floor_rate: null, cap_rate: null,
    }],
    bonuses: [],
    prepayments: [{
      id: 1, payment_date: prepaymentDate, amount: MORTGAGE_PREPAYMENT,
      mode: 'reduce_term', fee: 0, notes: null,
    }],
  }

  const overview: MortgageOverview = {
    id: 1,
    name: detail.name,
    lender: detail.lender ?? null,
    rate_type: 'fixed',
    initial_principal: MORTGAGE_PRINCIPAL,
    outstanding_balance: outstanding,
    amortized_principal: amortized,
    progress_pct: round2((amortized / MORTGAGE_PRINCIPAL) * 100),
    current_payment: upcoming?.payment ?? MORTGAGE_PAYMENT,
    current_rate: MORTGAGE_RATE_PCT,
    next_payment_date: rows.find(r => r.date > todayIso)?.date ?? null,
    interest_paid: interestPaid,
    interest_remaining: round2(totalInterest - interestPaid),
    total_interest: totalInterest,
    total_cost: totalPaid,
    months_elapsed: past.length,
    months_remaining: rows.length - past.length,
    end_date: rows[rows.length - 1]?.date ?? null,
    original_end_date: baseline[baseline.length - 1]?.date ?? null,
    months_saved: Math.max(baseline.length - rows.length, 0),
    interest_saved: round2(baselineInterest - totalInterest),
    property_value: MORTGAGE_PROPERTY_VALUE,
    ltv_pct: round2((outstanding / MORTGAGE_PROPERTY_VALUE) * 100),
    total_prepaid: MORTGAGE_PREPAYMENT,
    annual_bonus_cost: 0,
    has_projection: false,
    include_in_net_worth: true,
    linked_account_id: detail.linked_account_id ?? null,
    linked_category_id: detail.linked_category_id ?? null,
  }

  // Expected vs charged over the same 24-month window the API uses by default.
  const window = past.slice(-24)
  const chargedByMonth = new Map<string, number>()
  for (const tx of transactions) {
    if (tx.account !== ACCOUNT_MAIN) continue
    if (tx.category !== 'Housing') continue
    const key = tx.transaction_date.slice(0, 7)
    chargedByMonth.set(key, (chargedByMonth.get(key) ?? 0) + Math.abs(tx.amount))
  }

  const reconciliationRows = window.map(row => {
    const expected = round2(row.payment + row.prepayment)
    const actual = chargedByMonth.get(row.date.slice(0, 7)) ?? null
    if (actual === null) {
      return { period: row.date, expected, actual: null, deviation: null, deviation_pct: null, matched: false }
    }
    const deviation = round2(actual - expected)
    return {
      period: row.date,
      expected,
      actual: round2(actual),
      deviation,
      deviation_pct: expected > 0 ? round2((deviation / expected) * 100) : null,
      matched: true,
    }
  })

  return {
    detail,
    summary: {
      id: 1,
      name: detail.name,
      lender: detail.lender ?? null,
      rate_type: 'fixed',
      outstanding_balance: outstanding,
      monthly_payment: overview.current_payment,
      progress_pct: overview.progress_pct,
    },
    overview,
    schedule: {
      mortgage_id: 1,
      granularity: 'year',
      rows: [],
      years: groupByYear(rows, true),
      total_payment: totalPaid,
      total_interest: totalInterest,
      total_principal: round2(rows.reduce((s, r) => s + r.principal, 0)),
    },
    charts: {
      balance: rows.map(r => ({ date: r.date, balance: r.closing_balance, projected: false })),
      composition: groupByYear(rows, false),
    },
    reconciliation: {
      mortgage_id: 1,
      linked: true,
      account_id: detail.linked_account_id ?? null,
      category_id: detail.linked_category_id ?? null,
      rows: reconciliationRows,
      total_expected: round2(reconciliationRows.reduce((s, r) => s + r.expected, 0)),
      total_actual: round2(reconciliationRows.reduce((s, r) => s + (r.actual ?? 0), 0)),
    },
    netWorth: {
      outstanding_debt: outstanding,
      property_value: MORTGAGE_PROPERTY_VALUE,
      net_contribution: round2(MORTGAGE_PROPERTY_VALUE - outstanding),
      count: 1,
    },
  }
}
