import { useState, useRef, useId, useMemo } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'
import type { Tag } from '../api/types'
import { tagTextColor, paletteColor, useT } from '../i18n'
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
  ariaLabel?: string
  inputId?: string
}

/**
 * Tag typeahead for the import preview.
 * - Filters existing tags by case-insensitive substring as you type.
 * - Free-type creates new tags.
 * - Chips use: DB color → AI-suggested color → deterministic palette.
 */
export default function TagTypeahead({ tags, availableTags, suggestedColors, previewTagNames, onChange, placeholder, ariaLabel, inputId }: Props) {
  const { t } = useT()
  const [inputValue, setInputValue] = useState('')
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
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
    setActiveIndex(-1)
    setOpen(true)
  }

  const dbColorMap = useMemo(() => {
    const m: Record<string, string> = {}
    for (const tag of availableTags) m[tag.name] = tag.color
    return m
  }, [availableTags])

  const emojiMap = useMemo(() => {
    const m: Record<string, string | null> = {}
    for (const tag of availableTags) m[tag.name] = tag.emoji
    return m
  }, [availableTags])

  const txCountMap = useMemo(() => {
    const m: Record<string, number> = {}
    for (const tag of availableTags) m[tag.name] = tag.tx_count
    return m
  }, [availableTags])

  const query = inputValue.trim().toLowerCase()

  /** Merged, deduped candidates: DB tags first, then preview-wide names. */
  const candidates = useMemo(() => {
    const seen = new Set<string>()
    const result: Array<{ name: string; emoji: string | null }> = []
    for (const tag of availableTags) {
      const norm = tag.name.toLowerCase()
      if (!seen.has(norm)) { seen.add(norm); result.push({ name: tag.name, emoji: tag.emoji }) }
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

  const expanded = open && suggestions.length > 0

  function resolveColor(name: string): string {
    return dbColorMap[name] ?? suggestedColors[name] ?? paletteColor(name)
  }

  function addTag(name: string) {
    const norm = name.trim().toLowerCase()
    setActiveIndex(-1)
    if (!norm || tags.includes(norm)) { setInputValue(''); setOpen(false); return }
    onChange([...tags, norm])
    setInputValue('')
    setOpen(false)
  }

  function removeTag(name: string) {
    onChange(tags.filter(tag => tag !== name))
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) openSuggestions()
      else setActiveIndex(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(i => Math.max(i - 1, -1))
    } else if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      const active = open ? suggestions[activeIndex] : undefined
      addTag(active ? active.name : inputValue)
    } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeTag(tags[tags.length - 1])
    } else if (e.key === 'Escape' && expanded) {
      // Claim the key so an enclosing modal stays open.
      e.preventDefault()
      setOpen(false)
    }
  }

  return (
    // A pointer shortcut only: the input is keyboard-reachable on its own
    <div
      className="tag-typeahead"
      role="presentation"
      onClick={() => inputRef.current?.focus()}
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
              aria-label={t.tagChipRemoveNamed(tag)}
              style={{ color: textC }}
            ><IconClose size={12} /></button>
          </span>
        )
      })}

      <div className="tag-typeahead-input-wrap" ref={wrapRef}>
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          className="tag-editor-input"
          value={inputValue}
          placeholder={tags.length === 0 ? placeholder : ''}
          role="combobox"
          aria-label={ariaLabel ?? (inputId ? undefined : placeholder)}
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={expanded && suggestions[activeIndex] ? `${listId}-${activeIndex}` : undefined}
          onChange={e => { setInputValue(e.target.value); setActiveIndex(-1); setOpen(true) }}
          onKeyDown={handleKeyDown}
          onFocus={openSuggestions}
          onBlur={() => {
            // delay so onMouseDown on a suggestion fires first
            setTimeout(() => setOpen(false), 150)
            if (inputValue.trim()) addTag(inputValue)
          }}
        />
        {expanded && (
          <ul
            id={listId}
            className="tag-typeahead-suggestions"
            role="listbox"
            aria-label={ariaLabel ?? placeholder}
            style={dropdownStyle}
          >
            {suggestions.map((s, idx) => {
              const color = resolveColor(s.name)
              const textC = tagTextColor(color)
              return (
                <li
                  key={s.name}
                  id={`${listId}-${idx}`}
                  role="option"
                  aria-selected={idx === activeIndex}
                  className={idx === activeIndex ? 'is-active' : undefined}
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
