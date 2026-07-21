import type {
  Account, Category, Tag, Transaction, TransactionPage,
  Overview, CategorySummary, MonthSummary, AccountSummary,
  ImportResult, ImportTransaction, PreviewResponse, ConfirmRequest,
  TransactionsParams, SummaryParams, MonthSummaryParams,
  TransactionPatch, CashflowSummary, AuthStatus, AuthUser,
  MerchantSummary, DaySummary, InvestmentPlugin,
  InvestmentPortfolio, InvestmentConnection, ValidateAccountsResponse,
  StatementReminder, NotificationOut,
  NotificationChannelOut, TelegramChannelIn, TelegramTestIn, TelegramTestOut,
  AccountCreatePayload,
} from './types'

// ─── Static reference data ────────────────────────────────────────────────────

export const MOCK_ACCOUNTS: Account[] = [
  { id: 1, name: 'BBVA', type: 'checking', currency: 'EUR', tx_count: 42 },
  { id: 2, name: 'Indexa Capital', type: 'investment', currency: 'EUR', tx_count: 8 },
]

export const MOCK_CATEGORIES: Category[] = [
  { id: 1,  name: 'Groceries',    is_base: true, color: '#22c55e', name_es: null, tx_count: 8  },
  { id: 2,  name: 'Dining',       is_base: true, color: '#f59e0b', name_es: null, tx_count: 4  },
  { id: 3,  name: 'Transport',    is_base: true, color: '#3b82f6', name_es: null, tx_count: 3  },
  { id: 4,  name: 'Fuel',         is_base: true, color: '#f97316', name_es: null, tx_count: 2  },
  { id: 5,  name: 'Housing',      is_base: true, color: '#8b5cf6', name_es: null, tx_count: 2  },
  { id: 6,  name: 'Utilities',    is_base: true, color: '#06b6d4', name_es: null, tx_count: 4  },
  { id: 7,  name: 'Health',       is_base: true, color: '#ef4444', name_es: null, tx_count: 3  },
  { id: 8,  name: 'Insurance',    is_base: true, color: '#84cc16', name_es: null, tx_count: 0  },
  { id: 9,  name: 'Shopping',     is_base: true, color: '#ec4899', name_es: null, tx_count: 5  },
  { id: 10, name: 'Entertainment',is_base: true, color: '#a855f7', name_es: null, tx_count: 2  },
  { id: 11, name: 'Subscriptions',is_base: true, color: '#14b8a6', name_es: null, tx_count: 6  },
  { id: 12, name: 'Travel',       is_base: true, color: '#0ea5e9', name_es: null, tx_count: 1  },
  { id: 13, name: 'Education',    is_base: true, color: '#6366f1', name_es: null, tx_count: 0  },
  { id: 14, name: 'Income',       is_base: true, color: '#10b981', name_es: null, tx_count: 2  },
  { id: 15, name: 'Transfers',    is_base: true, color: '#64748b', name_es: null, tx_count: 1  },
  { id: 16, name: 'Investments',  is_base: true, color: '#2563eb', name_es: null, tx_count: 2  },
  { id: 17, name: 'Bank Fees',    is_base: true, color: '#94a3b8', name_es: null, tx_count: 0  },
  { id: 18, name: 'Taxes',        is_base: true, color: '#dc2626', name_es: null, tx_count: 0  },
  { id: 19, name: 'Cash/ATM',     is_base: true, color: '#ca8a04', name_es: null, tx_count: 1  },
  { id: 20, name: 'Other',        is_base: true, color: '#9ca3af', name_es: null, tx_count: 2  },
]

export const MOCK_TAGS: Tag[] = [
  { id: 1, name: 'agua',      color: '#3b82f6', emoji: '💧', tx_count: 2 },
  { id: 2, name: 'gas',       color: '#f97316', emoji: '🔥', tx_count: 1 },
  { id: 3, name: 'internet',  color: '#8b5cf6', emoji: '📶', tx_count: 3 },
  { id: 4, name: 'luz',       color: '#eab308', emoji: '💡', tx_count: 4 },
  { id: 5, name: 'teléfono',  color: '#ec4899', emoji: '📱', tx_count: 2 },
]

// Mutable tag store — persists within the browser session for mock CRUD
let _mockTags: Tag[] = [...MOCK_TAGS]
let _nextTagId = MOCK_TAGS.length + 1

// Mutable category store — persists within the browser session for mock CRUD
let _mockCategories: Category[] = [...MOCK_CATEGORIES]
let _nextCategoryId = MOCK_CATEGORIES.length + 1

// Mutable account store — persists within the browser session for mock CRUD
let _mockAccounts: Account[] = [...MOCK_ACCOUNTS]
let _nextAccountId = MOCK_ACCOUNTS.length + 1

// ─── Raw signed transactions ──────────────────────────────────────────────────
// amount < 0 → expense   |   amount > 0 → income

