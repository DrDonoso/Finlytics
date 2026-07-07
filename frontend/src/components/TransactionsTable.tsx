import { useState, useEffect, useCallback, useMemo } from 'react'
import type { Category, GlobalFilters, Tag, Transaction, TransactionPage } from '../api/types'
import { getTransactions, updateTransaction } from '../api/client'
import { useT, categoryLabel, formatDate, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import CategorySelect from './CategorySelect'
import TagEditor from './TagEditor'

interface Props {
  globalFilters: GlobalFilters
  categories: Category[]
  allTags: Tag[]
  refreshKey?: number
  pageSize?: number
  description?: string
  amountMin?: number
  amountMax?: number
  merchant?: string
  hideInternalFilters?: boolean
  onEditSuccess?: () => void
}

interface EditData {
  description: string
  category: string
  sign: '-' | '+'
  absAmount: string
  tags: string[]
  merchant: string
}

const LIMIT = 10

export default function TransactionsTable({ globalFilters, categories, allTags, refreshKey, pageSize, description, amountMin, amountMax, merchant, hideInternalFilters, onEditSuccess }: Props) {
  const { t, lang, formatCurrency } = useT()
  const limit = pageSize ?? LIMIT
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined)
  const [page, setPage] = useState(0)
  const [sortCol,   setSortCol]   = useState<string>('date')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<TransactionPage | null>(null)

  const [editingId,  setEditingId]  = useState<number | null>(null)
  const [editData,   setEditData]   = useState<EditData | null>(null)
  const [saving,     setSaving]     = useState(false)
  const [saveError,  setSaveError]  = useState<string | null>(null)

  // ── Dynamic ES labels for non-base categories
  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  // ── Sorted categories for filter dropdown
  const sortedCategories = useMemo(() =>
    [...categories].sort((a, b) =>
      categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs)),
    ),
    [categories, lang, dynamicEs],
  )

  // ── Sorted base categories for the inline edit select
  const sortedBaseCategories = useMemo(() =>
    categories
      .filter(c => c.is_base)
      .sort((a, b) => categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs))),
    [categories, lang, dynamicEs],
  )

  // ── Non-base categories from DB (for the edit select extra group)
  const dbExtraCategories = useMemo(() =>
    categories
      .filter(c => !c.is_base)
      .map(c => c.name)
      .sort((a, b) => a.localeCompare(b)),
    [categories],
  )

  // ── Tag info map for read-mode chips (color + emoji)
  const tagInfoMap = useMemo(() => {
    const map: Record<string, { color: string; emoji: string | null }> = {}
    for (const tg of allTags) map[tg.name] = { color: tg.color, emoji: tg.emoji }
    return map
  }, [allTags])

  // ── Category color map
  const categoryColorMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const c of categories) if (c.color) map[c.name] = c.color
    return map
  }, [categories])

  useEffect(() => { setPage(0) }, [globalFilters.from, globalFilters.to, globalFilters.account_id, globalFilters.category_id, globalFilters.tags, globalFilters.flow, categoryId, description, amountMin, amountMax, merchant, sortCol, sortOrder])

  const fetchData = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTransactions({
      from:        globalFilters.from,
      to:          globalFilters.to,
      account_id:  globalFilters.account_id,
      category_id: categoryId ?? globalFilters.category_id,
      tags:        globalFilters.tags.length > 0 ? globalFilters.tags : undefined,
      flow:        globalFilters.flow,
      description: description,
      amount_min:  amountMin,
      amount_max:  amountMax,
      merchant:    merchant,
      limit:       limit,
      offset:      page * limit,
      sort:        sortCol,
      order:       sortOrder,
    })
      .then(d  => { if (!cancelled) { setData(d); setLoading(false) } })
      .catch(e => { if (!cancelled) { setError(String(e)); setLoading(false) } })
    return () => { cancelled = true }
  }, [globalFilters.from, globalFilters.to, globalFilters.account_id, globalFilters.category_id, globalFilters.tags, globalFilters.flow, categoryId, page, refreshKey, description, amountMin, amountMax, merchant, limit, sortCol, sortOrder]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(fetchData, [fetchData])

  // ── Edit helpers
  function startEdit(tx: Transaction) {
    setEditingId(tx.id)
    setSaveError(null)
    setEditData({
      description: tx.description,
      category:    tx.category,
      sign:        tx.amount <= 0 ? '-' : '+',
      absAmount:   String(Math.abs(tx.amount)),
      tags:        tx.tags,
      merchant:    tx.merchant ?? '',
    })
  }
  function cancelEdit() {
    setEditingId(null)
    setEditData(null)
    setSaveError(null)
  }
  async function commitEdit(tx: Transaction) {
    if (!editData) return
    setSaving(true)
    setSaveError(null)
    const signedAmount = editData.sign === '-'
      ? -Math.abs(Number(editData.absAmount))
      :  Math.abs(Number(editData.absAmount))
    try {
      const updated = await updateTransaction(tx.id, {
        description: editData.description,
        category:    editData.category,
        amount:      signedAmount,
        tags:        editData.tags,
        merchant:    editData.merchant,
      })
      setData(d => d ? { ...d, items: d.items.map(item => item.id === tx.id ? updated : item) } : null)
      setEditingId(null)
      setEditData(null)
      onEditSuccess?.()
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setSaveError(msg.includes('409') ? t.tableSaveError : t.tableSaveError)
    } finally {
      setSaving(false)
    }
  }

  const totalPages = data ? Math.ceil(data.total / limit) : 0
  const start = page * limit + 1
  const end = data ? Math.min(page * limit + limit, data.total) : 0

  function handleSort(col: string) {
    if (col === sortCol) {
      setSortOrder(o => o === 'desc' ? 'asc' : 'desc')
    } else {
      setSortCol(col)
      setSortOrder('desc')
    }
  }

  function sortIndicator(col: string) {
    if (col !== sortCol) return null
    return <span className="th-sort-arrow">{sortOrder === 'asc' ? '▲' : '▼'}</span>
  }

  return (
    <div className="card">
      <div className="card-title">{t.tableTitle}</div>

      {!hideInternalFilters && (
        <div className="table-filters">
          <div className="filter-group">
            <label>{t.tableFilterCategory}</label>
            <select
              value={categoryId ?? ''}
              onChange={e => setCategoryId(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">{t.tableFilterAll}</option>
              {sortedCategories.map(c => (
                <option key={c.id} value={c.id}>{categoryLabel(c.name, lang, dynamicEs)}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {error && (
        <div className="state-box error">
          <span className="icon">⚠</span>
          <span>{t.tableErrorLoading}{error}</span>
        </div>
      )}

      {!error && loading && (
        <div>
          {[0, 1, 2, 3, 4].map(i => (
            <div key={i} className="skeleton" style={{ marginBottom: 10, height: 36 }} />
          ))}
        </div>
      )}

      {!error && !loading && data && data.items.length === 0 && (
        <div className="state-box">
          <span className="icon">📋</span>
          <span>{t.tableNoData}</span>
        </div>
      )}

      {!error && !loading && data && data.items.length > 0 && (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th
                    className={`th-sortable${sortCol === 'date' ? ' th-sort-active' : ''}`}
                    onClick={() => handleSort('date')}
                  >{t.tableColDate}{sortIndicator('date')}</th>
                  <th
                    className={`th-sortable${sortCol === 'account' ? ' th-sort-active' : ''}`}
                    onClick={() => handleSort('account')}
                  >{t.tableColAccount}{sortIndicator('account')}</th>
                  <th
                    className={`th-sortable${sortCol === 'description' ? ' th-sort-active' : ''}`}
                    onClick={() => handleSort('description')}
                  >{t.tableColDesc}{sortIndicator('description')}</th>
                  <th
                    className={`th-merchant th-sortable${sortCol === 'merchant' ? ' th-sort-active' : ''}`}
                    onClick={() => handleSort('merchant')}
                  >{t.colMerchant}{sortIndicator('merchant')}</th>
                  <th
                    className={`th-sortable${sortCol === 'category' ? ' th-sort-active' : ''}`}
                    onClick={() => handleSort('category')}
                  >{t.tableColCategory}{sortIndicator('category')}</th>
                  <th>{t.tableColTags}</th>
                  <th
                    className={`th-sortable${sortCol === 'amount' ? ' th-sort-active' : ''}`}
                    style={{ textAlign: 'right' }}
                    onClick={() => handleSort('amount')}
                  >{t.tableColAmount}{sortIndicator('amount')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(tx => {
                  const isEditing = editingId === tx.id
                  const amountColor = isEditing && editData
                    ? (editData.sign === '-' ? 'var(--expense)' : 'var(--income)')
                    : (tx.amount < 0 ? 'var(--expense)' : 'var(--income)')

                  if (isEditing && editData) {
                    return (
                      <tr key={tx.id} className="row-editing">
                        <td className="td-date">{formatDate(tx.transaction_date, lang)}</td>
                        <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{tx.account}</td>
                        <td>
                          <input
                            type="text"
                            className="td-edit-input"
                            value={editData.description}
                            disabled={saving}
                            onChange={e => setEditData(d => d ? { ...d, description: e.target.value } : d)}
                            onKeyDown={e => { if (e.key === 'Enter') commitEdit(tx); if (e.key === 'Escape') cancelEdit() }}
                          />
                        </td>
                        <td className="td-merchant">
                          <input
                            type="text"
                            className="td-edit-input"
                            value={editData.merchant}
                            disabled={saving}
                            placeholder={t.colMerchant}
                            onChange={e => setEditData(d => d ? { ...d, merchant: e.target.value } : d)}
                            onKeyDown={e => { if (e.key === 'Enter') commitEdit(tx); if (e.key === 'Escape') cancelEdit() }}
                          />
                        </td>
                        <td>
                          <CategorySelect
                            value={editData.category}
                            baseCategories={sortedBaseCategories}
                            extraCategories={dbExtraCategories}
                            lang={lang}
                            t={t}
                            onChange={val => setEditData(d => d ? { ...d, category: val } : d)}
                          />
                        </td>
                        <td className="td-tags">
                          <TagEditor
                            tags={editData.tags}
                            availableTags={allTags}
                            disabled={saving}
                            onChange={tags => setEditData(d => d ? { ...d, tags } : d)}
                            placeholder={t.tagEditorPlaceholder}
                          />
                        </td>
                        <td>
                          <div className="amount-cell" style={{ justifyContent: 'flex-end' }}>
                            <select
                              className="cell-sign"
                              value={editData.sign}
                              disabled={saving}
                              onChange={e => setEditData(d => d ? { ...d, sign: e.target.value as '-' | '+' } : d)}
                            >
                              <option value="-">{t.previewSignExpense}</option>
                              <option value="+">{t.previewSignIncome}</option>
                            </select>
                            <input
                              type="number"
                              className="td-edit-input"
                              style={{ color: amountColor, textAlign: 'right', width: 90 }}
                              value={editData.absAmount}
                              min="0"
                              step="0.01"
                              disabled={saving}
                              onChange={e => setEditData(d => d ? { ...d, absAmount: e.target.value } : d)}
                              onKeyDown={e => { if (e.key === 'Enter') commitEdit(tx); if (e.key === 'Escape') cancelEdit() }}
                            />
                          </div>
                          {saveError && (
                            <div className="save-error">{saveError}</div>
                          )}
                        </td>
                        <td>
                          <div className="td-actions">
                            <button
                              className="btn-row-icon btn-row-save"
                              onClick={() => commitEdit(tx)}
                              disabled={saving}
                              title={t.tableSaveRow}
                            >✓</button>
                            <button
                              className="btn-row-icon btn-row-cancel"
                              onClick={cancelEdit}
                              disabled={saving}
                              title={t.tableCancelEdit}
                            >✕</button>
                          </div>
                        </td>
                      </tr>
                    )
                  }

                  return (
                    <tr key={tx.id}>
                      <td className="td-date">{formatDate(tx.transaction_date, lang)}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{tx.account}</td>
                      <td title={tx.description}>
                        <div className="td-desc">{tx.description}</div>
                      </td>
                      <td className="td-merchant">{tx.merchant ?? ''}</td>
                      <td><span
                        className="badge"
                        style={categoryColorMap[tx.category] ? {
                          background: categoryColorMap[tx.category] + '22',
                          color: categoryColorMap[tx.category],
                          borderColor: categoryColorMap[tx.category] + '66',
                        } : undefined}
                      >{categoryLabel(tx.category, lang, dynamicEs)}</span></td>
                      <td className="td-tags">
                        {tx.tags.length > 0 && (
                          <div className="tag-chips-readonly">
                            {tx.tags.map(tag => {
                              const info = tagInfoMap[tag]
                              const color = info?.color ?? DEFAULT_TAG_COLOR
                              const textC = tagTextColor(color)
                              return (
                                <span key={tag} className="tag-chip tag-chip-sm" style={{ background: color, color: textC, borderColor: color + '88' }}>
                                  {info?.emoji ? `${info.emoji} ` : ''}{tag}
                                </span>
                              )
                            })}
                          </div>
                        )}
                      </td>
                      <td className={`td-amount ${tx.amount < 0 ? 'neg' : 'pos'}`}>
                        {formatCurrency(tx.amount)}
                      </td>
                      <td>
                        <div className="td-actions">
                          <button
                            className="btn-row-icon btn-row-edit"
                            onClick={() => startEdit(tx)}
                            title={t.tableEditRow}
                          >✎</button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <span>{data.total > 0 ? t.tablePaginationInfo(start, end, data.total) : '0'}</span>
            <button onClick={() => setPage(p => p - 1)} disabled={page === 0}>
              {t.tablePrev}
            </button>
            <button onClick={() => setPage(p => p + 1)} disabled={page >= totalPages - 1}>
              {t.tableNext}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
