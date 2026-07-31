import { useState, useEffect, useMemo } from 'react'
import { Outlet, NavLink, Link, useLocation, useNavigate } from 'react-router'
import { useT } from '../i18n'
import { useAuth } from '../contexts/AuthContext'
import { useConnections } from '../api/queries'
import { getPluginLogo, PLUGIN_VIEW_REGISTRY, pluginInitial } from '../investments/registry'
import AssistantLauncher from './AssistantLauncher'
import AssistantPanel from './AssistantPanel'
import NotificationBell from './NotificationBell'
import LanguageSelect from './LanguageSelect'
import { BrandMark } from './Brand'
import { IS_DEMO } from '../demo/config'
import {
  IconMenu, IconHome, IconWallet, IconReceipt, IconChartLine, IconFileText,
  IconTrendingUp, IconSettings, IconChevronDown, IconUser, IconLogout,
} from './icons'

const LS_COLLAPSED = 'finlytics_sidebar_collapsed'

function storedCollapsed(): boolean {
  try { return localStorage.getItem(LS_COLLAPSED) === '1' } catch { return false }
}

export default function Layout() {
  const { t } = useT()
  const { username, onLogout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(storedCollapsed)

  // ── Finances accordion ───────────────────────────────────────────────────
  const isOnFinances = ['/finances', '/transactions', '/analytics', '/statements']
    .some(p => location.pathname.startsWith(p))
  const [financesExpanded, setFinancesExpanded] = useState(isOnFinances)

  useEffect(() => {
    if (isOnFinances && !financesExpanded) setFinancesExpanded(true)
  }, [isOnFinances]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Investments accordion ────────────────────────────────────────────────
  const isOnInvestments = location.pathname.startsWith('/investments')
  const [investmentsExpanded, setInvestmentsExpanded] = useState(isOnInvestments)
  const connectionsQuery = useConnections()
  const connectedPlugins = useMemo(
    () => (connectionsQuery.data ?? []).filter(c => c.status === 'active'),
    [connectionsQuery.data],
  )

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
          <span className="hamburger-icon"><IconMenu size={18} /></span>
        </button>
        <Link to="/" className="topbar-logo-link">
          <BrandMark size={28} />
          <span className="topbar-logo">Finlytics</span>
        </Link>
        <div className="topbar-actions">
          <NotificationBell />
        </div>
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
            <IconHome size={17} className="nav-icon" />
            <span className="nav-label">{t.navHome}</span>
          </NavLink>

          {/* Finanzas expandable section */}
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <button
                type="button"
                className={`sidebar-section-btn${isOnFinances ? ' active' : ''}`}
                onClick={() => navigate('/finances')}
              >
                <IconWallet size={17} className="nav-icon" />
                <span className="nav-label">{t.navFinances}</span>
              </button>
              <button
                type="button"
                className={`sidebar-section-arrow-btn${isOnFinances ? ' active' : ''}`}
                onClick={() => setFinancesExpanded(v => !v)}
                aria-expanded={financesExpanded}
                aria-label={t.navFinances}
              >
                <IconChevronDown size={15} className={`sidebar-arrow${financesExpanded ? ' open' : ''}`} />
              </button>
            </div>
            {financesExpanded && (
              <div className="sidebar-subnav">
                <NavLink to="/transactions" className={navLinkClass}>
                  <IconReceipt size={17} className="nav-icon" />
                  <span className="nav-label">{t.navTransactions}</span>
                </NavLink>
                <NavLink to="/analytics" className={navLinkClass}>
                  <IconChartLine size={17} className="nav-icon" />
                  <span className="nav-label">{t.navAnalytics}</span>
                </NavLink>
                {!IS_DEMO && (
                  <NavLink to="/statements" className={navLinkClass}>
                    <IconFileText size={17} className="nav-icon" />
                    <span className="nav-label">{t.navStatements}</span>
                  </NavLink>
                )}
              </div>
            )}
          </div>

          {/* Inversiones expandable section */}
          <div className="sidebar-section">
            <div className="sidebar-section-header">
              <button
                type="button"
                className={`sidebar-section-btn${isOnInvestments ? ' active' : ''}`}
                onClick={() => navigate('/investments')}
              >
                <IconTrendingUp size={17} className="nav-icon" />
                <span className="nav-label">{t.navInvestments}</span>
              </button>
              {connectedPlugins.length > 0 && (
                <button
                  type="button"
                  className={`sidebar-section-arrow-btn${isOnInvestments ? ' active' : ''}`}
                  onClick={() => setInvestmentsExpanded(v => !v)}
                  aria-expanded={investmentsExpanded}
                  aria-label={t.navInvestments}
                >
                  <IconChevronDown size={15} className={`sidebar-arrow${investmentsExpanded ? ' open' : ''}`} />
                </button>
              )}
            </div>
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
                      {getPluginLogo(conn.plugin_id) ? (
                        <img src={getPluginLogo(conn.plugin_id) ?? ''} alt={entry.name} className="nav-icon plugin-logo nav-plugin-logo" />
                      ) : (
                        <span className="nav-icon plugin-logo-fallback nav-plugin-logo" aria-label={entry.name}>{pluginInitial(entry.name)}</span>
                      )}
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
              <IconSettings size={17} className="nav-icon" />
              <span className="nav-label">{t.navSettings}</span>
              <IconChevronDown size={15} className={`sidebar-arrow${settingsExpanded ? ' open' : ''}`} />
            </button>
            {settingsExpanded && (
              <div className="sidebar-subnav">
                {/* Data, rules and system settings are all write-oriented and
                    depend on endpoints the demo does not serve. */}
                {!IS_DEMO && (
                  <>
                    <button
                      type="button"
                      className="sidebar-group-label sidebar-group-toggle"
                      onClick={() => setSgData(v => !v)}
                      aria-expanded={sgData}
                    >
                      {t.settingsGroupData}
                      <IconChevronDown size={14} className={`sidebar-arrow${sgData ? ' open' : ''}`} />
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
                      <IconChevronDown size={14} className={`sidebar-arrow${sgRules ? ' open' : ''}`} />
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
                      <IconChevronDown size={14} className={`sidebar-arrow${sgSystem ? ' open' : ''}`} />
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
                  </>
                )}


                <button
                  type="button"
                  className="sidebar-group-label sidebar-group-toggle"
                  onClick={() => setSgApp(v => !v)}
                  aria-expanded={sgApp}
                >
                  {t.settingsGroupApp}
                  <IconChevronDown size={14} className={`sidebar-arrow${sgApp ? ' open' : ''}`} />
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
              <span className="sidebar-username">
                <IconUser size={15} />
                {username}
              </span>
              <button
                className="sidebar-logout"
                onClick={() => { setMobileOpen(false); void onLogout() }}
                type="button"
              >
                <IconLogout size={15} />
                {t.authLogout}
              </button>
            </div>
          )}
          <LanguageSelect />
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────── */}
      <div className={`app-content${desktopCollapsed ? ' desktop-collapsed' : ''}`}>
        <Outlet />
      </div>

      {/* Mounted here rather than per-page so the assistant follows the user
          across routes without losing the thread it is in the middle of. */}
      <AssistantLauncher />
      <AssistantPanel />
    </div>
  )
}