const RAW: Transaction[] = [
  // ── BBVA — May 2026 ──────────────────────────────────────────────────────
  { id: 1,  transaction_date: '2026-05-01', amount:  2500.00, currency: 'EUR', description: 'Nómina Mayo',                  category: 'Income',        account: 'BBVA',           category_confidence: 0.99, balance_after: 3200.00,  tags: [],             merchant: null },
  { id: 2,  transaction_date: '2026-05-02', amount:   -87.50, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 3112.50,  tags: [],             merchant: 'Mercadona' },
  { id: 3,  transaction_date: '2026-05-03', amount:  -800.00, currency: 'EUR', description: 'Alquiler Mayo',                category: 'Housing',       account: 'BBVA',           category_confidence: 0.99, balance_after: 2312.50,  tags: [],             merchant: null },
  { id: 4,  transaction_date: '2026-05-05', amount:   -95.00, currency: 'EUR', description: 'Endesa Electricidad',          category: 'Utilities',     account: 'BBVA',           category_confidence: 0.95, balance_after: 2217.50,  tags: ['luz'],        merchant: 'Endesa' },
  { id: 5,  transaction_date: '2026-05-07', amount:   -65.30, currency: 'EUR', description: 'Carrefour',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.95, balance_after: 2152.20,  tags: [],             merchant: 'Carrefour' },
  { id: 6,  transaction_date: '2026-05-08', amount:   -15.99, currency: 'EUR', description: 'Netflix',                      category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.99, balance_after: 2136.21,  tags: [],             merchant: 'Netflix' },
  { id: 7,  transaction_date: '2026-05-08', amount:    -9.99, currency: 'EUR', description: 'Spotify',                      category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.99, balance_after: 2126.22,  tags: [],             merchant: 'Spotify' },
  { id: 8,  transaction_date: '2026-05-10', amount:  -120.00, currency: 'EUR', description: 'El Corte Inglés',              category: 'Shopping',      account: 'BBVA',           category_confidence: 0.88, balance_after: 2006.22,  tags: [],             merchant: 'El Corte Inglés' },
  { id: 9,  transaction_date: '2026-05-12', amount:   -45.80, currency: 'EUR', description: 'Restaurante Casa Paco',        category: 'Dining',        account: 'BBVA',           category_confidence: 0.93, balance_after: 1960.42,  tags: [],             merchant: null },
  { id: 10, transaction_date: '2026-05-14', amount:   -92.40, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 1868.02,  tags: [],             merchant: 'Mercadona' },
  { id: 11, transaction_date: '2026-05-15', amount:   -28.50, currency: 'EUR', description: 'Farmacia Avenida',             category: 'Health',        account: 'BBVA',           category_confidence: 0.92, balance_after: 1839.52,  tags: [],             merchant: null },
  { id: 12, transaction_date: '2026-05-17', amount:   -12.40, currency: 'EUR', description: 'Cabify',                       category: 'Transport',     account: 'BBVA',           category_confidence: 0.96, balance_after: 1827.12,  tags: [],             merchant: 'Cabify' },
  { id: 13, transaction_date: '2026-05-18', amount:   -40.00, currency: 'EUR', description: 'Vodafone Internet',            category: 'Utilities',     account: 'BBVA',           category_confidence: 0.94, balance_after: 1787.12,  tags: ['internet'],   merchant: 'Vodafone' },
  { id: 14, transaction_date: '2026-05-20', amount:   -89.90, currency: 'EUR', description: 'Zara',                         category: 'Shopping',      account: 'BBVA',           category_confidence: 0.89, balance_after: 1697.22,  tags: [],             merchant: 'Zara' },
  { id: 15, transaction_date: '2026-05-21', amount:   -38.50, currency: 'EUR', description: 'Restaurante La Plaza',         category: 'Dining',        account: 'BBVA',           category_confidence: 0.91, balance_after: 1658.72,  tags: [],             merchant: null },
  { id: 16, transaction_date: '2026-05-22', amount:   -78.20, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 1580.52,  tags: [],             merchant: 'Mercadona' },
  { id: 17, transaction_date: '2026-05-25', amount:    -4.99, currency: 'EUR', description: 'Amazon Prime',                 category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.98, balance_after: 1575.53,  tags: [],             merchant: 'Amazon' },
  { id: 18, transaction_date: '2026-05-26', amount:   -55.00, currency: 'EUR', description: 'Repsol Gasolinera',            category: 'Fuel',          account: 'BBVA',           category_confidence: 0.94, balance_after: 1520.53,  tags: [],             merchant: 'Repsol' },
  { id: 19, transaction_date: '2026-05-28', amount:   -16.00, currency: 'EUR', description: 'Cine Odéon',                   category: 'Entertainment', account: 'BBVA',           category_confidence: 0.90, balance_after: 1504.53,  tags: [],             merchant: null },
  { id: 20, transaction_date: '2026-05-30', amount:   -35.00, currency: 'EUR', description: 'MetroFit Gimnasio',            category: 'Health',        account: 'BBVA',           category_confidence: 0.91, balance_after: 1469.53,  tags: [],             merchant: null },
  // ── Indexa Capital — May 2026 ─────────────────────────────────────────────
  { id: 21, transaction_date: '2026-05-02', amount:  -500.00, currency: 'EUR', description: 'Aportación cartera indexada',  category: 'Investments',   account: 'Indexa Capital', category_confidence: 0.99, balance_after: 12450.00, tags: [],             merchant: null },
  { id: 22, transaction_date: '2026-05-31', amount:    32.50, currency: 'EUR', description: 'Rendimiento cartera mayo',     category: 'Income',        account: 'Indexa Capital', category_confidence: 0.98, balance_after: 12482.50, tags: [],             merchant: null },
  // ── BBVA — June 2026 ─────────────────────────────────────────────────────
  { id: 23, transaction_date: '2026-06-01', amount:  2500.00, currency: 'EUR', description: 'Nómina Junio',                 category: 'Income',        account: 'BBVA',           category_confidence: 0.99, balance_after: 3969.53,  tags: [],             merchant: null },
  { id: 24, transaction_date: '2026-06-02', amount:   -93.10, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 3876.43,  tags: [],             merchant: 'Mercadona' },
  { id: 25, transaction_date: '2026-06-03', amount:  -800.00, currency: 'EUR', description: 'Alquiler Junio',               category: 'Housing',       account: 'BBVA',           category_confidence: 0.99, balance_after: 3076.43,  tags: [],             merchant: null },
  { id: 26, transaction_date: '2026-06-05', amount:   -88.00, currency: 'EUR', description: 'Iberdrola Electricidad',       category: 'Utilities',     account: 'BBVA',           category_confidence: 0.95, balance_after: 2988.43,  tags: ['luz'],        merchant: 'Iberdrola' },
  { id: 27, transaction_date: '2026-06-07', amount:   -71.20, currency: 'EUR', description: 'Carrefour',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.95, balance_after: 2917.23,  tags: [],             merchant: 'Carrefour' },
  { id: 28, transaction_date: '2026-06-08', amount:   -15.99, currency: 'EUR', description: 'Netflix',                      category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.99, balance_after: 2901.24,  tags: [],             merchant: 'Netflix' },
  { id: 29, transaction_date: '2026-06-08', amount:    -9.99, currency: 'EUR', description: 'Spotify',                      category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.99, balance_after: 2891.25,  tags: [],             merchant: 'Spotify' },
  { id: 30, transaction_date: '2026-06-10', amount:   -60.00, currency: 'EUR', description: 'Médico Especialista',          category: 'Health',        account: 'BBVA',           category_confidence: 0.94, balance_after: 2831.25,  tags: [],             merchant: null },
  { id: 31, transaction_date: '2026-06-12', amount:   -55.20, currency: 'EUR', description: 'Sushi Taro Restaurante',       category: 'Dining',        account: 'BBVA',           category_confidence: 0.92, balance_after: 2776.05,  tags: [],             merchant: null },
  { id: 32, transaction_date: '2026-06-14', amount:   -85.60, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 2690.45,  tags: [],             merchant: 'Mercadona' },
  { id: 33, transaction_date: '2026-06-16', amount:  -180.00, currency: 'EUR', description: 'Vueling Madrid-BCN',           category: 'Travel',        account: 'BBVA',           category_confidence: 0.97, balance_after: 2510.45,  tags: [],             merchant: 'Vueling' },
  { id: 34, transaction_date: '2026-06-18', amount:  -120.00, currency: 'EUR', description: 'Hotel Ibis Barcelona',         category: 'Travel',        account: 'BBVA',           category_confidence: 0.95, balance_after: 2390.45,  tags: [],             merchant: 'Ibis Hotels' },
  { id: 35, transaction_date: '2026-06-20', amount:  -145.30, currency: 'EUR', description: 'El Corte Inglés',              category: 'Shopping',      account: 'BBVA',           category_confidence: 0.88, balance_after: 2245.15,  tags: [],             merchant: 'El Corte Inglés' },
  { id: 36, transaction_date: '2026-06-21', amount:   -48.90, currency: 'EUR', description: 'El Faro Restaurante',          category: 'Dining',        account: 'BBVA',           category_confidence: 0.91, balance_after: 2196.25,  tags: [],             merchant: null },
  { id: 37, transaction_date: '2026-06-22', amount:   -68.40, currency: 'EUR', description: 'Mercadona',                    category: 'Groceries',     account: 'BBVA',           category_confidence: 0.97, balance_after: 2127.85,  tags: [],             merchant: 'Mercadona' },
  { id: 38, transaction_date: '2026-06-25', amount:    -4.99, currency: 'EUR', description: 'Amazon Prime',                 category: 'Subscriptions', account: 'BBVA',           category_confidence: 0.98, balance_after: 2122.86,  tags: [],             merchant: 'Amazon' },
  { id: 39, transaction_date: '2026-06-26', amount:   -62.00, currency: 'EUR', description: 'BP Gasolinera',               category: 'Fuel',          account: 'BBVA',           category_confidence: 0.94, balance_after: 2060.86,  tags: [],             merchant: 'BP' },
  { id: 40, transaction_date: '2026-06-28', amount:    -3.00, currency: 'EUR', description: 'Comisión mantenimiento',       category: 'Bank Fees',     account: 'BBVA',           category_confidence: 0.96, balance_after: 2057.86,  tags: [],             merchant: null },
  { id: 41, transaction_date: '2026-06-30', amount:   -35.00, currency: 'EUR', description: 'MetroFit Gimnasio',            category: 'Health',        account: 'BBVA',           category_confidence: 0.91, balance_after: 2022.86,  tags: [],             merchant: null },
  // ── Indexa Capital — June 2026 ────────────────────────────────────────────
  { id: 42, transaction_date: '2026-06-02', amount:  -500.00, currency: 'EUR', description: 'Aportación cartera indexada',  category: 'Investments',   account: 'Indexa Capital', category_confidence: 0.99, balance_after: 12982.50, tags: [],             merchant: null },
  { id: 43, transaction_date: '2026-06-30', amount:    48.20, currency: 'EUR', description: 'Rendimiento cartera junio',    category: 'Income',        account: 'Indexa Capital', category_confidence: 0.98, balance_after: 13030.70, tags: [],             merchant: null },
]

