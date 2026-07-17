import type {
  ImportQuality,
  ImportQualityRowFlag,
  ImportQualitySeverity,
  ImportQualitySignalCode,
  ImportTransaction,
} from '../api/types'

export const LOW_CONFIDENCE_THRESHOLD = 0.6

export type QualityEditableRow = ImportTransaction & {
  _key: number
  isDuplicate?: boolean
  _originalCategory?: string
}

export interface LiveImportQuality {
  quality: ImportQuality
  rowFlagsByKey: Map<number, ImportQualityRowFlag[]>
  dbDuplicateRowKeys: Set<number>
  duplicateRowKeys: Set<number>
  flaggedRowKeys: Set<number>
}

const SEVERITY_BY_CODE: Record<ImportQualitySignalCode, ImportQualitySeverity> = {
  low_confidence_category: 'warning',
  missing_category: 'warning',
  generic_category: 'warning',
  missing_merchant: 'warning',
  zero_amount: 'error',
  date_year_mismatch: 'warning',
  year_undetected: 'info',
  intra_batch_duplicate: 'warning',
}

const FIELDS_BY_CODE: Record<ImportQualitySignalCode, string[]> = {
  low_confidence_category: ['category'],
  missing_category: ['category'],
  generic_category: ['category'],
  missing_merchant: ['merchant'],
  zero_amount: ['amount'],
  date_year_mismatch: ['transaction_date'],
  year_undetected: [],
  intra_batch_duplicate: ['transaction_date', 'amount', 'description'],
}

const SIGNAL_ORDER: ImportQualitySignalCode[] = [
  'low_confidence_category',
  'missing_category',
  'generic_category',
  'missing_merchant',
  'zero_amount',
  'date_year_mismatch',
  'year_undetected',
  'intra_batch_duplicate',
]

const NON_MERCHANT_CATEGORIES = new Set(['income', 'transfers', 'taxes', 'bank fees', 'cash/atm'])

const NON_MERCHANT_DESCRIPTION_RE =
  /\b(salary|payroll|nomina|nómina|pension|pensión|transfer|transferencia|traspaso|bizum|tax|taxes|impuesto|hacienda|aeat|seguridad social|fee|commission|comision|comisión|maintenance|mantenimiento|atm|cash|cajero|efectivo)\b/i

