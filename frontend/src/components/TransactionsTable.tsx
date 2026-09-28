import { useState, useEffect, useMemo, useId } from 'react'
import type { ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Category, GlobalFilters, Tag, Transaction, TransactionPage, TransactionsParams } from '../api/types'
import { updateTransaction } from '../api/client'
import { queryKeys, useTransactions } from '../api/queries'
import { useT, categoryLabel, formatDate, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import CategorySelect from './CategorySelect'
import TagEditor from './TagEditor'
import RuleFormModal from './RuleFormModal'
import TransactionDetailModal from './TransactionDetailModal'
import CardHeader from './CardHeader'
import CategoryBadge from './CategoryBadge'
import { useIsMobile } from '../hooks/useIsMobile'
import { IconAlert, IconReceipt, IconCheck, IconClose, IconSettings, IconPencil, IconArrowLeft, IconArrowRight } from './icons'
import SortableTh from './SortableTh'

interface Props {
  globalFilters: GlobalFilters
  categories: Category[]
  allTags: Tag[]
  pageSize?: number
  description?: string
  amountMin?: number
  amountMax?: number
  merchant?: string
  hideInternalFilters?: boolean
  onEditSuccess?: () => void
  headerAction?: ReactNode
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

export default function TransactionsTable({ globalFilters, categories, allTags, pageSize, description, amountMin, amountMax, merchant, hideInternalFilters, onEditSuccess, headerAction }: Props) {
  const { t, lang, formatCurrency } = useT()
  const queryClient = useQueryClient()
  const limit = pageSize ?? LIMIT
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined)
  const [sortCol,   setSortCol]   = useState<string>('date')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  const [editingId,  setEditingId]  = useState<number | null>(null)
  const [editData,   setEditData]   = useState<EditData | null>(null)
  const [saving,     setSaving]     = useState(false)
  const [saveError,  setSaveError]  = useState<string | null>(null)

  const [createRuleFor, setCreateRuleFor] = useState<Transaction | null>(null)
  const [ruleToast,     setRuleToast]     = useState<string | null>(null)
  const [detailTx,      setDetailTx]      = useState<Transaction | null>(null)
  const isMobile = useIsMobile()
  const categoryFilterId = useId()

  useEffect(() => {
    if (!ruleToast) return
    const id = setTimeout(() => setRuleToast(null), 4000)
    return () => clearTimeout(id)
  }, [ruleToast])

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

  const filters: TransactionsParams = {
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
    day:         globalFilters.day || undefined,
    limit:       limit,
    sort:        sortCol,
    order:       sortOrder,
  }
  // New filters always start on the first page. Deriving that during render,
  // rather than resetting the page in an effect, avoids first fetching the new
  // filters at the old offset.
  const filtersKey = JSON.stringify(filters)
  const [paging, setPaging] = useState({ filtersKey, page: 0 })
  const page = paging.filtersKey === filtersKey ? paging.page : 0
  function goToPage(next: number) {
    setPaging({ filtersKey, page: next })
  }

  const params: TransactionsParams = { ...filters, offset: page * limit }
  const { data, isPending: loading, isPlaceholderData, error: queryError } = useTransactions(params)
  const error = queryError ? String(queryError) : null

  // Patches the row in place instead of refetching: an edit that moves the row
  // out of the current filter must not make it vanish under the cursor.
  function replaceRow(updated: Transaction) {
    queryClient.setQueryData<TransactionPage>(queryKeys.transactions(params), current =>
      current && { ...current, items: current.items.map(item => (item.id === updated.id ? updated : item)) },
    )
    void queryClient.invalidateQueries({ queryKey: queryKeys.transactionsAll, refetchType: 'none' })
  }

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
      replaceRow(updated)
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

  function sortableHeader(col: string, label: string, className?: string) {
    return (
      <SortableTh
        label={label}
        active={col === sortCol}
        direction={sortOrder}
        onSort={() => handleSort(col)}
        className={className}
      />
    )
  }

  return (
    <>
      <div className="card">
      <CardHeader title={t.tableTitle} action={headerAction} />

      {!hideInternalFilters && (
        <div className="table-filters">
          <div className="filter-group">
            <label htmlFor={categoryFilterId}>{t.tableFilterCategory}</label>
            <select
              id={categoryFilterId}
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
          <IconAlert size={18} />
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
          <IconReceipt size={18} />
          <span>{t.tableNoData}</span>
        </div>
      )}

      {!error && !loading && data && data.items.length > 0 && (
        <>
          <div className="table-wrapper" aria-busy={isPlaceholderData} style={isPlaceholderData ? { opacity: 0.6 } : undefined}>
            <table className="tx-table">
              <thead>
                <tr>
                  {sortableHeader('date', t.tableColDate)}
                  {sortableHeader('account', t.tableColAccount)}
                  {sortableHeader('description', t.tableColDesc)}
                  {sortableHeader('merchant', t.colMerchant, 'th-merchant')}
                  {sortableHeader('category', t.tableColCategory)}
                  <th>{t.tableColTags}</th>
                  {sortableHeader('amount', t.tableColAmount, 'th-amount')}
                  <th><span className="sr-only">{t.tableColActions}</span></th>
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
                        <td className="td-account">{tx.account}</td>
                        <td>
                          <input
                            type="text"
                            className="td-edit-input"
                            aria-label={t.tableColDesc}
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
                            aria-label={t.colMerchant}
                            value={editData.merchant}
                            disabled={saving}
                            placeholder={t.colMerchant}
                            onChange={e => setEditData(d => d ? { ...d, merchant: e.target.value } : d)}
                            onKeyDown={e => { if (e.key === 'Enter') commitEdit(tx); if (e.key === 'Escape') cancelEdit() }}
                          />
                        </td>
                        <td>
                          <CategorySelect
                            ariaLabel={t.tableColCategory}
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
                              aria-label={t.txDetailSignLabel}
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
                              aria-label={t.tableColAmount}
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
                            ><IconCheck size={15} /></button>
                            <button
                              className="btn-row-icon btn-row-cancel"
                              onClick={cancelEdit}
                              disabled={saving}
                              title={t.tableCancelEdit}
                            ><IconClose size={15} /></button>
                          </div>
                        </td>
                      </tr>
                    )
                  }

                  return (
                    <tr
                      key={tx.id}
                      className={isMobile ? 'tr-mobile-tappable' : undefined}
                      onClick={() => { if (isMobile) setDetailTx(tx) }}
                    >
                      <td className="td-date">{formatDate(tx.transaction_date, lang)}</td>
                      <td className="td-account">{tx.account}</td>
                      <td className="td-description" title={tx.description}>
                        <div className="td-desc">{tx.description}</div>
                        {tx.is_system && (
                          <span className="tx-system-badge" title={t.systemTxBadgeTooltip}>
                            {t.systemTxBadge}
                          </span>
                        )}
                        {tx.detail && (
                          <div className="tx-detail-subline">{tx.detail}</div>
                        )}
                      </td>
                      <td className="td-merchant">{tx.merchant ?? ''}</td>
                      <td className="td-category">
                        <CategoryBadge label={categoryLabel(tx.category, lang, dynamicEs)} color={categoryColorMap[tx.category]} />
                      </td>
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
                      <td className={`td-amount private ${tx.amount < 0 ? 'neg' : 'pos'}`}>
                        {formatCurrency(tx.amount)}
                      </td>
                      <td className="td-row-actions">
                        <div className="td-actions">
                          <button
                            className="btn-row-icon btn-create-rule"
                            onClick={e => { e.stopPropagation(); setCreateRuleFor(tx) }}
                            title={t.createRuleBtn}
                            aria-label={t.createRuleBtn}
                          ><IconSettings size={15} /></button>
                          <button
                            className="btn-row-icon btn-row-edit"
                            onClick={e => {
                              e.stopPropagation()
                              // A card has no room for the inline editor; the detail sheet edits the same fields.
                              if (isMobile) setDetailTx(tx)
                              else startEdit(tx)
                            }}
                            title={t.tableEditRow}
                            aria-label={t.tableEditRow}
                          ><IconPencil size={15} /></button>
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
            <button onClick={() => goToPage(page - 1)} disabled={page === 0}>
              <IconArrowLeft size={14} /> {t.tablePrev}
            </button>
            <button onClick={() => goToPage(page + 1)} disabled={page >= totalPages - 1}>
              {t.tableNext} <IconArrowRight size={14} />
            </button>
          </div>
        </>
      )}
    </div>

      {createRuleFor && (
        <RuleFormModal
          initialValues={{
            description_mode:  'contains',
            description_value: createRuleFor.description,
            set_category:      createRuleFor.category,
            set_merchant:      createRuleFor.merchant,
            add_tags:          createRuleFor.tags,
          }}
          categories={categories}
          availableTags={allTags}
          onSave={() => { setCreateRuleFor(null); setRuleToast(t.createRuleToast) }}
          onClose={() => setCreateRuleFor(null)}
        />
      )}

      {ruleToast && <div className="rule-toast">{ruleToast}</div>}

      {detailTx && (
        <TransactionDetailModal
          key={detailTx.id}
          tx={detailTx}
          sortedBaseCategories={sortedBaseCategories}
          dbExtraCategories={dbExtraCategories}
          allTags={allTags}
          categoryColorMap={categoryColorMap}
          dynamicEs={dynamicEs}
          onClose={() => setDetailTx(null)}
          onSaved={updated => {
            replaceRow(updated)
            setDetailTx(null)
            onEditSuccess?.()
          }}
        />
      )}
    </>
  )
}
