import { useState, useEffect, useMemo } from 'react'
import type { Account, Category, Tag, Overview, TransactionsViewFilters } from '../api/types'
import { getAccounts, getCategories, getTags, getOverview } from '../api/client'
import { useT, categoryLabel, formatDate, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import TransactionsTable from '../components/TransactionsTable'
import TagFilterSelect from '../components/TagFilterSelect'

const DEFAULT_FILTERS: TransactionsViewFilters = {
  from: '',
  to:   '',
  tags: [],
}

export default function TransactionsPage() {
  const { t, lang, formatCurrency } = useT()

  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [panelOpen, setPanelOpen] = useState(false)

  // Committed filter state (sent to API)
  const [filters, setFilters] = useState<TransactionsViewFilters>(DEFAULT_FILTERS)

  // Raw input values for debounced controls
  const [descRaw,      setDescRaw]      = useState('')
  const [amountMinRaw, setAmountMinRaw] = useState('')
  const [amountMaxRaw, setAmountMaxRaw] = useState('')
  const [merchantRaw,  setMerchantRaw]  = useState('')

  // Overview / totals
  const [overview,        setOverview]        = useState<Overview | null>(null)
  const [overviewLoading, setOverviewLoading] = useState(true)
  const [overviewError,   setOverviewError]   = useState<string | null>(null)
  const [overviewRefKey,  setOverviewRefKey]  = useState(0)

  // Load reference data once
  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
  }, [])

  // Debounce description → 300 ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters(f => ({ ...f, description: descRaw.trim() || undefined }))
    }, 300)
    return () => clearTimeout(timer)
  }, [descRaw])

  // Debounce amount_min → 300 ms
  useEffect(() => {
    const timer = setTimeout(() => {
      const v = parseFloat(amountMinRaw)
      setFilters(f => ({ ...f, amount_min: amountMinRaw !== '' && v >= 0 ? v : undefined }))
    }, 300)
    return () => clearTimeout(timer)
  }, [amountMinRaw])

  // Debounce amount_max → 300 ms
  useEffect(() => {
    const timer = setTimeout(() => {
      const v = parseFloat(amountMaxRaw)
      setFilters(f => ({ ...f, amount_max: amountMaxRaw !== '' && v >= 0 ? v : undefined }))
    }, 300)
    return () => clearTimeout(timer)
  }, [amountMaxRaw])

  // Debounce merchant → 300 ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters(f => ({ ...f, merchant: merchantRaw.trim() || undefined }))
    }, 300)
    return () => clearTimeout(timer)
  }, [merchantRaw])

  // Fetch overview whenever filters or overviewRefKey change
  useEffect(() => {
    let cancelled = false
    setOverviewLoading(true)
    setOverviewError(null)
    getOverview({
      from:        filters.from || undefined,
      to:          filters.to   || undefined,
      account_id:  filters.account_id,
      category_id: filters.category_id,
      tags:        filters.tags.length > 0 ? filters.tags : undefined,
      flow:        filters.flow,
      description: filters.description,
      amount_min:  filters.amount_min,
      amount_max:  filters.amount_max,
      merchant:    filters.merchant,
    })
      .then(d  => { if (!cancelled) { setOverview(d);        setOverviewLoading(false) } })
      .catch(e => { if (!cancelled) { setOverviewError(String(e)); setOverviewLoading(false) } })
    return () => { cancelled = true }
  }, [filters, overviewRefKey])

  function clearFilters() {
    setFilters({ from: '', to: '', tags: [] })
    setDescRaw('')
    setAmountMinRaw('')
    setAmountMaxRaw('')
    setMerchantRaw('')
  }

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const sortedCategories = useMemo(() =>
    [...categories].sort((a, b) =>
      categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs))
    ),
    [categories, lang, dynamicEs],
  )

  // Count of active non-search panel filters (differs from default or is explicitly set)
  const activeFilterCount = useMemo(() => {
    let count = 0
    if (filters.from !== DEFAULT_FILTERS.from) count++
    if (filters.to !== DEFAULT_FILTERS.to) count++
    if (filters.account_id !== undefined) count++
    if (filters.category_id !== undefined) count++
    count += filters.tags.length
    if (filters.amount_min !== undefined) count++
    if (filters.amount_max !== undefined) count++
    if (filters.merchant !== undefined) count++
    return count
  }, [filters])

  const activeAccountName  = accounts.find(a => a.id === filters.account_id)?.name
  const activeCategoryName = categories.find(c => c.id === filters.category_id)?.name

  return (
    <main className="tx-page">
      <div className="tx-page-header">
        <h1 className="tx-page-title">{t.txTitle}</h1>
      </div>

      {/* ── Toolbar: search + filters toggle ─────────────────── */}
      <div className="tx-toolbar">
        <div className="tx-search">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            value={descRaw}
            placeholder={t.searchPlaceholder}
            onChange={e => setDescRaw(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="tx-filters-btn"
          onClick={() => setPanelOpen(o => !o)}
          aria-expanded={panelOpen}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
          {t.btnFilters}
          {activeFilterCount > 0 && (
            <span className="tx-filters-btn__badge">{activeFilterCount}</span>
          )}
        </button>
      </div>

      {/* ── Filter panel (collapsible) ────────────────────────── */}
      {panelOpen && (
        <div className="tx-filter-panel">
          <div className="date-range-wrap">
            <div className="filter-group">
              <label>{t.filterFrom}</label>
              <input
                type="date"
                className="date-input-native"
                value={filters.from}
                onChange={e => setFilters(f => ({ ...f, from: e.target.value }))}
              />
            </div>
            <span className="date-range-sep" aria-hidden="true">—</span>
            <div className="filter-group">
              <label>{t.filterTo}</label>
              <input
                type="date"
                className="date-input-native"
                value={filters.to}
                onChange={e => setFilters(f => ({ ...f, to: e.target.value }))}
              />
            </div>
          </div>

          <div className="filter-group">
            <label>{t.filterAccount}</label>
            <select
              value={filters.account_id ?? ''}
              onChange={e => setFilters(f => ({
                ...f,
                account_id: e.target.value ? Number(e.target.value) : undefined,
              }))}
            >
              <option value="">{t.filterAllAccounts}</option>
              {accounts.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          <div className="filter-group">
            <label>{t.filterCategory}</label>
            <select
              value={filters.category_id ?? ''}
              onChange={e => setFilters(f => ({
                ...f,
                category_id: e.target.value ? Number(e.target.value) : undefined,
              }))}
            >
              <option value="">{t.filterAllCategories}</option>
              {sortedCategories.map(c => (
                <option key={c.id} value={c.id}>{categoryLabel(c.name, lang, dynamicEs)}</option>
              ))}
            </select>
          </div>

          {allTags.length > 0 && (
            <div className="filter-group">
              <label>{t.filterTag}</label>
              <TagFilterSelect
                availableTags={allTags}
                selected={filters.tags}
                onChange={next => setFilters(f => ({ ...f, tags: next }))}
              />
            </div>
          )}

          <div className="filter-group">
            <label>{t.filterAmountMin}</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amountMinRaw}
              placeholder="0"
              onChange={e => setAmountMinRaw(e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label>{t.filterAmountMax}</label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amountMaxRaw}
              placeholder="∞"
              onChange={e => setAmountMaxRaw(e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label>{t.filterMerchant}</label>
            <input
              type="text"
              value={merchantRaw}
              placeholder={t.filterMerchant}
              onChange={e => setMerchantRaw(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* ── Active filter chips ───────────────────────────────── */}
      {activeFilterCount > 0 && (
        <div className="tx-chips">
          {filters.from !== DEFAULT_FILTERS.from && (
            <span className="filter-chip">
              {t.filterFrom}: {formatDate(filters.from, lang)}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => setFilters(f => ({ ...f, from: DEFAULT_FILTERS.from }))}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {filters.to !== DEFAULT_FILTERS.to && (
            <span className="filter-chip">
              {t.filterTo}: {formatDate(filters.to, lang)}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => setFilters(f => ({ ...f, to: DEFAULT_FILTERS.to }))}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {activeAccountName !== undefined && (
            <span className="filter-chip">
              {activeAccountName}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => setFilters(f => ({ ...f, account_id: undefined }))}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {activeCategoryName !== undefined && (
            <span className="filter-chip">
              {categoryLabel(activeCategoryName, lang, dynamicEs)}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => setFilters(f => ({ ...f, category_id: undefined }))}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {filters.tags.map(tagName => {
            const tag = allTags.find(tg => tg.name === tagName)
            const color = tag?.color || DEFAULT_TAG_COLOR
            const textC = tagTextColor(color)
            return (
              <span
                key={tagName}
                className="filter-chip filter-chip-tag"
                style={{ background: color, color: textC, borderColor: color }}
              >
                {tag?.emoji ? `${tag.emoji} ` : '🏷 '}{tagName}
                <button
                  type="button"
                  className="filter-chip-remove"
                  onClick={() => setFilters(f => ({ ...f, tags: f.tags.filter(n => n !== tagName) }))}
                  aria-label={t.filterClearChip}
                  style={{ color: textC }}
                >✕</button>
              </span>
            )
          })}
          {filters.amount_min !== undefined && (
            <span className="filter-chip">
              {t.filterAmountMin}: {filters.amount_min}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => { setAmountMinRaw(''); setFilters(f => ({ ...f, amount_min: undefined })) }}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {filters.amount_max !== undefined && (
            <span className="filter-chip">
              {t.filterAmountMax}: {filters.amount_max}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => { setAmountMaxRaw(''); setFilters(f => ({ ...f, amount_max: undefined })) }}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          {filters.merchant !== undefined && (
            <span className="filter-chip">
              {t.filterMerchant}: {filters.merchant}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => { setMerchantRaw(''); setFilters(f => ({ ...f, merchant: undefined })) }}
                aria-label={t.filterClearChip}
              >✕</button>
            </span>
          )}
          <button type="button" className="btn-secondary" onClick={clearFilters}>
            {t.filterClear}
          </button>
        </div>
      )}

      {/* ── Totals panel ──────────────────────────────────── */}
      <div className="tx-totals">
        {overviewLoading ? (
          [0, 1].map(i => (
            <div key={i} className="tx-total">
              <div className="skeleton" style={{ width: 80, height: 13, marginBottom: 6 }} />
              <div className="skeleton" style={{ width: 110, height: 26 }} />
            </div>
          ))
        ) : overviewError ? (
          <div className="tx-total" style={{ color: 'var(--expense)', fontSize: 13 }}>
            {t.kpiErrorLoading}{overviewError}
          </div>
        ) : overview ? (
          <>
            <div className="tx-total tx-total--income">
              <span className="tx-total-label">{t.kpiTotalIncome}</span>
              <span className="tx-total-value">{formatCurrency(overview.total_income)}</span>
            </div>
            <div className="tx-total tx-total--expense">
              <span className="tx-total-label">{t.kpiTotalExpense}</span>
              <span className="tx-total-value">{formatCurrency(overview.total_expense)}</span>
            </div>
          </>
        ) : null}
      </div>

      {/* ── Transactions table (full-page, 25 rows) ───────── */}
      <TransactionsTable
        globalFilters={filters}
        categories={categories}
        allTags={allTags}
        pageSize={25}
        description={filters.description}
        amountMin={filters.amount_min}
        amountMax={filters.amount_max}
        merchant={filters.merchant}
        hideInternalFilters
        onEditSuccess={() => setOverviewRefKey(k => k + 1)}
      />
    </main>
  )
}
