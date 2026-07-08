import { useRef } from 'react'
import { PALETTE, useT } from '../i18n'

interface Props {
  value: string
  onChange: (hex: string) => void
  disabled?: boolean
}

export default function ColorSwatchPicker({ value, onChange, disabled = false }: Props) {
  const { t } = useT()
  const inputRef = useRef<HTMLInputElement>(null)

  const isCustom = !PALETTE.includes(value)

  return (
    <div className="color-swatch-picker">
      {PALETTE.map(hex => {
        const selected = value === hex
        return (
          <button
            key={hex}
            type="button"
            className={`color-swatch${selected ? ' color-swatch-selected' : ''}`}
            style={{ background: hex }}
            onClick={() => onChange(hex)}
            disabled={disabled}
            aria-pressed={selected}
            aria-label={hex}
          />
        )
      })}

      {/* Extra swatch for the current custom color when not in PALETTE */}
      {isCustom && (
        <button
          type="button"
          className="color-swatch color-swatch-selected"
          style={{ background: value }}
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          aria-pressed={true}
          aria-label={`${t.colorSwatchCustom}: ${value}`}
        />
      )}

      {/* Rainbow swatch — opens the native color picker */}
      <button
        type="button"
        className="color-swatch color-swatch-custom"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-label={t.colorSwatchCustom}
        title={t.colorSwatchCustom}
      >
        +
      </button>

      {/* Visually hidden native color input — opened programmatically */}
      <input
        ref={inputRef}
        type="color"
        value={value}
        onChange={e => onChange(e.target.value)}
        disabled={disabled}
        tabIndex={-1}
        aria-hidden="true"
        className="color-swatch-hidden-input"
      />
    </div>
  )
}
