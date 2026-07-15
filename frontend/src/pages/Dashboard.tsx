import { useState, useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import type { Account, Category, Tag, Overview, ImportResult, FidelityReminderResponse } from '../api/types'
import {
  getAccounts, getCategories, getTags, getOverview, getOverviewMonths,
  getFidelityReminder,
} from '../api/client'
import KpiCards from '../components/KpiCards'
import ImportModal from '../components/ImportModal'
import ImportLauncher, { type ImportLauncherHandle } from '../components/ImportLauncher'
import ImportSourcePicker from '../components/ImportSourcePicker'
import InvestmentSnapshotCard from '../components/InvestmentSnapshotCard'
import { useT } from '../i18n'
import { defaultRange } from '../utils'

interface AsyncState<T> {
  loading: boolean
  error: string | null
  data: T | null
}

function idle<T>(): AsyncState<T> { return { loading: true, error: null, data: null } }

/** "YYYY-MM" → { from: "YYYY-MM-01", to: "YYYY-MM-DD" } */
function monthRange(ym: string): { from: string; to: string } {
  const [yearStr, monthStr] = ym.split('-')
  const year = Number(yearStr)
  const month = Number(monthStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  const lastDay = new Date(year, month, 0).getDate()
  return { from: `${year}-${pad(month)}-01`, to: `${year}-${pad(month)}-${pad(lastDay)}` }
}

/** "YYYY-MM" → "Junio 2026" (locale-aware, first letter capitalised) */
function formatMonthLabel(ym: string, locale: string): string {
  const [yearStr, monthStr] = ym.split('-')
  const d = new Date(Number(yearStr), Number(monthStr) - 1, 1)
  const label = new Intl.DateTimeFormat(locale, { month: 'long', year: 'numeric' }).format(d)
  return label.charAt(0).toUpperCase() + label.slice(1)
}

/** Previous calendar month as "YYYY-MM" — used as graceful fallback. */
function fallbackMonth(): string {
  return defaultRange().from.slice(0, 7)
}

export default function Dashboard() {
  const { t, lang } = useT()
  const navigate = useNavigate()
  const locale = lang === 'es' ? 'es-ES' : 'en-GB'

  const [accounts,   setAccounts]   = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [allTags,    setAllTags]    = useState<Tag[]>([])

  const [overview,   setOverview]   = useState<AsyncState<Overview>>(idle())
  const [refreshKey, setRefreshKey] = useState(0)
  const [pickerOpen,   setPickerOpen]   = useState(false)
  const [importFiles,  setImportFiles]  = useState<File[] | null>(null)
  const launcherRef = useRef<ImportLauncherHandle>(null)
  const [toast, setToast] = useState<string | null>(null)

  // ESPP upload-reminder banner
  const [esppReminder, setEsppReminder] = useState<FidelityReminderResponse | null>(null)

  // Available months from the backend; selectedMonth defaults to the last one
  const [availableMonths, setAvailableMonths] = useState<string[]>([])
  const [selectedMonth,   setSelectedMonth]   = useState<string>(fallbackMonth())

  function handleImportSuccess(result: ImportResult) {
    setImportFiles(null)
    setToast(t.toastSuccess(result.num_inserted, result.num_duplicates))
    setTimeout(() => setToast(null), 6000)
    setRefreshKey(k => k + 1)
  }

  useEffect(() => {
    getAccounts().then(setAccounts).catch(() => {})
    getCategories().then(setCategories).catch(() => {})
    getTags().then(setAllTags).catch(() => {})
    getFidelityReminder().then(setEsppReminder).catch(() => {})
  }, [])

  // Fetch available months — default to the LAST month with data (mes vencido)
  useEffect(() => {
    getOverviewMonths()
      .then(({ months, latest }) => {
        if (months.length > 0) {
          setAvailableMonths(months)
          setSelectedMonth(latest ?? months[months.length - 1])
        } else {
          const fb = fallbackMonth()
          setAvailableMonths([fb])
          // selectedMonth already initialised to fallbackMonth()
        }
      })
      .catch(() => {
        const fb = fallbackMonth()
        setAvailableMonths([fb])
      })
  }, [])

  // Fetch overview for the currently selected month
  useEffect(() => {
    const { from, to } = monthRange(selectedMonth)
    setOverview(idle())
    getOverview({ from, to })
      .then(d  => setOverview({ loading: false, error: null,     data: d }))
      .catch(e => setOverview({ loading: false, error: String(e), data: null }))
  }, [selectedMonth, refreshKey])

  const monthIdx = availableMonths.indexOf(selectedMonth)
  const canPrev  = monthIdx > 0
  const canNext  = monthIdx < availableMonths.length - 1
  const monthLabel = formatMonthLabel(selectedMonth, locale)

  return (
    <>
      <main className="dashboard">
        <div className="dashboard-header">
          {/* Month navigation — full-width top row inside the header card */}
          <div style={{ flex: '0 0 100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 20px', borderBottom: '1px solid var(--border)' }}>
            <button
              className="month-nav-arrow"
              style={{ width: 32, height: 32, minWidth: 32, minHeight: 32, fontSize: 18 }}
              onClick={() => canPrev && setSelectedMonth(availableMonths[monthIdx - 1])}
              disabled={!canPrev}
              aria-label={t.datePickerPrevMonth}
            >‹</button>
            <span style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', minWidth: 130, textAlign: 'center' }}>
              {monthLabel}
            </span>
            <button
              className="month-nav-arrow"
              style={{ width: 32, height: 32, minWidth: 32, minHeight: 32, fontSize: 18 }}
              onClick={() => canNext && setSelectedMonth(availableMonths[monthIdx + 1])}
              disabled={!canNext}
              aria-label={t.datePickerNextMonth}
            >›</button>
          </div>
          <KpiCards
            overview={overview.data}
            loading={overview.loading}
            error={overview.error}
            compact
          />
          <div className="dashboard-header-actions">
            <button
              className="btn-secondary"
              onClick={() => navigate('/transactions')}
            >
              {t.btnViewTransactions}
            </button>
            <button
              className="btn-primary"
              onClick={() => setPickerOpen(true)}
            >
              {t.btnImport}
            </button>
          </div>
        </div>

        <InvestmentSnapshotCard />

        {esppReminder?.overdue && (
          <div className="espp-reminder-banner" role="alert">
            <span>⚠ {t.esppReminderBanner(esppReminder.period_label)}</span>
            <Link to="/investments/fidelity-espp" className="espp-reminder-banner__link">
              {t.esppReminderAction}
            </Link>
          </div>
        )}
      </main>

      {pickerOpen && (
        <ImportSourcePicker
          onClose={() => setPickerOpen(false)}
          onStatements={() => launcherRef.current?.open()}
        />
      )}

      <ImportLauncher ref={launcherRef} onFiles={files => setImportFiles(files)} />

      {importFiles && (
        <ImportModal
          accounts={accounts}
          categories={categories}
          allTags={allTags}
          initialFiles={importFiles}
          onClose={() => setImportFiles(null)}
          onSuccess={handleImportSuccess}
        />
      )}

      {toast && (
        <div className="toast">
          <span>{toast}</span>
          <button className="toast-close" onClick={() => setToast(null)} aria-label={t.toastClose}>✕</button>
        </div>
      )}
    </>
  )
}
