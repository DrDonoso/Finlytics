import { useState } from 'react'
import type { Category } from '../api/types'
import { categoryLabel, type Lang, type Dict } from '../i18n'

interface Props {
  value: string
  baseCategories: Category[]       // sorted base categories (already sorted by caller)
  extraCategories?: string[]       // non-base categories to show in a second group
  lang: Lang
  t: Dict
  onChange: (value: string) => void
  className?: string
}

/** Reusable category selector: base categories + extra/custom categories + free-text option.
 *  Manages its own "custom editing" state so the free-text input stays visible
 *  while the user is typing, even if the partial value would match a known category. */
export default function CategorySelect({
  value, baseCategories, extraCategories = [], lang, t, onChange, className,
}: Props) {
  const [editingCustom, setEditingCustom] = useState(false)

  const isBase = baseCategories.some(c => c.name === value)
  const isKnownCustom = !isBase && extraCategories.includes(value)

  const selectValue = isBase
    ? value
    : (!editingCustom && isKnownCustom)
      ? value
      : '__custom__'

  return (
    <div className="category-cell">
      <select
        className={`cell-input cell-category${className ? ' ' + className : ''}`}
        value={selectValue}
        onChange={e => {
          if (e.target.value === '__custom__') {
            onChange('')
            setEditingCustom(true)
          } else {
            onChange(e.target.value)
            setEditingCustom(false)
          }
        }}
      >
        {baseCategories.map(c => (
          <option key={c.id} value={c.name}>{categoryLabel(c.name, lang)}</option>
        ))}
        {extraCategories.map(cat => (
          <option key={cat} value={cat}>{cat}</option>
        ))}
        <option value="__custom__">{t.previewCategoryCustom}</option>
      </select>

      {selectValue === '__custom__' && (
        <input
          type="text"
          className={`cell-input cell-category${className ? ' ' + className : ''}`}
          placeholder={t.previewCategoryCustomPlaceholder}
          value={value}
          autoFocus
          onChange={e => { onChange(e.target.value); setEditingCustom(true) }}
          onBlur={() => { if (value.trim()) setEditingCustom(false) }}
          style={{ marginTop: 2 }}
        />
      )}
    </div>
  )
}