// ─── Filter helper ────────────────────────────────────────────────────────────

function filterTxns(params?: {
  from?: string; to?: string; account_id?: number; category_id?: number; tags?: string[]; flow?: 'expense' | 'income'
  description?: string; amount_min?: number; amount_max?: number; merchant?: string
}): Transaction[] {
  return RAW.filter(t => {
    if (params?.from && t.transaction_date < params.from) return false
    if (params?.to   && t.transaction_date > params.to)   return false
    if (params?.account_id !== undefined) {
      const acc = MOCK_ACCOUNTS.find(a => a.id === params.account_id)
      if (acc && t.account !== acc.name) return false
    }
    if (params?.category_id !== undefined) {
      const cat = MOCK_CATEGORIES.find(c => c.id === params.category_id)
      if (cat && t.category !== cat.name) return false
    }
    if (params?.tags !== undefined && params.tags.length > 0) {
      const lower = params.tags.map(tag => tag.toLowerCase())
      if (!lower.some(tag => t.tags.includes(tag))) return false
    }
    if (params?.flow === 'expense' && t.amount >= 0) return false
    if (params?.flow === 'income'  && t.amount <= 0) return false
    if (params?.description) {
      const q = params.description.toLowerCase()
      if (!t.description.toLowerCase().includes(q)) return false
    }
    if (params?.merchant) {
      const q = params.merchant.toLowerCase()
      if (!t.merchant?.toLowerCase().includes(q)) return false
    }
    return true
  })
}

