import type { Category } from '../api/types'
import { categoryLabel, type Lang, type Dict } from '../i18n'
import PreviewTypeahead from './PreviewTypeahead'

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
  const options = [
    ...baseCategories.map(c => ({ value: c.name, label: categoryLabel(c.name, lang) })),
    ...extraCategories.map(cat => ({ value: cat, label: cat })),
  ]

  return (
    <div className="category-cell">
      <PreviewTypeahead
        value={value}
        options={options}
        onChange={onChange}
        placeholder={t.previewCategoryCustomPlaceholder || t.previewCategoryCustom}
        className={`cell-category${className ? ' ' + className : ''}`}
        freeText
      />
    </div>
  )
}
