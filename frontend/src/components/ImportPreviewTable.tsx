import { useCallback, useMemo, useState } from 'react'
import type { Account, Category, Tag, ImportTransaction, ImportQualityRowFlag } from '../api/types'
import { useT, categoryLabel } from '../i18n'
import DateInput from './DateInput'
import TagTypeahead from './TagTypeahead'
import PreviewTypeahead, { type PreviewTypeaheadOption } from './PreviewTypeahead'
import type { LiveImportQuality } from './importQuality'
import { IconAlert, IconInfo, IconSettings, IconClose, IconLink } from './icons'

export type EditRow = ImportTransaction & {
  _key: number
  isDuplicate?: boolean
  allow_duplicate?: boolean
  _qualityFlags?: ImportQualityRowFlag[]
  _originalCategory?: string
}

interface Props {
  rows: EditRow[]
  accounts: Account[]
  categories: Category[]
  allTags: Tag[]
  suggestedColors: Record<string, string>
  onUpdateRow: (key: number, patch: Partial<Omit<EditRow, '_key'>>) => void
  onDeleteRow: (key: number) => void
  onAddBlankRow: () => void
  onCreateRule: (row: EditRow) => void
  showYearWarning?: boolean
  liveQuality: LiveImportQuality
}

export default function ImportPreviewTable({
  rows, accounts, categories, allTags, suggestedColors,
  onUpdateRow, onDeleteRow, onAddBlankRow, onCreateRule,
  showYearWarning = false, liveQuality,
}: Props) {
  const { t, lang, formatCurrency } = useT()
  const [flaggedOnly, setFlaggedOnly] = useState(false)
  const [focusedRowKey, setFocusedRowKey] = useState<number | null>(null)

  const flaggedRowCount = liveQuality.flaggedRowKeys.size
  const visibleRows = flaggedOnly
    ? rows.filter(r => liveQuality.flaggedRowKeys.has(r._key) || focusedRowKey === r._key)
    : rows

  const signalLabel = (code: string) => t.importQualitySignalLabels[code] ?? t.importQualityUnknownSignal
  const signalMessage = (code: string) => t.importQualitySignalMessages[code] ?? t.importQualityUnknownSignal
  const severityMark = (severity: string) => severity === 'info' ? <IconInfo size={12} /> : <IconAlert size={12} />
  const flagBadges = (row: EditRow, field: string) => {
    const flags = (liveQuality.rowFlagsByKey.get(row._key) ?? []).filter(flag => flag.fields.includes(field))
    if (flags.length === 0) return null
    return (
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 3 }}>
        {flags.map((flag, i) => {
          const title = `${signalLabel(flag.code)} — ${signalMessage(flag.code)}`
          const color = flag.severity === 'error' ? 'var(--expense)' : flag.severity === 'warning' ? '#b45309' : 'var(--text-muted)'
          return (
            <span
              key={`${flag.code}-${i}`}
              className="import-dup-badge"
              title={title}
              aria-label={title}
              style={{ color, borderColor: color }}
            >
              {severityMark(flag.severity)}
            </span>
          )
        })}
      </div>
    )
  }

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const baseCategories = useMemo(() =>
    categories
      .filter(c => c.is_base)
      .sort((a, b) => categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs))),
    [categories, lang, dynamicEs],
  )

  const customCategories = useMemo(() => {
    const baseNames = new Set(categories.filter(c => c.is_base).map(c => c.name))
    const seen = new Set<string>()
    const result: string[] = []
    for (const row of rows) {
      const val = row.category.trim()
      if (val && !baseNames.has(val) && !seen.has(val)) { seen.add(val); result.push(val) }
    }
    return result.sort()
  }, [rows, categories])

  const categoryOptions = useMemo<PreviewTypeaheadOption[]>(() => [
    ...baseCategories.map(c => ({ value: c.name, label: categoryLabel(c.name, lang, dynamicEs) })),
    ...customCategories.map(cat => ({ value: cat, label: categoryLabel(cat, lang, dynamicEs) })),
  ], [baseCategories, customCategories, lang, dynamicEs])

  const getPreviewCategoryLabel = useCallback(
    (value: string) => categoryLabel(value, lang, dynamicEs),
    [lang, dynamicEs],
  )

  const normalizeCategoryInput = useCallback((input: string, options: PreviewTypeaheadOption[]) => {
    const trimmed = input.trim()
    const lower = trimmed.toLocaleLowerCase(lang)
    const match = options.find(opt => {
      const optionValue = opt.value.toLocaleLowerCase(lang)
      const optionLabel = (opt.label ?? getPreviewCategoryLabel(opt.value)).toLocaleLowerCase(lang)
      return optionValue === lower || optionLabel === lower
    })
    return match?.value ?? trimmed
  }, [getPreviewCategoryLabel, lang])

  const distinctMerchants = useMemo(() => {
    const seen = new Set<string>()
    for (const row of rows) { const m = row.merchant?.trim(); if (m) seen.add(m) }
    return [...seen].sort()
  }, [rows])

  const distinctPreviewTagNames = useMemo(() => {
    const seen = new Set<string>()
    for (const row of rows) for (const tag of row.tags) if (tag) seen.add(tag)
    return [...seen].sort()
  }, [rows])

  const hasLowConf = rows.some(r =>
    (liveQuality.rowFlagsByKey.get(r._key) ?? []).some(flag => flag.code === 'low_confidence_category')
  )
  const accountOptions = useMemo(() => accounts.map(a => ({ value: a.name })), [accounts])
  const merchantOptions = useMemo(() => distinctMerchants.map(m => ({ value: m })), [distinctMerchants])

  return (
    <div>
      <div style={{ marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="btn-outline" onClick={onAddBlankRow}>{t.modalAddRow}</button>
        {flaggedRowCount > 0 && (
          <button
            type="button"
            className="btn-outline"
            onClick={() => setFlaggedOnly(v => !v)}
            aria-pressed={flaggedOnly}
          >
            {flaggedOnly ? t.importQualityShowAllRows : t.importQualityFlaggedOnly}
          </button>
        )}
        {hasLowConf && (
          <span className="confidence-hint" style={{ fontSize: 12 }}>
            <IconAlert size={13} /> {t.modalLowConfidence}
          </span>
        )}
      </div>

      {showYearWarning && (
        <div className="year-warning-banner">
          <IconAlert size={15} /> {t.modalYearNotFound}
        </div>
      )}

      <div className="preview-table-wrap">
        <table className="preview-table">
          <thead>
            <tr>
              <th>{t.previewColDate}</th>
              <th>{t.previewColDesc}</th>
              <th>{t.colMerchant}</th>
              <th>{t.previewColAmount}</th>
              <th>{t.previewColCategory}</th>
              <th>{t.previewColAccount}</th>
              <th>{t.previewColTags}</th>
              <th>{t.previewColConf}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ color: 'var(--text-muted)', padding: 14, textAlign: 'center' }}>
                  {t.importQualityNoFlaggedRows}
                </td>
              </tr>
            )}
            {visibleRows.map(row => {
              const rowFlags = liveQuality.rowFlagsByKey.get(row._key) ?? []
              const lowConf = rowFlags.some(flag => flag.code === 'low_confidence_category')
              const isDuplicate = liveQuality.duplicateRowKeys.has(row._key) && !row.allow_duplicate
              const amountColor = row.amount < 0 ? 'var(--expense)' : row.amount > 0 ? 'var(--income)' : 'inherit'
              const rowClass = [lowConf ? 'row-low-confidence' : '', isDuplicate ? 'row-duplicate' : ''].filter(Boolean).join(' ')
              return (
                <tr
                  key={row._key}
                  className={rowClass || undefined}
                  onFocus={() => setFocusedRowKey(row._key)}
                  onBlur={e => {
                    const nextFocus = e.relatedTarget
                    if (!(nextFocus instanceof Node) || !e.currentTarget.contains(nextFocus)) {
                      setFocusedRowKey(current => current === row._key ? null : current)
                    }
                  }}
                >
                  <td>
                    <DateInput
                      className="cell-input cell-date"
                      value={row.transaction_date}
                      lang={lang}
                      onChange={iso => onUpdateRow(row._key, { transaction_date: iso })}
                    />
                    {flagBadges(row, 'transaction_date')}
                  </td>
                  <td>
                    <input
                      type="text"
                      className="cell-input cell-desc"
                      value={row.description}
                      onChange={e => onUpdateRow(row._key, { description: e.target.value })}
                    />
                    {isDuplicate && (
                      <div className="import-dup-badge-wrap" style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                        <span className="import-dup-badge">{t.importDuplicateBadge}</span>
                        <button
                          type="button"
                          onClick={() => onUpdateRow(row._key, { allow_duplicate: true, isDuplicate: false })}
                          title={t.importDuplicateOverrideTooltip}
                          style={{
                            border: 'none',
                            background: 'transparent',
                            color: 'var(--primary)',
                            cursor: 'pointer',
                            fontSize: 12,
                            padding: 0,
                            textDecoration: 'underline',
                          }}
                        >
                          {t.importDuplicateOverrideLabel}
                        </button>
                      </div>
                    )}
                    {row.detail && (
                      <div className="tx-detail-subline tx-detail-subline--input-aligned">{row.detail}</div>
                    )}
                    {flagBadges(row, 'description')}
                  </td>
                  <td>
                    <PreviewTypeahead
                      value={row.merchant ?? ''}
                      options={merchantOptions}
                      placeholder={t.importMerchantPlaceholder}
                      className="cell-merchant import-merchant-input"
                      onChange={value => onUpdateRow(row._key, { merchant: value || null })}
                    />
                    {flagBadges(row, 'merchant')}
                  </td>
                  <td>
                    <div className="amount-cell">
                      <select
                        className="cell-sign"
                        value={row.amount <= 0 ? '-' : '+'}
                        onChange={e => {
                          const neg = e.target.value === '-'
                          onUpdateRow(row._key, { amount: neg ? -Math.abs(row.amount) : Math.abs(row.amount) })
                        }}
                        title={row.amount <= 0 ? t.previewSignExpense : t.previewSignIncome}
                      >
                        <option value="-">{t.previewSignExpense}</option>
                        <option value="+">{t.previewSignIncome}</option>
                      </select>
                      <input
                        type="number"
                        className="cell-input cell-amount"
                        value={Math.abs(row.amount)}
                        min="0"
                        step="0.01"
                        style={{ color: amountColor }}
                        onChange={e => {
                          const abs = Math.abs(Number(e.target.value))
                          onUpdateRow(row._key, { amount: row.amount <= 0 ? -abs : abs })
                        }}
                      />
                    </div>
                    {flagBadges(row, 'amount')}
                  </td>
                  <td>
                    <div className="category-cell-wrap">
                      <PreviewTypeahead
                        value={row.category}
                        options={categoryOptions}
                        onChange={val => onUpdateRow(row._key, { category: val })}
                        placeholder={t.previewCategoryCustomPlaceholder || t.previewCategoryCustom}
                        className="cell-category"
                        getLabel={getPreviewCategoryLabel}
                        normalizeInput={normalizeCategoryInput}
                      />
                      {flagBadges(row, 'category')}
                      {row.matched_rule_id != null && (
                        <span
                          className="rule-match-badge"
                          title={t.ruleMatchTooltip(row.matched_rule_name ?? '')}
                        >
                          <IconLink size={11} /> {t.ruleMatchBadge}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <PreviewTypeahead
                      value={row.account_ref}
                      options={accountOptions}
                      className="cell-account"
                      onChange={value => onUpdateRow(row._key, { account_ref: value })}
                    />
                    {flagBadges(row, 'account_ref')}
                  </td>
                  <td>
                    <TagTypeahead
                      tags={row.tags}
                      availableTags={allTags}
                      suggestedColors={suggestedColors}
                      previewTagNames={distinctPreviewTagNames}
                      onChange={tags => onUpdateRow(row._key, { tags })}
                      placeholder={t.tagTypeaheadPlaceholder}
                    />
                  </td>
                  <td>
                    {row.category_confidence !== null ? (
                      <span className={`conf-badge ${lowConf ? 'conf-low' : 'conf-ok'}`}>
                        {Math.round(row.category_confidence * 100)}%
                      </span>
                    ) : (
                      <span className="conf-badge conf-na">—</span>
                    )}
                  </td>
                  <td>
                    <div className="td-actions">
                      <button
                        className="btn-row-icon btn-create-rule"
                        onClick={() => onCreateRule(row)}
                        title={t.createRuleBtn}
                      ><IconSettings size={15} /></button>
                      <button
                        className="btn-row-delete"
                        onClick={() => onDeleteRow(row._key)}
                        title={t.previewDeleteRow}
                      ><IconClose size={15} /></button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
        {t.previewTotalExpenses}: <strong className="private" style={{ color: 'var(--expense)' }}>
          {formatCurrency(visibleRows.filter(r => r.amount < 0).reduce((s, r) => s + Math.abs(r.amount), 0))}
        </strong>
        &nbsp;·&nbsp;
        {t.previewTotalIncome}: <strong className="private" style={{ color: 'var(--income)' }}>
          {formatCurrency(visibleRows.filter(r => r.amount > 0).reduce((s, r) => s + r.amount, 0))}
        </strong>
      </div>
    </div>
  )
}