function round2(n: number) { return Math.round(n * 100) / 100 }

// ─── Mock API functions ───────────────────────────────────────────────────────

export function mockGetAccounts(): Promise<Account[]> {
  return delay([..._mockAccounts])
}

export function mockCreateAccount(payload: AccountCreatePayload): Promise<Account> {
  const account: Account = {
    id: _nextAccountId++,
    name: payload.name,
    type: payload.type ?? 'bank',
    currency: payload.currency ?? 'EUR',
    tx_count: (payload.opening_balance != null && payload.opening_balance !== 0) ? 1 : 0,
    account_number_masked: null,
  }
  _mockAccounts.push(account)
  return delay({ ...account })
}

export function mockGetCategories(): Promise<Category[]> {
  return delay([..._mockCategories])
}

export function mockGetTags(): Promise<Tag[]> {
  return delay([..._mockTags])
}

export function mockCreateTag(name: string, color: string): Promise<Tag> {
  const newTag: Tag = { id: _nextTagId++, name, color, emoji: null, tx_count: 0 }
  _mockTags.push(newTag)
  return delay({ ...newTag })
}

export function mockUpdateTag(id: number, patch: { name?: string; color?: string; emoji?: string | null }): Promise<Tag> {
  const tag = _mockTags.find(t => t.id === id)
  if (!tag) return Promise.reject(new Error('HTTP 404'))
  if (patch.name  !== undefined) tag.name  = patch.name
  if (patch.color !== undefined) tag.color = patch.color
  if (patch.emoji !== undefined) tag.emoji = patch.emoji
  return delay({ ...tag })
}

export function mockDeleteTag(id: number): Promise<void> {
  const idx = _mockTags.findIndex(t => t.id === id)
  if (idx === -1) return Promise.reject(new Error('HTTP 404'))
  _mockTags.splice(idx, 1)
  return delay(undefined as unknown as void)
}

export function mockGetTransactions(params?: TransactionsParams): Promise<TransactionPage> {
  const filtered = filterTxns(params)

  const sortCol = params?.sort ?? 'date'
  const sortDir = params?.order === 'asc' ? 1 : -1

  const sorted = [...filtered].sort((a, b) => {
    switch (sortCol) {
      case 'amount':
        return (a.amount - b.amount) * sortDir
      case 'description':
        return a.description.localeCompare(b.description) * sortDir
      case 'merchant':
        return (a.merchant ?? '').localeCompare(b.merchant ?? '') * sortDir
      case 'category':
        return a.category.localeCompare(b.category) * sortDir
      case 'account':
        return a.account.localeCompare(b.account) * sortDir
      default: // date
        return b.transaction_date.localeCompare(a.transaction_date) * sortDir * -1
    }
  })

  const limit = params?.limit ?? 50
  const offset = params?.offset ?? 0
  return delay({ items: sorted.slice(offset, offset + limit), total: filtered.length, limit, offset })
}

export function mockGetOverview(params?: SummaryParams): Promise<Overview> {
  const txns = filterTxns(params)
  const total_expense = txns.filter(t => t.amount < 0)
    .reduce((s, t) => s + Math.abs(t.amount), 0)
  const total_income = txns.filter(t => t.amount > 0)
    .reduce((s, t) => s + t.amount, 0)

  const catMap = new Map<string, number>()
  for (const t of txns.filter(t => t.amount < 0)) {
    catMap.set(t.category, (catMap.get(t.category) ?? 0) + Math.abs(t.amount))
  }
  let top_category: { name: string; amount: number } | null = null
  for (const [name, amount] of catMap) {
    if (!top_category || amount > top_category.amount) top_category = { name, amount: round2(amount) }
  }

  return delay({
    total_expense: round2(total_expense),
    total_income:  round2(total_income),
    net:           round2(total_income - total_expense),
    num_transactions: txns.length,
    top_category,
    currency: 'EUR',
  })
}

