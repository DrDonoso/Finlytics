import { useId, useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { SummaryParams } from '../api/types'
import { useAccounts, useCategories, useTags, useOverview, queryKeys } from '../api/queries'
import { errorMessage } from '../api/errors'
import { useT, categoryLabel, formatDate, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import TransactionsTable from '../components/TransactionsTable'
import TagFilterSelect from '../components/TagFilterSelect'
import DatePicker from '../components/DatePicker'
import { IconArrowDown, IconArrowUp, IconClose, IconTag } from '../components/icons'
import { useDebouncedFilter, useUrlFilters } from '../hooks/useUrlFilters'
import type { DateRange } from '../utils'

// The full ledger opens unfiltered; the period is whatever the link or the user sets.
function openRange(): DateRange {
  return { from: '', to: '' }
}

export default function TransactionsPage() {
  const { t, lang, formatCurrency } = useT()
  const queryClient = useQueryClient()
  const { filters, setFilters } = useUrlFilters(openRange)

  const EMPTY: never[] = useMemo(() => [], [])
  const accounts   = useAccounts().data   ?? EMPTY
  const categories = useCategories().data ?? EMPTY
  const allTags    = useTags().data       ?? EMPTY

  const [panelOpen, setPanelOpen] = useState(false)
  const uid = useId()
  const ids = {
    panel:     `${uid}-panel`,
    from:      `${uid}-from`,
    to:        `${uid}-to`,
    account:   `${uid}-account`,
    category:  `${uid}-category`,
    tags:      `${uid}-tags`,
    amountMin: `${uid}-amount-min`,
    amountMax: `${uid}-amount-max`,
    merchant:  `${uid}-merchant`,
  }

  // Text boxes answer every keystroke; the URL follows 300 ms after the last one.
  const [descRaw,      setDescRaw]      = useDebouncedFilter(filters, setFilters, 'description')
  const [merchantRaw,  setMerchantRaw]  = useDebouncedFilter(filters, setFilters, 'merchant')
  const [amountMinRaw, setAmountMinRaw] = useDebouncedFilter(filters, setFilters, 'amount_min')
  const [amountMaxRaw, setAmountMaxRaw] = useDebouncedFilter(filters, setFilters, 'amount_max')

  // Overview / totals — the query key includes the filters, which prevents out-of-order responses
  const overviewParams: SummaryParams = useMemo(() => ({
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
    day:         filters.day,
  }), [filters])
  const overviewQuery = useOverview(overviewParams)
  const overview = overviewQuery.data ?? null
  const overviewLoading = overviewQuery.isPending
  const overviewError = overviewQuery.error ? errorMessage(overviewQuery.error, t) : null

  function clearFilters() {
    setFilters({ from: '', to: '', tags: [] })
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

  // Active filters other than the search box, which is always visible anyway
  const activeFilterCount = (filters.from ? 1 : 0)
    + (filters.to ? 1 : 0)
    + (filters.account_id !== undefined ? 1 : 0)
    + (filters.category_id !== undefined ? 1 : 0)
    + filters.tags.length
    + (filters.amount_min !== undefined ? 1 : 0)
    + (filters.amount_max !== undefined ? 1 : 0)
    + (filters.merchant !== undefined ? 1 : 0)
    + (filters.flow !== undefined ? 1 : 0)
    + (filters.day !== undefined ? 1 : 0)

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
            aria-label={t.filterDescription}
            onChange={e => setDescRaw(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="tx-filters-btn"
          onClick={() => setPanelOpen(o => !o)}
          aria-expanded={panelOpen}
          aria-controls={ids.panel}
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
        <div className="tx-filter-panel" id={ids.panel}>
          <div className="date-range-wrap">
            <div className="filter-group">
              <label htmlFor={ids.from}>{t.filterFrom}</label>
              <DatePicker
                id={ids.from}
                value={filters.from}
                onChange={v => setFilters(f => ({ ...f, from: v }))}
                ariaLabel={t.filterFrom}
              />
            </div>
            <span className="date-range-sep" aria-hidden="true">—</span>
            <div className="filter-group">
              <label htmlFor={ids.to}>{t.filterTo}</label>
              <DatePicker
                id={ids.to}
                value={filters.to}
                onChange={v => setFilters(f => ({ ...f, to: v }))}
                ariaLabel={t.filterTo}
              />
            </div>
          </div>

          <div className="filter-group">
            <label htmlFor={ids.account}>{t.filterAccount}</label>
            <select
              id={ids.account}
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
            <label htmlFor={ids.category}>{t.filterCategory}</label>
            <select
              id={ids.category}
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
              <label id={ids.tags}>{t.filterTag}</label>
              <TagFilterSelect
                availableTags={allTags}
                selected={filters.tags}
                onChange={next => setFilters(f => ({ ...f, tags: next }))}
                labelledBy={ids.tags}
              />
            </div>
          )}

          <div className="filter-group">
            <label htmlFor={ids.amountMin}>{t.filterAmountMin}</label>
            <input
              id={ids.amountMin}
              type="number"
              min="0"
              step="0.01"
              value={amountMinRaw}
              placeholder="0"
              onChange={e => setAmountMinRaw(e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label htmlFor={ids.amountMax}>{t.filterAmountMax}</label>
            <input
              id={ids.amountMax}
              type="number"
              min="0"
              step="0.01"
              value={amountMaxRaw}
              placeholder="∞"
              onChange={e => setAmountMaxRaw(e.target.value)}
            />
          </div>

          <div className="filter-group">
            <label htmlFor={ids.merchant}>{t.filterMerchant}</label>
            <input
              id={ids.merchant}
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
          {filters.from !== '' && (
            <FilterChip
              label={`${t.filterFrom}: ${formatDate(filters.from, lang)}`}
              onRemove={() => setFilters(f => ({ ...f, from: '' }))}
            />
          )}
          {filters.to !== '' && (
            <FilterChip
              label={`${t.filterTo}: ${formatDate(filters.to, lang)}`}
              onRemove={() => setFilters(f => ({ ...f, to: '' }))}
            />
          )}
          {filters.day !== undefined && (
            <FilterChip
              label={`${t.filterChipDay}: ${formatDate(filters.day, lang)}`}
              onRemove={() => setFilters(f => ({ ...f, day: undefined }))}
            />
          )}
          {filters.flow !== undefined && (
            <FilterChip
              className="filter-chip-flow"
              icon={filters.flow === 'expense' ? <IconArrowDown size={13} /> : <IconArrowUp size={13} />}
              label={filters.flow === 'expense' ? t.filterExpenseOnly : t.filterIncomeOnly}
              onRemove={() => setFilters(f => ({ ...f, flow: undefined }))}
            />
          )}
          {activeAccountName !== undefined && (
            <FilterChip
              label={activeAccountName}
              onRemove={() => setFilters(f => ({ ...f, account_id: undefined }))}
            />
          )}
          {activeCategoryName !== undefined && (
            <FilterChip
              label={categoryLabel(activeCategoryName, lang, dynamicEs)}
              onRemove={() => setFilters(f => ({ ...f, category_id: undefined }))}
            />
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
                {tag?.emoji ? `${tag.emoji} ` : <IconTag size={13} />}{tagName}
                <button
                  type="button"
                  className="filter-chip-remove"
                  onClick={() => setFilters(f => ({ ...f, tags: f.tags.filter(n => n !== tagName) }))}
                  aria-label={t.tagChipRemoveNamed(tagName)}
                  style={{ color: textC }}
                ><IconClose size={13} /></button>
              </span>
            )
          })}
          {filters.amount_min !== undefined && (
            <FilterChip
              label={`${t.filterAmountMin}: ${filters.amount_min}`}
              onRemove={() => setFilters(f => ({ ...f, amount_min: undefined }))}
            />
          )}
          {filters.amount_max !== undefined && (
            <FilterChip
              label={`${t.filterAmountMax}: ${filters.amount_max}`}
              onRemove={() => setFilters(f => ({ ...f, amount_max: undefined }))}
            />
          )}
          {filters.merchant !== undefined && (
            <FilterChip
              label={`${t.filterMerchant}: ${filters.merchant}`}
              onRemove={() => setFilters(f => ({ ...f, merchant: undefined }))}
            />
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
              <span className="tx-total-value private">{formatCurrency(overview.total_income)}</span>
            </div>
            <div className="tx-total tx-total--expense">
              <span className="tx-total-label">{t.kpiTotalExpense}</span>
              <span className="tx-total-value private">{formatCurrency(overview.total_expense)}</span>
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
        onEditSuccess={() => queryClient.invalidateQueries({ queryKey: queryKeys.overview(overviewParams) })}
      />
    </main>
  )
}

function FilterChip({ label, onRemove, icon, className }: {
  label: string
  onRemove: () => void
  icon?: ReactNode
  className?: string
}) {
  const { t } = useT()
  return (
    <span className={className ? `filter-chip ${className}` : 'filter-chip'}>
      {icon}{label}
      <button
        type="button"
        className="filter-chip-remove"
        onClick={onRemove}
        aria-label={t.tagChipRemoveNamed(label)}
      ><IconClose size={13} /></button>
    </span>
  )
}
