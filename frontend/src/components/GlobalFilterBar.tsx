import type { Account, Category, Tag, GlobalFilters } from '../api/types'
import { useT, categoryLabel, DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import { useMemo } from 'react'

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
  const hasClearable = activeCategoryName !== undefined
    || filters.tags.length > 0
    || filters.flow !== undefined
    || filters.account_id !== undefined

  return (
    <div className="filter-bar">
      <div className="filter-group">
        <label>{t.filterFrom}</label>
        <input
          type="date"
          className="date-input-native"
          value={filters.from}
          onChange={e => set({ from: e.target.value })}
        />
      </div>

      <div className="filter-group">
        <label>{t.filterTo}</label>
        <input
          type="date"
          className="date-input-native"
          value={filters.to}
          onChange={e => set({ to: e.target.value })}
        />
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
          <div className="tag-multi-select">
            {tags.map(tag => {
              const selected = filters.tags.includes(tag.name)
              const color = tag.color || DEFAULT_TAG_COLOR
              return (
                <button
                  key={tag.id}
                  type="button"
                  className="tag-toggle-btn"
                  style={selected
                    ? { background: color, borderColor: color, color: tagTextColor(color) }
                    : { background: 'transparent', borderColor: color, color: color }
                  }
                  onClick={() => {
                    const newTags = selected
                      ? filters.tags.filter(n => n !== tag.name)
                      : [...filters.tags, tag.name]
                    set({ tags: newTags })
                  }}
                >
                  {tag.emoji ? `${tag.emoji} ` : ''}{tag.name}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {hasClearable && (
        <div className="filter-chips">
          {filters.flow !== undefined && (
            <span className="filter-chip filter-chip-flow">
              {filters.flow === 'expense' ? `💸 ${t.filterExpenseOnly}` : `💰 ${t.filterIncomeOnly}`}
              <button
                type="button"
                className="filter-chip-remove"
                onClick={() => set({ flow: undefined })}
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
                onClick={() => set({ category_id: undefined })}
                aria-label={t.filterClearChip}
              >✕</button>
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
                {tag?.emoji ? `${tag.emoji} ` : '🏷 '}{tagName}
                <button
                  type="button"
                  className="filter-chip-remove"
                  onClick={() => set({ tags: filters.tags.filter(n => n !== tagName) })}
                  aria-label={t.filterClearChip}
                  style={{ color: textC }}
                >✕</button>
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