export function mockGetByCategory(params?: SummaryParams): Promise<CategorySummary[]> {
  const catMap = new Map<string, { amount: number; count: number }>()
  for (const t of filterTxns(params).filter(t => t.amount < 0)) {
    const prev = catMap.get(t.category) ?? { amount: 0, count: 0 }
    catMap.set(t.category, { amount: prev.amount + Math.abs(t.amount), count: prev.count + 1 })
  }
  const result: CategorySummary[] = []
  for (const [category, { amount, count }] of catMap) {
    const cat = MOCK_CATEGORIES.find(c => c.name === category)
    result.push({ category, category_id: cat?.id ?? 0, amount: round2(amount), count })
  }
  return delay(result.sort((a, b) => b.amount - a.amount))
}

export function mockGetByMonth(params?: MonthSummaryParams): Promise<MonthSummary[]> {
  const monthMap = new Map<string, { expense: number; income: number }>()
  for (const t of filterTxns(params)) {
    const month = t.transaction_date.slice(0, 7)
    const prev = monthMap.get(month) ?? { expense: 0, income: 0 }
    if (t.amount < 0) prev.expense += Math.abs(t.amount)
    else prev.income += t.amount
    monthMap.set(month, prev)
  }
  const result: MonthSummary[] = []
  for (const [month, { expense, income }] of monthMap) {
    result.push({ month, expense: round2(expense), income: round2(income), net: round2(income - expense) })
  }
  return delay(result.sort((a, b) => a.month.localeCompare(b.month)))
}

export function mockGetByAccount(params?: SummaryParams): Promise<AccountSummary[]> {
  const accMap = new Map<string, { expense: number; income: number }>()
  for (const t of filterTxns(params)) {
    const prev = accMap.get(t.account) ?? { expense: 0, income: 0 }
    if (t.amount < 0) prev.expense += Math.abs(t.amount)
    else prev.income += t.amount
    accMap.set(t.account, prev)
  }
  const result: AccountSummary[] = []
  for (const [account, { expense, income }] of accMap) {
    const acc = MOCK_ACCOUNTS.find(a => a.name === account)
    result.push({
      account,
      expense: round2(expense),
      income: round2(income),
      net: round2(income - expense),
      currency: acc?.currency ?? 'EUR',
    })
  }
  return delay(result)
}

export function mockPostImport(_file: File, _accountName: string): Promise<ImportResult> {
  return delay({ import_run_id: 1, num_parsed: 10, num_inserted: 10, num_duplicates: 0 })
}

// ─── Mock import preview / confirm ───────────────────────────────────────────

const MOCK_PREVIEW_TXNS: ImportTransaction[] = [
  { transaction_date: '2026-07-01', amount:  2500.00, currency: 'EUR', description: 'Nómina Julio',          category: 'Income',        category_confidence: 0.97, account_ref: 'BBVA', raw_line: '01/07/2026  NOMINA JULIO                     +2.500,00', balance_after: 4522.86, tags: [], merchant: null },
  { transaction_date: '2026-07-02', amount:   -93.40, currency: 'EUR', description: 'Mercadona',              category: 'Groceries',     category_confidence: 0.96, account_ref: 'BBVA', raw_line: '02/07/2026  COMPRA TPV MERCADONA 1234        -93,40',   balance_after: 4429.46, tags: [], merchant: 'Mercadona' },
  { transaction_date: '2026-07-03', amount:  -800.00, currency: 'EUR', description: 'Alquiler Julio',         category: 'Housing',       category_confidence: 0.99, account_ref: 'BBVA', raw_line: '03/07/2026  TRANSF. ALQUILER JULIO           -800,00',  balance_after: 3629.46, tags: [], merchant: null },
  { transaction_date: '2026-07-01', amount:   -24.99, currency: 'EUR', description: 'Pago en comercio online',category: 'Other',         category_confidence: 0.38, account_ref: 'BBVA', raw_line: '01/07/2026  PAGO TPV COMERCIO ONLINE 5678    -24,99',   balance_after: null,    tags: [], merchant: null },
  { transaction_date: '2026-07-02', amount:    -9.99, currency: 'EUR', description: 'Spotify',                category: 'Subscriptions', category_confidence: 0.99, account_ref: 'BBVA', raw_line: '02/07/2026  SPOTIFY AB SPOTIFY               -9,99',    balance_after: null,    tags: [], merchant: 'Spotify' },
  { transaction_date: '2026-07-03', amount:   -44.50, currency: 'EUR', description: 'Estación de servicio',   category: 'Fuel',          category_confidence: 0.43, account_ref: 'BBVA', raw_line: '03/07/2026  ESTACION SERVICIO BP 9012        -44,50',   balance_after: null,    tags: ['combustible'], merchant: null },
]

export function mockPreviewImport(_file: File, _accountName: string): Promise<PreviewResponse> {
  return delay({
    account_ref: 'BBVA',
    filename: 'extracto-bbva-julio-2026.pdf',
    transactions: MOCK_PREVIEW_TXNS,
    statement_year: 2026,
    year_detected: true,
    quality: {
      summary: { error_count: 0, warning_count: 3, info_count: 1, flagged_row_count: 3 },
      signals: [
        { code: 'low_confidence_category', severity: 'warning', count: 2 },
        { code: 'missing_merchant', severity: 'info', count: 1 },
        { code: 'generic_category', severity: 'warning', count: 1 },
      ],
      row_flags: [
        { row_index: 3, code: 'low_confidence_category', severity: 'warning', fields: ['category'] },
        { row_index: 3, code: 'generic_category', severity: 'warning', fields: ['category'] },
        { row_index: 3, code: 'missing_merchant', severity: 'info', fields: ['merchant'] },
        { row_index: 5, code: 'low_confidence_category', severity: 'warning', fields: ['category'] },
        { row_index: 5, code: 'missing_merchant', severity: 'info', fields: ['merchant'] },
      ],
    },
  })
}

