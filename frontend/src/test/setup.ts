/** Common setup for all frontend tests. */
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, vi } from 'vitest'

// jsdom does not implement matchMedia, which ThemeContext uses to resolve the
// system theme. Without this, any test that mounts the theme provider fails.
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  }
})

// Testing Library does not unmount automatically when `globals` is active in
// Vitest; without this, components from one test would linger in the DOM during the next.
afterEach(() => {
  cleanup()
})

// jsdom reflects `open` on <dialog> but implements neither showModal() nor close(), nor
// Escape → cancel → close. This is the subset Modal relies on, kept close to the spec.
if (typeof HTMLDialogElement.prototype.showModal !== 'function') {
  const modalStack: HTMLDialogElement[] = []
  const previousFocus = new WeakMap<HTMLDialogElement, Element | null>()
  const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

  HTMLDialogElement.prototype.show = function show(this: HTMLDialogElement) {
    this.open = true
  }

  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    if (this.open && modalStack.includes(this)) return
    if (this.open || !this.isConnected) throw new DOMException('Cannot open the dialog', 'InvalidStateError')
    this.open = true
    modalStack.push(this)
    previousFocus.set(this, document.activeElement)
    const target = this.querySelector<HTMLElement>('[autofocus]')
      ?? Array.from(this.querySelectorAll<HTMLElement>(FOCUSABLE))
        .find(el => !el.hidden && !(el as HTMLButtonElement).disabled)
      ?? this
    target.focus()
  }

  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.open) return
    this.open = false
    const index = modalStack.indexOf(this)
    if (index !== -1) modalStack.splice(index, 1)
    const previous = previousFocus.get(this)
    previousFocus.delete(this)
    if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    setTimeout(() => this.dispatchEvent(new Event('close')), 0)
  }

  // Runs after React's own handlers, so an Escape a widget claimed with preventDefault()
  // never reaches the dialog — as in a browser.
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || e.defaultPrevented) return
    const top = [...modalStack].reverse().find(d => d.open && d.isConnected)
    if (top && top.dispatchEvent(new Event('cancel', { cancelable: true }))) top.close()
  })
}
