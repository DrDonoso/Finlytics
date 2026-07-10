import { useMemo } from 'react'
import type { Account, Category, Tag, ImportTransaction } from '../api/types'
import { useT, categoryLabel } from '../i18n'
import DateInput from './DateInput'
import CategorySelect from './CategorySelect'
import TagTypeahead from './TagTypeahead'

export type EditRow = ImportTransaction & { _key: number; isDuplicate?: boolean }

interface Props {
  rows: EditRow[]
  /** Unique string prefix used for datalist element IDs — prevents conflicts when multiple tables are on screen */
  fileKey: string
  accounts: Account[]
  categories: Category[]
  allTags: Tag[]
  suggestedColors: Record<string, string>
  onUpdateRow: (key: number, patch: Partial<Omit<EditRow, '_key'>>) => void
  onDeleteRow: (key: number) => void
  onAddBlankRow: () => void
  onCreateRule: (row: EditRow) => void
  showYearWarning?: boolean
}

export default function ImportPreviewTable({
  rows, fileKey, accounts, categories, allTags, suggestedColors,
  onUpdateRow, onDeleteRow, onAddBlankRow, onCreateRule,
  showYearWarning = false,
}: Props) {
  const { t, lang, formatCurrency } = useT()

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

  const hasLowConf = rows.some(r => r.category_confidence !== null && r.category_confidence < 0.5)
  const accsListId = `prev-accs-${fileKey}`
  const merListId  = `prev-merch-${fileKey}`

  return (
    <div>
      <div style={{ marginBottom: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <button className="btn-outline" onClick={onAddBlankRow}>{t.modalAddRow}</button>
        {hasLowConf && <span className="confidence-hint" style={{ fontSize: 12 }}>{t.modalLowConfidence}</span>}
      </div>

      {showYearWarning && <div className="year-warning-banner">{t.modalYearNotFound}</div>}

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
            {rows.map(row => {
              const lowConf = row.category_confidence !== null && row.category_confidence < 0.5
              const amountColor = row.amount < 0 ? 'var(--expense)' : row.amount > 0 ? 'var(--income)' : 'inherit'
              const rowClass = [lowConf ? 'row-low-confidence' : '', row.isDuplicate ? 'row-duplicate' : ''].filter(Boolean).join(' ')
              return (
                <tr key={row._key} className={rowClass || undefined}>
                  <td>
                    <DateInput
                      className="cell-input cell-date"
                      value={row.transaction_date}
                      lang={lang}
                      onChange={iso => onUpdateRow(row._key, { transaction_date: iso })}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      className="cell-input cell-desc"
                      value={row.description}
                      onChange={e => onUpdateRow(row._key, { description: e.target.value })}
                    />
                    {row.isDuplicate && (
                      <div className="import-dup-badge-wrap">
                        <span className="import-dup-badge">{t.importDuplicateBadge}</span>
                      </div>
                    )}
                    {row.detail && (
                      <div className="tx-detail-subline tx-detail-subline--input-aligned">{row.detail}</div>
                    )}
                  </td>
                  <td>
                    <input
                      type="text"
                      list={merListId}
                      className="cell-input cell-merchant import-merchant-input"
                      value={row.merchant ?? ''}
                      placeholder={t.importMerchantPlaceholder}
                      onChange={e => onUpdateRow(row._key, { merchant: e.target.value || null })}
                    />
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
                  </td>
                  <td>
                    <div className="category-cell-wrap">
                      <CategorySelect
                        value={row.category}
                        baseCategories={baseCategories}
                        extraCategories={customCategories}
                        lang={lang}
                        t={t}
                        onChange={val => onUpdateRow(row._key, { category: val })}
                      />
                      {row.matched_rule_id != null && (
                        <span
                          className="rule-match-badge"
                          title={t.ruleMatchTooltip(row.matched_rule_name ?? '')}
                        >
                          {t.ruleMatchBadge}
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <input
                      type="text"
                      list={accsListId}
                      className="cell-input cell-account"
                      value={row.account_ref}
                      onChange={e => onUpdateRow(row._key, { account_ref: e.target.value })}
                    />
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
                      >⚙+</button>
                      <button
                        className="btn-row-delete"
                        onClick={() => onDeleteRow(row._key)}
                        title={t.previewDeleteRow}
                      >✕</button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <datalist id={accsListId}>
        {accounts.map(a => <option key={a.id} value={a.name} />)}
      </datalist>
      <datalist id={merListId}>
        {distinctMerchants.map(m => <option key={m} value={m} />)}
      </datalist>

      <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
        {t.previewTotalExpenses}: <strong style={{ color: 'var(--expense)' }}>
          {formatCurrency(rows.filter(r => r.amount < 0).reduce((s, r) => s + Math.abs(r.amount), 0))}
        </strong>
        &nbsp;·&nbsp;
        {t.previewTotalIncome}: <strong style={{ color: 'var(--income)' }}>
          {formatCurrency(rows.filter(r => r.amount > 0).reduce((s, r) => s + r.amount, 0))}
        </strong>
      </div>
    </div>
  )
}