export function mockConfirmImport(payload: ConfirmRequest): Promise<ImportResult> {
  return delay({
    import_run_id:  2,
    num_parsed:     payload.transactions.length,
    num_inserted:   payload.transactions.length,
    num_duplicates: 0,
  })
}

export function mockUpdateTransaction(id: number, patch: TransactionPatch): Promise<Transaction> {
  const tx = RAW.find(t => t.id === id)
  if (!tx) return Promise.reject(new Error('HTTP 404'))
  const tags = patch.tags !== undefined ? patch.tags : tx.tags
  const merchant = patch.merchant !== undefined
    ? (patch.merchant === '' ? null : patch.merchant)
    : tx.merchant
  return delay({ ...tx, ...patch, tags, merchant })
}

export function mockGetCashflow(params?: SummaryParams): Promise<CashflowSummary> {
  const txns = filterTxns(params)

  const incomeMap = new Map<string, number>()
  const expenseMap = new Map<string, number>()
  for (const t of txns) {
    if (t.amount > 0) {
      incomeMap.set(t.category, (incomeMap.get(t.category) ?? 0) + t.amount)
    } else if (t.amount < 0) {
      expenseMap.set(t.category, (expenseMap.get(t.category) ?? 0) + Math.abs(t.amount))
    }
  }

  const income = Array.from(incomeMap.entries())
    .map(([category, amount]) => ({ category, amount: round2(amount) }))
    .sort((a, b) => b.amount - a.amount)
  const expense = Array.from(expenseMap.entries())
    .map(([category, amount]) => ({ category, amount: round2(amount) }))
    .sort((a, b) => b.amount - a.amount)

  return delay({
    income,
    expense,
    total_income:  round2(income.reduce((s, i) => s + i.amount, 0)),
    total_expense: round2(expense.reduce((s, e) => s + e.amount, 0)),
    currency: 'EUR',
  })
}

export function mockUpdateCategory(id: number, patch: { color?: string }): Promise<Category> {
  const cat = _mockCategories.find(c => c.id === id)
  if (!cat) return Promise.reject(new Error('HTTP 404'))
  if (patch.color !== undefined) cat.color = patch.color
  return delay({ ...cat })
}

export function mockCreateCategory(name: string, color?: string): Promise<Category> {
  const newCat: Category = {
    id: _nextCategoryId++,
    name,
    is_base: false,
    color: color ?? '#94a3b8',
    name_es: null,
    tx_count: 0,
  }
  _mockCategories.push(newCat)
  return delay({ ...newCat }, 800)
}

export function mockGetByMerchant(_params?: SummaryParams): Promise<MerchantSummary[]> {
  return delay([])
}

export function mockGetByDay(params?: MonthSummaryParams): Promise<DaySummary[]> {
  const dayMap = new Map<string, { expense: number; income: number }>()
  for (const t of filterTxns(params)) {
    const day = t.transaction_date
    const prev = dayMap.get(day) ?? { expense: 0, income: 0 }
    if (t.amount < 0) prev.expense += Math.abs(t.amount)
    else prev.income += t.amount
    dayMap.set(day, prev)
  }
  const result: DaySummary[] = []
  for (const [day, { expense, income }] of dayMap) {
    result.push({ day, expense: round2(expense), income: round2(income), net: round2(income - expense) })
  }
  return delay(result.sort((a, b) => a.day.localeCompare(b.day)))
}

export function mockGetStatementReminder(): Promise<StatementReminder> {
  return delay({ year: null, month: null, missing_account_ids: [] })
}

// ─── Simulate async latency ───────────────────────────────────────────────────

function delay<T>(data: T, ms = 150): Promise<T> {
  return new Promise(resolve => setTimeout(() => resolve(data), ms))
}

// ─── Mock auth state (initialized + authenticated for demo) ───────────────────

let _mockInitialized = true
let _mockAuthenticated = true
let _mockUsername = 'demo'

export function mockGetAuthStatus(): Promise<AuthStatus> {
  return delay({ initialized: _mockInitialized, authenticated: _mockAuthenticated })
}

export function mockSetupUser(username: string, _password: string): Promise<AuthUser> {
  _mockInitialized = true
  _mockAuthenticated = true
  _mockUsername = username
  return delay({ username })
}

export function mockLogin(username: string, _password: string): Promise<AuthUser> {
  _mockAuthenticated = true
  _mockUsername = username
  return delay({ username })
}

export function mockLogout(): Promise<void> {
  _mockAuthenticated = false
  return delay(undefined as void)
}

export function mockGetMe(): Promise<AuthUser> {
  return delay({ username: _mockUsername })
}

// ─── Investments ──────────────────────────────────────────────────────────────

