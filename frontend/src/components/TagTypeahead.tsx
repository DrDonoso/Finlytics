import { useState, useRef, useId, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import type { Tag } from '../api/types'
import { tagTextColor, paletteColor } from '../i18n'
import { IconClose } from './icons'

interface Props {
  tags: string[]
  availableTags: Tag[]
  /** AI-suggested colors for proposed tags. name → hex. */
  suggestedColors: Record<string, string>
  /** Tag names already used/proposed on ANY preview row (not yet in DB). */
  previewTagNames?: string[]
  onChange: (tags: string[]) => void
  placeholder?: string
}

/**
 * Tag typeahead for the import preview.
 * - Filters existing tags by case-insensitive substring as you type.
 * - Free-type creates new tags.
 * - Chips use: DB color → AI-suggested color → deterministic palette.
 */
export default function TagTypeahead({ tags, availableTags, suggestedColors, previewTagNames, onChange, placeholder }: Props) {
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

  const txCountMap = useMemo(() => {
    const m: Record<string, number> = {}
    for (const t of availableTags) m[t.name] = t.tx_count
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

  /** Merged, deduped candidates: DB tags first, then preview-wide names. */
  const candidates = useMemo(() => {
    const seen = new Set<string>()
    const result: Array<{ name: string; emoji: string | null }> = []
    for (const t of availableTags) {
      const norm = t.name.toLowerCase()
      if (!seen.has(norm)) { seen.add(norm); result.push({ name: t.name, emoji: t.emoji }) }
    }
    for (const name of previewTagNames ?? []) {
      const norm = name.toLowerCase()
      if (!seen.has(norm)) { seen.add(norm); result.push({ name, emoji: null }) }
    }
    return result
  }, [availableTags, previewTagNames])

  const suggestions = useMemo(() => {
    const notAdded = candidates.filter(c => !tags.includes(c.name))
    if (!query) {
      return [...notAdded]
        .sort((a, b) => {
          const diff = (txCountMap[b.name] ?? 0) - (txCountMap[a.name] ?? 0)
          return diff !== 0 ? diff : a.name.localeCompare(b.name)
        })
        .slice(0, 8)
    }
    return notAdded.filter(c => c.name.toLowerCase().includes(query))
  }, [candidates, tags, query, txCountMap])

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
            ><IconClose size={12} /></button>
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
                  key={s.name}
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
