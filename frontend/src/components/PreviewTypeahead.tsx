import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent } from 'react'

export interface PreviewTypeaheadOption {
  value: string
  label?: string
}

interface Props {
  value: string
  options: PreviewTypeaheadOption[]
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  freeText?: boolean
  ariaLabel?: string
  getLabel?: (value: string) => string
  normalizeInput?: (input: string, options: PreviewTypeaheadOption[]) => string
}

export default function PreviewTypeahead({
  value,
  options,
  onChange,
  placeholder,
  className,
  freeText = true,
  ariaLabel,
  getLabel,
  normalizeInput,
}: Props) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({})
  const wrapRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const dedupedOptions = useMemo(() => {
    const seen = new Set<string>()
    const result: PreviewTypeaheadOption[] = []
    for (const opt of options) {
      const key = opt.value.toLowerCase()
      if (!seen.has(key)) {
        seen.add(key)
        result.push(opt)
      }
    }
    return result
  }, [options])

  // Memoizadas para poder declararlas como dependencia del efecto y del memo.
  // Antes se listaban a mano las dependencias internas (getLabel, dedupedOptions);
  // funcionaba, pero cualquier dependencia nueva dentro de estas funciones habría
  // dejado de propagarse sin que nada avisara.
  const optionLabel = useCallback(
    (opt: PreviewTypeaheadOption) => opt.label ?? (getLabel ? getLabel(opt.value) : opt.value),
    [getLabel],
  )
  const formatValue = useCallback(
    (next: string) => {
      const match = dedupedOptions.find(opt => opt.value === next)
      return match ? optionLabel(match) : next
    },
    [dedupedOptions, optionLabel],
  )
  const [inputValue, setInputValue] = useState(() => formatValue(value))

  useEffect(() => {
    if (document.activeElement === inputRef.current) return
    setInputValue(formatValue(value))
  }, [value, formatValue])

  const suggestions = useMemo(() => {
    const query = searchQuery.trim().toLowerCase()
    const ranked = dedupedOptions.filter(opt => {
      const label = optionLabel(opt)
      return !query || opt.value.toLowerCase().includes(query) || label.toLowerCase().includes(query)
    })
    return ranked
  }, [dedupedOptions, optionLabel, searchQuery])

  function openSuggestions() {
    if (wrapRef.current) {
      const r = wrapRef.current.getBoundingClientRect()
      setDropdownStyle({ top: r.bottom + 2, left: r.left, minWidth: Math.max(r.width, 160) })
    }
    setSearchQuery('')
    setActiveIndex(0)
    setOpen(true)
  }

  function commit(next: string) {
    onChange(next)
    setInputValue(formatValue(next))
    setSearchQuery('')
    setOpen(false)
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) openSuggestions()
      else setActiveIndex(i => Math.min(i + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      if (open && suggestions[activeIndex]) {
        e.preventDefault()
        commit(suggestions[activeIndex].value)
      } else if (!freeText) {
        e.preventDefault()
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className={`preview-typeahead${className ? ' ' + className : ''}`} ref={wrapRef}>
      <input
        ref={inputRef}
        type="text"
        className="preview-typeahead-input"
        value={inputValue}
        placeholder={placeholder}
        aria-label={ariaLabel}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        onFocus={() => {
          openSuggestions()
          requestAnimationFrame(() => inputRef.current?.select())
        }}
        onClick={() => {
          setSearchQuery('')
          inputRef.current?.select()
        }}
        onChange={e => {
          const next = e.target.value
          setInputValue(next)
          setSearchQuery(next)
          onChange(normalizeInput ? normalizeInput(next, dedupedOptions) : next)
          setOpen(true)
          setActiveIndex(0)
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          setTimeout(() => setOpen(false), 150)
          const currentDisplayValue = formatValue(value)
          if (inputValue === currentDisplayValue) {
            setInputValue(currentDisplayValue)
            setSearchQuery('')
            return
          }
          const normalized = normalizeInput ? normalizeInput(inputValue, dedupedOptions) : inputValue
          if (!freeText && normalized && !dedupedOptions.some(opt => opt.value === normalized)) {
            commit('')
          } else if (normalized !== value) {
            commit(normalized)
          } else {
            setInputValue(formatValue(value))
            setSearchQuery('')
          }
        }}
      />
      {open && suggestions.length > 0 && (
        <ul className="tag-typeahead-suggestions preview-typeahead-suggestions" role="listbox" style={dropdownStyle}>
          {suggestions.map((suggestion, idx) => (
            <li
              key={suggestion.value}
              role="option"
              aria-selected={idx === activeIndex}
              className={idx === activeIndex ? 'is-active' : undefined}
              onMouseDown={e => {
                e.preventDefault()
                commit(suggestion.value)
              }}
            >
              <span className="preview-typeahead-option-label">
                {optionLabel(suggestion)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
