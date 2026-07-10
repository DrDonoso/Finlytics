import type {
  Account, Category, Tag, TransactionPage, Overview,
  CategorySummary, MonthSummary, DaySummary, AccountSummary, ImportResult,
  ImportTransaction, PreviewResponse, ConfirmRequest,
  TransactionsParams, SummaryParams, MonthSummaryParams,
  Transaction, TransactionPatch, CashflowSummary, CategoryPatch,
  AuthStatus, AuthUser, BackupImportSummary,
  Rule, RuleInput, RulePatch,
  StatementMonth, MerchantSummary,
} from './types'
import {
  mockGetAccounts, mockGetCategories, mockGetTags, mockGetTransactions,
  mockGetOverview, mockGetByCategory, mockGetByMonth,
  mockGetByAccount, mockPostImport, mockPreviewImport, mockConfirmImport,
  mockUpdateTransaction, mockGetCashflow,
  mockCreateTag, mockUpdateTag, mockDeleteTag, mockUpdateCategory,
  mockCreateCategory,
  mockGetAuthStatus, mockSetupUser, mockLogin, mockLogout, mockGetMe,
  mockGetByMerchant, mockGetByDay,
} from './mock'

const USE_MOCK = import.meta.env.VITE_USE_MOCK === '1'

// ─── 401 global handler ───────────────────────────────────────────────────────

let _on401: (() => void) | null = null

/** Register a callback invoked whenever any protected API call gets a 401 response. */
export function registerOn401Handler(fn: () => void): void {
  _on401 = fn
}

// ─── URL builder ─────────────────────────────────────────────────────────────

/** Builds a URL with query params. Arrays are serialised as repeated params.
 *  Special mapping: key 'tags' → URL param name 'tag' (backend uses ?tag=x&tag=y). */
function buildUrl(path: string, params?: Record<string, unknown>): string {
  const url = new URL(path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue
      if (Array.isArray(v)) {
        const urlKey = k === 'tags' ? 'tag' : k
        for (const item of v) url.searchParams.append(urlKey, String(item))
      } else {
        url.searchParams.set(k, String(v))
      }
    }
  }
  return url.toString()
}

async function apiFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, { credentials: 'same-origin', ...options })
  if (res.status === 401) {
    _on401?.()
    throw new Error('HTTP 401 Unauthorized')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

/** POST to an auth endpoint without triggering the global 401 handler.
 *  Attaches status to thrown errors so callers can branch on 401 / 409. */
async function authPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data: { detail?: string } = await res.json().catch(() => ({}))
    throw Object.assign(new Error(data.detail ?? `HTTP ${res.status}`), { status: res.status })
  }
  return res.json() as Promise<T>
}

// ─── Public API ───────────────────────────────────────────────────────────────

export async function getAccounts(): Promise<Account[]> {
  if (USE_MOCK) return mockGetAccounts()
  try { return await apiFetch<Account[]>(buildUrl('/api/accounts')) }
  catch { return mockGetAccounts() }
}

