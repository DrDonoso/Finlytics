import { lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import Layout from './components/Layout'
import SettingsLayout from './components/SettingsLayout'
import LoginPage from './pages/LoginPage'
import SetupPage from './pages/SetupPage'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { AssistantProvider } from './contexts/AssistantContext'
import { NotificationsProvider } from './contexts/NotificationsContext'
import { ToastProvider } from './contexts/ToastContext'
import { useT } from './i18n'
import { IS_DEMO } from './demo/config'
import { pageChunks } from './routePrefetch'

// One chunk per page, so the first load does not download every screen (and the
// chart library) up front. The loaders are shared with routePrefetch.ts, which
// fetches a page on hover or at idle before it is opened. The shell and the
// pre-login screens stay in the entry chunk: they are what a visitor sees first.
// Layout owns the Suspense boundary.
const Dashboard = lazy(pageChunks['/'])
const TransactionsPage = lazy(pageChunks['/transactions'])
const StatementsPage = lazy(pageChunks['/statements'])
const AnalyticsPage = lazy(pageChunks['/analytics'])
const SettingsPage = lazy(pageChunks['/settings/tags'])
const CategoriesPage = lazy(pageChunks['/settings/categories'])
const AppearancePage = lazy(pageChunks['/settings/appearance'])
const BackupPage = lazy(pageChunks['/settings/backup'])
const SecurityPage = lazy(pageChunks['/settings/security'])
const RulesPage = lazy(pageChunks['/settings/rules'])
const AccountsPage = lazy(pageChunks['/settings/accounts'])
const InvestmentsLandingPage = lazy(pageChunks['/investments'])
const MortgagePage = lazy(pageChunks['/mortgage'])
const FinancesOverviewPage = lazy(pageChunks['/finances'])
const PluginViewWrapper = lazy(pageChunks['/investments/:pluginId'])
const ConnectorsPage = lazy(pageChunks['/settings/connectors'])
const AssistantSettingsPage = lazy(pageChunks['/settings/assistant'])
const AboutPage = lazy(pageChunks['/settings/about'])

/** Demo builds expose a deliberately reduced surface: read-only views backed by
 *  the synthetic dataset. Everything that imports, deletes, edits configuration
 *  or asks for third-party credentials is left unrouted, so a stale bookmark
 *  lands on the dashboard instead of a page whose endpoints answer 501. */
function DemoRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="finances" element={<FinancesOverviewPage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="investments">
          <Route index element={<InvestmentsLandingPage />} />
          <Route path=":pluginId" element={<PluginViewWrapper />} />
        </Route>
        <Route path="mortgage" element={<MortgagePage />} />
        <Route path="settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="appearance" replace />} />
          <Route path="appearance" element={<AppearancePage />} />
          <Route path="about" element={<AboutPage />} />
          <Route path="*" element={<Navigate to="/settings/appearance" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

function FullRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="finances" element={<FinancesOverviewPage />} />
        <Route path="transactions" element={<TransactionsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="investments">
          <Route index element={<InvestmentsLandingPage />} />
          <Route path=":pluginId" element={<PluginViewWrapper />} />
        </Route>
        <Route path="statements" element={<StatementsPage />} />
        <Route path="mortgage" element={<MortgagePage />} />
        <Route path="rules" element={<Navigate to="/settings/rules" replace />} />
        <Route path="settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="tags" replace />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="tags" element={<SettingsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="appearance" element={<AppearancePage />} />
          <Route path="backup" element={<BackupPage />} />
          <Route path="security" element={<SecurityPage />} />
          <Route path="connectors" element={<ConnectorsPage />} />
          <Route path="assistant" element={<AssistantSettingsPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="about" element={<AboutPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

function AppContent() {
  const { loading, initialized, authenticated } = useAuth()
  const { t } = useT()

  if (loading) {
    return (
      <div className="auth-container">
        <span className="auth-loading">{t.loading}</span>
      </div>
    )
  }

  if (!initialized) return <SetupPage />
  if (!authenticated) return <LoginPage />

  return (
    <ToastProvider>
    <NotificationsProvider>
      <AssistantProvider>
        <BrowserRouter>
          {IS_DEMO ? <DemoRoutes /> : <FullRoutes />}
        </BrowserRouter>
      </AssistantProvider>
    </NotificationsProvider>
    </ToastProvider>
  )
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}

export default App
