import { Suspense, useState, useEffect, useMemo } from 'react'
import type { SyntheticEvent } from 'react'
import { Outlet, NavLink, Link, useLocation, useNavigate } from 'react-router'
import { useT } from '../i18n'
import { useAuth } from '../contexts/AuthContext'
import { useConnections } from '../api/queries'
import { getPluginLogo, PLUGIN_VIEW_REGISTRY, pluginInitial } from '../investments/registry'
import { LIKELY_NEXT, prefetch } from '../routePrefetch'
import AssistantLauncher from './AssistantLauncher'
import AssistantPanel from './AssistantPanel'
import NotificationBell from './NotificationBell'
import LanguageSelect from './LanguageSelect'
import PrivacyToggle from './PrivacyToggle'
import PageLoading from './PageLoading'
import RouteErrorBoundary from './RouteErrorBoundary'
import { BrandMark } from './Brand'
import { IS_DEMO } from '../demo/config'
import { useIsCompactNav } from '../hooks/useMediaQuery'
import {
  IconMenu, IconHome, IconWallet, IconReceipt, IconChartLine, IconFileText,
  IconTrendingUp, IconSettings, IconChevronDown, IconUser, IconLogout,
  IconBuilding, IconAlert,
} from './icons'

const LS_COLLAPSED = 'finlytics_sidebar_collapsed'
const SIDEBAR_ID = 'app-sidebar'

function storedCollapsed(): boolean {
  try { return localStorage.getItem(LS_COLLAPSED) === '1' } catch { return false }
}

/** Starts loading a page as soon as its link is pointed at or focused. */
function prefetchFrom(event: SyntheticEvent) {
  prefetch.target(event.target)
}

/**
 * A nav group unfolds when one of its routes becomes active, and stays
 * foldable by hand while the visitor is still on it.
 */
function useExpandedWhenActive(active: boolean) {
  const [expanded, setExpanded] = useState(active)
  const [wasActive, setWasActive] = useState(active)
  if (active !== wasActive) {
    setWasActive(active)
    if (active) setExpanded(true)
  }
  return [expanded, setExpanded] as const
}

