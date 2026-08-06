/**
 * Application data queries.
 *
 * Previously each screen managed its own useEffect + useState fetches. 22 of 26
 * effects had no out-of-order protection: switching months quickly could let an
 * earlier response arrive after a later one and display stale data — a silent,
 * intermittent bug almost impossible to catch manually.
 *
 * Centralising here also provides caching and deduplication: two components
 * requesting the same data used to fire two requests.
 */
import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import {
  getAccounts,
  getAppVersion,
  getAssistantConversation,
  getAssistantConversations,
  getAssistantSettings,
  getAssistantStatus,
  getAssistantSuggestions,
  getAssistantUsage,
  getByAccount,
  getByCategory,
  getByDay,
  getByMerchant,
  getByMonth,
  getCashflow,
  getCategories,
  getCombinedOverview,
  getConnections,
  getEuriborSeries,
  getInvestmentPlugins,
  getInvestmentPortfolio,
  getMortgage,
  getMortgageCharts,
  getMortgageNetWorth,
  getMortgageOverview,
  getMortgagePaymentCandidates,
  getMortgageReconciliation,
  getMortgageSchedule,
  getMortgages,
  getOverview,
  getOverviewMonths,
  getRules,
  getStatementMonths,
  getStatementOriginals,
  getStatementReminder,
  getTags,
} from './client'
import type {
  Account,
  AccountSummary,
  AppVersion,
  AssistantConversation,
  AssistantConversationDetail,
  AssistantSettings,
  AssistantStatus,
  AssistantSuggestions,
  AssistantUsage,
  CashflowSummary,
  Category,
  CategorySummary,
  CombinedOverview,
  DaySummary,
  EuriborSeries,
  InvestmentConnection,
  InvestmentPlugin,
  InvestmentPortfolio,
  MerchantSummary,
  MonthSummary,
  MonthSummaryParams,
  Mortgage,
  MortgageCharts,
  MortgageNetWorth,
  MortgageOverview,
  MortgagePaymentCandidates,
  MortgageReconciliation,
  MortgageSchedule,
  MortgageSummary,
  Overview,
  Rule,
  StatementMonth,
  StatementOriginal,
  StatementReminder,
  SummaryMonths,
  SummaryParams,
  Tag,
} from './types'

/**
 * Common options for queries that should not fire yet — for example, while the
 * comparison month is still unknown. An undefined `enabled` means enabled, so
 * existing call sites are unaffected.
 */
interface QueryOptions {
  enabled?: boolean
}

/**
 * Cache keys.
 *
 * Grouped here so that post-mutation invalidation is explicit, rather than
 * scattered string literals throughout the codebase.
 */
export const queryKeys = {
  accounts: ['accounts'] as const,
  categories: ['categories'] as const,
  tags: ['tags'] as const,
  rules: ['rules'] as const,
  connections: ['investment-connections'] as const,
  combinedOverview: ['investments', 'combined-overview'] as const,
  overviewMonths: ['summary', 'months'] as const,
  statementMonths: (accountId?: number) => ['statements', 'months', accountId ?? null] as const,
  statementReminder: ['statements', 'reminder'] as const,
  overview: (params?: SummaryParams) => ['summary', 'overview', params ?? null] as const,
  byCategory: (params?: SummaryParams) => ['summary', 'by-category', params ?? null] as const,
  byAccount: (params?: SummaryParams) => ['summary', 'by-account', params ?? null] as const,
  byMerchant: (params?: SummaryParams) => ['summary', 'by-merchant', params ?? null] as const,
  byMonth: (params?: MonthSummaryParams) => ['summary', 'by-month', params ?? null] as const,
  byDay: (params?: MonthSummaryParams) => ['summary', 'by-day', params ?? null] as const,
  cashflow: (params?: SummaryParams) => ['summary', 'cashflow', params ?? null] as const,
  statementOriginals: (year: number, month: number, accountId?: number) =>
    ['statements', 'originals', year, month, accountId ?? null] as const,
  investmentPlugins: ['investment-plugins'] as const,
  investmentPortfolio: ['investments', 'portfolio'] as const,
  appVersion: ['app-version'] as const,
  assistantStatus: ['assistant', 'status'] as const,
  assistantSuggestions: ['assistant', 'suggestions'] as const,
  assistantConversations: ['assistant', 'conversations'] as const,
  assistantConversation: (id: number) => ['assistant', 'conversation', id] as const,
  assistantSettings: ['assistant', 'settings'] as const,
  assistantUsage: ['assistant', 'usage'] as const,
  mortgages: ['mortgages'] as const,
  mortgage: (id: number) => ['mortgages', id] as const,
  mortgageOverview: (id: number) => ['mortgages', id, 'overview'] as const,
  mortgageSchedule: (id: number, granularity: 'month' | 'year') =>
    ['mortgages', id, 'schedule', granularity] as const,
  mortgageCharts: (id: number) => ['mortgages', id, 'charts'] as const,
  mortgageReconciliation: (id: number, months: number) =>
    ['mortgages', id, 'reconciliation', months] as const,
  mortgageNetWorth: ['mortgages', 'net-worth'] as const,
  mortgagePaymentCandidates: (amount: number | null) =>
    ['mortgages', 'payment-candidates', amount] as const,
  euribor: ['mortgages', 'euribor'] as const,
}

