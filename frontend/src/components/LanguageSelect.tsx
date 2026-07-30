import { useEffect, useRef, useState } from 'react'
import { LANG_NAMES, useT } from '../i18n'
import type { Lang } from '../i18n'
import { IconGlobe, IconChevronDown, IconCheck } from './icons'

const LANGS: readonly Lang[] = ['es', 'en']

/** Language selector for the sidebar footer.
 *
 * Replaces a pair of ES / EN toggle buttons: those showed opaque codes and made
 * the list grow sideways with every new language. This shows the current
 * language by its native name and opens a menu on demand.
 *
 * Opens upward because it sits at the bottom of the sidebar.
 */
export default function LanguageSelect() {
  const { t, lang, setLang } = useT()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)

  // Close on outside click and on Escape. Both listeners are only attached
  // while the menu is open, so the common case costs nothing.
  useEffect(() => {
    if (!open) return

    function onPointerDown(e: MouseEvent | TouchEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  function choose(next: Lang) {
    setLang(next)
    setOpen(false)
    buttonRef.current?.focus()
  }

  return (
    <div className="lang-select" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={`lang-select-trigger${open ? ' open' : ''}`}
        onClick={() => setOpen(v => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t.langSelectLabel}
      >
        <IconGlobe size={15} className="lang-select-icon" />
        <span className="lang-select-current">{LANG_NAMES[lang]}</span>
        <IconChevronDown size={13} className={`lang-select-arrow${open ? ' open' : ''}`} />
      </button>

      {open && (
        <ul className="lang-select-menu" role="listbox" aria-label={t.langSelectLabel}>
          {LANGS.map(code => (
            <li key={code} role="none">
              <button
                type="button"
                role="option"
                aria-selected={code === lang}
                className={`lang-select-option${code === lang ? ' selected' : ''}`}
                onClick={() => choose(code)}
              >
                <span className="lang-select-option-name">{LANG_NAMES[code]}</span>
                {code === lang && (
                  <IconCheck size={13} className="lang-select-check" />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
