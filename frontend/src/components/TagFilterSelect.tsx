import { useState, useRef, useId, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import type { Tag } from '../api/types'
import { DEFAULT_TAG_COLOR, tagTextColor, useT } from '../i18n'

/** Switch from toggle-buttons to typeahead when there are more than this many tags. */
const TYPEAHEAD_THRESHOLD = 8

interface Props {
  availableTags: Tag[]
  /** Currently selected tag names. */
  selected: string[]
  onChange: (next: string[]) => void
  label?: string
  placeholder?: string
}

/**
 * Tag filter control used in filter bars (GlobalFilterBar + TransactionsPage).
 *
 * - FEW tags (≤ TYPEAHEAD_THRESHOLD): renders toggle-button pills (existing UX).
 * - MANY tags (> TYPEAHEAD_THRESHOLD): renders a typeahead input.
 *   - Empty/focused → shows top-5 most-used tags (by tx_count desc) not already selected.
 *   - Typing → substring match over all available tags, excluding already-selected.
 *   - Selecting a suggestion adds it to `selected`; no free-create (filter mode only).
 *   - Backspace on empty input removes the last selected tag.
 *   - Escape closes the dropdown.
 *   - Dropdown uses position:fixed (same technique as TagTypeahead) to escape
 *     overflow-container clipping in the filter bar.
 *
 * Selected chips are rendered by the CALLER's chip row — this component only handles
 * adding. Removing is done by the caller via the chip ✕ buttons.
 */
export default function TagFilterSelect({ availableTags, selected, onChange, placeholder }: Props) {
  const { t } = useT()

  if (availableTags.length === 0) return null

  if (availableTags.length <= TYPEAHEAD_THRESHOLD) {
    return (
      <div className="tag-multi-select">
        {availableTags.map(tag => {
          const isSelected = selected.includes(tag.name)
          const color = tag.color || DEFAULT_TAG_COLOR
          return (
            <button
              key={tag.id}
              type="button"
              className="tag-toggle-btn"
              style={
                isSelected
                  ? { background: color, borderColor: color, color: tagTextColor(color) }
                  : { background: 'transparent', borderColor: color, color: color }
              }
              onClick={() => {
                const next = isSelected
                  ? selected.filter(n => n !== tag.name)
                  : [...selected, tag.name]
                onChange(next)
              }}
            >
              {tag.emoji ? `${tag.emoji} ` : ''}{tag.name}
            </button>
          )
        })}
      </div>
    )
  }

  return <TagFilterTypeahead
    availableTags={availableTags}
    selected={selected}
    onChange={onChange}
    placeholder={placeholder ?? t.filterTagSearchPlaceholder}
    mostUsedLabel={t.filterTagMostUsed}
  />
}

// ─── Internal typeahead (only rendered when > TYPEAHEAD_THRESHOLD) ─────────

interface TypeaheadProps {
  availableTags: Tag[]
  selected: string[]
  onChange: (next: string[]) => void
  placeholder: string
  mostUsedLabel: string
}

function TagFilterTypeahead({ availableTags, selected, onChange, placeholder, mostUsedLabel }: TypeaheadProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const uid = useId()
  const listId = `tfs-${uid}`

  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({})

  /** Compute viewport-relative coords for fixed dropdown — escapes scroll-container clipping. */
  function openDropdown() {
    if (wrapRef.current) {
      const r = wrapRef.current.getBoundingClientRect()
      setDropdownStyle({ top: r.bottom + 2, left: r.left, minWidth: Math.max(r.width, 180) })
    }
    setOpen(true)
    setActiveIdx(0)
  }

  /** Top-5 most-used, excluding already-selected. */
  const top5 = useMemo(
    () =>
      [...availableTags]
        .sort((a, b) => b.tx_count - a.tx_count)
        .slice(0, 5)
        .filter(t => !selected.includes(t.name)),
    [availableTags, selected],
  )

  const q = query.trim().toLowerCase()

  /** Filtered suggestions when typing, or top-5 on empty. */
  const suggestions = useMemo<Tag[]>(() => {
    if (!q) return top5
    return availableTags.filter(
      t => !selected.includes(t.name) && t.name.toLowerCase().includes(q),
    )
  }, [availableTags, selected, q, top5])

  const isTopMode = !q

  function select(tag: Tag) {
    onChange([...selected, tag.name])
    setQuery('')
    setActiveIdx(0)
    inputRef.current?.focus()
    // Recompute dropdown position after re-render
    setTimeout(() => {
      if (wrapRef.current) {
        const r = wrapRef.current.getBoundingClientRect()
        setDropdownStyle({ top: r.bottom + 2, left: r.left, minWidth: Math.max(r.width, 180) })
      }
    }, 0)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) {
      if (e.key === 'Backspace' && !query && selected.length > 0) {
        onChange(selected.slice(0, -1))
      }
      if (e.key === 'ArrowDown' && suggestions.length > 0) {
        openDropdown()
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (suggestions[activeIdx]) select(suggestions[activeIdx])
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      setQuery('')
    } else if (e.key === 'Backspace' && !query && selected.length > 0) {
      onChange(selected.slice(0, -1))
    }
  }

  return (
    <div className="tag-filter-select" ref={wrapRef}>
      <input
        ref={inputRef}
        id={listId}
        type="text"
        className="tag-filter-input"
        value={query}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={`${listId}-lb`}
        aria-autocomplete="list"
        onChange={e => { setQuery(e.target.value); setActiveIdx(0); if (!open) openDropdown() }}
        onFocus={openDropdown}
        onBlur={() => setTimeout(() => setOpen(false), 160)}
        onKeyDown={handleKeyDown}
      />
      {open && suggestions.length > 0 && (
        <ul
          id={`${listId}-lb`}
          className="tag-typeahead-suggestions"
          role="listbox"
          aria-label={placeholder}
          style={dropdownStyle}
        >
          {isTopMode && (
            <li className="tag-filter-suggestions-header" role="presentation">
              {mostUsedLabel}
            </li>
          )}
          {suggestions.map((tag, idx) => {
            const color = tag.color || DEFAULT_TAG_COLOR
            const textC = tagTextColor(color)
            return (
              <li
                key={tag.name}
                role="option"
                aria-selected={idx === activeIdx}
                className={idx === activeIdx ? 'tag-filter-option-active' : undefined}
                onMouseDown={e => { e.preventDefault(); select(tag) }}
                onMouseEnter={() => setActiveIdx(idx)}
              >
                <span
                  className="preview-tag-chip tag-chip-sm"
                  style={{ background: color, color: textC, borderColor: color + '88' }}
                >
                  {tag.emoji ? `${tag.emoji} ` : ''}{tag.name}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
