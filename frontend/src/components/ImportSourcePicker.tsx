import { useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useInvestmentPlugins } from '../api/queries'
import { useT } from '../i18n'
import { getPluginLogo, pluginInitial } from '../investments/registry'
import { IconClose, IconFileText, IconChevronRight } from './icons'

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
  const pluginsQuery = useInvestmentPlugins()
  // Only sources with an import path; the rest cannot be imported here.
  const plugins = useMemo(
    () => (pluginsQuery.data ?? []).filter(p => p.import_route !== null),
    [pluginsQuery.data],
  )

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
            <IconClose size={16} />
          </button>
        </div>

        <div className="import-picker-list">
          {/* Bank statements — always the first source */}
          <button
            type="button"
            className="import-picker-row"
            onClick={() => { onClose(); onStatements() }}
          >
            <span className="import-picker-icon"><IconFileText size={20} /></span>
            <div className="import-picker-text">
              <span className="import-picker-name">{t.importPickerStatements}</span>
              <span className="import-picker-desc">{t.importPickerStatementsDesc}</span>
            </div>
            <IconChevronRight size={16} className="import-picker-arrow" />
          </button>

          {/* Dynamic: investment plugins that expose an import_route */}
          {plugins.map(p => {
            // The backend sends an emoji in `icon`; prefer the provider's real logo
            // and fall back to its initial — never the emoji.
            const logo = getPluginLogo(p.id)
            return (
              <button
                key={p.id}
                type="button"
                className="import-picker-row"
                onClick={() => { onClose(); navigate(p.import_route!) }}
              >
                <span className="import-picker-icon" aria-hidden="true">
                  {logo
                    ? <img src={logo} alt="" className="plugin-logo" />
                    : <span className="plugin-logo-fallback">{pluginInitial(p.name)}</span>}
                </span>
                <div className="import-picker-text">
                  <span className="import-picker-name">{p.name}</span>
                  <span className="import-picker-desc">{p.description}</span>
                </div>
                <IconChevronRight size={16} className="import-picker-arrow" />
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
