import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useT } from '../i18n'

type ShowToast = (message: string) => void
type RegisterHost = (host: HTMLElement) => () => void

const ToastContext = createContext<ShowToast | null>(null)
const ModalToastHostContext = createContext<RegisterHost | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useT()
  const [toast, setToast] = useState<{ message: string } | null>(null)
  const [hosts, setHosts] = useState<HTMLElement[]>([])
  const popoverRef = useRef<HTMLDivElement>(null)
  const host = hosts[hosts.length - 1] ?? document.body

  const showToast = useCallback((message: string) => setToast({ message }), [])
  const registerHost = useCallback((element: HTMLElement) => {
    setHosts(current => [...current, element])
    return () => setHosts(current => current.filter(item => item !== element))
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 6000)
    return () => window.clearTimeout(timer)
  }, [toast])

  useLayoutEffect(() => {
    const element = popoverRef.current
    if (!toast || !element?.isConnected || typeof element.showPopover !== 'function') return
    element.hidePopover()
    element.showPopover()
  }, [toast, host])

  return (
    <ToastContext.Provider value={showToast}>
      <ModalToastHostContext.Provider value={registerHost}>
        {children}
        {createPortal(
          <div role="status" aria-live="polite" aria-atomic="true">
            {toast && (
              <div
                className="toast"
                popover={typeof HTMLElement.prototype.showPopover === 'function' ? 'manual' : undefined}
                ref={popoverRef}
              >
                <span>{toast.message}</span>
                <button type="button" className="toast-close" onClick={() => setToast(null)}>
                  {t.toastClose}
                </button>
              </div>
            )}
          </div>,
          host,
        )}
      </ModalToastHostContext.Provider>
    </ToastContext.Provider>
  )
}

export function useToast(): ShowToast {
  const showToast = useContext(ToastContext)
  if (!showToast) throw new Error('useToast must be used within ToastProvider')
  return showToast
}

export function useModalToastHost(): RegisterHost | null {
  return useContext(ModalToastHostContext)
}
