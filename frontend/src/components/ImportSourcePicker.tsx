import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { getInvestmentPlugins } from '../api/client'
import type { InvestmentPlugin } from '../api/types'
import { useT } from '../i18n'

interface ImportSourcePickerProps {
  onClose: () => void
  /** Called when the user picks "bank statements" — caller opens the file picker. */
  onStatements: () => void
}

/**
 * Modal that lists all import sources:
 *  - Bank statements (always shown)
 *  - Any investment plugin where import_route is non-null (data-driven)
 */
export default function ImportSourcePicker({ onClose, onStatements }: ImportSourcePickerProps) {
  const { t } = useT()
  const navigate = useNavigate()
  const [plugins, setPlugins] = useState<InvestmentPlugin[]>([])

  useEffect(() => {
    getInvestmentPlugins()
      .then(ps => setPlugins(ps.filter(p => p.import_route !== null)))
      .catch(() => {})
  }, [])

  const handleBackdrop = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }, [onClose])

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={t.importPickerTitle}
      onClick={handleBackdrop}
      onKeyDown={handleKeyDown}
    >
      <div className="modal-box import-picker-modal">
        <div className="modal-header">
          <span className="modal-title">{t.importPickerTitle}</span>
          <button
            className="modal-close"
            onClick={onClose}
            aria-label={t.importPickerClose}
            type="button"
          >
            ✕
          </button>
        </div>

        <div className="import-picker-list">
          {/* Bank statements — always the first source */}
          <button
            type="button"
            className="import-picker-row"
            onClick={() => { onClose(); onStatements() }}
          >
            <span className="import-picker-icon" aria-hidden="true">📄</span>
            <div className="import-picker-text">
              <span className="import-picker-name">{t.importPickerStatements}</span>
              <span className="import-picker-desc">{t.importPickerStatementsDesc}</span>
            </div>
            <span className="import-picker-arrow" aria-hidden="true">›</span>
          </button>

          {/* Dynamic: investment plugins that expose an import_route */}
          {plugins.map(p => (
            <button
              key={p.id}
              type="button"
              className="import-picker-row"
              onClick={() => { onClose(); navigate(p.import_route!) }}
            >
              <span className="import-picker-icon" aria-hidden="true">{p.icon}</span>
              <div className="import-picker-text">
                <span className="import-picker-name">{p.name}</span>
                <span className="import-picker-desc">{p.description}</span>
              </div>
              <span className="import-picker-arrow" aria-hidden="true">›</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
