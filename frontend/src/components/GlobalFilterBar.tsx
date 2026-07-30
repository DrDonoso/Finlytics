import type { Account, Category, Tag, GlobalFilters } from '../api/types'
import { useT, categoryLabel, DEFAULT_TAG_COLOR, tagTextColor, formatDate } from '../i18n'
import { useMemo } from 'react'
import TagFilterSelect from './TagFilterSelect'
import DatePicker from './DatePicker'
import { defaultRange } from '../utils'
import { IconClose, IconTag, IconArrowUp, IconArrowDown } from './icons'

interface Props {
  filters: GlobalFilters
  accounts: Account[]
  categories: Category[]
  tags: Tag[]
  onChange: (f: GlobalFilters) => void
  onClear?: () => void
}

export default function GlobalFilterBar({ filters, accounts, categories, tags, onChange, onClear }: Props) {
  const { t, lang } = useT()

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  function set(patch: Partial<GlobalFilters>) {
    onChange({ ...filters, ...patch })
  }

  const activeCategoryName = filters.category_id !== undefined
    ? categories.find(c => c.id === filters.category_id)?.name
    : undefined

  // Show chips/clear row when any filter is active
  const def = defaultRange()
  const dateChanged = filters.from !== def.from || filters.to !== def.to
  const hasClearable = activeCategoryName !== undefined
    || filters.tags.length > 0
    || filters.flow !== undefined
    || filters.account_id !== undefined
    || filters.merchant !== undefined
    || filters.day !== undefined
    || dateChanged

  return (
    <div className="filter-bar">
      <div className="date-range-wrap">
        <div className="filter-group">
          <label>{t.filterFrom}</label>
          <DatePicker
            value={filters.from}
            onChange={v => set({ from: v })}
            ariaLabel={t.filterFrom}
          />
        </div>
        <span className="date-range-sep" aria-hidden="true">—</span>
        <div className="filter-group">
          <label>{t.filterTo}</label>
          <DatePicker
            value={filters.to}
            onChange={v => set({ to: v })}
            ariaLabel={t.filterTo}
          />
        </div>
      </div>

      <div className="filter-group">
        <label>{t.filterAccount}</label>
        <select
          value={filters.account_id ?? ''}
          onChange={e =>
            set({ account_id: e.target.value ? Number(e.target.value) : undefined })
          }
        >
          <option value="">{t.filterAllAccounts}</option>
          {accounts.map(a => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>

      {tags.length > 0 && (
        <div className="filter-group">
          <label>{t.filterTag}</label>
          <TagFilterSelect
            availableTags={tags}
            selected={filters.tags}
            onChange={next => set({ tags: next })}
          />
        </div>
      )}

      {hasClearable && (
        <div className="filter-chips">
          {filters.flow !== undefined && (
            <span className="filter-chip filter-chip-flow">
              {filters.flow === 'expense'
                ? <><IconArrowDown size={13} />{t.filterExpenseOnly}</>
                : <><IconArrowUp size={13} />{t.filterIncomeOnly}</>}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => set({ flow: undefined })}
                aria-label={t.filterClearChip}
              ><IconClose size={13} /></button>
            </span>
          )}
          {activeCategoryName !== undefined && (
            <span className="filter-chip">
              {categoryLabel(activeCategoryName, lang, dynamicEs)}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => set({ category_id: undefined })}
                aria-label={t.filterClearChip}
              ><IconClose size={13} /></button>
            </span>
          )}
          {filters.merchant !== undefined && (
            <span className="filter-chip">
              {t.filterChipMerchant}: {filters.merchant}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => set({ merchant: undefined })}
                aria-label={t.filterClearChip}
              ><IconClose size={13} /></button>
            </span>
          )}
          {filters.day !== undefined && (
            <span className="filter-chip">
              {t.filterChipDay}: {formatDate(filters.day, lang)}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => set({ day: undefined })}
                aria-label={t.filterClearChip}
              ><IconClose size={13} /></button>
            </span>
          )}
          {filters.tags.map(tagName => {
            const tag = tags.find(tg => tg.name === tagName)
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
                  onClick={() => set({ tags: filters.tags.filter(n => n !== tagName) })}
                  aria-label={t.filterClearChip}
                  style={{ color: textC }}
                ><IconClose size={13} /></button>
              </span>
            )
          })}
          {onClear && (
            <button type="button" className="btn-clear-filters" onClick={onClear}>
              {t.filterClear}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
