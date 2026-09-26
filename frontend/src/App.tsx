import { lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import Layout from './components/Layout'
import SettingsLayout from './components/SettingsLayout'
import LoginPage from './pages/LoginPage'
import SetupPage from './pages/SetupPage'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { AssistantProvider } from './contexts/AssistantContext'
import { NotificationsProvider } from './contexts/NotificationsContext'
import { useT } from './i18n'
import { IS_DEMO } from './demo/config'

// One chunk per page, so the first load does not download every screen (and the
// chart library) up front. The shell and the pre-login screens stay in the entry
// chunk: they are what a visitor sees first. Layout owns the Suspense boundary.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const TransactionsPage = lazy(() => import('./pages/TransactionsPage'))
const StatementsPage = lazy(() => import('./pages/StatementsPage'))
const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'))
const SettingsPage = lazy(() => import('./pages/SettingsPage'))
const CategoriesPage = lazy(() => import('./pages/CategoriesPage'))
const AppearancePage = lazy(() => import('./pages/AppearancePage'))
const BackupPage = lazy(() => import('./pages/BackupPage'))
const SecurityPage = lazy(() => import('./pages/SecurityPage'))
const RulesPage = lazy(() => import('./pages/RulesPage'))
const AccountsPage = lazy(() => import('./pages/AccountsPage'))
const InvestmentsLandingPage = lazy(() => import('./pages/InvestmentsLandingPage'))
const MortgagePage = lazy(() => import('./pages/MortgagePage'))
const FinancesOverviewPage = lazy(() => import('./pages/FinancesOverviewPage'))
const PluginViewWrapper = lazy(() => import('./investments/PluginViewWrapper'))
const ConnectorsPage = lazy(() => import('./pages/ConnectorsPage'))
const AssistantSettingsPage = lazy(() => import('./pages/AssistantSettingsPage'))
const AboutPage = lazy(() => import('./pages/AboutPage'))

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
    <NotificationsProvider>
      <AssistantProvider>
        <BrowserRouter>
          {IS_DEMO ? <DemoRoutes /> : <FullRoutes />}
        </BrowserRouter>
      </AssistantProvider>
    </NotificationsProvider>
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
