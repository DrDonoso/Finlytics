import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
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
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { useT } from './i18n'

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
    <BrowserRouter>
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
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
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
