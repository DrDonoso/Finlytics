import { useState, useRef, useId, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import type { Tag } from '../api/types'
import { tagTextColor } from '../i18n'

/** Deterministic palette for brand-new tags not yet in the DB. */
const PALETTE = [
  '#3b82f6', '#f97316', '#8b5cf6', '#eab308', '#10b981',
  '#ef4444', '#ec4899', '#06b6d4', '#84cc16', '#f59e0b',
]

function paletteColor(name: string): string {
  let h = 0
  for (const c of name) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff
  return PALETTE[Math.abs(h) % PALETTE.length]
}

interface Props {
  tags: string[]
  availableTags: Tag[]
  /** AI-suggested colors for proposed tags. name → hex. */
  suggestedColors: Record<string, string>
  onChange: (tags: string[]) => void
  placeholder?: string
}

/**
 * Tag typeahead for the import preview.
 * - Filters existing tags by case-insensitive substring as you type.
 * - Free-type creates new tags.
 * - Chips use: DB color → AI-suggested color → deterministic palette.
 */
export default function TagTypeahead({ tags, availableTags, suggestedColors, onChange, placeholder }: Props) {
  const [inputValue, setInputValue] = useState('')
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const wrapRef  = useRef<HTMLDivElement>(null)
  const uid = useId()
  const listId = `tth-${uid}`

  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({})

  /** Compute viewport-relative coords for the fixed dropdown, escaping table scroll-container. */
  function openSuggestions() {
    if (wrapRef.current) {
      const r = wrapRef.current.getBoundingClientRect()
      setDropdownStyle({ top: r.bottom + 2, left: r.left, minWidth: Math.max(r.width, 160) })
    }
    setOpen(true)
  }

  const dbColorMap = useMemo(() => {
    const m: Record<string, string> = {}
    for (const t of availableTags) m[t.name] = t.color
    return m
  }, [availableTags])

  const emojiMap = useMemo(() => {
    const m: Record<string, string | null> = {}
    for (const t of availableTags) m[t.name] = t.emoji
    return m
  }, [availableTags])

  function resolveColor(name: string): string {
    return dbColorMap[name] ?? suggestedColors[name] ?? paletteColor(name)
  }

  function addTag(name: string) {
    const norm = name.trim().toLowerCase()
    if (!norm || tags.includes(norm)) { setInputValue(''); setOpen(false); return }
    onChange([...tags, norm])
    setInputValue('')
    setOpen(false)
  }

  function removeTag(name: string) {
    onChange(tags.filter(t => t !== name))
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(inputValue)
    } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeTag(tags[tags.length - 1])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  const query = inputValue.trim().toLowerCase()
  const suggestions = useMemo(() => {
    const notAdded = availableTags.filter(t => !tags.includes(t.name))
    if (!query) return notAdded.slice(0, 6)
    return notAdded.filter(t => t.name.includes(query))
  }, [availableTags, tags, query])

  return (
    <div
      className="tag-typeahead"
      onClick={() => inputRef.current?.focus()}
      data-listid={listId}
    >
      {tags.map(tag => {
        const color = resolveColor(tag)
        const textC = tagTextColor(color)
        return (
          <span
            key={tag}
            className="preview-tag-chip"
            style={{ background: color, color: textC, borderColor: color + '88' }}
          >
            {emojiMap[tag] ? `${emojiMap[tag]} ` : ''}{tag}
            <button
              type="button"
              className="tag-chip-remove"
              onClick={e => { e.stopPropagation(); removeTag(tag) }}
              aria-label={`Remove ${tag}`}
              style={{ color: textC }}
            >✕</button>
          </span>
        )
      })}

      <div className="tag-typeahead-input-wrap" ref={wrapRef}>
        <input
          ref={inputRef}
          type="text"
          className="tag-editor-input"
          value={inputValue}
          placeholder={tags.length === 0 ? placeholder : ''}
          onChange={e => { setInputValue(e.target.value); setOpen(true) }}
          onKeyDown={handleKeyDown}
          onFocus={openSuggestions}
          onBlur={() => {
            // delay so onMouseDown on a suggestion fires first
            setTimeout(() => setOpen(false), 150)
            if (inputValue.trim()) addTag(inputValue)
          }}
        />
        {open && suggestions.length > 0 && (
          <ul className="tag-typeahead-suggestions" role="listbox" style={dropdownStyle}>
            {suggestions.map(s => {
              const color = resolveColor(s.name)
              const textC = tagTextColor(color)
              return (
                <li
                  key={s.id}
                  role="option"
                  aria-selected={false}
                  onMouseDown={e => { e.preventDefault(); addTag(s.name) }}
                >
                  <span
                    className="preview-tag-chip tag-chip-sm"
                    style={{ background: color, color: textC, borderColor: color + '88' }}
                  >
                    {s.emoji ? `${s.emoji} ` : ''}{s.name}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
