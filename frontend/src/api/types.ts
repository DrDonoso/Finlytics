// ─── Entity types ─────────────────────────────────────────────────────────────

export interface Account {
  id: number
  name: string
  type: string | null
  currency: string
}

export interface Category {
  id: number
  name: string
  is_base: boolean
  color: string
  name_es: string | null
  tx_count: number
}

export interface Tag {
  id: number
  name: string
  color: string
  emoji: string | null
  tx_count: number
}

export interface Transaction {
  id: number
  transaction_date: string
  amount: number          // signed: negative = expense, positive = income
  currency: string
  description: string
  category: string
  account: string
  category_confidence: number | null
  balance_after: number | null
  tags: string[]
  merchant: string | null
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  limit: number
  offset: number
}

// ─── Query param types ────────────────────────────────────────────────────────

export interface TransactionsParams {
  from?: string
  to?: string
  account_id?: number
  category_id?: number
  limit?: number
  offset?: number
  tags?: string[]
  flow?: 'expense' | 'income'
  description?: string
  amount_min?: number
  amount_max?: number
  merchant?: string
  sort?: string
  order?: 'asc' | 'desc'
}

export interface SummaryParams {
  from?: string
  to?: string
  account_id?: number
  category_id?: number
  tags?: string[]
  flow?: 'expense' | 'income'
  description?: string
  amount_min?: number
  amount_max?: number
  merchant?: string
}

// MonthSummaryParams is now identical to SummaryParams (category_id merged up)
export type MonthSummaryParams = SummaryParams

export interface DateRangeParams {
  from?: string
  to?: string
}

// ─── Response types ───────────────────────────────────────────────────────────

export interface Overview {
  total_expense: number   // positive magnitude
  total_income: number    // positive
  net: number             // income - expense; can be negative
  num_transactions: number
  top_category: { name: string; amount: number } | null
  currency: string
}

export interface CategorySummary {
  category: string
  category_id: number
  amount: number          // positive magnitude
  count: number
}

export interface MonthSummary {
  month: string           // "YYYY-MM"
  expense: number         // positive magnitude
  income: number          // positive
  net: number
}

export interface AccountSummary {
  account: string
  expense: number         // positive magnitude
  income: number
  net: number
  currency: string
}

export interface ImportResult {
  import_run_id: number
  num_parsed: number
  num_inserted: number
  num_duplicates: number
}

// ─── Import preview / confirm ─────────────────────────────────────────────────

/** Single extracted transaction — not yet persisted. */
export interface ImportTransaction {
  transaction_date: string        // "YYYY-MM-DD"
  amount: number                  // signed: negative = expense, positive = income
  currency: string
  description: string
  raw_line: string | null
  category: string
  category_confidence: number | null
  account_ref: string
  balance_after: number | null
  tags: string[]
  merchant: string | null
}

export interface PreviewResponse {
  account_ref: string | null
  filename: string
  transactions: ImportTransaction[]
  statement_year: number | null
  year_detected: boolean
  /** AI-suggested colors for tags the LLM proposed in this preview. */
  suggested_tags?: { name: string; color: string }[]
}

export interface ConfirmRequest {
  account_name: string
  source_filename: string
  transactions: ImportTransaction[]
  /** Colors for brand-new tags (not yet in the DB). name→hex. */
  tag_colors?: Record<string, string>
}

// ─── Transaction update ───────────────────────────────────────────────────────

export interface TransactionPatch {
  description?: string
  category?: string
  amount?: number
  tags?: string[]
  merchant?: string
}

// ─── Category update ──────────────────────────────────────────────────────────

export interface CategoryPatch {
  color?: string
}

// ─── Cashflow summary ─────────────────────────────────────────────────────────

export interface CashflowItem {
  category: string
  amount: number        // positive magnitude
}

export interface CashflowSummary {
  income: CashflowItem[]
  expense: CashflowItem[]
  total_income: number
  total_expense: number
  currency: string
}

// ─── Backup ───────────────────────────────────────────────────────────────────

export interface BackupImportSummary {
  accounts_created: number
  accounts_existing: number
  categories_created: number
  categories_updated: number
  tags_created: number
  tags_updated: number
  transactions_inserted: number
  transactions_duplicates: number
}

// ─── Auth types ───────────────────────────────────────────────────────────────

export interface AuthStatus {
  initialized: boolean
  authenticated: boolean
}

export interface AuthUser {
  username: string
}

// ─── UI types ─────────────────────────────────────────────────────────────────

export interface GlobalFilters {
  from: string
  to: string
  account_id?: number
  category_id?: number
  tags: string[]
  flow?: 'expense' | 'income'
}

/** Superset of GlobalFilters used by the Transactions full-page view. */
export interface TransactionsViewFilters extends GlobalFilters {
  description?: string
  amount_min?: number
  amount_max?: number
  merchant?: string
}