export function mockGetInvestmentPlugins(): Promise<InvestmentPlugin[]> {
  return delay([
    {
      id: 'indexa-capital',
      name: 'Indexa Capital',
      description: 'Automated index-fund portfolio management',
      icon: '🏦',
      status: _mockConnected ? 'connected' : 'available',
      auth_type: 'token',
      supported_features: ['holdings', 'transactions', 'performance'],
      import_route: null,
    },
    {
      id: 'fidelity-espp',
      name: 'Fidelity ESPP',
      description: 'Import MSFT ESPP holdings from Fidelity CSV',
      icon: '🏢',
      status: 'available',
      auth_type: 'none',
      supported_features: ['holdings'],
      import_route: '/investments/fidelity-espp',
    },
    {
      id: 'generic-broker',
      name: 'Broker (Stocks & ETFs)',
      description: 'Connect a stock/ETF broker account',
      icon: '📈',
      status: 'coming_soon',
      auth_type: 'api_key',
      supported_features: ['holdings', 'transactions'],
      import_route: null,
    },
    {
      id: 'crypto-exchange',
      name: 'Crypto Exchange',
      description: 'Track crypto holdings from an exchange',
      icon: '🪙',
      status: 'coming_soon',
      auth_type: 'api_key',
      supported_features: ['holdings'],
      import_route: null,
    },
  ])
}

// ─── Investments Phase 2 ─────────────────────────────────────────────────────

let _mockConnected = false

export function mockValidateIndexaToken(token: string): Promise<ValidateAccountsResponse> {
  if (!token || token.trim().length < 8) {
    return Promise.reject(
      Object.assign(new Error('Token inválido — verifícalo en Indexa Capital.'), { status: 400 }),
    )
  }
  return delay({
    accounts: [
      { account_number: 'PBK12345Z5', account_number_masked: 'PBK•••Z5', type: 'fondos', status: 'active' },
    ],
  })
}

export function mockConnectPlugin(_token: string, _accountNumbers: string[]): Promise<InvestmentConnection[]> {
  _mockConnected = true
  return delay([
    {
      id: 1,
      plugin_id: 'indexa-capital',
      status: 'active',
      account_label_masked: 'PBK•••Z5',
      created_at: '2026-07-14T11:10:33+02:00',
      last_synced_at: '2026-07-14T11:12:00+02:00',
    },
  ])
}

export function mockGetConnections(): Promise<InvestmentConnection[]> {
  if (!_mockConnected) return delay([])
  return delay([
    {
      id: 1,
      plugin_id: 'indexa-capital',
      status: 'active',
      account_label_masked: 'PBK•••Z5',
      created_at: '2026-07-14T11:10:33+02:00',
      last_synced_at: '2026-07-14T11:12:00+02:00',
    },
  ])
}

export function mockDisconnectConnection(_id: number): Promise<void> {
  _mockConnected = false
  return delay(undefined as void)
}

export function mockGetInvestmentPortfolio(): Promise<InvestmentPortfolio> {
  if (!_mockConnected) {
    return delay({
      total_value: 0,
      total_invested: null,
      total_gain_loss: null,
      total_gain_loss_pct: null,
      currency: 'EUR',
      plugins_connected: 0,
      last_updated: null,
      returns: null,
      value_series: [],
      contributions_series: [],
      monthly_returns: null,
      drawdown: null,
      cash_invested: null,
      holdings: [],
    })
  }
  return delay({
    total_value: 12345.67,
    total_invested: 11000.00,
    total_gain_loss: 1345.67,
    total_gain_loss_pct: 0.1223,
    currency: 'EUR',
    plugins_connected: 1,
    last_updated: '2026-07-14T11:12:00.123456+00:00',
    returns: {
      twr_annual: 0.0851,
      xirr: 0.0912,
      pl: 1345.67,
      invested: 11000.00,
      twr_total: 0.1223,
      twr_last_week: 0.0042,
      twr_last_month: 0.0187,
      twr_last_year: 0.0831,
      money_return: 0.1222,
      volatility: 0.0614,
      aportaciones: 11000.00,
      retenciones: -0.01,
      rentabilidad_eur: 1345.67,
      rentabilidad_pct: 0.1222,
      sharpe_ratio: 1.12,
      money_return_annual: 0.0851,
    },
    value_series: [
      { date: '2023-01-01', value: 9800.00 },
      { date: '2023-02-01', value: 10050.00 },
      { date: '2023-03-01', value: 9950.00 },
      { date: '2023-04-01', value: 10200.00 },
      { date: '2023-05-01', value: 10450.00 },
      { date: '2023-06-01', value: 10600.00 },
      { date: '2023-07-01', value: 10800.00 },
      { date: '2023-08-01', value: 10700.00 },
      { date: '2023-09-01', value: 11050.00 },
      { date: '2023-10-01', value: 11200.00 },
      { date: '2023-11-01', value: 11400.00 },
      { date: '2023-12-01', value: 11600.00 },
      { date: '2024-01-01', value: 11850.00 },
      { date: '2024-02-01', value: 12100.00 },
      { date: '2024-03-01', value: 12345.67 },
    ],
    contributions_series: [
      { date: '2023-01-01', value: 9500.00 },
      { date: '2023-04-01', value: 9750.00 },
      { date: '2023-07-01', value: 10250.00 },
      { date: '2023-10-01', value: 10750.00 },
      { date: '2024-01-01', value: 11000.00 },
    ],
    monthly_returns: [
      {
        year: 2023,
        months_pct: { '1': 0.012, '2': 0.008, '3': -0.005, '4': 0.021, '5': 0.015, '6': 0.009, '7': 0.018, '8': -0.008, '9': 0.022, '10': 0.017, '11': 0.014, '12': 0.019 },
        months_eur: { '1': 110, '2': 75, '3': -46, '4': 197, '5': 142, '6': 87, '7': 173, '8': -77, '9': 215, '10': 166, '11': 138, '12': 188 },
        total_pct: 0.1485,
        total_eur: 1368.0,
        benchmark_pct: 0.1210,
      },
      {
        year: 2024,
        months_pct: { '1': 0.025, '2': 0.012, '3': -0.003 },
        months_eur: { '1': 290, '2': 140, '3': -36 },
        total_pct: 0.0342,
        total_eur: 394.0,
        benchmark_pct: 0.0280,
      },
    ],
    drawdown: {
      max_drawdown: -0.0912,
      max_drawdown_eur: -1024.32,
      start_date: '2023-08-01',
      end_date: '2023-08-31',
    },
    cash_invested: {
      cash_amount: 250.00,
      instruments_amount: 12095.67,
      instruments_cost: 10750.00,
      total_amount: 12345.67,
    },
    holdings: [
      {
        plugin_id: 'indexa-capital',
        name: 'Vanguard Global Stock Index Fund',
        ticker: 'IE00B03HCZ61',
        asset_class: 'equity',
        units: 42.5,
        current_value: 8320.00,
        cost_basis: 7500.00,
        currency: 'EUR',
        gain_loss: 820.00,
        gain_loss_pct: 0.1093,
        last_updated: '2026-07-14T11:12:00.123456+00:00',
      },
      {
        plugin_id: 'indexa-capital',
        name: 'iShares Core Euro Corporate Bond',
        ticker: 'IE00B3F81R35',
        asset_class: 'fixed_income',
        units: 28.0,
        current_value: 3525.67,
        cost_basis: 3000.00,
        currency: 'EUR',
        gain_loss: 525.67,
        gain_loss_pct: 0.1752,
        last_updated: '2026-07-14T11:12:00.123456+00:00',
      },
      {
        plugin_id: 'indexa-capital',
        name: 'Cash / Money Market',
        ticker: 'CASH',
        asset_class: 'cash',
        units: 250.00,
        current_value: 250.00,
        cost_basis: 250.00,
        currency: 'EUR',
        gain_loss: 0.00,
        gain_loss_pct: 0.00,
        last_updated: '2026-07-14T11:12:00.123456+00:00',
      },
    ],
  })
}

