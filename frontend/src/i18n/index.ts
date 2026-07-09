import { createContext, createElement, useContext, useState, useCallback } from 'react'
import type { ReactNode } from 'react'
import es from './es'
import en from './en'

export type Lang = 'es' | 'en'

export interface Dict {
  appSubtitle: string
  filterFrom: string
  filterTo: string
  filterAccount: string
  filterAllAccounts: string
  btnImport: string
  kpiTotalExpense: string
  kpiTotalIncome: string
  kpiNet: string
  kpiTransactions: string
  kpiTopCategory: string
  kpiErrorLoading: string
  loading: string
  noDataPeriod: string
  chartByCategory: string
  tooltipAmount: string
  chartOverTime: string
  legendExpense: string
  legendIncome: string
  chartByAccount: string
  tableTitle: string
  tableFilterCategory: string
  tableFilterAll: string
  tableColDate: string
  tableColDesc: string
  tableColCategory: string
  tableColAccount: string
  tableColAmount: string
  tableErrorLoading: string
  tableNoData: string
  tablePrev: string
  tableNext: string
  tablePaginationInfo: (start: number, end: number, total: number) => string
  modalTitleUpload: string
  modalTitlePreview: string
  modalClose: string
  modalFileLabel: string
  modalFileHint: string
  modalAccountLabel: string
  modalAccountPlaceholder: string
  modalAccountHint: string
  modalExtractingSpinner: string
  modalSavingSpinner: string
  modalPreviewMeta: (count: number, filename: string) => string
  modalLowConfidence: string
  modalAddRow: string
  previewColDate: string
  previewColDesc: string
  previewColAmount: string
  previewColCategory: string
  previewColAccount: string
  previewColConf: string
  previewSignExpense: string
  previewSignIncome: string
  previewDeleteRow: string
  previewTotalExpenses: string
  previewTotalIncome: string
  previewCategoryCustom: string
  previewCategoryCustomPlaceholder: string
  modalBtnCancel: string
  modalBtnExtract: string
  modalBtnConfirm: (count: number) => string
  error503: string
  error400: string
  errorNetwork: string
  errorUnexpected: (msg: string) => string
  toastSuccess: (inserted: number, dupes: number) => string
  toastClose: string
  modalAccountNew: string
  modalYearNotFound: string
  chartCashflow: string
  cashflowNode: string
  tableEditRow: string
  tableSaveRow: string
  tableCancelEdit: string
  tableSaveError: string
  tableColTags: string
  filterTag: string
  filterAllTags: string
  tagEditorPlaceholder: string
  tagChipRemove: string
  filterClearChip: string
  previewColTags: string
  navHome: string
  navSettings: string
  settingsTagsTitle: string
  settingsTagsAddName: string
  settingsTagsAddBtn: string
  settingsTagsDelete: string
  settingsTagsDeleteConfirm: (name: string) => string
  settingsTagsEmpty: string
  settingsTagsEmojiLabel: string
  settingsSubTags: string
  settingsSubCategories: string
  settingsCatsTitle: string
  settingsCatsEmpty: string
  settingsCatsSaved: string
  settingsCatsAddName: string
  settingsCatsAddBtn: string
  colorSwatchCustom: string
  settingsCountLabel: (n: number) => string
  // ── Auth ──────────────────────────────────────────────────────────────────
  authLoginTitle: string
  authSetupTitle: string
  authSetupSubtitle: string
  authUsername: string
  authPassword: string
  authConfirmPassword: string
  authLoginBtn: string
  authSetupBtn: string
  authLogout: string
  authErrorInvalidCredentials: string
  authErrorPasswordMismatch: string
  authErrorPasswordTooShort: string
  authErrorUsernameTooShort: string
  authErrorAlreadySetup: string
  authErrorUnexpected: string
  // ── Flow filter ───────────────────────────────────────────────────────────
  filterExpenseOnly: string
  filterIncomeOnly: string
  // ── Appearance / Theme ────────────────────────────────────────────────────
  settingsSubAppearance: string
  settingsAppearanceTitle: string
  settingsThemeLabel: string
  themeLight: string
  themeDark: string
  themeSystem: string
  // ── Category chart table ──────────────────────────────────────────────
  catColCategories: string
  catColValue: string
  catColWeight: string
  catCenterLabel: string
  // ── Transactions page ─────────────────────────────────────────────────
  navTransactions: string
  navRules: string
  txTitle: string
  filterCategory: string
  filterAllCategories: string
  filterDescription: string
  filterAmountMin: string
  filterAmountMax: string
  filterClear: string
  searchPlaceholder: string
  btnFilters: string
  colMerchant: string
  filterMerchant: string
  // ── Backup page ───────────────────────────────────────────────────────────
  settingsSubBackup: string
  backupPageTitle: string
  backupIntro: string
  backupExportTitle: string
  backupExportBtn: string
  backupExporting: string
  backupImportTitle: string
  backupImportBtn: string
  backupImporting: string
  backupImportConfirm: string
  backupSummaryTitle: string
  backupSummaryAccountsCreated: string
  backupSummaryAccountsExisting: string
  backupSummaryCategoriesCreated: string
  backupSummaryCategoriesUpdated: string
  backupSummaryTagsCreated: string
  backupSummaryTagsUpdated: string
  backupSummaryTxInserted: string
  backupSummaryTxDuplicates: string
  backupErrorInvalidJson: string
  backupErrorInvalidShape: string
  // ── Import preview — merchant + tag typeahead ─────────────────────────
  importMerchantPlaceholder: string
  tagTypeaheadPlaceholder: string
  // ── Rules page ────────────────────────────────────────────────────────────
  rulesTitle: string
  rulesAddBtn: string
  rulesAddTitle: string
  rulesEditTitle: string
  rulesEmpty: string
  rulesFieldName: string
  rulesFieldNamePlaceholder: string
  rulesFieldPriority: string
  rulesFieldPriorityHint: string
  rulesFieldEnabled: string
  rulesFieldDescMode: string
  rulesFieldDescValue: string
  rulesFieldDescValuePlaceholder: string
  rulesFieldAmountSign: string
  rulesFieldAmountAny: string
  rulesFieldAmountExpense: string
  rulesFieldAmountIncome: string
  rulesFieldAccount: string
  rulesFieldAccountPlaceholder: string
  rulesFieldCurrency: string
  rulesFieldCurrencyPlaceholder: string
  rulesFieldCategory: string
  rulesFieldMerchant: string
  rulesFieldMerchantPlaceholder: string
  rulesFieldTags: string
  rulesFieldSkipAi: string
  rulesFieldSkipAiHint: string
  rulesBtnSave: string
  rulesBtnCancel: string
  rulesBtnEdit: string
  rulesBtnDelete: string
  rulesDeleteConfirm: (name: string) => string
  rulesColName: string
  rulesColPattern: string
  rulesColCategory: string
  rulesColMerchant: string
  rulesColTags: string
  rulesColPriority: string
  rulesColEnabled: string
  rulesColActions: string
  rulesModeContains: string
  rulesModeStartsWith: string
  rulesModeExact: string
  rulesModeRegex: string
  rulesValidationName: string
  rulesValidationPattern: string
  rulesValidationCategory: string
  rulesValidationRegex: (msg: string) => string
  // ── Create rule from row ──────────────────────────────────────────────────
  createRuleBtn: string
  ruleMatchBadge: string
  ruleMatchTooltip: (name: string) => string
  createRuleToast: string
  // ── Tag filter typeahead ──────────────────────────────────────────────────
  filterTagSearchPlaceholder: string
  filterTagMostUsed: string
  // ── Rule detail condition ─────────────────────────────────────────────────
  rulesFieldDetailLabel: string
  rulesFieldDetailHint: string
  rulesFieldDetailValuePlaceholder: string
  // ── Rule form section headings ────────────────────────────────────────────
  rulesSectionIdentity: string
  rulesSectionMatch: string
  rulesSectionActions: string
  rulesConditionTitle: string
  rulesConditionFilters: string
  // ── Rule amount filter ────────────────────────────────────────────────────
  rulesFieldAmountMin: string
  rulesFieldAmountMax: string
  rulesFieldAmountHint: string
  rulesValidationAmount: string
  // ── Period comparison ─────────────────────────────────────────────────────
  kpiSavingsRate: string
  deltaBadgeNew: string
  moversTitle: string
  moversColCategory: string
  moversColCurrent: string
  moversColPrevious: string
  moversColChange: string
  moversNoPrevious: string
  // ── Statements page ──────────────────────────────────────────────────────────
  navStatements: string
  stmtsPrev: string
  stmtsNext: string
  stmtsDeleteMonth: string
  stmtsDeleteTitle: (monthLabel: string) => string
  stmtsDeleteBody: (n: number, monthLabel: string) => string
  stmtsDeleteBtn: string
  stmtsDeleteOk: string
  stmtsEmptyTitle: (monthLabel: string) => string
  stmtsEmptyHint: string
  stmtsImportBtn: string
  // ── MonthPicker ───────────────────────────────────────────────────────────────
  monthPickerTriggerLabel: (formatted: string) => string
  monthPickerDialogLabel: string
  monthPickerCurrentMonth: string
  monthPickerPrevYear: string
  monthPickerNextYear: string
  // ── Rule preview / apply ──────────────────────────────────────────────────────
  rulesPreviewLoading: string
  rulesPreviewCount: (n: number) => string
  rulesPreviewNone: string
  rulesPreviewError: string
  rulesApplyBtn: (n: number) => string
  rulesApplySuccess: (n: number) => string
  // ── Accounts settings page ────────────────────────────────────────────────────
  settingsSubAccounts: string
  accountsPageTitle: string
  accountsEmpty: string
  accountsDeleteBtn: string
  accountsDeleteTitle: (name: string) => string
  accountsDeleteBody: (name: string, n: number) => string
  accountsDeleteOk: string
  accountsDeleteToast: (name: string, n: number) => string
  // ── Import modal validation ───────────────────────────────────────────────
  modalFileRequired: string
  modalAccountRequired: string
  // ── DatePicker ────────────────────────────────────────────────────────────────
  datePickerTriggerLabel: (formatted: string) => string
  datePickerDialogLabel: string
  datePickerToday: string
  datePickerPrevMonth: string
  datePickerNextMonth: string
  datePickerPlaceholder: string
}

