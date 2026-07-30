import type {
  Account, Category, Tag, TransactionPage, Overview,
  CategorySummary, MonthSummary, DaySummary, AccountSummary, ImportResult,
  PreviewResponse, ConfirmRequest,
  TransactionsParams, SummaryParams, MonthSummaryParams,
  Transaction, TransactionPatch, CashflowSummary, CategoryPatch,
  AuthStatus, AuthUser, BackupDocument, BackupExportSelection, BackupImportSummary,
  Rule, RuleInput, RulePatch,
  StatementMonth, StatementReminder, MerchantSummary, StatementOriginal, InvestmentPlugin,
  InvestmentPortfolio, InvestmentConnection, ValidateAccountsResponse,
  FidelityKpis, FidelityEvolution, FidelityLots,
  FidelityImportPreview, FidelityImportConfirmResult, FidelityReminderResponse,
  CombinedOverview, SummaryMonths, AppVersion, NotificationOut,
  NotificationChannelOut, TelegramChannelIn, TelegramTestIn, TelegramTestOut,
  AccountCreatePayload,
} from './types'
import {
  mockGetAccounts, mockGetCategories, mockGetTags, mockGetTransactions,
  mockGetOverview, mockGetByCategory, mockGetByMonth,
  mockGetByAccount, mockPostImport, mockPreviewImport, mockConfirmImport,
  mockUpdateTransaction, mockGetCashflow,
  mockCreateTag, mockUpdateTag, mockDeleteTag, mockUpdateCategory,
  mockCreateCategory,
  mockGetAuthStatus, mockSetupUser, mockLogin, mockLogout, mockGetMe,
  mockGetByMerchant, mockGetByDay, mockGetInvestmentPlugins,
  mockValidateIndexaToken, mockConnectPlugin, mockGetConnections,
  mockDisconnectConnection, mockGetInvestmentPortfolio, mockGetStatementReminder,
  mockGetNotifications, mockGetUnreadCount,
  mockMarkNotificationRead, mockMarkAllNotificationsRead, mockDismissNotification,
  mockGetNotificationChannels, mockCreateTelegramChannel,
  mockDeleteNotificationChannel, mockTestTelegramChannel,
  mockCreateAccount,
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
 *  Attaches status to thrown errors so callers can branch on 401 / 409 / 429. */
async function authPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const data: { detail?: string } = await res.json().catch(() => ({}))
    // Retry-After acompaña al 429 del límite de intentos: sin él sólo se puede
    // decir «demasiados intentos», no cuánto hay que esperar.
    const retryAfterHeader = res.headers.get('Retry-After')
    const retryAfter = retryAfterHeader === null ? undefined : Number(retryAfterHeader)
    throw Object.assign(new Error(data.detail ?? `HTTP ${res.status}`), {
      status: res.status,
      retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined,
    })
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

/** POST /api/accounts → 201, returns new Account.
 *  Uses raw fetch to surface 409 (duplicate name/IBAN) and 422 (balance without date). */
export async function createAccount(payload: AccountCreatePayload): Promise<Account> {
  if (USE_MOCK) return mockCreateAccount(payload)
  const res = await fetch('/api/accounts', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) {
    const data: { detail?: string } = await res.json().catch(() => ({}))
    throw Object.assign(new Error(data.detail ?? `HTTP ${res.status}`), { status: res.status })
  }
  return res.json() as Promise<Account>
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

/** GET /api/backup/export — returns backup JSON. Does NOT fall back to mock. */
export async function exportBackup(selection?: BackupExportSelection): Promise<BackupDocument> {
  const allSelected = selection
    ? Object.values(selection).every(Boolean)
    : true
  return apiFetch<BackupDocument>(
    buildUrl('/api/backup/export', selection && !allSelected ? selection as unknown as Record<string, unknown> : undefined),
  )
}

/** POST /api/backup/import — restores a backup. Does NOT fall back to mock. */
export async function importBackup(data: BackupDocument): Promise<BackupImportSummary> {
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

/** GET /api/statements/reminder → previous completed month and accounts missing its statement. */
export async function getStatementReminder(): Promise<StatementReminder> {
  if (USE_MOCK) return mockGetStatementReminder()
  return apiFetch<StatementReminder>(buildUrl('/api/statements/reminder'))
}

/** GET /api/statements/originals?year={y}&month={m}&account_id={id?}
 *  Returns only statements with a stored original PDF. Degrades to [] on any error. */
export async function getStatementOriginals(year: number, month: number, accountId?: number): Promise<StatementOriginal[]> {
  try {
    return await apiFetch<StatementOriginal[]>(buildUrl('/api/statements/originals', { year, month, ...(accountId !== undefined ? { account_id: accountId } : {}) }))
  } catch {
    return []
  }
}

/** GET /api/statements/original/{importRunId} → PDF as attachment.
 *  Uses authenticated fetch+blob+objectURL to trigger a browser download. */
export async function downloadStatementOriginal(importRunId: number, filename: string): Promise<void> {
  const res = await fetch(`/api/statements/original/${importRunId}`, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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

// ─── Investments ──────────────────────────────────────────────────────────────

export async function getInvestmentPlugins(): Promise<InvestmentPlugin[]> {
  if (USE_MOCK) return mockGetInvestmentPlugins()
  return apiFetch<InvestmentPlugin[]>(buildUrl('/api/investments/plugins'))
}

/** POST /api/investments/connections/validate — verifies token and returns discovered accounts.
 *  400 = invalid token; 503 = network/config error. */
export async function validateIndexaToken(token: string): Promise<ValidateAccountsResponse> {
  if (USE_MOCK) return mockValidateIndexaToken(token)
  const res = await fetch('/api/investments/connections/validate', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) {
    const data: { detail?: string } = await res.json().catch(() => ({}))
    throw Object.assign(new Error(data.detail ?? `HTTP ${res.status}`), { status: res.status })
  }
  return res.json() as Promise<ValidateAccountsResponse>
}

/** POST /api/investments/connections — stores selected accounts; returns ConnectionOut[]. */
export async function connectPlugin(token: string, accountNumbers: string[]): Promise<InvestmentConnection[]> {
  if (USE_MOCK) return mockConnectPlugin(token, accountNumbers)
  return apiFetch<InvestmentConnection[]>('/api/investments/connections', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, account_numbers: accountNumbers }),
  })
}

/** GET /api/investments/connections — all active connections for the current user. */
export async function getConnections(): Promise<InvestmentConnection[]> {
  if (USE_MOCK) return mockGetConnections()
  return apiFetch<InvestmentConnection[]>(buildUrl('/api/investments/connections'))
}

/** DELETE /api/investments/connections/{id} — hard-deletes connection + encrypted token. */
export async function disconnectConnection(id: number): Promise<void> {
  if (USE_MOCK) return mockDisconnectConnection(id)
  const res = await fetch(`/api/investments/connections/${id}`, { method: 'DELETE', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

/** GET /api/investments/portfolio — aggregated portfolio for all active connections. */
export async function getInvestmentPortfolio(): Promise<InvestmentPortfolio> {
  if (USE_MOCK) return mockGetInvestmentPortfolio()
  return apiFetch<InvestmentPortfolio>(buildUrl('/api/investments/portfolio'))
}

// ─── Fidelity ESPP ────────────────────────────────────────────────────────────

/** GET /api/investments/fidelity/kpis — KPI summary for the MSFT ESPP portfolio. */
export async function getFidelityKpis(): Promise<FidelityKpis> {
  return apiFetch<FidelityKpis>(buildUrl('/api/investments/fidelity/kpis'))
}

/** GET /api/investments/fidelity/evolution — time-series: portfolio value + contributions. */
export async function getFidelityEvolution(): Promise<FidelityEvolution> {
  return apiFetch<FidelityEvolution>(buildUrl('/api/investments/fidelity/evolution'))
}

/** GET /api/investments/fidelity/lots — all purchase lots, ordered by purchase_date DESC. */
export async function getFidelityLots(): Promise<FidelityLots> {
  return apiFetch<FidelityLots>(buildUrl('/api/investments/fidelity/lots'))
}

/** POST /api/investments/fidelity/import/preview — parse CSV and return new lots (not yet persisted). */
export async function fidelityImportPreview(file: File): Promise<FidelityImportPreview> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<FidelityImportPreview>('/api/investments/fidelity/import/preview', {
    method: 'POST',
    body: form,
  })
}

/** POST /api/investments/fidelity/import/confirm — re-send the file to persist new lots. */
export async function fidelityImportConfirm(file: File): Promise<FidelityImportConfirmResult> {
  const form = new FormData()
  form.append('file', file)
  return apiFetch<FidelityImportConfirmResult>('/api/investments/fidelity/import/confirm', {
    method: 'POST',
    body: form,
  })
}

/** GET /api/investments/fidelity/reminder — ESPP upload reminder status.
 *  Always returns 200; overdue=false when no connection. Fails silently (caller ignores errors). */
export async function getFidelityReminder(): Promise<FidelityReminderResponse> {
  return apiFetch<FidelityReminderResponse>(buildUrl('/api/investments/fidelity/reminder'))
}

/** GET /api/investments/combined-overview — consolidated overview across all providers. */
export async function getCombinedOverview(): Promise<CombinedOverview> {
  return apiFetch<CombinedOverview>(buildUrl('/api/investments/combined-overview'))
}

/** GET /api/summary/months → { months: ["YYYY-MM", …], latest: "YYYY-MM" | null }.
 *  Degrades to { months: [], latest: null } on any error; caller falls back to the previous calendar month. */
export async function getOverviewMonths(): Promise<SummaryMonths> {
  try {
    return await apiFetch<SummaryMonths>(buildUrl('/api/summary/months'))
  } catch {
    return { months: [], latest: null }
  }
}

/** GET /api/version → { version, commit, built_at }.
 *  Fails silently — callers fall back to the frontend build version. */
export async function getAppVersion(): Promise<AppVersion> {
  return apiFetch<AppVersion>('/api/version')
}

// ─── Notifications ────────────────────────────────────────────────────────────

/** GET /api/notifications — full notification list (excludes dismissed+resolved; sorted warning→info, newest first). */
export async function getNotifications(): Promise<NotificationOut[]> {
  if (USE_MOCK) return mockGetNotifications()
  try { return await apiFetch<NotificationOut[]>('/api/notifications') }
  catch { return mockGetNotifications() }
}

/** GET /api/notifications/unread-count — cheap, poll-safe badge count. */
export async function getUnreadCount(): Promise<{ count: number }> {
  if (USE_MOCK) return mockGetUnreadCount()
  return apiFetch<{ count: number }>('/api/notifications/unread-count')
}

/** POST /api/notifications/{id}/read — mark one notification read (204). */
export async function markNotificationRead(id: number): Promise<void> {
  if (USE_MOCK) return mockMarkNotificationRead(id)
  const res = await fetch(`/api/notifications/${id}/read`, { method: 'POST', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

/** POST /api/notifications/read-all — mark all unread notifications read. */
export async function markAllNotificationsRead(): Promise<{ updated: number }> {
  if (USE_MOCK) return mockMarkAllNotificationsRead()
  return apiFetch<{ updated: number }>('/api/notifications/read-all', { method: 'POST' })
}

/** POST /api/notifications/{id}/dismiss — dismiss one notification (204). */
export async function dismissNotification(id: number): Promise<void> {
  if (USE_MOCK) return mockDismissNotification(id)
  const res = await fetch(`/api/notifications/${id}/dismiss`, { method: 'POST', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

// ─── Notification channels ────────────────────────────────────────────────────

/** GET /api/notifications/channels → list of configured notification channels (no secrets). */
export async function getNotificationChannels(): Promise<NotificationChannelOut[]> {
  if (USE_MOCK) return mockGetNotificationChannels()
  return apiFetch<NotificationChannelOut[]>('/api/notifications/channels')
}

/** POST /api/notifications/channels (body TelegramChannelIn) → 201 NotificationChannelOut.
 *  400 = bad token (server Telegram getMe failed); 503 = encryption key not configured. */
export async function createTelegramChannel(body: TelegramChannelIn): Promise<NotificationChannelOut> {
  if (USE_MOCK) return mockCreateTelegramChannel(body)
  const res = await fetch('/api/notifications/channels', {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) {
    const data: { detail?: string } = await res.json().catch(() => ({}))
    throw Object.assign(new Error(data.detail ?? `HTTP ${res.status}`), { status: res.status })
  }
  return res.json() as Promise<NotificationChannelOut>
}

/** DELETE /api/notifications/channels/{id} → 204 (404 if not owned). */
export async function deleteNotificationChannel(id: number): Promise<void> {
  if (USE_MOCK) return mockDeleteNotificationChannel(id)
  const res = await fetch(`/api/notifications/channels/${id}`, { method: 'DELETE', credentials: 'same-origin' })
  if (res.status === 401) { _on401?.(); throw new Error('HTTP 401 Unauthorized') }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

/** POST /api/notifications/channels/telegram/test (body TelegramTestIn) → TelegramTestOut.
 *  Both creds → tests those creds; neither → tests stored channel; only one → 400. */
export async function testTelegramChannel(body: TelegramTestIn): Promise<TelegramTestOut> {
  if (USE_MOCK) return mockTestTelegramChannel(body)
  return apiFetch<TelegramTestOut>('/api/notifications/channels/telegram/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