export function computeLiveImportQuality(
  rows: QualityEditableRow[],
  statementYear: number | null | undefined,
  yearDetected: boolean,
): LiveImportQuality {
  const rowFlags: ImportQualityRowFlag[] = []
  const rowFlagsByKey = new Map<number, ImportQualityRowFlag[]>()
  const signalCounts = new Map<ImportQualitySignalCode, number>()

  const addRowFlag = (rowIndex: number, code: ImportQualitySignalCode) => {
    const flag: ImportQualityRowFlag = {
      row_index: rowIndex,
      code,
      severity: SEVERITY_BY_CODE[code],
      fields: FIELDS_BY_CODE[code],
    }
    rowFlags.push(flag)
    signalCounts.set(code, (signalCounts.get(code) ?? 0) + 1)
    const key = rows[rowIndex]._key
    rowFlagsByKey.set(key, [...(rowFlagsByKey.get(key) ?? []), flag])
  }

  rows.forEach((row, idx) => {
    const categoryHumanVerified =
      row._originalCategory != null && row.category.trim() !== row._originalCategory.trim()

    if (!categoryHumanVerified) {
      if (row.category_confidence != null && asNumber(row.category_confidence) < LOW_CONFIDENCE_THRESHOLD) {
        addRowFlag(idx, 'low_confidence_category')
      }

      if (isBlank(row.category)) {
        addRowFlag(idx, 'missing_category')
      } else if (
        normalizeText(row.category) === 'other' &&
        row.category_confidence != null &&
        asNumber(row.category_confidence) < LOW_CONFIDENCE_THRESHOLD
      ) {
        addRowFlag(idx, 'generic_category')
      }
    }

    if (amountIsZeroOrNonFinite(row.amount)) addRowFlag(idx, 'zero_amount')

    if (statementYear != null && dateYear(row.transaction_date) != null && dateYear(row.transaction_date) !== statementYear) {
      addRowFlag(idx, 'date_year_mismatch')
    }

    if (isBlank(row.merchant) && shouldFlagMissingMerchant(row)) {
      addRowFlag(idx, 'missing_merchant')
    }
  })

  for (const idx of intraBatchDuplicateIndexes(rows)) addRowFlag(idx, 'intra_batch_duplicate')

  if (!yearDetected) signalCounts.set('year_undetected', (signalCounts.get('year_undetected') ?? 0) + 1)

  const summaryCounts: Record<ImportQualitySeverity, number> = { error: 0, warning: 0, info: 0 }
  for (const [code, count] of signalCounts.entries()) summaryCounts[SEVERITY_BY_CODE[code]] += count

  const dbDuplicateRowKeys = new Set<number>()
  rows.forEach(row => { if (row.isDuplicate) dbDuplicateRowKeys.add(row._key) })
  const duplicateRowKeys = new Set<number>(dbDuplicateRowKeys)
  for (const flag of rowFlags) {
    if (flag.code === 'intra_batch_duplicate') duplicateRowKeys.add(rows[flag.row_index]._key)
  }

  const flaggedRowKeys = new Set<number>(duplicateRowKeys)
  for (const flag of rowFlags) flaggedRowKeys.add(rows[flag.row_index]._key)

  return {
    quality: {
      summary: {
        error_count: summaryCounts.error,
        warning_count: summaryCounts.warning,
        info_count: summaryCounts.info,
        flagged_row_count: new Set(rowFlags.map(flag => flag.row_index)).size,
      },
      signals: SIGNAL_ORDER
        .filter(code => (signalCounts.get(code) ?? 0) > 0)
        .map(code => ({ code, severity: SEVERITY_BY_CODE[code], count: signalCounts.get(code)! })),
      row_flags: rowFlags,
    },
    rowFlagsByKey,
    dbDuplicateRowKeys,
    duplicateRowKeys,
    flaggedRowKeys,
  }
}

function intraBatchDuplicateIndexes(rows: QualityEditableRow[]): number[] {
  const seen = new Set<string>()
  const duplicateIndexes: number[] = []
  rows.forEach((row, idx) => {
    const key = dedupKey(row)
    if (!key) return
    if (seen.has(key)) duplicateIndexes.push(idx)
    else seen.add(key)
  })
  return duplicateIndexes
}

function dedupKey(row: QualityEditableRow): string | null {
  if (!Number.isFinite(row.amount) || !row.transaction_date) return null
  return JSON.stringify({
    account: (row.account_ref ?? '').trim().toLowerCase(),
    date: row.transaction_date,
    amount: String(row.amount),
    description: (row.description ?? '').trim().toLowerCase(),
    detail: row.detail?.trim().toLowerCase() || null,
  })
}

function shouldFlagMissingMerchant(row: QualityEditableRow): boolean {
  if (!Number.isFinite(row.amount) || row.amount >= 0) return false
  if (NON_MERCHANT_CATEGORIES.has(normalizeText(row.category ?? ''))) return false
  const haystack = stripAccents([row.description, row.detail, row.raw_line, row.category].map(v => v ?? '').join(' '))
  return !NON_MERCHANT_DESCRIPTION_RE.test(haystack)
}

function dateYear(value: string): number | null {
  const match = value.match(/^(\d{4})-/)
  return match ? Number(match[1]) : null
}

function amountIsZeroOrNonFinite(value: number): boolean {
  return !Number.isFinite(value) || value === 0
}

function isBlank(value: unknown): boolean {
  return value == null || (typeof value === 'string' && value.trim() === '')
}

function asNumber(value: unknown): number {
  return typeof value === 'number' ? value : Number(value)
}

function normalizeText(value: string): string {
  return stripAccents(value).trim().toLowerCase().split(/\s+/).join(' ')
}

function stripAccents(value: string): string {
  return value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}