const ES_LABELS: Record<string, string> = {
  Groceries: 'Alimentación',
  Dining: 'Restaurantes',
  Transport: 'Transporte',
  Fuel: 'Combustible',
  Housing: 'Vivienda',
  Utilities: 'Suministros',
  Health: 'Salud',
  Insurance: 'Seguros',
  Shopping: 'Compras',
  Entertainment: 'Ocio',
  Subscriptions: 'Suscripciones',
  Travel: 'Viajes',
  Education: 'Educación',
  Income: 'Ingresos',
  Transfers: 'Transferencias',
  Investments: 'Inversiones',
  'Bank Fees': 'Comisiones bancarias',
  Taxes: 'Impuestos',
  'Cash/ATM': 'Efectivo/Cajero',
  Other: 'Otros',
}

export function categoryLabel(canonical: string, lang: Lang, dynamicEs?: Record<string, string>): string {
  if (lang !== 'es') return canonical
  return ES_LABELS[canonical] ?? dynamicEs?.[canonical] ?? canonical
}

const LOCALES: Record<Lang, string> = { es: 'es-ES', en: 'en-GB' }

export function formatCurrency(amount: number, lang: Lang): string {
  return new Intl.NumberFormat(LOCALES[lang], { style: 'currency', currency: 'EUR' }).format(amount)
}