// ── Catalogs ─────────────────────────────────────────────────────────────────
// Rarely change, so they can stay cached longer than summaries.

const CATALOG_STALE_MS = 5 * 60_000

export function useAccounts(): UseQueryResult<Account[]> {
  return useQuery({
    queryKey: queryKeys.accounts,
    queryFn: getAccounts,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useCategories(): UseQueryResult<Category[]> {
  return useQuery({
    queryKey: queryKeys.categories,
    queryFn: getCategories,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useTags(): UseQueryResult<Tag[]> {
  return useQuery({
    queryKey: queryKeys.tags,
    queryFn: getTags,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useRules(): UseQueryResult<Rule[]> {
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: getRules,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useConnections(): UseQueryResult<InvestmentConnection[]> {
  return useQuery({
    queryKey: queryKeys.connections,
    queryFn: getConnections,
    staleTime: CATALOG_STALE_MS,
  })
}

// ── Summaries ────────────────────────────────────────────────────────────────
// Filter-dependent; this is where arrival order used to matter.

export function useOverview(params?: SummaryParams, options?: QueryOptions): UseQueryResult<Overview> {
  return useQuery({
    queryKey: queryKeys.overview(params),
    queryFn: () => getOverview(params),
    enabled: options?.enabled,
  })
}

export function useByCategory(params?: SummaryParams, options?: QueryOptions): UseQueryResult<CategorySummary[]> {
  return useQuery({
    queryKey: queryKeys.byCategory(params),
    queryFn: () => getByCategory(params),
    enabled: options?.enabled,
  })
}

export function useByAccount(params?: SummaryParams): UseQueryResult<AccountSummary[]> {
  return useQuery({
    queryKey: queryKeys.byAccount(params),
    queryFn: () => getByAccount(params),
  })
}

export function useByMerchant(params?: SummaryParams): UseQueryResult<MerchantSummary[]> {
  return useQuery({
    queryKey: queryKeys.byMerchant(params),
    queryFn: () => getByMerchant(params),
  })
}

export function useByMonth(params?: MonthSummaryParams): UseQueryResult<MonthSummary[]> {
  return useQuery({
    queryKey: queryKeys.byMonth(params),
    queryFn: () => getByMonth(params),
  })
}

export function useByDay(params?: MonthSummaryParams): UseQueryResult<DaySummary[]> {
  return useQuery({
    queryKey: queryKeys.byDay(params),
    queryFn: () => getByDay(params),
  })
}

export function useCashflow(params?: SummaryParams): UseQueryResult<CashflowSummary> {
  return useQuery({
    queryKey: queryKeys.cashflow(params),
    queryFn: () => getCashflow(params),
  })
}

export function useOverviewMonths(): UseQueryResult<SummaryMonths> {
  return useQuery({
    queryKey: queryKeys.overviewMonths,
    queryFn: getOverviewMonths,
    staleTime: CATALOG_STALE_MS,
  })
}

// ── Investments and statements ───────────────────────────────────────────────

export function useCombinedOverview(): UseQueryResult<CombinedOverview> {
  return useQuery({
    queryKey: queryKeys.combinedOverview,
    queryFn: getCombinedOverview,
  })
}

export function useStatementMonths(accountId?: number): UseQueryResult<StatementMonth[]> {
  return useQuery({
    queryKey: queryKeys.statementMonths(accountId),
    queryFn: () => getStatementMonths(accountId),
  })
}

export function useStatementOriginals(
  year: number,
  month: number,
  accountId?: number,
  options?: QueryOptions,
): UseQueryResult<StatementOriginal[]> {
  return useQuery({
    queryKey: queryKeys.statementOriginals(year, month, accountId),
    queryFn: () => getStatementOriginals(year, month, accountId),
    enabled: options?.enabled,
  })
}

export function useStatementReminder(): UseQueryResult<StatementReminder> {
  return useQuery({
    queryKey: queryKeys.statementReminder,
    queryFn: getStatementReminder,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useInvestmentPlugins(): UseQueryResult<InvestmentPlugin[]> {
  return useQuery({
    queryKey: queryKeys.investmentPlugins,
    queryFn: getInvestmentPlugins,
    staleTime: CATALOG_STALE_MS,
  })
}

export function useInvestmentPortfolio(): UseQueryResult<InvestmentPortfolio> {
  return useQuery({
    queryKey: queryKeys.investmentPortfolio,
    queryFn: getInvestmentPortfolio,
  })
}

export function useAppVersion(): UseQueryResult<AppVersion> {
  return useQuery({
    queryKey: queryKeys.appVersion,
    queryFn: getAppVersion,
    staleTime: CATALOG_STALE_MS,
  })
}

// ── Mortgage ─────────────────────────────────────────────────────────────────
//
// The schedule is derived from the loan terms, so it only changes when the user
// edits the mortgage or records a prepayment. Both paths invalidate the
// ['mortgages'] prefix, which covers every key below.

export function useMortgages(options?: QueryOptions): UseQueryResult<MortgageSummary[]> {
  return useQuery({
    queryKey: queryKeys.mortgages,
    queryFn: getMortgages,
    staleTime: CATALOG_STALE_MS,
    enabled: options?.enabled,
  })
}

export function useMortgage(id: number | null): UseQueryResult<Mortgage> {
  return useQuery({
    queryKey: queryKeys.mortgage(id ?? 0),
    queryFn: () => getMortgage(id as number),
    enabled: id !== null,
  })
}

export function useMortgageOverview(id: number | null): UseQueryResult<MortgageOverview> {
  return useQuery({
    queryKey: queryKeys.mortgageOverview(id ?? 0),
    queryFn: () => getMortgageOverview(id as number),
    enabled: id !== null,
  })
}

export function useMortgageSchedule(
  id: number | null,
  granularity: 'month' | 'year' = 'year',
): UseQueryResult<MortgageSchedule> {
  return useQuery({
    queryKey: queryKeys.mortgageSchedule(id ?? 0, granularity),
    queryFn: () => getMortgageSchedule(id as number, granularity),
    enabled: id !== null,
  })
}

export function useMortgageCharts(id: number | null): UseQueryResult<MortgageCharts> {
  return useQuery({
    queryKey: queryKeys.mortgageCharts(id ?? 0),
    queryFn: () => getMortgageCharts(id as number),
    enabled: id !== null,
  })
}

export function useMortgageReconciliation(
  id: number | null,
  months = 24,
): UseQueryResult<MortgageReconciliation> {
  return useQuery({
    queryKey: queryKeys.mortgageReconciliation(id ?? 0, months),
    queryFn: () => getMortgageReconciliation(id as number, months),
    enabled: id !== null,
  })
}

export function useMortgageNetWorth(options?: QueryOptions): UseQueryResult<MortgageNetWorth> {
  return useQuery({
    queryKey: queryKeys.mortgageNetWorth,
    queryFn: getMortgageNetWorth,
    staleTime: CATALOG_STALE_MS,
    enabled: options?.enabled,
  })
}

export function useEuriborSeries(options?: QueryOptions): UseQueryResult<EuriborSeries> {
  return useQuery({
    queryKey: queryKeys.euribor,
    queryFn: getEuriborSeries,
    // A monthly series: re-fetching it while the user is in the app is pointless.
    staleTime: Infinity,
    enabled: options?.enabled,
  })
}

export function useMortgagePaymentCandidates(
  amount: number | undefined,
  options?: QueryOptions,
): UseQueryResult<MortgagePaymentCandidates> {
  return useQuery({
    queryKey: queryKeys.mortgagePaymentCandidates(amount ?? null),
    queryFn: () => getMortgagePaymentCandidates(amount),
    staleTime: CATALOG_STALE_MS,
    enabled: options?.enabled,
  })
}

// ── Finance assistant ────────────────────────────────────────────────────────
//
// Only the non-streaming parts live here. The answer stream is imperative by
// nature — it mutates a buffer token by token — so it stays outside react-query.

export function useAssistantStatus(): UseQueryResult<AssistantStatus> {
  return useQuery({
    queryKey: queryKeys.assistantStatus,
    queryFn: getAssistantStatus,
    // Whether OPENAI_* is configured only changes on a restart, so there is no
    // point re-checking it while the user is in the app.
    staleTime: Infinity,
    retry: false,
  })
}

export function useAssistantSuggestions(options?: QueryOptions): UseQueryResult<AssistantSuggestions> {
  return useQuery({
    queryKey: queryKeys.assistantSuggestions,
    queryFn: getAssistantSuggestions,
    staleTime: Infinity,
    enabled: options?.enabled,
  })
}

export function useAssistantConversations(options?: QueryOptions): UseQueryResult<AssistantConversation[]> {
  return useQuery({
    queryKey: queryKeys.assistantConversations,
    queryFn: getAssistantConversations,
    enabled: options?.enabled,
  })
}

export function useAssistantConversation(
  id: number | null,
  options?: QueryOptions,
): UseQueryResult<AssistantConversationDetail> {
  return useQuery({
    queryKey: queryKeys.assistantConversation(id ?? 0),
    queryFn: () => getAssistantConversation(id as number),
    enabled: (options?.enabled ?? true) && id !== null,
  })
}

export function useAssistantSettings(): UseQueryResult<AssistantSettings> {
  return useQuery({
    queryKey: queryKeys.assistantSettings,
    queryFn: getAssistantSettings,
  })
}

export function useAssistantUsage(): UseQueryResult<AssistantUsage> {
  return useQuery({
    queryKey: queryKeys.assistantUsage,
    queryFn: getAssistantUsage,
  })
}
