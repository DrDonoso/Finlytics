import { useState, useEffect } from 'react'
import { Outlet, NavLink, useLocation } from 'react-router-dom'
import { useT } from '../i18n'
import { useAuth } from '../contexts/AuthContext'

const LS_COLLAPSED = 'finlytics_sidebar_collapsed'

function storedCollapsed(): boolean {
  try { return localStorage.getItem(LS_COLLAPSED) === '1' } catch { return false }
}

export default function Layout() {
  const { t, lang, setLang } = useT()
  const { username, onLogout } = useAuth()
  const location = useLocation()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(storedCollapsed)

  // Auto-expand settings sub-nav when on any /settings/* route
  const isOnSettings = location.pathname.startsWith('/settings')
  const [settingsExpanded, setSettingsExpanded] = useState(isOnSettings)

  useEffect(() => {
    if (isOnSettings && !settingsExpanded) setSettingsExpanded(true)
  }, [isOnSettings]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close mobile sidebar when route changes
  useEffect(() => { setMobileOpen(false) }, [location.pathname])

  function toggleDesktop() {
    setDesktopCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem(LS_COLLAPSED, next ? '1' : '0') } catch { /* ignore */ }
      return next
    })
  }

  function navLinkClass({ isActive }: { isActive: boolean }) {
    return `sidebar-nav-link${isActive ? ' active' : ''}`
  }

  return (
    <div className="app-shell">
      {/* ── Sticky top bar (always visible) ─────────────────── */}
      <header className="app-topbar">
        <button
          className="hamburger-btn"
          onClick={() => {
            if (window.innerWidth < 768) {
              setMobileOpen(v => !v)
            } else {
              toggleDesktop()
            }
          }}
          aria-label="Toggle navigation"
          type="button"
        >
          <span className="hamburger-icon">☰</span>
        </button>
        <span className="topbar-logo">Finlytics</span>
      </header>

      {/* ── Mobile overlay ───────────────────────────────────── */}
      {mobileOpen && (
        <div
          className="sidebar-overlay"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── Sidebar ─────────────────────────────────────────── */}
      <aside
        className={[
          'sidebar',
          mobileOpen ? 'mobile-open' : '',
          desktopCollapsed ? 'desktop-collapsed' : '',
        ].filter(Boolean).join(' ')}
      >
        {/* Nav */}
        <nav className="sidebar-nav">
          <NavLink to="/" end className={navLinkClass}>
            <span className="nav-icon">🏠</span>
            <span className="nav-label">{t.navHome}</span>
          </NavLink>

          <NavLink to="/transactions" className={navLinkClass}>
            <span className="nav-icon">📋</span>
            <span className="nav-label">{t.navTransactions}</span>
          </NavLink>

          {/* Ajustes expandable section */}
          <div className="sidebar-section">
            <button
              type="button"
              className={`sidebar-section-btn${isOnSettings ? ' active' : ''}`}
              onClick={() => setSettingsExpanded(v => !v)}
            >
              <span className="nav-icon">⚙️</span>
              <span className="nav-label">{t.navSettings}</span>
              <span className={`sidebar-arrow${settingsExpanded ? ' open' : ''}`}>▾</span>
            </button>
            {settingsExpanded && (
              <div className="sidebar-subnav">
                <NavLink to="/settings/tags" className={navLinkClass}>
                  <span className="nav-label">{t.settingsSubTags}</span>
                </NavLink>
                <NavLink to="/settings/categories" className={navLinkClass}>
                  <span className="nav-label">{t.settingsSubCategories}</span>
                </NavLink>
                <NavLink to="/settings/appearance" className={navLinkClass}>
                  <span className="nav-label">{t.settingsSubAppearance}</span>
                </NavLink>
                <NavLink to="/settings/backup" className={navLinkClass}>
                  <span className="nav-label">{t.settingsSubBackup}</span>
                </NavLink>
              </div>
            )}
          </div>
        </nav>

        {/* Footer: user + logout + lang */}
        <div className="sidebar-footer">
          {username && (
            <div className="sidebar-user">
              <span className="sidebar-username">👤 {username}</span>
              <button
                className="sidebar-logout"
                onClick={() => { setMobileOpen(false); void onLogout() }}
                type="button"
              >
                {t.authLogout}
              </button>
            </div>
          )}
          <div className="lang-switcher">
            <button
              className={`lang-btn${lang === 'es' ? ' active' : ''}`}
              onClick={() => setLang('es')}
              aria-label="Español"
              type="button"
            >ES</button>
            <button
              className={`lang-btn${lang === 'en' ? ' active' : ''}`}
              onClick={() => setLang('en')}
              aria-label="English"
              type="button"
            >EN</button>
          </div>
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────── */}
      <div className={`app-content${desktopCollapsed ? ' desktop-collapsed' : ''}`}>
        <Outlet />
      </div>
    </div>
  )
}

