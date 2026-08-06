import { createContext, createElement, useContext, useState, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import es from './es'
import en from './en'

export type Lang = 'es' | 'en'

/** Native names, shown in the language selector. A language is always listed in
 *  its own language — that is what makes the menu usable to someone who cannot
 *  read the current one. */
export const LANG_NAMES: Record<Lang, string> = {
  es: 'Español',
  en: 'English',
}

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
  modalChangeFile: string
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
  /** 429: se ha agotado el cupo de intentos de acceso desde esta red. */
  authErrorTooManyAttempts: (minutes: number) => string
  authErrorUnexpected: string
  authRememberMe: string
  // ── Flow filter ───────────────────────────────────────────────────────────
  filterExpenseOnly: string
  filterIncomeOnly: string
  // ── Appearance / Theme ────────────────────────────────────────────────────
  settingsSubAppearance: string
  settingsAppearanceTitle: string
  settingsThemeLabel: string
  settingsAccentLabel: string
  settingsAccentHint: string
  themeLight: string
  themeDark: string
  themeSystem: string
  paletteClassicBlue: string
  paletteEmerald: string
  paletteViolet: string
  paletteAmber: string
  paletteHighContrast: string
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
  backupExportSectionIntro: string
  backupExportBtn: string
  backupExporting: string
  backupSelectAtLeastOne: string
  backupSectionTransactions: string
  backupSectionAccounts: string
  backupSectionCategories: string
  backupSectionTags: string
  backupSectionRules: string
  backupSectionInvestments: string
  backupIndexaTokenNote: string
  backupImportTitle: string
  backupImportIntro: string
  backupImportBtn: string
  backupImportSubmitBtn: string
  backupImporting: string
  backupImportNoFile: string
  backupImportSelectedFile: string
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
  backupSummaryRulesCreated: string
  backupSummaryRulesUpdated: string
  backupSummaryInvestmentConnectionsCreated: string
  backupSummaryInvestmentConnectionsUpdated: string
  backupSummaryEsppLotsInserted: string
  backupSummaryEsppLotsDuplicates: string
  backupSummaryPriceHistoryInserted: string
  backupSummaryPriceHistoryDuplicates: string
  backupSummaryInvestmentConnections: string
  backupSummaryEsppLots: string
  backupSummaryPriceHistory: string
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
  stmtsDownloadOriginal: string
  stmtsDownloadOriginalDropdown: string
  stmtsDeltaNew: string
  // ── MonthPicker ───────────────────────────────────────────────────────────────
  monthPickerTriggerLabel: (formatted: string) => string
  monthPickerDialogLabel: string
  monthPickerCurrentMonth: string
  monthPickerPrevYear: string
  monthPickerNextYear: string
  // ── Rule preview / apply ──────────────────────────────────────────────────────
  rulesPreviewLoading: string
  rulesPreviewNone: string
  rulesPreviewError: string
  rulesApplyCheckbox: (n: number) => string
  rulesBtnSaveAndApply: string
  rulesSaveAndApplyToast: (n: number) => string
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
  // ── Import account resolution (Phase 2) ───────────────────────────────────────
  importDetectedAccount: (masked: string, name: string) => string
  importNewAccountDetected: (masked: string) => string
  modalBtnContinue: string
  // ── Accounts — edit name ──────────────────────────────────────────────────────
  accountsEditBtn: string
  accountsEditTitle: (name: string) => string
  accountsEditLabel: string
  accountsEditSave: string
  accountsEditToast: (name: string) => string
  accountsEditNameRequired: string
  // ── Accounts — create ─────────────────────────────────────────────────────────
  accountsCreateBtn: string
  accountsCreateTitle: string
  accountsCreateLabelName: string
  accountsCreateLabelType: string
  accountsCreateTypeBank: string
  accountsCreateTypeBroker: string
  accountsCreateTypeSavings: string
  accountsCreateLabelCurrency: string
  accountsCreateLabelIban: string
  accountsCreateOpeningTitle: string
  accountsCreateOpeningHint: string
  accountsCreateLabelAmount: string
  accountsCreateLabelDate: string
  accountsCreateErrName: string
  accountsCreateErrDate: string
  accountsCreateErr409: string
  accountsCreateSubmit: string
  accountsCreateToast: (name: string) => string
  // ── Batch import ─────────────────────────────────────────────────────────────
  batchCapWarning:        (count: number) => string
  batchCapBlocked:        (count: number) => string
  batchExtractingTitle:   string
  batchFileProgress:      (i: number, n: number) => string
  batchResolveTitle:      string
  batchResolveNewIbanName: string
  batchResolveManualFile: (filename: string) => string
  importOpeningBalanceLabel: string
  importOpeningBalanceHelpText: string
  importOpeningBalanceHint: string
  batchPreviewTitle:      string
  batchPreviewGroup:      (files: number, txns: number) => string
  batchPreviewFileSep:    (filename: string) => string
  batchConfirmAllBtn:     (n: number) => string
  batchConfirmingTitle:   string
  batchConfirmFileProgress: (i: number, n: number) => string
  batchSummaryTitle:      string
  batchSummaryStmts:      (n: number) => string
  batchSummaryNewTx:      (n: number) => string
  batchSummaryDupes:      (n: number) => string
  batchSummaryErrors:     (n: number) => string
  batchSummaryFileDone:   (file: string, inserted: number, dupes: number) => string
  batchSummaryFileError:  (file: string, reason: string) => string
  batchRetryFile:         string
  importDuplicateBadge:   string
  importDuplicateOverrideLabel: string
  importDuplicateOverrideTooltip: string
  importDuplicateCount:   (n: number) => string
  // ── Import quality report ────────────────────────────────────────────────
  importQualityTitle: string
  importQualityDetails: string
  importQualityFlaggedOnly: string
  importQualityShowAllRows: string
  importQualityNoFlaggedRows: string
  importQualityErrors: (n: number) => string
  importQualityWarnings: (n: number) => string
  importQualityInfo: (n: number) => string
  importQualityDuplicates: (n: number) => string
  importQualitySeverityError: string
  importQualitySeverityWarning: string
  importQualitySeverityInfo: string
  importQualityUnknownSignal: string
  importQualitySignalLabels: Record<string, string>
  importQualitySignalMessages: Record<string, string>
  // ── Spending heatmap ──────────────────────────────────────────────────────
  heatmapTitle: string
  heatmapLess: string
  heatmapMore: string
  heatmapEmpty: string
  heatmapZoomOut: string
  // ── Top merchants panel ───────────────────────────────────────────────────
  topMerchantsTitle: string
  topMerchantsEmpty: string
  topMerchantsCenterLabel: string
  merchantCoverage: (pct: number) => string
  // ── Cross-filter chips ────────────────────────────────────────────────────
  filterChipMerchant: string
  filterChipDay: string
  // ── Analytics / Tendencias page ───────────────────────────────────────────
  navAnalytics: string
  analyticsTitle: string
  // ── Home → Transactions navigation ────────────────────────────────────────
  btnViewTransactions: string
  // ── DatePicker year navigation ────────────────────────────────────────────
  datePickerPrevYear: string
  datePickerNextYear: string
  // ── Constant (unfiltered) net KPI ─────────────────────────────────────────
  kpiCurrentNet: string
  // ── Inicio dashboard redesign ────────────────────────────────────────────
  dashboardKpiTotalNet: string
  dashboardKpiSavingsRate: string
  dashboardKpiSavingsRateInfo: string
  dashboardKpiAverageMonthlyNet: string
  dashboardKpiAverageMonthlyNetInfo: string
  dashboardPerMonthSuffix: string
  dashboardAccountsTitle: string
  dashboardAccountsAccount: string
  dashboardAccountsNet: string
  dashboardAccountsAvgMonthlyExpense: string
  dashboardAccountsEmpty: string
  dashboardStatementMissingLabel: string
  dashboardStatementMissingTooltip: (month: string) => string
  /** Desglose del patrimonio en la KPI destacada: cuentas vs inversiones. */
  dashboardNetWorthAccounts: string
  dashboardNetWorthInvestments: string
  dashboardNetWorthMortgage: string
  /** Se muestra en el desglose cuando el valor de inversiones no se ha podido leer. */
  dashboardNetWorthUnavailable: string
  /** Aviso cuando el patrimonio excluye las inversiones por un fallo de lectura. */
  dashboardNetWorthPartial: string
  /** Variación de la tasa de ahorro del último mes con datos frente al anterior. */
  dashboardSavingsRateVsPrevMonth: string
  /** Nº de meses sobre los que se calcula el promedio mensual. */
  dashboardMonthsTracked: (months: number) => string
  // ── Investments page ──────────────────────────────────────────────────────
  investmentsTitle: string
  investmentsKpiTotalValue: string
  investmentsKpiTotalInvested: string
  investmentsKpiPnL: string
  investmentsHoldingsTitle: string
  investmentsEmptyHoldings: string
  investmentsCatalogTitle: string
  investmentsComingSoon: string
  investmentsConnect: string
  navInvestments: string
  // ── Connectors settings page ──────────────────────────────────────────────
  settingsSubConnectors: string
  investmentsManageConnectors: string
  connectorsInvestmentsTitle: string
  connectorsNotificationsTitle: string
  // ── Indexa Wizard ─────────────────────────────────────────────────────────
  wizardTitle: string
  wizardProgressLabel: string
  wizardStep1Title: string
  wizardStep1Desc: string
  wizardStep1Link: string
  wizardSecurityNote: string
  wizardNext: string
  wizardStep2Title: string
  wizardTokenLabel: string
  wizardTokenPlaceholder: string
  wizardValidate: string
  wizardStep3Validating: string
  wizardStep3Title: string
  wizardStep3Desc: string
  wizardConnect: string
  wizardStep4Title: string
  wizardStep4Desc: string
  wizardViewInvestments: string
  wizardErrorInvalidToken: string
  wizardErrorNetwork: string
  wizardBack: string
  wizardRetry: string
  wizardClose: string
  wizardOpen: string
  // ── Investments populated page ────────────────────────────────────────────
  invKpiTwr: string
  invKpiXirr: string
  invChartValueTitle: string
  invChartAllocationTitle: string
  invHoldingsEmpty: string
  invHoldingsCount: string
  invAccountUpdated: (relTime: string) => string
  invColName: string
  invColISIN: string
  invColClass: string
  invColValue: string
  invColWeight: string
  invColCost: string
  invColUnits: string
  invColPnL: string
  invColPnLPct: string
  invColPnLInfo: string
  invColPnLPctInfo: string
  invAssetEquity: string
  invAssetFixed_income: string
  invAssetCash: string
  invAssetOther: string
  invErrorLoading: string
  // ── Returns table ─────────────────────────────────────────────────────────
  invReturnsTitle: string
  invReturnsWeek: string
  invReturnsMonth: string
  invReturnsYear: string
  invReturnsTotal: string
  invReturnsAnnual: string
  invReturnsXirr: string
  invReturnsVolatility: string
  // ── Connectors card states ────────────────────────────────────────────────
  connectorConnected: string
  connectorError: string
  connectorDisconnect: string
  connectorErrorRetry: string
  // ── Investments redesign — Block 1: Summary ───────────────────────────────
  invSummaryValorTotal: string
  invSummaryRentabilidad: string
  invSummaryAportaciones: string
  invSummaryRetenciones: string
  // ── Investments redesign — Block 2: Evolution chart ───────────────────────
  invEvolutionTitle: string
  invPeriod1M: string
  invPeriod3M: string
  invPeriod6M: string
  invPeriod1A: string
  invPeriodAll: string
  invToggleEur: string
  invTogglePct: string
  invLegendPortfolio: string
  invLegendContributions: string
  // ── Investments redesign — Block 3: Returns matrix ────────────────────────
  invMatrixTitle: string
  invMonthENE: string
  invMonthFEB: string
  invMonthMAR: string
  invMonthABR: string
  invMonthMAY: string
  invMonthJUN: string
  invMonthJUL: string
  invMonthAGO: string
  invMonthSEP: string
  invMonthOCT: string
  invMonthNOV: string
  invMonthDIC: string
  invMatrixTotal: string
  invMatrixBenchmark: string
  invDrawdownNote: (pct: string, eur: string, start: string, end: string) => string
  // ── Investments polish — Metrics strip ───────────────────────────────────
  invMetricTwr: string
  invMetricMwr: string
  invMetricVolatility: string
  invMetricSubAnnual: string
  invMetricSubXirr: string
  // ── Investments polish — Donuts ───────────────────────────────────────────
  invDonutAssetTitle: string
  invDonutInstrumentTitle: string
  // ── Investments polish 2 — Metric info tooltips ───────────────────────────
  invMetricTwrInfo: string
  invMetricMwrInfo: string
  invMetricVolInfo: string
  // ── Nav restructure — Investments accordion ────────────────────────────────
  navInvestmentsOverview: string
  invNoPluginsHint: string
  invLandingTitle: string
  invLandingEmpty: string
  invPluginNotAvailable: string
  // ── Nav restructure — Settings regrouping ─────────────────────────────────
  settingsGroupData: string
  settingsGroupRules: string
  settingsGroupSystem: string
  settingsGroupApp: string
  // ── Nav restructure — Finanzas group ──────────────────────────────────────
  navFinances: string
  financesOverviewTitle: string
  // ── Combined investments overview ─────────────────────────────────────────
  invCombinedTitle: string
  invCombinedTotalValue: string
  invCombinedTotalGain: string
  invCombinedByProvider: string
  invCombinedByAssetClass: string
  // ── Fidelity ESPP ─────────────────────────────────────────────────────────
  fidelityTitle: string
  fidelityKpiShares: string
  fidelityKpiSharesSub: (n: number) => string
  fidelityKpiInvested: string
  fidelityKpiCurrentValue: string
  fidelityKpiGainLoss: string
  fidelityAsOf: (date: string) => string
  fidelityPriceStale: string
  fidelityPriceInfo: (usd: number, rate: number) => string
  fidelityImportBtn: string
  fidelityImportTitle: string
  fidelityImportStep1Hint: string
  fidelityImportPreviewTitle: string
  fidelityImportNewLots: (n: number) => string
  fidelityImportDuplicates: (n: number) => string
  fidelityImportConfirmBtn: string
  fidelityImportConfirmingBtn: string
  fidelityImportSuccessTitle: string
  fidelityImportSuccessSub: (inserted: number, dupes: number) => string
  fidelityEmptyTitle: string
  fidelityEvolutionTitle: string
  fidelityLegendPortfolio: string
  fidelityLegendInvested: string
  fidelityColDate: string
  fidelityColSource: string
  fidelityColShares: string
  fidelityColCostPerShare: string
  fidelityColTotalCost: string
  fidelityColCurrentValue: string
  fidelityColGain: string
  fidelityColGainPct: string
  fidelityImportCta: string
  fidelitySourceSpTooltip: string
  fidelitySourceDoTooltip: string
  // ── InvestmentSnapshotCard (Inicio cross-domain hub) ──────────────────────
  invSnapshotTitle: string
  invSnapshotNoConnections: string
  invSnapshotGoTo: string
  /** CTA de la tarjeta de proveedor en la portada de Inversiones. */
  invProviderCta: string
  // ── ImportSourcePicker (Inicio import prompt) ─────────────────────────────
  importPickerTitle: string
  importPickerStatements: string
  importPickerStatementsDesc: string
  importPickerClose: string
  // ── Plugin descriptions (localized, keyed by plugin id) ───────────────────
  invPluginDescIndexa: string
  invPluginDescFidelity: string
  // ── ESPP upload-reminder banner ───────────────────────────────────────────
  esppReminderBanner: (periodLabel: string | null) => string
  esppReminderAction: string
  // ── About page ────────────────────────────────────────────────────────────
  settingsSubAbout: string
  aboutTitle: string
  aboutVersion: string
  aboutBuiltAt: string
  aboutRepository: string
  aboutReportIssue: string
  aboutChangelog: string
  aboutLicense: string
  // ── Notifications ──────────────────────────────────────────────────────────
  notifPanelTitle: string
  notifMarkAllRead: string
  notifEmpty: string
  notifDismiss: string
  notifTimeJustNow: string
  notifTimeMinutes: (n: number) => string
  notifTimeHours: (n: number) => string
  notifTimeDays: (n: number) => string
  notifTimeWeeks: (n: number) => string
  notifTitleStatementMissing: (args: { month: string | number; account: string | number }) => string
  notifTitleEsppOverdue: (args: { period: string | number }) => string
  notifActionView: string
  notifMarkRead: string
  notifTitleUnknown: string
  notifBodyStatementMissing: (args: { month: string | number; account: string | number }) => string
  notifBodyEsppOverdue: (args: { period: string | number }) => string
  // ── Telegram wizard ────────────────────────────────────────────────────────
  tgWizardTitle: string
  tgWizardProgressLabel: string
  tgWizardStep1Title: string
  tgWizardStep1Desc: string
  tgWizardStep1Link: string
  tgWizardSecurityNote: string
  tgWizardBotFatherStep1: string
  tgWizardBotFatherStep2: string
  tgWizardBotFatherStep3: string
  tgWizardBotFatherLink: string
  tgWizardStep2Title: string
  tgWizardStep2TokenLabel: string
  tgWizardStep2TokenPlaceholder: string
  tgWizardStep3Title: string
  tgWizardStep3ChatIdLabel: string
  tgWizardStep3ChatIdPlaceholder: string
  tgWizardStep3ChatIdHint: string
  tgWizardChatIdValidationError: string
  tgWizardThreadIdLabel: string
  tgWizardThreadIdOptional: string
  tgWizardThreadIdPlaceholder: string
  tgWizardThreadIdHint: string
  tgWizardThreadIdValidationError: string
  tgWizardStep3TestBtn: string
  tgWizardStep3Testing: string
  tgWizardStep3TestOk: string
  tgWizardStep4Title: string
  tgWizardStep4Desc: string
  tgWizardStep4Saving: string
  tgWizardNext: string
  tgWizardBack: string
  tgWizardClose: string
  tgWizardConnect: string
  tgWizardRetry: string
  tgWizardDone: string
  tgWizardErrorBadToken: string
  tgWizardErrorNoKey: string
  tgWizardErrorSave: string
  // ── Notifications settings page ────────────────────────────────────────────
  settingsSubNotifications: string
  notifSettingsTitle: string
  notifSettingsNoChannels: string
  notifSettingsTelegramLabel: string
  notifSettingsEnabled: string
  notifSettingsDisabled: string
  notifSettingsConnectBtn: string
  notifSettingsEditBtn: string
  notifSettingsDeleteBtn: string
  notifSettingsDeleteConfirm: string
  notifSettingsDeleted: string
  // ── Transaction detail modal ──────────────────────────────────────────────
  txDetailModalTitle: string
  // ── Finances drill-down table ─────────────────────────────────────────────
  drillDownActiveFilters: string
  drillDownClearAll: string
  // ── System transaction badge (is_system=true, "Saldo inicial") ────────────
  systemTxBadge: string
  systemTxBadgeTooltip: string
  // ── Indexa contributions/withdrawals table ────────────────────────────────
  invContribTableTitle: string
  invContribColDate: string
  invContribColAmount: string
  invContribColCumulative: string
  invContribTypeContribution: string
  invContribTypeWithdrawal: string
  invContribEmpty: string
  // ── Language selector ─────────────────────────────────────────────────────
  langSelectLabel: string
  // ── Demo mode (login screen notice) ───────────────────────────────────────
  demoNoticeTitle: string
  demoNoticeBody: string
  demoNoticeCredentials: string

  // ── Finance assistant ─────────────────────────────────────────────────────
  assistantTitle: string
  assistantOpen: string
  assistantClose: string
  assistantNewChat: string
  assistantThreads: string
  assistantNoThreads: string
  assistantDeleteThread: string
  assistantDeleteConfirm: string
  assistantPlaceholder: string
  assistantSend: string
  assistantStop: string
  assistantThinking: string
  assistantEmptyTitle: string
  assistantEmptyBody: string
  assistantDisclaimer: string
  assistantErrorGeneric: string
  assistantErrorRateLimited: string
  assistantErrorTooLong: string
  assistantToolsUsed: (count: number) => string
  assistantUntitled: string
  suggestionSpendingLastMonth: string
  suggestionBiggestCategory: string
  suggestionCompareQuarters: string
  suggestionSubscriptions: string
  suggestionWhereToCut: string
  suggestionInvestProjection: string
  assistantToolReferenceData: string
  assistantToolSummary: string
  assistantToolByCategory: string
  assistantToolByMonth: string
  assistantToolByMerchant: string
  assistantToolCashflow: string
  assistantToolSearch: string
  assistantToolCompare: string
  assistantToolInvestments: string
  assistantToolProjection: string

  // ── Assistant settings page ───────────────────────────────────────────────
  assistantSettingsTitle: string
  assistantSettingsSave: string
  assistantSettingsSaved: string
  assistantUsageTitle: string
  assistantUsageHint: string
  assistantUsageThisMonth: string
  assistantUsageMessages: string
  assistantUsageAllTime: string
  assistantUsageUnavailable: string
  assistantBudgetLabel: string
  assistantBudgetUsed: (used: string, budget: string) => string
  assistantInstructionsLabel: string
  assistantInstructionsHint: string
  assistantInstructionsPlaceholder: string
  assistantInstructionsCoreNote: string
  assistantPromptLabel: string
  assistantPromptHint: string
  assistantPromptRestore: string
  assistantPromptIsDefault: string
  assistantPromptPlaceholderMissing: string
  assistantPromptSafetyTitle: string
  assistantPromptSafetyItem: (key: string) => string
  assistantPromptSafetyNote: string
  assistantLimitsLabel: string
  assistantLimitsHint: string
  assistantLimitsInheritHint: string
  assistantLimitMessages: string
  assistantLimitWindow: string
  assistantBudgetField: string
  assistantBudgetNone: string
  assistantBudgetNote: string
  settingsSubAssistant: string
  // ── Mortgage ──────────────────────────────────────────────────────────────
  navMortgage: string
  mortgageTitle: string
  mortgageEmptyText: string
  mortgageAddBtn: string
  mortgageEditBtn: string
  mortgageDeleteBtn: string
  mortgageDeleteConfirm: string
  mortgageProjectionNote: string
  // KPIs
  mortgageKpiOutstanding: string
  mortgageKpiOutstandingInfo: string
  mortgageKpiAmortized: string
  mortgageKpiPayment: string
  mortgageKpiInterestPaid: string
  mortgageKpiInterestRemaining: string
  mortgageKpiEndDate: string
  mortgageKpiLtv: string
  mortgageKpiLtvInfo: string
  mortgageKpiTotalInterest: string
  mortgageKpiSavedByPrepayments: string
  mortgageMonthsShort: string
  mortgageRemainingSuffix: string
  // Rate types
  mortgageRateFixed: string
  mortgageRateVariable: string
  mortgageRateMixed: string
  // Charts
  mortgageChartBalance: string
  mortgageChartBalanceInfo: string
  mortgageChartComposition: string
  mortgageChartCompositionInfo: string
  mortgageChartEuribor: string
  mortgageSeriesBalance: string
  mortgageSeriesPrincipal: string
  mortgageSeriesInterest: string
  mortgageSeriesProjected: string
  // Schedule table
  mortgageScheduleTitle: string
  mortgageColYear: string
  mortgageColDate: string
  mortgageColPayment: string
  mortgageColInterest: string
  mortgageColPrincipal: string
  mortgageColPrepayment: string
  mortgageColBalance: string
  mortgageColRate: string
  mortgageScheduleTotal: string
  // Prepayments
  mortgagePrepaymentsTitle: string
  mortgagePrepaymentsEmpty: string
  mortgagePrepaymentAdd: string
  mortgagePrepaymentDelete: string
  mortgagePrepaymentDeleteConfirm: string
  mortgageModeReduceTerm: string
  mortgageModeReducePayment: string
  mortgageColMode: string
  mortgageColFee: string
  // Simulator
  mortgageSimulatorTitle: string
  mortgageSimulatorIntro: string
  mortgageSimAmount: string
  mortgageSimDate: string
  mortgageSimMode: string
  mortgageSimFee: string
  mortgageSimAltReturn: string
  mortgageSimAltReturnInfo: string
  mortgageSimRun: string
  mortgageSimApply: string
  mortgageSimApplied: string
  mortgageSimBefore: string
  mortgageSimAfter: string
  mortgageSimInterestSaved: string
  mortgageSimMonthsSaved: string
  mortgageSimNewPayment: string
  mortgageSimNewEnd: string
  mortgageSimImpliedReturn: string
  mortgageSimImpliedReturnInfo: string
  mortgageSimAlternative: string
  mortgageSimWorthIt: string
  mortgageSimNotWorthIt: string
  mortgageSimNetSaving: string
  // Reconciliation
  mortgageReconTitle: string
  mortgageReconIntro: string
  mortgageReconNotLinked: string
  mortgageReconColPeriod: string
  mortgageReconColExpected: string
  mortgageReconColActual: string
  mortgageReconColDeviation: string
  mortgageReconMissing: string
  // Form wizard
  mortgageFormCreateTitle: string
  mortgageFormEditTitle: string
  mortgageFormStepLoan: string
  mortgageFormStepRate: string
  mortgageFormStepLink: string
  mortgageFormName: string
  mortgageFormLender: string
  mortgageFormPrincipal: string
  mortgageFormStartDate: string
  mortgageFormTermYears: string
  mortgageFormPaymentDay: string
  mortgageFormRateType: string
  mortgageFormTin: string
  mortgageFormSpread: string
  mortgageFormIndex: string
  mortgageFormReviewMonths: string
  mortgageFormReviewLag: string
  mortgageFormReviewLagInfo: string
  mortgageFormFloor: string
  mortgageFormCap: string
  mortgageFormFixedYears: string
  mortgageFormBonuses: string
  mortgageFormBonusesInfo: string
  mortgageFormBonusName: string
  mortgageFormBonusReduction: string
  mortgageFormBonusCost: string
  mortgageFormBonusAdd: string
  mortgageFormLinkAccount: string
  mortgageFormLinkCategory: string
  mortgageFormLinkInfo: string
  mortgageFormPropertyValue: string
  mortgageFormIncludeNetWorth: string
  mortgageFormIncludeNetWorthInfo: string
  mortgageFormNotes: string
  mortgageFormNone: string
  mortgageFormPreview: string
  mortgageFormPreviewPayment: string
  mortgageFormPreviewTotalInterest: string
  mortgageFormBack: string
  mortgageFormNext: string
  mortgageFormSave: string
  mortgageFormCancel: string
  // Dashboard card
  mortgageCardTitle: string
  mortgageCardViewDetail: string
  mortgageKpiNetWorthInfo: string
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

/** Resolve a backend `assistant.suggestion.*` key into a translated prompt.
 *
 *  The backend sends keys rather than prose so the starter prompts appear in the
 *  user's language. An unknown key returns null and the caller drops it: adding
 *  a suggestion server-side should not render a raw identifier in the panel. */
export function assistantSuggestion(key: string, t: Dict): string | null {
  switch (key) {
    case 'assistant.suggestion.spendingLastMonth': return t.suggestionSpendingLastMonth
    case 'assistant.suggestion.biggestCategory':   return t.suggestionBiggestCategory
    case 'assistant.suggestion.compareQuarters':   return t.suggestionCompareQuarters
    case 'assistant.suggestion.subscriptions':     return t.suggestionSubscriptions
    case 'assistant.suggestion.whereToCut':        return t.suggestionWhereToCut
    case 'assistant.suggestion.investProjection':  return t.suggestionInvestProjection
    default: return null
  }
}

/** Translate the activity chip shown while an assistant tool runs.
 *
 *  Keyed off the tool NAME, which is a stable identifier, rather than off the
 *  human label the backend also sends: that label is English prose, so using it
 *  directly left Spanish users reading "Breaking down by category". The label
 *  survives as the fallback so a tool this build does not know about still
 *  shows something rather than a blank chip. */
export function assistantToolLabel(name: string, fallback: string, t: Dict): string {
  switch (name) {
    case 'list_reference_data':      return t.assistantToolReferenceData
    case 'get_spending_summary':     return t.assistantToolSummary
    case 'get_spending_by_category': return t.assistantToolByCategory
    case 'get_spending_by_month':    return t.assistantToolByMonth
    case 'get_spending_by_merchant': return t.assistantToolByMerchant
    case 'get_cashflow':             return t.assistantToolCashflow
    case 'search_transactions':      return t.assistantToolSearch
    case 'compare_periods':          return t.assistantToolCompare
    case 'get_investment_overview':  return t.assistantToolInvestments
    case 'project_investment':       return t.assistantToolProjection
    default: return fallback
  }
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

const SUPPORTED: readonly Lang[] = ['es', 'en']

function isLang(v: unknown): v is Lang {
  return typeof v === 'string' && (SUPPORTED as readonly string[]).includes(v)
}

/** Best match for the browser's preferred languages, or null when it asks for
 *  something we don't ship. `navigator.languages` is ordered by preference and
 *  entries are BCP-47 tags ('es-ES', 'en-GB'), so only the primary subtag is
 *  compared. */
function browserLang(): Lang | null {
  try {
    const preferred = navigator.languages?.length
      ? navigator.languages
      : [navigator.language]
    for (const tag of preferred) {
      const primary = tag?.split('-')[0]?.toLowerCase()
      if (isLang(primary)) return primary
    }
  } catch { /* SSR or a locked-down browser — fall through */ }
  return null
}

/** The language in force right now, resolved the same way the provider does.
 *
 *  Exported for code that runs OUTSIDE React and so cannot use `useT` — the
 *  demo's MSW handlers answer at the network layer, where there is no context.
 *  They must not re-implement this fallback chain, or the mocked API would
 *  answer in a different language to the UI rendering it. */
export function currentLang(): Lang {
  try {
    const stored = localStorage.getItem(LS_KEY)
    if (isLang(stored)) return stored
  } catch { /* storage blocked — fall through to detection */ }
  return browserLang() ?? 'es'
}

/** An explicit choice always wins; otherwise follow the browser, and only fall
 *  back to Spanish when the browser asks for a language this app doesn't have. */
function initialLang(): Lang {
  return currentLang()
}

interface LanguageContextValue {
  lang: Lang
  setLang: (l: Lang) => void
}

const LanguageContext = createContext<LanguageContextValue>({ lang: 'es', setLang: () => {} })

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)

  // Keep <html lang> in sync: screen readers and browser translation prompts
  // read it, and it is wrong on first paint since index.html hardcodes one value.
  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

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
