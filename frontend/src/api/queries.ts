/**
 * Consultas de datos de la aplicación.
 *
 * Antes cada pantalla resolvía sus peticiones a mano con useEffect + useState.
 * De los 26 efectos que hacían fetch, 22 no se protegían contra respuestas que
 * llegan fuera de orden: al cambiar de mes rápido, la respuesta del primero
 * podía llegar después que la del segundo y dejar en pantalla datos que no se
 * corresponden con el filtro activo. Un fallo silencioso e intermitente,
 * prácticamente imposible de reproducir a mano.
 *
 * Centralizar aquí resuelve además la caché y la deduplicación: dos componentes
 * que piden lo mismo hacían dos peticiones.
 */
import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'

import {
  getAccounts,
  getAppVersion,
  getByAccount,
  getByCategory,
  getByDay,
  getByMerchant,
  getByMonth,
  getCashflow,
  getCategories,
  getCombinedOverview,
  getConnections,
  getInvestmentPlugins,
  getInvestmentPortfolio,
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
  CashflowSummary,
  Category,
  CategorySummary,
  CombinedOverview,
  DaySummary,
  InvestmentConnection,
  InvestmentPlugin,
  InvestmentPortfolio,
  MerchantSummary,
  MonthSummary,
  MonthSummaryParams,
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
 * Opciones comunes a las consultas que a veces no deben lanzarse todavía
 * (por ejemplo, mientras no se conoce el mes a comparar). `enabled` sin definir
 * equivale a activada, así que las llamadas existentes no cambian.
 */
interface QueryOptions {
  enabled?: boolean
}

/**
 * Claves de caché.
 *
 * Se agrupan aquí para que invalidar tras una mutación sea explícito y no haya
 * que ir buscando strings sueltos por el código.
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
}

// ── Catálogos ────────────────────────────────────────────────────────────────
// Cambian muy poco, así que aguantan más tiempo en caché que los resúmenes.

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

// ── Resúmenes ────────────────────────────────────────────────────────────────
// Dependen de los filtros activos: es donde importaba el orden de llegada.

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

// ── Inversiones y extractos ──────────────────────────────────────────────────

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