export default function Layout() {
  const { t } = useT()
  const { username, onLogout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const compactNav = useIsCompactNav()

  const [mobileOpen, setMobileOpen] = useState(false)
  const [desktopCollapsed, setDesktopCollapsed] = useState(storedCollapsed)

  // The drawer closes when a navigation lands on another route
  const [drawerPath, setDrawerPath] = useState(location.pathname)
  if (drawerPath !== location.pathname) {
    setDrawerPath(location.pathname)
    setMobileOpen(false)
  }

  // ── Finances accordion ───────────────────────────────────────────────────
  const isOnFinances = ['/finances', '/transactions', '/analytics', '/statements']
    .some(p => location.pathname.startsWith(p))
  const [financesExpanded, setFinancesExpanded] = useExpandedWhenActive(isOnFinances)

  // ── Investments accordion ────────────────────────────────────────────────
  const isOnInvestments = location.pathname.startsWith('/investments')
  const [investmentsExpanded, setInvestmentsExpanded] = useExpandedWhenActive(isOnInvestments)
  const connectionsQuery = useConnections()
  // An `error` connection still holds money, so its view stays reachable and
  // carries a warning instead of vanishing from the menu.
  const connectedPlugins = useMemo(() => {
    const byPlugin = new Map<string, { pluginId: string; name: string; hasError: boolean }>()
    for (const conn of connectionsQuery.data ?? []) {
      if (conn.status !== 'active' && conn.status !== 'error') continue
      const entry = PLUGIN_VIEW_REGISTRY[conn.plugin_id]
      if (!entry) continue
      const seen = byPlugin.get(conn.plugin_id)
      const hasError = conn.status === 'error'
      if (seen) seen.hasError ||= hasError
      else byPlugin.set(conn.plugin_id, { pluginId: conn.plugin_id, name: entry.name, hasError })
    }
    return [...byPlugin.values()]
  }, [connectionsQuery.data])

  // ── Settings accordion ───────────────────────────────────────────────────
  const isOnSettings = location.pathname.startsWith('/settings')
  const [settingsExpanded, setSettingsExpanded] = useExpandedWhenActive(isOnSettings)

  // ── Settings group collapsibles (default collapsed) ─────────────────────
  const [sgData,   setSgData]   = useState(false)
  const [sgRules,  setSgRules]  = useState(false)
  const [sgSystem, setSgSystem] = useState(false)
  const [sgApp,    setSgApp]    = useState(false)

  // Warm the pages a visitor most likely opens next, once the first one has
  // settled. Production only: under the dev server every import is a fresh
  // transform, so warming them all would just slow it down.
  useEffect(() => (import.meta.env.PROD ? prefetch.whenIdle(LIKELY_NEXT) : undefined), [])

  useEffect(() => {
    if (!mobileOpen) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMobileOpen(false) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [mobileOpen])

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

  function bottomNavClass(active: boolean) {
    return `bottom-nav-item${active ? ' active' : ''}`
  }

  return (
    <div className="app-shell" onPointerOver={prefetchFrom} onFocus={prefetchFrom}>
      {/* ── Sticky top bar (always visible) ─────────────────── */}
      <header className="app-topbar">
        <button
          className="hamburger-btn"
          onClick={() => {
            if (compactNav) {
              setMobileOpen(v => !v)
            } else {
              toggleDesktop()
            }
          }}
          aria-label={t.navToggle}
          aria-controls={SIDEBAR_ID}
          aria-expanded={compactNav ? mobileOpen : !desktopCollapsed}
          type="button"
        >
          <span className="hamburger-icon"><IconMenu size={18} /></span>
        </button>
        <Link to="/" className="topbar-logo-link">
          <BrandMark size={28} />
          <span className="topbar-logo">Finlytics</span>
        </Link>
        <div className="topbar-actions">
          {compactNav && <AssistantLauncher variant="toolbar" />}
          <PrivacyToggle />
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
        id={SIDEBAR_ID}
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
                data-prefetch="/finances"
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
                data-prefetch="/investments"
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
                {connectedPlugins.map(plugin => {
                  const logo = getPluginLogo(plugin.pluginId)
                  return (
                    <NavLink
                      key={plugin.pluginId}
                      to={`/investments/${plugin.pluginId}`}
                      className={navLinkClass}
                    >
                      {logo ? (
                        <img src={logo} alt="" className="nav-icon plugin-logo nav-plugin-logo" />
                      ) : (
                        <span className="nav-icon plugin-logo-fallback nav-plugin-logo" aria-hidden="true">{pluginInitial(plugin.name)}</span>
                      )}
                      <span className="nav-label">{plugin.name}</span>
                      {plugin.hasError && (
                        <>
                          <IconAlert size={14} className="nav-alert" />
                          <span className="sr-only">{t.navConnectionError}</span>
                        </>
                      )}
                    </NavLink>
                  )
                })}
              </div>
            )}
          </div>

          {/* Mortgage */}
          <NavLink to="/mortgage" className={navLinkClass}>
            <IconBuilding size={17} className="nav-icon" />
            <span className="nav-label">{t.navMortgage}</span>
          </NavLink>

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
                        <NavLink to="/settings/assistant" className={navLinkClass}>
                          <span className="nav-label">{t.settingsSubAssistant}</span>
                        </NavLink>
                        <NavLink to="/settings/backup" className={navLinkClass}>
                          <span className="nav-label">{t.settingsSubBackup}</span>
                        </NavLink>
                        <NavLink to="/settings/security" className={navLinkClass}>
                          <span className="nav-label">{t.settingsSubSecurity}</span>
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
        {/* Pages are code-split (App.tsx). This is the only Suspense boundary:
            navigations run in a transition, so after the first page React keeps the
            current one on screen until the next chunk arrives instead of flashing
            the fallback. */}
        <RouteErrorBoundary resetKey={location.pathname}>
          <Suspense fallback={<PageLoading />}>
            <Outlet />
          </Suspense>
        </RouteErrorBoundary>
      </div>

      {compactNav && (
        <nav className="bottom-nav" aria-label={t.navPrimary}>
          <NavLink to="/" end className={({ isActive }) => bottomNavClass(isActive)}>
            <IconHome size={20} />
            <span>{t.navHome}</span>
          </NavLink>
          <NavLink to="/finances" className={() => bottomNavClass(isOnFinances)}>
            <IconWallet size={20} />
            <span>{t.navFinances}</span>
          </NavLink>
          <NavLink to="/investments" className={() => bottomNavClass(isOnInvestments)}>
            <IconTrendingUp size={20} />
            <span>{t.navInvestments}</span>
          </NavLink>
          <NavLink to="/mortgage" className={({ isActive }) => bottomNavClass(isActive)}>
            <IconBuilding size={20} />
            <span>{t.navMortgage}</span>
          </NavLink>
          <button
            type="button"
            className={bottomNavClass(mobileOpen || isOnSettings)}
            onClick={() => setMobileOpen(v => !v)}
            aria-controls={SIDEBAR_ID}
            aria-expanded={mobileOpen}
          >
            <IconMenu size={20} />
            <span>{t.navMore}</span>
          </button>
        </nav>
      )}

      {/* Mounted here rather than per-page so the assistant follows the user
          across routes without losing the thread it is in the middle of. */}
      {!compactNav && <AssistantLauncher />}
      <AssistantPanel />
    </div>
  )
}
