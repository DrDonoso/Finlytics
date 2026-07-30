import { BrowserRouter, Routes, Route, Navigate } from 'react-router'
import Layout from './components/Layout'
import SettingsLayout from './components/SettingsLayout'
import Dashboard from './pages/Dashboard'
import TransactionsPage from './pages/TransactionsPage'
import StatementsPage from './pages/StatementsPage'
import AnalyticsPage from './pages/AnalyticsPage'
import SettingsPage from './pages/SettingsPage'
import CategoriesPage from './pages/CategoriesPage'
import AppearancePage from './pages/AppearancePage'
import BackupPage from './pages/BackupPage'
import RulesPage from './pages/RulesPage'
import AccountsPage from './pages/AccountsPage'
import LoginPage from './pages/LoginPage'
import SetupPage from './pages/SetupPage'
import InvestmentsLandingPage from './pages/InvestmentsLandingPage'
import FinancesOverviewPage from './pages/FinancesOverviewPage'
import PluginViewWrapper from './investments/PluginViewWrapper'
import ConnectorsPage from './pages/ConnectorsPage'
import AboutPage from './pages/AboutPage'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { NotificationsProvider } from './contexts/NotificationsContext'
import { useT } from './i18n'
import { IS_DEMO } from './demo/config'

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
        <Route path="rules" element={<Navigate to="/settings/rules" replace />} />
        <Route path="settings" element={<SettingsLayout />}>
          <Route index element={<Navigate to="tags" replace />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="tags" element={<SettingsPage />} />
          <Route path="categories" element={<CategoriesPage />} />
          <Route path="appearance" element={<AppearancePage />} />
          <Route path="backup" element={<BackupPage />} />
          <Route path="connectors" element={<ConnectorsPage />} />
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
      <BrowserRouter>
        {IS_DEMO ? <DemoRoutes /> : <FullRoutes />}
      </BrowserRouter>
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