/** PATCH /api/accounts/{id} body { name } → updated account. (Name only; number immutable.) */
export async function patchAccount(id: number, name: string): Promise<Account> {
  return apiFetch<Account>(`/api/accounts/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
}

/** DELETE /api/accounts/{id} → { deleted: number }. Returns 404 if account not found. */
export async function deleteAccount(id: number): Promise<{ deleted: number }> {
  return apiFetch<{ deleted: number }>(`/api/accounts/${id}`, { method: 'DELETE' })
}

export async function getCategories(): Promise<Category[]> {
  if (USE_MOCK) return mockGetCategories()
  try { return await apiFetch<Category[]>(buildUrl('/api/categories')) }
  catch { return mockGetCategories() }
}

export async function getTags(): Promise<Tag[]> {
  if (USE_MOCK) return mockGetTags()
  try { return await apiFetch<Tag[]>(buildUrl('/api/tags')) }
  catch { return mockGetTags() }
}

export async function getTransactions(params?: TransactionsParams): Promise<TransactionPage> {
  if (USE_MOCK) return mockGetTransactions(params)
  try { return await apiFetch<TransactionPage>(buildUrl('/api/transactions', params as Record<string, unknown>)) }
  catch { return mockGetTransactions(params) }
}

export async function getOverview(params?: SummaryParams): Promise<Overview> {
  if (USE_MOCK) return mockGetOverview(params)
  try { return await apiFetch<Overview>(buildUrl('/api/summary/overview', params as Record<string, unknown>)) }
  catch { return mockGetOverview(params) }
}

export async function getByCategory(params?: SummaryParams): Promise<CategorySummary[]> {
  if (USE_MOCK) return mockGetByCategory(params)
  try { return await apiFetch<CategorySummary[]>(buildUrl('/api/summary/by-category', params as Record<string, unknown>)) }
  catch { return mockGetByCategory(params) }
}

export async function getByMonth(params?: MonthSummaryParams): Promise<MonthSummary[]> {
  if (USE_MOCK) return mockGetByMonth(params)
  try { return await apiFetch<MonthSummary[]>(buildUrl('/api/summary/by-month', params as Record<string, unknown>)) }
  catch { return mockGetByMonth(params) }
}

export async function getByAccount(params?: SummaryParams): Promise<AccountSummary[]> {
  if (USE_MOCK) return mockGetByAccount(params)
  try { return await apiFetch<AccountSummary[]>(buildUrl('/api/summary/by-account', params as Record<string, unknown>)) }
  catch { return mockGetByAccount(params) }
}

export async function getByMerchant(params?: SummaryParams): Promise<MerchantSummary[]> {
  if (USE_MOCK) return mockGetByMerchant(params)
  try { return await apiFetch<MerchantSummary[]>(buildUrl('/api/summary/by-merchant', params as Record<string, unknown>)) }
  catch { return mockGetByMerchant(params) }
}

export async function getByDay(params?: MonthSummaryParams): Promise<DaySummary[]> {
  if (USE_MOCK) return mockGetByDay(params)
  try { return await apiFetch<DaySummary[]>(buildUrl('/api/summary/by-day', params as Record<string, unknown>)) }
  catch { return mockGetByDay(params) }
}

export async function postImport(file: File, accountName: string): Promise<ImportResult> {
  if (USE_MOCK) return mockPostImport(file, accountName)
  try {
    const form = new FormData()
    form.append('file', file)
    form.append('account_name', accountName)
    return await apiFetch<ImportResult>('/api/imports', { method: 'POST', body: form })
  } catch { return mockPostImport(file, accountName) }
}

// ─── Two-step import ──────────────────────────────────────────────────────────

export async function previewImport(file: File, accountName?: string): Promise<PreviewResponse> {
  if (USE_MOCK) return mockPreviewImport(file, accountName ?? '')
  const form = new FormData()
  form.append('file', file)
  if (accountName) form.append('account_name', accountName)
  return apiFetch<PreviewResponse>('/api/imports/preview', { method: 'POST', body: form })
}

/** POST /api/imports/check-duplicates — detects which preview rows already exist in the DB.
 *  Callers must degrade gracefully on error (no marks, don't block preview). */
export async function checkDuplicates(
  accountName: string,
  transactions: Array<{ transaction_date: string; amount: number; description: string; detail: string | null }>,
): Promise<{ is_duplicate: boolean[] }> {
  return apiFetch<{ is_duplicate: boolean[] }>('/api/imports/check-duplicates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account_name: accountName, transactions }),
  })
}

/** Call POST /api/imports/confirm — does NOT fall back to mock on real errors. */
export async function confirmImport(payload: ConfirmRequest): Promise<ImportResult> {
  if (USE_MOCK) return mockConfirmImport(payload)
  return apiFetch<ImportResult>('/api/imports/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** PATCH /api/transactions/{id} — does NOT fall back to mock on real errors.
 *  Returns 404 if missing, 409 on dedup collision. */
export async function updateTransaction(id: number, patch: TransactionPatch): Promise<Transaction> {
  if (USE_MOCK) return mockUpdateTransaction(id, patch)
  return apiFetch<Transaction>(`/api/transactions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function getCashflow(params?: SummaryParams): Promise<CashflowSummary> {
  if (USE_MOCK) return mockGetCashflow(params)
  try { return await apiFetch<CashflowSummary>(buildUrl('/api/summary/cashflow', params as Record<string, unknown>)) }
  catch { return mockGetCashflow(params) }
}

// ─── Tag CRUD ─────────────────────────────────────────────────────────────────

export async function createTag(name: string, color: string): Promise<Tag> {
  if (USE_MOCK) return mockCreateTag(name, color)
  return apiFetch<Tag>('/api/tags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, color }),
  })
}

export async function updateTag(id: number, patch: { name?: string; color?: string; emoji?: string | null }): Promise<Tag> {
  if (USE_MOCK) return mockUpdateTag(id, patch)
  return apiFetch<Tag>(`/api/tags/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function deleteTag(id: number): Promise<void> {
  if (USE_MOCK) return mockDeleteTag(id)
  const res = await fetch(`/api/tags/${id}`, { method: 'DELETE', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function updateCategory(id: number, patch: CategoryPatch): Promise<Category> {
  if (USE_MOCK) return mockUpdateCategory(id, patch)
  return apiFetch<Category>(`/api/categories/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
}

export async function createCategory(name: string, color?: string): Promise<Category> {
  if (USE_MOCK) return mockCreateCategory(name, color)
  return apiFetch<Category>('/api/categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...(color ? { color } : {}) }),
  })
}

// ─── Rules CRUD ───────────────────────────────────────────────────────────────

/** GET /api/rules — returns all rules ordered by (priority, id). No mock fallback. */
export async function getRules(): Promise<Rule[]> {
  return apiFetch<Rule[]>('/api/rules')
}

/** POST /api/rules — surfaces backend 422 detail on validation failure. */
export async function createRule(input: RuleInput): Promise<Rule> {
  const res = await fetch('/api/rules', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) {
    const data: { detail?: unknown } = await res.json().catch(() => ({}))
    const msg = typeof data.detail === 'string'
      ? data.detail
      : Array.isArray(data.detail)
        ? (data.detail as Array<{ msg?: string }>).map(d => d.msg ?? String(d)).join('; ')
        : `HTTP ${res.status}`
    throw new Error(msg)
  }
  return res.json() as Promise<Rule>
}

/** PATCH /api/rules/{id} — surfaces backend 422 detail on validation failure. */
export async function updateRule(id: number, patch: RulePatch): Promise<Rule> {
  const res = await fetch(`/api/rules/${id}`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) {
    const data: { detail?: unknown } = await res.json().catch(() => ({}))
    const msg = typeof data.detail === 'string'
      ? data.detail
      : Array.isArray(data.detail)
        ? (data.detail as Array<{ msg?: string }>).map(d => d.msg ?? String(d)).join('; ')
        : `HTTP ${res.status}`
    throw new Error(msg)
  }
  return res.json() as Promise<Rule>
}

/** DELETE /api/rules/{id} — returns 204 on success. */
export async function deleteRule(id: number): Promise<void> {
  const res = await fetch(`/api/rules/${id}`, { method: 'DELETE', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ─── Backup ───────────────────────────────────────────────────────────────────

/** GET /api/backup/export — returns full backup JSON. Does NOT fall back to mock. */
export async function exportBackup(): Promise<unknown> {
  return apiFetch<unknown>('/api/backup/export')
}

/** POST /api/backup/import — restores a backup. Does NOT fall back to mock. */
export async function importBackup(data: unknown): Promise<BackupImportSummary> {
  return apiFetch<BackupImportSummary>('/api/backup/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

// ─── Statements ───────────────────────────────────────────────────────────────

/** GET /api/statements/months?account_id={id?} → months with transactions, sorted DESC by (year, month). */
export async function getStatementMonths(account_id?: number): Promise<StatementMonth[]> {
  return apiFetch<StatementMonth[]>(buildUrl('/api/statements/months', account_id !== undefined ? { account_id } : undefined))
}

/** DELETE /api/statements/month?year={y}&month={m}&account_id={id?} → { deleted: number }. */
export async function deleteStatementMonth(year: number, month: number, account_id?: number): Promise<{ deleted: number }> {
  return apiFetch<{ deleted: number }>(
    buildUrl('/api/statements/month', { year, month, ...(account_id !== undefined ? { account_id } : {}) }),
    { method: 'DELETE' },
  )
}

// ─── Rules preview / apply ────────────────────────────────────────────────────

/** POST /api/rules/preview — counts current transactions the rule would match. */
export async function previewRule(payload: RuleInput): Promise<{ count: number }> {
  return apiFetch<{ count: number }>('/api/rules/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** POST /api/rules/apply — applies the rule to all matching current transactions. */
export async function applyRule(payload: RuleInput): Promise<{ applied: number }> {
  return apiFetch<{ applied: number }>('/api/rules/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// ─── Shared formatter ─────────────────────────────────────────────────────────

export function formatEur(amount: number): string {
  return new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' }).format(amount)
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export async function getAuthStatus(): Promise<AuthStatus> {
  if (USE_MOCK) return mockGetAuthStatus()
  return apiFetch<AuthStatus>(buildUrl('/api/auth/status'))
}

export async function setupUser(username: string, password: string): Promise<AuthUser> {
  if (USE_MOCK) return mockSetupUser(username, password)
  return authPost<AuthUser>('/api/auth/setup', { username, password })
}

export async function login(username: string, password: string, remember = false): Promise<AuthUser> {
  if (USE_MOCK) return mockLogin(username, password)
  return authPost<AuthUser>('/api/auth/login', { username, password, remember })
}

export async function logout(): Promise<void> {
  if (USE_MOCK) return mockLogout()
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' })
}

export async function getMe(): Promise<AuthUser> {
  if (USE_MOCK) return mockGetMe()
  return apiFetch<AuthUser>(buildUrl('/api/auth/me'))
}
