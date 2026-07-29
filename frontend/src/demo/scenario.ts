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
  CombinedOverview, ContributionEvent, InvestmentConnection, InvestmentHolding, InvestmentPortfolio,
  MonthlyReturnRow, ValuePoint,
} from '../api/types'
import { DEMO_MONTHS, DEMO_SEED } from './config'

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

const TAG_WATER = 'agua'
const TAG_GAS = 'gas'
const TAG_INTERNET = 'internet'
const TAG_POWER = 'luz'
const TAG_PHONE = 'teléfono'

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
  { day: 3, description: 'Alquiler vivienda', merchant: 'Administración Fincas Rosales', category: 'Housing', account: ACCOUNT_MAIN, min: -935, max: -935 },
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
  connections: InvestmentConnection[]
  combined: CombinedOverview
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
  const byYear = new Map<number, MonthlyReturnRow>()
  for (const m of monthlyPct) {
    let row = byYear.get(m.year)
    if (!row) {
      row = { year: m.year, months_pct: {}, months_eur: {}, total_pct: 0, total_eur: 0, benchmark_pct: null }
      byYear.set(m.year, row)
    }
    const key = pad2(m.month0 + 1)
    row.months_pct[key] = Math.round(m.pct * 1000) / 10   // percent, 1 decimal
    row.months_eur[key] = m.eur
  }
  const monthlyReturns: MonthlyReturnRow[] = [...byYear.values()].map(row => {
    const pcts = Object.values(row.months_pct).filter((v): v is number => typeof v === 'number')
    const eurs = Object.values(row.months_eur).filter((v): v is number => typeof v === 'number')
    const compounded = pcts.reduce((acc, p) => acc * (1 + p / 100), 1) - 1
    return {
      ...row,
      total_pct: Math.round(compounded * 1000) / 10,
      total_eur: Math.round(eurs.reduce((a, b) => a + b, 0) * 100) / 100,
      benchmark_pct: Math.round((compounded * 0.92) * 1000) / 10,
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
    returns: {
      twr_annual: Math.round(gainLossPct * 0.7 * 10000) / 10000,
      xirr: Math.round(gainLossPct * 0.82 * 10000) / 10000,
      pl: gainLoss,
      invested,
      twr_total: Math.round(gainLossPct * 10000) / 10000,
      money_return: gainLoss,
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

  const connections: InvestmentConnection[] = [{
    id: 1,
    plugin_id: 'indexa-capital',
    status: 'active',
    account_label_masked: 'ES••••••••••••••••4417',
    created_at: new Date(today.getFullYear() - 1, today.getMonth(), 14).toISOString(),
    last_synced_at: portfolio.last_updated,
  }]

  const byAssetClass = new Map<string, number>()
  for (const h of holdings) {
    byAssetClass.set(h.asset_class, (byAssetClass.get(h.asset_class) ?? 0) + h.current_value)
  }
  const ASSET_LABELS: Record<string, string> = {
    equity: 'Renta variable',
    fixed_income: 'Renta fija',
    cash: 'Efectivo',
  }

  const combined: CombinedOverview = {
    total_value_eur: totalValue,
    total_invested_eur: invested,
    total_gain_loss_eur: gainLoss,
    total_gain_loss_pct: Math.round(gainLossPct * 10000) / 10000,
    by_provider: [
      { provider: 'indexa', label: 'Indexa Capital', value_eur: totalValue, pct: 1 },
    ],
    by_asset_class: [...byAssetClass.entries()].map(([assetClass, valueEur]) => ({
      asset_class: assetClass,
      label: ASSET_LABELS[assetClass] ?? assetClass,
      value_eur: Math.round(valueEur * 100) / 100,
      pct: totalValue > 0 ? Math.round((valueEur / totalValue) * 10000) / 10000 : 0,
    })),
    providers: [{
      id: 'indexa-capital',
      name: 'Indexa Capital',
      icon: '/logos/indexa-capital.svg',
      value_eur: totalValue,
      gain_loss_eur: gainLoss,
      gain_loss_pct: Math.round(gainLossPct * 10000) / 10000,
      route: '/investments/indexa-capital',
    }],
  }

  return { portfolio, connections, combined }
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
  const { portfolio, connections, combined } = buildPortfolio(rng, today)

  return { accounts, categories, tags, transactions, portfolio, connections, combined }
}
