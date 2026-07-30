import { useState, useRef, useId, useMemo } from 'react'
import type { Tag } from '../api/types'
import { DEFAULT_TAG_COLOR, tagTextColor } from '../i18n'
import { IconClose } from './icons'

interface Props {
  tags: string[]
  availableTags: Tag[]
  onChange: (tags: string[]) => void
  disabled?: boolean
  placeholder?: string
}

/** Tag chip editor: shows existing tags as chips with remove, plus an input
 *  with autocomplete from availableTags. Free-form tags are allowed.
 *  All tag names are normalised to lowercase before being stored. */
export default function TagEditor({ tags, availableTags, onChange, disabled, placeholder }: Props) {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const uid = useId()
  const listId = `tag-sug-${uid}`

  const colorMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const tg of availableTags) map[tg.name] = tg.color
    return map
  }, [availableTags])

  const emojiMap = useMemo(() => {
    const map: Record<string, string | null> = {}
    for (const tg of availableTags) map[tg.name] = tg.emoji
    return map
  }, [availableTags])

  function addTag(name: string) {
    const norm = name.trim().toLowerCase()
    if (!norm || tags.includes(norm)) { setInputValue(''); return }
    onChange([...tags, norm])
    setInputValue('')
  }

  function removeTag(name: string) {
    onChange(tags.filter(t => t !== name))
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      addTag(inputValue)
    } else if (e.key === 'Backspace' && !inputValue && tags.length > 0) {
      removeTag(tags[tags.length - 1])
    }
  }

  // Only suggest tags that are not already added and that start with the current input
  const suggestions = availableTags
    .filter(t => !tags.includes(t.name) && (inputValue === '' || t.name.startsWith(inputValue.toLowerCase())))

  return (
    <div
      className="tag-editor"
      onClick={() => !disabled && inputRef.current?.focus()}
    >
      {tags.map(tag => {
        const color = colorMap[tag] ?? DEFAULT_TAG_COLOR
        const textC = tagTextColor(color)
        return (
          <span key={tag} className="tag-chip" style={{ background: color, color: textC, borderColor: color + '88' }}>
            {emojiMap[tag] ? `${emojiMap[tag]} ` : ''}{tag}
            {!disabled && (
              <button
                type="button"
                className="tag-chip-remove"
                onClick={e => { e.stopPropagation(); removeTag(tag) }}
                aria-label={`Remove ${tag}`}
                style={{ color: textC }}
              ><IconClose size={12} /></button>
            )}
          </span>
        )
      })}

      {!disabled && (
        <>
          <input
            ref={inputRef}
            type="text"
            list={listId}
            className="tag-editor-input"
            value={inputValue}
            placeholder={tags.length === 0 ? placeholder : ''}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => { if (inputValue.trim()) addTag(inputValue) }}
          />
          <datalist id={listId}>
            {suggestions.map(s => <option key={s.id} value={s.name} />)}
          </datalist>
        </>
      )}
    </div>
  )
}
