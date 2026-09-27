import type { Account, Category, Tag, GlobalFilters } from '../api/types'
import { useT, categoryLabel, DEFAULT_TAG_COLOR, tagTextColor, formatDate } from '../i18n'
import { useId, useMemo, useState } from 'react'
import TagFilterSelect from './TagFilterSelect'
import DatePicker from './DatePicker'
import { RANGE_PRESETS, matchPreset, presetRange, type DateRange, type RangePreset } from '../utils'
import { IconClose, IconTag, IconArrowUp, IconArrowDown, IconFilter, IconChevronDown } from './icons'

interface Props {
  filters: GlobalFilters
  /** The page's own default period, which "clear" returns to and the active count ignores. */
  defaults: DateRange
  accounts: Account[]
  categories: Category[]
  tags: Tag[]
  onChange: (f: GlobalFilters) => void
  onClear?: () => void
}

const CUSTOM_PERIOD = 'custom'

// Outlives the remount when moving between the pages that share this bar.
let lastPickedPreset: RangePreset | undefined

export default function GlobalFilterBar({ filters, defaults, accounts, categories, tags, onChange, onClear }: Props) {
  const { t, lang } = useT()
  const [open, setOpen] = useState(false)
  const [pickedPreset, setPickedPreset] = useState(lastPickedPreset)
  const uid = useId()
  const ids = {
    body:    `${uid}-body`,
    period:  `${uid}-period`,
    from:    `${uid}-from`,
    to:      `${uid}-to`,
    account: `${uid}-account`,
    tags:    `${uid}-tags`,
  }

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  function set(patch: Partial<GlobalFilters>) {
    onChange({ ...filters, ...patch })
  }

  const presetLabels: Record<RangePreset, string> = {
    thisMonth: t.filterPresetThisMonth,
    lastMonth: t.filterPresetLastMonth,
    '3m':      t.filterPreset3m,
    ytd:       t.filterPresetYtd,
    '12m':     t.filterPreset12m,
    all:       t.filterPresetAll,
  }
  const activePreset = matchPreset(filters, new Date(), pickedPreset)
  const periodSummary = activePreset
    ? presetLabels[activePreset]
    : `${filters.from ? formatDate(filters.from, lang) : '…'} – ${filters.to ? formatDate(filters.to, lang) : '…'}`

  const activeCategoryName = filters.category_id !== undefined
    ? categories.find(c => c.id === filters.category_id)?.name
    : undefined

  const dateChanged = filters.from !== defaults.from || filters.to !== defaults.to
  const activeCount = filters.tags.length
    + (filters.account_id !== undefined ? 1 : 0)
    + (filters.category_id !== undefined ? 1 : 0)
    + (filters.flow !== undefined ? 1 : 0)
    + (filters.merchant !== undefined ? 1 : 0)
    + (filters.day !== undefined ? 1 : 0)
  const hasClearable = activeCount > 0 || dateChanged

  return (
    <div className="filter-bar" data-open={open ? 'true' : undefined}>
      <button
        type="button"
        className="filter-bar-toggle"
        aria-expanded={open}
        aria-controls={ids.body}
        onClick={() => setOpen(o => !o)}
      >
        <IconFilter size={16} />
        <span className="filter-bar-toggle__label">{t.btnFilters}</span>
        <span className="filter-bar-toggle__summary">{periodSummary}</span>
        {activeCount > 0 && (
          <span className="filter-bar-toggle__count">{t.filtersActiveCount(activeCount)}</span>
        )}
        <IconChevronDown size={16} className="filter-bar-toggle__chevron" />
      </button>

      <div className="filter-bar-body" id={ids.body}>
        <div className="filter-group filter-group-period">
          <label htmlFor={ids.period}>{t.filterPresetsLabel}</label>
          <select
            id={ids.period}
            value={activePreset ?? CUSTOM_PERIOD}
            onChange={e => {
              const preset = RANGE_PRESETS.find(p => p === e.target.value)
              if (!preset) return
              lastPickedPreset = preset
              setPickedPreset(preset)
              set({ ...presetRange(preset), day: undefined })
            }}
          >
            {RANGE_PRESETS.map(p => (
              <option key={p} value={p}>{presetLabels[p]}</option>
            ))}
            {!activePreset && <option value={CUSTOM_PERIOD} disabled>{t.filterPresetCustom}</option>}
          </select>
        </div>

        <div className="date-range-wrap">
          <div className="filter-group">
            <label htmlFor={ids.from}>{t.filterFrom}</label>
            <DatePicker
              id={ids.from}
              value={filters.from}
              onChange={v => set({ from: v })}
              ariaLabel={t.filterFrom}
            />
          </div>
          <span className="date-range-sep" aria-hidden="true">—</span>
          <div className="filter-group">
            <label htmlFor={ids.to}>{t.filterTo}</label>
            <DatePicker
              id={ids.to}
              value={filters.to}
              onChange={v => set({ to: v })}
              ariaLabel={t.filterTo}
            />
          </div>
        </div>

        <div className="filter-group">
          <label htmlFor={ids.account}>{t.filterAccount}</label>
          <select
            id={ids.account}
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
            <label id={ids.tags}>{t.filterTag}</label>
            <TagFilterSelect
              availableTags={tags}
              selected={filters.tags}
              onChange={next => set({ tags: next })}
              labelledBy={ids.tags}
            />
          </div>
        )}
      </div>

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
                aria-label={t.tagChipRemoveNamed(filters.flow === 'expense' ? t.filterExpenseOnly : t.filterIncomeOnly)}
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
                aria-label={t.tagChipRemoveNamed(categoryLabel(activeCategoryName, lang, dynamicEs))}
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
                aria-label={t.tagChipRemoveNamed(`${t.filterChipMerchant}: ${filters.merchant}`)}
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
                aria-label={t.tagChipRemoveNamed(`${t.filterChipDay}: ${formatDate(filters.day, lang)}`)}
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
                  aria-label={t.tagChipRemoveNamed(tagName)}
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
