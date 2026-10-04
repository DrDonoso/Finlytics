import { useState, type CSSProperties } from 'react'

interface Props {
  id: string
  value: string
  onChange: (text: string) => void
  inputMode?: 'decimal' | 'numeric'
  error?: string | null
  showError?: boolean
  placeholder?: string
  disabled?: boolean
  style?: CSSProperties
}

/**
 * Text input for a number typed in the user's own format. It keeps the text
 * exactly as typed — the parent parses it with `parseAmount` / `parseDecimal`
 * and passes `error` when the text is malformed. The error stays hidden until
 * the field is first left, so a half-typed value is not flagged; `showError`
 * reveals it earlier, typically once the user has tried to submit the form.
 */
export default function NumericInput({
  id, value, onChange, inputMode = 'decimal', error = null, showError = false, placeholder, disabled, style,
}: Props) {
  const [touched, setTouched] = useState(false)
  const shown = (touched || showError) && !!error
  const errorId = `${id}-error`

  return (
    <>
      <input
        id={id}
        type="text"
        className={`form-input${shown ? ' form-input--error' : ''}`}
        inputMode={inputMode}
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        style={style}
        aria-invalid={shown || undefined}
        aria-describedby={shown ? errorId : undefined}
        onChange={e => onChange(e.target.value)}
        onBlur={() => setTouched(true)}
      />
      {shown && <span id={errorId} className="form-field-error">{error}</span>}
    </>
  )
}