export function langLocale(lang: Lang): string {
  return LOCALES[lang]
}

/** Fallback color for tags that have no color assigned yet. */
export const DEFAULT_TAG_COLOR = '#94a3b8'

/** Deterministic palette used for name-based color derivation. */
export const PALETTE = [
  '#3b82f6', '#f97316', '#8b5cf6', '#eab308', '#10b981',
  '#ef4444', '#ec4899', '#06b6d4', '#84cc16', '#f59e0b',
]

/** Map a name string to a stable palette color. */
export function paletteColor(name: string): string {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff
  return PALETTE[Math.abs(h) % PALETTE.length]
}

/** Returns 'black' or 'white' for maximum contrast on the given hex background. */
export function tagTextColor(hex: string): 'black' | 'white' {
  if (!hex || hex.length < 7) return 'white'
  try {
    const r = parseInt(hex.slice(1, 3), 16)
    const g = parseInt(hex.slice(3, 5), 16)
    const b = parseInt(hex.slice(5, 7), 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.55 ? 'black' : 'white'
  } catch {
    return 'white'
  }
}

export function formatDate(iso: string, lang: Lang): string {
  if (!iso) return ''
  try {
    const parts = iso.split('-')
    if (parts.length !== 3) return iso
    const [y, m, d] = parts.map(Number)
    if (!y || !m || !d) return iso
    const dt = new Date(y, m - 1, d)
    return new Intl.DateTimeFormat(LOCALES[lang], { day: '2-digit', month: '2-digit', year: 'numeric' }).format(dt)
  } catch {
    return iso
  }
}

const LS_KEY = 'finlytics_lang'

function storedLang(): Lang {
  try {
    const v = localStorage.getItem(LS_KEY)
    return v === 'en' ? 'en' : 'es'
  } catch {
    return 'es'
  }
}

interface LanguageContextValue {
  lang: Lang
  setLang: (l: Lang) => void
}

const LanguageContext = createContext<LanguageContextValue>({ lang: 'es', setLang: () => {} })

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(storedLang)
  const setLang = useCallback((l: Lang) => {
    try { localStorage.setItem(LS_KEY, l) } catch { }
    setLangState(l)
  }, [])
  return createElement(LanguageContext.Provider, { value: { lang, setLang } }, children)
}

export interface UseTResult {
  t: Dict
  lang: Lang
  setLang: (l: Lang) => void
  formatCurrency: (amount: number) => string
}

export function useT(): UseTResult {
  const { lang, setLang } = useContext(LanguageContext)
  return {
    t: lang === 'es' ? es : en,
    lang,
    setLang,
    formatCurrency: (amount: number) => formatCurrency(amount, lang),
  }
}
