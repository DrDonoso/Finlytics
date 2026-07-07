import { useState, useEffect } from 'react'
import { formatDate, type Lang } from '../i18n'

interface Props {
  value: string         // ISO "YYYY-MM-DD"
  lang: Lang
  onChange: (iso: string) => void
  className?: string
}

function tryParse(s: string): string | null {
  const m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (!m) return null
  const nd = Number(m[1]), nm = Number(m[2]), ny = Number(m[3])
  if (nd < 1 || nd > 31 || nm < 1 || nm > 12) return null
  const dt = new Date(ny, nm - 1, nd)
  if (dt.getFullYear() !== ny || dt.getMonth() !== nm - 1 || dt.getDate() !== nd) return null
  return `${ny}-${String(nm).padStart(2, '0')}-${String(nd).padStart(2, '0')}`
}

/**
 * Text input that displays and edits dates as dd/mm/yyyy (or dd/mm/aaaa in ES),
 * but commits only valid dates as ISO "YYYY-MM-DD" via onChange.
 * Invalid input is reset to the last valid value on blur.
 */
export default function DateInput({ value, lang, onChange, className }: Props) {
  const [text, setText] = useState(() => formatDate(value, lang))
  const placeholder = lang === 'es' ? 'dd/mm/aaaa' : 'dd/mm/yyyy'

  useEffect(() => {
    setText(formatDate(value, lang))
  }, [value, lang])

  return (
    <input
      type="text"
      className={className}
      value={text}
      placeholder={placeholder}
      onChange={e => setText(e.target.value)}
      onBlur={() => {
        const iso = tryParse(text)
        if (iso) {
          onChange(iso)
          setText(formatDate(iso, lang))
        } else {
          setText(formatDate(value, lang))
        }
      }}
    />
  )
}
