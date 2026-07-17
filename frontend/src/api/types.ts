// ─── Entity types ─────────────────────────────────────────────────────────────

export interface Account {
  id: number
  name: string
  type: string | null
  currency: string
  tx_count: number
  account_number_masked?: string | null
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
  detail?: string | null
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
  day?: string
}

// MonthSummaryParams is now identical to SummaryParams (category_id merged up)
export type MonthSummaryParams = SummaryParams

export interface DateRangeParams {
  from?: string
  to?: string
}

// ─── Response types ───────────────────────────────────────────────────────────

export interface SummaryMonths {
  months: string[]          // "YYYY-MM" sorted ascending
  latest: string | null     // last month with data, or null if empty
}

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

export interface DaySummary {
  day: string             // "YYYY-MM-DD"
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

export type ImportQualitySeverity = 'error' | 'warning' | 'info'

export type ImportQualitySignalCode =
  | 'low_confidence_category'
  | 'missing_category'
  | 'generic_category'
  | 'missing_merchant'
  | 'zero_amount'
  | 'date_year_mismatch'
  | 'year_undetected'
  | 'intra_batch_duplicate'

export interface ImportQualitySummary {
  error_count: number
  warning_count: number
  info_count: number
  flagged_row_count: number
}

export interface ImportQualitySignal {
  code: ImportQualitySignalCode
  severity: ImportQualitySeverity
  count: number
}

export interface ImportQualityRowFlag {
  row_index: number
  code: ImportQualitySignalCode
  severity: ImportQualitySeverity
  fields: string[]
}

export interface ImportQuality {
  summary: ImportQualitySummary
  signals: ImportQualitySignal[]
  row_flags: ImportQualityRowFlag[]
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
  detail?: string | null
  /** User override: force import even when the natural dedup key matches an existing transaction. */
  allow_duplicate?: boolean
  /** Set when a classification rule matched this line during preview. */
  matched_rule_id?: number | null
  matched_rule_name?: string | null
}

export interface PreviewResponse {
  account_ref: string | null
  filename: string
  transactions: ImportTransaction[]
  statement_year: number | null
  year_detected: boolean
  /** AI-suggested colors for tags the LLM proposed in this preview. */
  suggested_tags?: { name: string; color: string }[]
  /** Masked IBAN detected from the statement (e.g. ES****…****1332). */
  detected_account_masked?: string | null
  /** Full IBAN detected — keep in state, never display. */
  detected_account_iban?: string | null
  /** ID of an existing account that matched the detected IBAN. */
  matched_account_id?: number | null
  /** Name of the matched account, if any. */
  matched_account_name?: string | null
  /** Advisory import quality report; never blocks confirm. */
  quality: ImportQuality
}

export interface ConfirmRequest {
  account_name: string
  source_filename: string
  transactions: ImportTransaction[]
  /** Colors for brand-new tags (not yet in the DB). name→hex. */
  tag_colors?: Record<string, string>
  /** Full IBAN — only sent when creating a brand-new detected account. */
  account_number?: string | null
  /** Original PDF as base64 (data URL prefix stripped) — stored server-side for re-download. */
  source_pdf_base64?: string
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

// ─── Merchant summary ────────────────────────────────────────────────────────

export interface MerchantSummary { merchant: string; amount: number; count: number }

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

// ─── Statements ──────────────────────────────────────────────────────────────

export interface StatementMonth {
  year: number
  month: number
  count: number
}

export interface StatementOriginal {
  import_run_id: number
  source_filename: string
  account_name: string
  imported_at: string
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

// ─── Rules ────────────────────────────────────────────────────────────────────

export type DescriptionMode = 'contains' | 'starts_with' | 'exact' | 'regex'
export type AmountSign = 'negative' | 'positive'

export interface Rule {
  id: number
  name: string
  priority: number
  enabled: boolean
  description_mode: DescriptionMode
  description_value: string
  detail_mode?: DescriptionMode | null
  detail_value?: string | null
  amount_sign: AmountSign | null
  amount_min?: number | null
  amount_max?: number | null
  account_ref: string | null
  currency: string | null
  set_category: string | null
  set_merchant: string | null
  add_tags: string[]
  skip_ai: boolean
  created_at: string
  updated_at: string
}

export interface RuleInput {
  name: string
  priority?: number
  enabled?: boolean
  description_mode: DescriptionMode
  description_value: string
  detail_mode?: DescriptionMode | null
  detail_value?: string | null
  amount_sign?: AmountSign | null
  amount_min?: number | null
  amount_max?: number | null
  account_ref?: string | null
  currency?: string | null
  set_category?: string | null
  set_merchant?: string | null
  add_tags?: string[]
  skip_ai?: boolean
}

export interface RulePatch {
  name?: string
  priority?: number
  enabled?: boolean
  description_mode?: DescriptionMode
  description_value?: string
  detail_mode?: DescriptionMode | null
  detail_value?: string | null
  amount_sign?: AmountSign | null
  amount_min?: number | null
  amount_max?: number | null
  account_ref?: string | null
  currency?: string | null
  set_category?: string | null
  set_merchant?: string | null
  add_tags?: string[]
  skip_ai?: boolean
}

// ─── UI types ─────────────────────────────────────────────────────────────────

export interface GlobalFilters {
  from: string
  to: string
  account_id?: number
  category_id?: number
  tags: string[]
  flow?: 'expense' | 'income'
  merchant?: string
  day?: string
}

/** Superset of GlobalFilters used by the Transactions full-page view. */
export interface TransactionsViewFilters extends GlobalFilters {
  description?: string
  amount_min?: number
  amount_max?: number
  merchant?: string
}

// ─── Investments ──────────────────────────────────────────────────────────────

export interface InvestmentPlugin {
  id: string
  name: string
  description: string
  icon: string
  status: 'coming_soon' | 'available' | 'connected' | 'error'
  auth_type: 'api_key' | 'oauth' | 'token' | 'none'
  supported_features: string[]
  /** Non-null for plugins that support CSV/file import; value is the import page route (e.g. '/investments/fidelity-espp'). Added by Shuri. */
  import_route: string | null
}

export interface InvestmentReturns {
  twr_annual: number | null
  xirr: number | null
  pl: number | null
  invested: number | null
  twr_total?: number | null
  twr_last_week?: number | null
  twr_last_month?: number | null
  twr_last_year?: number | null
  money_return?: number | null
  volatility?: number | null
  // Indexa redesign fields
  aportaciones?: number | null
  retenciones?: number | null
  rentabilidad_eur?: number | null
  rentabilidad_pct?: number | null
  sharpe_ratio?: number | null
  money_return_annual?: number | null
}

export interface ValuePoint {
  date: string    // "YYYY-MM-DD"
  value: number
}

export interface MonthlyReturnRow {
  year: number
  months_pct: Record<string, number | null | undefined>
  months_eur: Record<string, number | null | undefined>
  total_pct: number | null
  total_eur: number | null
  benchmark_pct: number | null
}

export interface DrawdownOut {
  max_drawdown: number
  max_drawdown_eur: number
  start_date: string    // "YYYY-MM-DD"
  end_date: string      // "YYYY-MM-DD"
}

export interface CashInvestedSplit {
  cash_amount: number
  instruments_amount: number
  instruments_cost: number
  total_amount: number
}

export interface InvestmentHolding {
  plugin_id: string
  name: string
  ticker: string
  asset_class: string
  units: number
  current_value: number
  cost_basis: number
  currency: string
  gain_loss: number
  gain_loss_pct: number    // decimal: 0.1093 = 10.93%
  last_updated: string
}

export interface InvestmentPortfolio {
  total_value: number
  total_invested: number | null
  total_gain_loss: number | null
  total_gain_loss_pct: number | null   // decimal
  currency: string
  plugins_connected: number
  last_updated: string | null
  returns: InvestmentReturns | null
  value_series: ValuePoint[]
  contributions_series: ValuePoint[]
  monthly_returns: MonthlyReturnRow[] | null
  drawdown: DrawdownOut | null
  cash_invested: CashInvestedSplit | null
  holdings: InvestmentHolding[]
}

export interface InvestmentConnection {
  id: number
  plugin_id: string
  status: 'active' | 'error' | 'disconnected'
  account_label_masked: string | null
  created_at: string
  last_synced_at: string | null
}

export interface ValidatedAccount {
  account_number: string
  account_number_masked: string
  type: string
  status: string
}

export interface ValidateAccountsResponse {
  accounts: ValidatedAccount[]
}

// ─── Fidelity ESPP ────────────────────────────────────────────────────────────

export interface FidelityReminderResponse {
  overdue: boolean
  expected_date: string | null      // "YYYY-MM-DD"
  period_label: string | null       // e.g. "Q2 2026"
  last_lot_date: string | null      // "YYYY-MM-DD"
}

export interface FidelityKpis {
  total_shares: number
  invested_eur: number
  current_value_eur: number | null
  gain_loss_eur: number | null
  gain_loss_pct: number | null
  msft_price_usd: number | null
  usd_eur_rate: number | null
  last_price_date: string | null   // "YYYY-MM-DD"
  price_stale: boolean
  as_of_date: string               // "YYYY-MM-DD"
}

export interface FidelityEvolution {
  value_series: ValuePoint[]
  contributions_series: ValuePoint[]
}

export interface FidelityLot {
  id: number
  purchase_date: string            // "YYYY-MM-DD"
  shares: number
  cost_basis_per_share_eur: number
  cost_basis_total_eur: number
  current_value_eur: number | null
  gain_loss_eur: number | null
  gain_loss_pct: number | null     // percentage: 12.5 = 12.5%
  share_source: 'SP' | 'DO'
  grant_date: string | null        // "YYYY-MM-DD"
}

export interface FidelityLots {
  lots: FidelityLot[]
}

export interface FidelityImportPreviewLot {
  purchase_date: string
  shares: number
  cost_basis_per_share_eur: number
  cost_basis_total_eur: number
  share_source: 'SP' | 'DO'
  grant_date: string | null
}

export interface FidelityImportPreview {
  new_lots: FidelityImportPreviewLot[]
  duplicate_count: number
  total_in_file: number
  source_currency: string
  file_already_imported: boolean
}

export interface FidelityImportConfirmResult {
  inserted: number
  duplicates: number
}

// ─── App version ─────────────────────────────────────────────────────────────

export interface AppVersion {
  version: string
  image_tag: string | null
  built_at: string | null
}

// ─── Combined investments overview ────────────────────────────────────────────

export interface CombinedOverviewProviderSlice {
  provider: string
  label: string
  value_eur: number
  pct: number
}

export interface CombinedOverviewAssetClassSlice {
  asset_class: string
  label: string
  value_eur: number
  pct: number
}

export interface CombinedOverviewProvider {
  id: string
  name: string
  icon: string
  value_eur: number | null
  gain_loss_eur: number | null
  gain_loss_pct: number | null
  route: string
}

export interface CombinedOverview {
  total_value_eur: number
  total_invested_eur: number | null
  total_gain_loss_eur: number | null
  total_gain_loss_pct: number | null
  by_provider: CombinedOverviewProviderSlice[]
  by_asset_class: CombinedOverviewAssetClassSlice[]
  providers: CombinedOverviewProvider[]
}
