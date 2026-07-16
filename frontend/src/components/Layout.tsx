import { useState, useEffect } from 'react'
import { Outlet, NavLink, Link, useLocation, useNavigate } from 'react-router-dom'
import { useT } from '../i18n'
import { useAuth } from '../contexts/AuthContext'
import { getConnections } from '../api/client'
import { PLUGIN_VIEW_REGISTRY } from '../investments/registry'
import type { InvestmentConnection } from '../api/types'

const LS_COLLAPSED = 'finlytics_sidebar_collapsed'

function storedCollapsed(): boolean {
  try { return localStorage.getItem(LS_COLLAPSED) === '1' } catch { return false }
}

export default function Layout() {
  const { t, lang, setLang } = useT()
  const { username, onLogout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(storedCollapsed)

  // ── Finanzas accordion ───────────────────────────────────────────────────
  const isOnFinances = ['/finances', '/transactions', '/analytics', '/statements']
    .some(p => location.pathname.startsWith(p))
  const [financesExpanded, setFinancesExpanded] = useState(isOnFinances)

  useEffect(() => {
    if (isOnFinances && !financesExpanded) setFinancesExpanded(true)
  }, [isOnFinances]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Investments accordion ────────────────────────────────────────────────
  const isOnInvestments = location.pathname.startsWith('/investments')
  const [investmentsExpanded, setInvestmentsExpanded] = useState(isOnInvestments)
  const [connectedPlugins, setConnectedPlugins] = useState<InvestmentConnection[]>([])

  useEffect(() => {
    getConnections()
      .then(conns => setConnectedPlugins(conns.filter(c => c.status === 'active')))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (isOnInvestments && !investmentsExpanded) setInvestmentsExpanded(true)
  }, [isOnInvestments]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Settings accordion ───────────────────────────────────────────────────
  const isOnSettings = location.pathname.startsWith('/settings')
  const [settingsExpanded, setSettingsExpanded] = useState(isOnSettings)

  useEffect(() => {
    if (isOnSettings && !settingsExpanded) setSettingsExpanded(true)
  }, [isOnSettings]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Settings group collapsibles (default collapsed) ─────────────────────
  const [sgData,   setSgData]   = useState(false)
  const [sgRules,  setSgRules]  = useState(false)
  const [sgSystem, setSgSystem] = useState(false)
  const [sgApp,    setSgApp]    = useState(false)

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
        <Link to="/" className="topbar-logo-link">
          <img src="/logo.png" alt="Finlytics" className="topbar-logo-img" />
          <span className="topbar-logo">Finlytics</span>
        </Link>
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

          {/* Finanzas expandable section */}
          <div className="sidebar-section">
            <button
              type="button"
              className={`sidebar-section-btn${isOnFinances ? ' active' : ''}`}
              onClick={() => {
                setFinancesExpanded(v => !v)
                navigate('/finances')
              }}
            >
              <span className="nav-icon">💳</span>
              <span className="nav-label">{t.navFinances}</span>
              <span className={`sidebar-arrow${financesExpanded ? ' open' : ''}`}>▾</span>
            </button>
            {financesExpanded && (
              <div className="sidebar-subnav">
                <NavLink to="/transactions" className={navLinkClass}>
                  <span className="nav-icon">📋</span>
                  <span className="nav-label">{t.navTransactions}</span>
                </NavLink>
                <NavLink to="/analytics" className={navLinkClass}>
                  <span className="nav-icon">📈</span>
                  <span className="nav-label">{t.navAnalytics}</span>
                </NavLink>
                <NavLink to="/statements" className={navLinkClass}>
                  <span className="nav-icon">📄</span>
                  <span className="nav-label">{t.navStatements}</span>
                </NavLink>
              </div>
            )}
          </div>

          {/* Inversiones expandable section */}
          <div className="sidebar-section">
            <button
              type="button"
              className={`sidebar-section-btn${isOnInvestments ? ' active' : ''}`}
              onClick={() => {
                setInvestmentsExpanded(v => !v)
                navigate('/investments')
              }}
              aria-expanded={investmentsExpanded}
            >
              <span className="nav-icon">💰</span>
              <span className="nav-label">{t.navInvestments}</span>
              {connectedPlugins.length > 0 && (
                <span className={`sidebar-arrow${investmentsExpanded ? ' open' : ''}`}>▾</span>
              )}
            </button>
            {investmentsExpanded && connectedPlugins.length > 0 && (
              <div className="sidebar-subnav">
                {connectedPlugins.map(conn => {
                  const entry = PLUGIN_VIEW_REGISTRY[conn.plugin_id]
                  if (!entry) return null
                  return (
                    <NavLink
                      key={conn.id}
                      to={`/investments/${conn.plugin_id}`}
                      className={navLinkClass}
                    >
                      <span className="nav-icon">{entry.icon}</span>
                      <span className="nav-label">{entry.name}</span>
                    </NavLink>
                  )
                })}
              </div>
            )}
          </div>

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
                {/* DATOS */}
                <button
                  type="button"
                  className="sidebar-group-label sidebar-group-toggle"
                  onClick={() => setSgData(v => !v)}
                  aria-expanded={sgData}
                >
                  {t.settingsGroupData}
                  <span className={`sidebar-arrow${sgData ? ' open' : ''}`}>▾</span>
                </button>
                {sgData && (
                  <>
                    <NavLink to="/settings/categories" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubCategories}</span>
                    </NavLink>
                    <NavLink to="/settings/tags" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubTags}</span>
                    </NavLink>
                    <NavLink to="/settings/accounts" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubAccounts}</span>
                    </NavLink>
                  </>
                )}

                {/* REGLAS */}
                <button
                  type="button"
                  className="sidebar-group-label sidebar-group-toggle"
                  onClick={() => setSgRules(v => !v)}
                  aria-expanded={sgRules}
                >
                  {t.settingsGroupRules}
                  <span className={`sidebar-arrow${sgRules ? ' open' : ''}`}>▾</span>
                </button>
                {sgRules && (
                  <NavLink to="/settings/rules" className={navLinkClass}>
                    <span className="nav-label">{t.navRules}</span>
                  </NavLink>
                )}

                {/* SISTEMA */}
                <button
                  type="button"
                  className="sidebar-group-label sidebar-group-toggle"
                  onClick={() => setSgSystem(v => !v)}
                  aria-expanded={sgSystem}
                >
                  {t.settingsGroupSystem}
                  <span className={`sidebar-arrow${sgSystem ? ' open' : ''}`}>▾</span>
                </button>
                {sgSystem && (
                  <>
                    <NavLink to="/settings/connectors" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubConnectors}</span>
                    </NavLink>
                    <NavLink to="/settings/backup" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubBackup}</span>
                    </NavLink>
                  </>
                )}

                {/* APLICACIÓN */}
                <button
                  type="button"
                  className="sidebar-group-label sidebar-group-toggle"
                  onClick={() => setSgApp(v => !v)}
                  aria-expanded={sgApp}
                >
                  {t.settingsGroupApp}
                  <span className={`sidebar-arrow${sgApp ? ' open' : ''}`}>▾</span>
                </button>
                {sgApp && (
                  <>
                    <NavLink to="/settings/appearance" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubAppearance}</span>
                    </NavLink>
                    <NavLink to="/settings/about" className={navLinkClass}>
                      <span className="nav-label">{t.settingsSubAbout}</span>
                    </NavLink>
                  </>
                )}
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