// ─── Notifications ────────────────────────────────────────────────────────────

const MOCK_NOTIFICATIONS_INITIAL: NotificationOut[] = [
  {
    id: 1,
    source: 'espp',
    type: 'espp_overdue',
    severity: 'warning',
    title_key: 'notif.espp_overdue',
    title_args: { period: 'Q2 2026' },
    body_key: null,
    body_args: null,
    action_link: '/investments/fidelity-espp',
    created_at: '2026-07-15T10:00:00+02:00',
    read_at: null,
    dismissed_at: null,
  },
  {
    id: 2,
    source: 'statement',
    type: 'statement_missing',
    severity: 'info',
    title_key: 'notif.statement_missing',
    title_args: { month: 'Junio 2026', account: 'BBVA' },
    body_key: null,
    body_args: null,
    action_link: '/finances?account_id=1',
    created_at: '2026-07-16T08:00:00+02:00',
    read_at: null,
    dismissed_at: null,
  },
]

let _mockNotifications: NotificationOut[] = [...MOCK_NOTIFICATIONS_INITIAL]

export function mockGetNotifications(): Promise<NotificationOut[]> {
  return delay(_mockNotifications.filter(n => !n.dismissed_at))
}

export function mockGetUnreadCount(): Promise<{ count: number }> {
  return delay({ count: _mockNotifications.filter(n => !n.dismissed_at && !n.read_at).length })
}

export function mockMarkNotificationRead(id: number): Promise<void> {
  _mockNotifications = _mockNotifications.map(n =>
    n.id === id ? { ...n, read_at: new Date().toISOString() } : n,
  )
  return delay(undefined as void)
}

export function mockMarkAllNotificationsRead(): Promise<{ updated: number }> {
  let count = 0
  _mockNotifications = _mockNotifications.map(n => {
    if (!n.read_at && !n.dismissed_at) { count++; return { ...n, read_at: new Date().toISOString() } }
    return n
  })
  return delay({ updated: count })
}

export function mockDismissNotification(id: number): Promise<void> {
  _mockNotifications = _mockNotifications.map(n =>
    n.id === id ? { ...n, dismissed_at: new Date().toISOString() } : n,
  )
  return delay(undefined as void)
}

// ─── Notification channels ────────────────────────────────────────────────────

let _mockChannels: NotificationChannelOut[] = []
let _nextChannelId = 1

export function mockGetNotificationChannels(): Promise<NotificationChannelOut[]> {
  return delay([..._mockChannels])
}

export function mockCreateTelegramChannel(body: TelegramChannelIn): Promise<NotificationChannelOut> {
  _mockChannels = _mockChannels.filter(c => c.channel !== 'telegram')
  const masked = body.chat_id.replace(/./g, '*').slice(0, -3) + body.chat_id.slice(-3)
  const channel: NotificationChannelOut = {
    id: _nextChannelId++,
    channel: 'telegram',
    label: masked,
    enabled: true,
    created_at: new Date().toISOString(),
  }
  _mockChannels.push(channel)
  return delay(channel)
}

export function mockDeleteNotificationChannel(id: number): Promise<void> {
  _mockChannels = _mockChannels.filter(c => c.id !== id)
  return delay(undefined as void)
}

export function mockTestTelegramChannel(_body: TelegramTestIn): Promise<TelegramTestOut> {
  return delay({ ok: true })
}

