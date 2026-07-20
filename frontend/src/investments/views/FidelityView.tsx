import { useState, useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import type {
  FidelityKpis, FidelityEvolution, FidelityLot,
  FidelityImportPreview, FidelityImportConfirmResult,
} from '../../api/types'
import {
  getFidelityKpis, getFidelityEvolution, getFidelityLots,
  fidelityImportPreview as callImportPreview,
  fidelityImportConfirm as callImportConfirm,
} from '../../api/client'
import { useT, langLocale } from '../../i18n'
import { useNotifications } from '../../contexts/NotificationsContext'

// ── Date helpers (mirrored from IndexaView) ────────────────────────────────────

function formatDDMMYYYY(isoDate: string): string {
  try {
    const parts = isoDate.split('-')
    if (parts.length < 3) return isoDate
    return `${parts[2]}/${parts[1]}/${parts[0]}`
  } catch {
    return isoDate
  }
}

// ── Evolution domain helpers (mirrored from IndexaView, EUR only) ─────────────

function niceStep(range: number): number {
  if (range > 50000) return 5000
  if (range > 10000) return 1000
  if (range > 5000)  return 500
  if (range > 1000)  return 200
  if (range > 500)   return 100
  return 50
}

function niceFloor(value: number, step: number): number {
  return Math.floor(value / step) * step
}

function niceCeil(value: number, step: number): number {
  return Math.ceil(value / step) * step
}

// ── Types ─────────────────────────────────────────────────────────────────────

type EvolutionPeriod = string
type WizStep = 'upload' | 'preview' | 'confirming' | 'done'
type LotsSortCol = 'date' | 'source' | 'shares' | 'costPerShare' | 'totalCost' | 'currentValue' | 'gain' | 'gainPct'

const LOTS_PAGE_SIZE = 15

// ── Component ─────────────────────────────────────────────────────────────────

export default function FidelityView() {
  const { t, lang, formatCurrency } = useT()
  const locale = langLocale(lang)
  const { notifications } = useNotifications()

  // ── Data state ─────────────────────────────────────────────────────────────
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)
  const [kpis, setKpis]           = useState<FidelityKpis | null>(null)
  const [evolution, setEvolution] = useState<FidelityEvolution | null>(null)
  const [lots, setLots]           = useState<FidelityLot[]>([])

  // ── Lots table: sort + pagination ─────────────────────────────────────────
  const [lotsSortCol, setLotsSortCol] = useState<LotsSortCol>('date')
  const [lotsSortDir, setLotsSortDir] = useState<'asc' | 'desc'>('desc')
  const [lotsPage,    setLotsPage]    = useState(0)

  // ── Tooltip portal (same pattern as IndexaView) ───────────────────────────
  const [openTip, setOpenTip] = useState<{ text: string; x: number; y: number } | null>(null)

  // ── Evolution chart state ──────────────────────────────────────────────────
  const [evPeriod, setEvPeriod] = useState<EvolutionPeriod>('Todo')

  // ── Import wizard state ────────────────────────────────────────────────────
  const [importOpen, setImportOpen]           = useState(false)
  const [wizStep, setWizStep]                 = useState<WizStep>('upload')
  const [importFile, setImportFile]           = useState<File | null>(null)
  const [importPreview, setImportPreview]     = useState<FidelityImportPreview | null>(null)
  const [importError, setImportError]         = useState<string | null>(null)
  const [importLoading, setImportLoading]     = useState(false)
  const [importResult, setImportResult]       = useState<FidelityImportConfirmResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Load all data ──────────────────────────────────────────────────────────
  function loadAll() {
    setLoading(true)
    setError(null)
    Promise.all([
      getFidelityKpis(),
      getFidelityEvolution(),
      getFidelityLots(),
    ])
      .then(([kpisData, evolutionData, lotsData]) => {
        setKpis(kpisData)
        setEvolution(evolutionData)
        setLots(lotsData.lots)
        setLoading(false)
      })
      .catch(err => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }

  useEffect(() => {
    loadAll()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Dynamic year buttons from first lot to current year ───────────────────
  const evolutionYears = useMemo((): string[] => {
    if (!evolution?.value_series?.length) return []
    const firstYear = parseInt(evolution.value_series[0].date.slice(0, 4), 10)
    const lastYear  = new Date().getFullYear()
    return Array.from({ length: lastYear - firstYear + 1 }, (_, i) => String(firstYear + i))
  }, [evolution])

  // ── Lots: sorted + paginated ──────────────────────────────────────────────
  const sortedLots = useMemo(() => {
    const data = [...lots]
    const dir = lotsSortDir === 'asc' ? 1 : -1
    data.sort((a, b) => {
      switch (lotsSortCol) {
        case 'date':         return dir * a.purchase_date.localeCompare(b.purchase_date)
        case 'source':       return dir * a.share_source.localeCompare(b.share_source)
        case 'shares':       return dir * (a.shares - b.shares)
        case 'costPerShare': return dir * (a.cost_basis_per_share_eur - b.cost_basis_per_share_eur)
        case 'totalCost':    return dir * (a.cost_basis_total_eur - b.cost_basis_total_eur)
        case 'currentValue':
          if (a.current_value_eur == null && b.current_value_eur == null) return 0
          if (a.current_value_eur == null) return 1
          if (b.current_value_eur == null) return -1
          return dir * (a.current_value_eur - b.current_value_eur)
        case 'gain':
          if (a.gain_loss_eur == null && b.gain_loss_eur == null) return 0
          if (a.gain_loss_eur == null) return 1
          if (b.gain_loss_eur == null) return -1
          return dir * (a.gain_loss_eur - b.gain_loss_eur)
        case 'gainPct':
          if (a.gain_loss_pct == null && b.gain_loss_pct == null) return 0
          if (a.gain_loss_pct == null) return 1
          if (b.gain_loss_pct == null) return -1
          return dir * (a.gain_loss_pct - b.gain_loss_pct)
        default: return 0
      }
    })
    return data
  }, [lots, lotsSortCol, lotsSortDir])

  const lotsPageCount = Math.ceil(sortedLots.length / LOTS_PAGE_SIZE)

  const pageLots = useMemo(
    () => sortedLots.slice(lotsPage * LOTS_PAGE_SIZE, (lotsPage + 1) * LOTS_PAGE_SIZE),
    [sortedLots, lotsPage],
  )

  function handleLotsSortClick(col: LotsSortCol) {
    setLotsPage(0)
    if (col === lotsSortCol) {
      setLotsSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setLotsSortCol(col)
      setLotsSortDir('desc')
    }
  }

  function LotsSortArrow({ col }: { col: LotsSortCol }) {
    if (col !== lotsSortCol) return null
    return <span aria-hidden="true">{lotsSortDir === 'asc' ? ' ▲' : ' ▼'}</span>
  }

  // ── Evolution data: period-filtered with carry-forward contributions ───────
  const evolutionData = useMemo(() => {
    if (!evolution?.value_series?.length) return []

    // Sort contributions ascending for carry-forward logic
    const sortedContribs = [...(evolution.contributions_series ?? [])]
      .sort((a, b) => a.date.localeCompare(b.date))
    const contribByDate = new Map(sortedContribs.map(c => [c.date, c.value]))

    const now    = new Date()
    const cutoff: Date | null = (() => {
      if (evPeriod === '1M') return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
      if (evPeriod === '3M') return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate())
      if (evPeriod === '1A') return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate())
      return null
    })()

    const filtered = evolution.value_series.filter(pt => {
      if (evPeriod !== 'Todo' && evPeriod.length === 4) return pt.date.startsWith(evPeriod)
      if (cutoff) return new Date(pt.date) >= cutoff
      return true
    })

    if (filtered.length === 0) return []

    // Seed carry-forward: last known contribution before filter window
    let lastContrib: number | null = null
    for (const c of sortedContribs) {
      if (c.date <= filtered[0].date) lastContrib = c.value
      else break
    }

    return filtered.map(pt => {
      if (contribByDate.has(pt.date)) {
        lastContrib = contribByDate.get(pt.date)!
      }
      return {
        date:          pt.date,
        value:         pt.value,
        contributions: lastContrib,
      }
    })
  }, [evolution, evPeriod])

  // ── Evolution Y-axis domain ────────────────────────────────────────────────
  const evolutionDomain = useMemo((): [number, number] => {
    if (evolutionData.length === 0) return [0, 100]
    const values: number[] = []
    for (const pt of evolutionData) {
      values.push(pt.value)
      if (pt.contributions != null) values.push(pt.contributions)
    }
    const minVal = Math.min(...values)
    const maxVal = Math.max(...values)
    const pad  = minVal === maxVal
      ? Math.abs(minVal) * 0.1 || 500
      : (maxVal - minVal) * 0.08
    const step = niceStep(maxVal - minVal + pad * 2)
    return [niceFloor(minVal - pad, step), niceCeil(maxVal + pad, step)]
  }, [evolutionData])

  // ── Period selector buttons ────────────────────────────────────────────────
  const FIXED_PERIODS: Array<{ id: EvolutionPeriod; label: string }> = [
    { id: '1M', label: t.invPeriod1M },
    { id: '3M', label: t.invPeriod3M },
    { id: '1A', label: t.invPeriod1A },
  ]

  // ── Import wizard helpers ──────────────────────────────────────────────────
  function resetImport() {
    setWizStep('upload')
    setImportFile(null)
    setImportPreview(null)
    setImportError(null)
    setImportLoading(false)
    setImportResult(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function openImport() {
    resetImport()
    setImportOpen(true)
  }

  function closeImport() {
    setImportOpen(false)
    resetImport()
  }

  async function handlePreview() {
    if (!importFile) return
    setImportLoading(true)
    setImportError(null)
    try {
      const preview = await callImportPreview(importFile)
      setImportPreview(preview)
      setWizStep('preview')
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err))
    } finally {
      setImportLoading(false)
    }
  }

  async function handleConfirm() {
    if (!importFile) return
    setWizStep('confirming')
    setImportError(null)
    try {
      const result = await callImportConfirm(importFile)
      setImportResult(result)
      setWizStep('done')
      loadAll()
    } catch (err) {
      setImportError(err instanceof Error ? err.message : String(err))
      setWizStep('preview')
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.fidelityTitle}</h1>
        </div>
        <div className="card">
          <div className="state-box">
            <span className="icon">⏳</span>
            <span>{t.loading}</span>
          </div>
        </div>
      </main>
    )
  }

  // ── Error state ────────────────────────────────────────────────────────────
  if (error) {
    return (
      <main className="dashboard">
        <div className="investments-header">
          <h1 className="investments-page-title">{t.fidelityTitle}</h1>
        </div>
        <div className="card">
          <div className="state-box error">
            <span className="icon">⚠️</span>
            <span>{t.invErrorLoading}: {error}</span>
          </div>
        </div>
      </main>
    )
  }

  const isEmpty = lots.length === 0 && kpis === null

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <main className="dashboard">

      {/* Page header */}
      <div className="investments-header">
        <h1 className="investments-page-title">{t.fidelityTitle}</h1>
        <button className="btn-primary" type="button" onClick={openImport}>
          {t.fidelityImportBtn}
        </button>
      </div>

      {(() => {
        const activeEspp = notifications.find(n => n.source === 'espp')
        if (!activeEspp) return null
        const period = typeof activeEspp.title_args.period === 'string' ? activeEspp.title_args.period : null
        return (
          <div className="espp-reminder-banner" role="alert">
            <span>⚠ {t.esppReminderBanner(period)}</span>
            <Link to="/investments/fidelity-espp" className="espp-reminder-banner__link">
              {t.esppReminderAction}
            </Link>
          </div>
        )
      })()}

      {isEmpty ? (

        /* ── Empty state ── */
        <div className="card investments-holdings-card">
          <div className="investments-empty">
            <span className="investments-empty__icon" aria-hidden="true">💼</span>
            <p className="investments-empty__text">{t.fidelityEmptyTitle}</p>
            <button className="btn-primary" type="button" onClick={openImport}>
              {t.fidelityImportBtn}
            </button>
          </div>
        </div>

      ) : (
        <>
          {/* ── Account header strip ── */}
          <div className="inv-account-header">
            <div className="inv-account-header__left">
              <span className="inv-account-header__icon" aria-hidden="true">💼</span>
              <span className="inv-account-header__label">Fidelity ESPP – MSFT</span>
              {kpis?.as_of_date && (
                <span className="inv-account-header__updated">
                  {t.fidelityAsOf(formatDDMMYYYY(kpis.as_of_date))}
                </span>
              )}
            </div>
            {kpis?.price_stale && (
              <span className="inv-account-header__updated inv-account-header__updated--stale" role="alert">
                ⚠ {t.fidelityPriceStale}
              </span>
            )}
          </div>

          {/* ── KPI cards ── */}
          <div className="kpi-grid">

            {/* 1. Total MSFT shares */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiShares}</div>
              <div className="kpi-value">
                {kpis != null
                  ? `${new Intl.NumberFormat(locale, { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(kpis.total_shares)} MSFT`
                  : '—'}
              </div>
              <div className="kpi-sub">
                {kpis != null ? t.fidelityKpiSharesSub(lots.length) : ''}
              </div>
            </div>

            {/* 2. Invested (EUR cost basis) */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiInvested}</div>
              <div className="kpi-value">
                {kpis != null ? formatCurrency(kpis.invested_eur) : '—'}
              </div>
            </div>

            {/* 3. Current value */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiCurrentValue}</div>
              <div className="kpi-value">
                {kpis?.current_value_eur != null ? formatCurrency(kpis.current_value_eur) : '—'}
              </div>
              {kpis?.msft_price_usd != null && kpis.usd_eur_rate != null && (
                <div className="kpi-sub">
                  {t.fidelityPriceInfo(kpis.msft_price_usd, kpis.usd_eur_rate)}
                </div>
              )}
            </div>

            {/* 4. Gain / Loss */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiGainLoss}</div>
              <div className={`kpi-value${kpis?.gain_loss_eur != null ? (kpis.gain_loss_eur >= 0 ? ' net-pos' : ' net-neg') : ''}`}>
                {kpis?.gain_loss_eur != null
                  ? `${kpis.gain_loss_eur >= 0 ? '+' : ''}${formatCurrency(kpis.gain_loss_eur)}`
                  : '—'}
              </div>
              {kpis?.gain_loss_pct != null && (
                <div className={`kpi-sub${kpis.gain_loss_pct >= 0 ? ' kpi-sub--pos' : ' kpi-sub--neg'}`}>
                  {kpis.gain_loss_pct >= 0 ? '+' : ''}{kpis.gain_loss_pct.toFixed(2)}%
                </div>
              )}
            </div>

          </div>

          {/* ── Evolution chart ── */}
          <div className="card inv-evolution-card">

            <div className="inv-evolution-header">
              <h3 className="card-title">{t.fidelityEvolutionTitle}</h3>
              <div className="inv-evolution-controls">
                <div className="inv-period-selector">
                  {FIXED_PERIODS.map(p => (
                    <button
                      key={p.id}
                      type="button"
                      className={`inv-period-btn${evPeriod === p.id ? ' inv-period-btn--active' : ''}`}
                      onClick={() => setEvPeriod(p.id)}
                    >{p.label}</button>
                  ))}
                  {evolutionYears.map(y => (
                    <button
                      key={y}
                      type="button"
                      className={`inv-period-btn${evPeriod === y ? ' inv-period-btn--active' : ''}`}
                      onClick={() => setEvPeriod(y)}
                    >{y}</button>
                  ))}
                  <button
                    type="button"
                    className={`inv-period-btn${evPeriod === 'Todo' ? ' inv-period-btn--active' : ''}`}
                    onClick={() => setEvPeriod('Todo')}
                  >{t.invPeriodTodo}</button>
                </div>
              </div>
            </div>

            {evolutionData.length === 0 ? (
              <div className="state-box">
                <span className="icon">📈</span>
                <span>{t.noDataPeriod}</span>
              </div>
            ) : (
              <>
                <div className="inv-evolution-chart-wrap">
                  <ResponsiveContainer width="100%" height={360}>
                    <LineChart data={evolutionData} margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(isoDate: string) =>
                          new Date(isoDate).toLocaleDateString(locale, { month: 'short', year: '2-digit' })
                        }
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        tickLine={false}
                        axisLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        domain={evolutionDomain}
                        tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k€`}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        width={52}
                      />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                        labelStyle={{ color: 'var(--text)' }}
                        itemStyle={{ color: 'var(--text)' }}
                        labelFormatter={(isoDate: string) => formatDDMMYYYY(isoDate)}
                        formatter={(value: number, name: string) => [
                          formatCurrency(value),
                          name === 'value' ? t.fidelityLegendPortfolio : t.fidelityLegendInvested,
                        ]}
                      />
                      {/* Portfolio value — primary colour, solid */}
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="var(--primary)"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 4, fill: 'var(--primary)' }}
                        connectNulls
                      />
                      {/* Contributions (invested) — muted, step-after dashed */}
                      <Line
                        type="stepAfter"
                        dataKey="contributions"
                        stroke="var(--text-muted)"
                        strokeWidth={1.5}
                        strokeDasharray="5 3"
                        dot={false}
                        activeDot={false}
                        connectNulls
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Chart legend */}
                <div className="inv-chart-legend">
                  <span className="inv-chart-legend-item">
                    <span className="inv-chart-legend-swatch" style={{ background: 'var(--primary)' }} />
                    <span>{t.fidelityLegendPortfolio}</span>
                  </span>
                  <span className="inv-chart-legend-item">
                    <span
                      className="inv-chart-legend-swatch"
                      style={{
                        background: 'var(--text-muted)',
                        backgroundImage: 'repeating-linear-gradient(90deg, var(--text-muted) 0 5px, transparent 5px 8px)',
                      }}
                    />
                    <span>{t.fidelityLegendInvested}</span>
                  </span>
                </div>
              </>
            )}

          </div>

          {/* ── Lots table ── */}
          <div className="card inv-holdings-card">
            <div className="card-title card-title--has-action">
              <span>{t.fidelityTitle}</span>
              <span className="kpi-sub">{t.fidelityKpiSharesSub(lots.length)}</span>
            </div>
            {lots.length === 0 ? (
              <div className="state-box">
                <span className="icon">📋</span>
                <span>{t.noDataPeriod}</span>
              </div>
            ) : (
              <div className="inv-holdings-table-wrap">
                <table className="inv-holdings-table">
                  <thead>
                    <tr>
                      <th
                        className={`inv-th-sortable${lotsSortCol === 'date' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('date')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('date')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'date' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColDate}<LotsSortArrow col="date" /></th>
                      <th
                        className={`inv-th-sortable${lotsSortCol === 'source' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('source')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('source')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'source' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColSource}<LotsSortArrow col="source" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'shares' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('shares')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('shares')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'shares' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColShares}<LotsSortArrow col="shares" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'costPerShare' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('costPerShare')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('costPerShare')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'costPerShare' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColCostPerShare}<LotsSortArrow col="costPerShare" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'totalCost' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('totalCost')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('totalCost')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'totalCost' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColTotalCost}<LotsSortArrow col="totalCost" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'currentValue' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('currentValue')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('currentValue')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'currentValue' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColCurrentValue}<LotsSortArrow col="currentValue" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'gain' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('gain')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('gain')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'gain' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColGain}<LotsSortArrow col="gain" /></th>
                      <th
                        className={`inv-th-num inv-th-sortable${lotsSortCol === 'gainPct' ? ' inv-th-sort-active' : ''}`}
                        onClick={() => handleLotsSortClick('gainPct')}
                        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && handleLotsSortClick('gainPct')}
                        tabIndex={0} role="columnheader"
                        aria-sort={lotsSortCol === 'gainPct' ? (lotsSortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                      >{t.fidelityColGainPct}<LotsSortArrow col="gainPct" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageLots.map(lot => {
                      const isPos   = lot.gain_loss_eur != null && lot.gain_loss_eur >= 0
                      const gainCls = lot.gain_loss_eur != null
                        ? (isPos ? 'inv-pnl--pos' : 'inv-pnl--neg')
                        : ''
                      return (
                        <tr key={lot.id}>
                          <td>{formatDDMMYYYY(lot.purchase_date)}</td>
                          <td>
                            <span
                              className={`fid-source-badge fid-source-badge--${lot.share_source.toLowerCase()}`}
                              tabIndex={0}
                              onMouseEnter={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip, x: r.left + r.width / 2, y: r.top }) }}
                              onFocus={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip, x: r.left + r.width / 2, y: r.top }) }}
                              onMouseLeave={() => setOpenTip(null)}
                              onBlur={() => setOpenTip(null)}
                            >
                              {lot.share_source}
                            </span>
                          </td>
                          <td className="inv-td-num">
                            {new Intl.NumberFormat(locale, {
                              minimumFractionDigits: 3,
                              maximumFractionDigits: 3,
                            }).format(lot.shares)}
                          </td>
                          <td className="inv-td-num">{formatCurrency(lot.cost_basis_per_share_eur)}</td>
                          <td className="inv-td-num">{formatCurrency(lot.cost_basis_total_eur)}</td>
                          <td className="inv-td-num">
                            {lot.current_value_eur != null ? formatCurrency(lot.current_value_eur) : '—'}
                          </td>
                          <td className={`inv-td-num ${gainCls}`}>
                            {lot.gain_loss_eur != null
                              ? `${isPos ? '+' : ''}${formatCurrency(lot.gain_loss_eur)}`
                              : '—'}
                          </td>
                          <td className={`inv-td-num ${gainCls}`}>
                            {lot.gain_loss_pct != null
                              ? `${isPos ? '+' : ''}${lot.gain_loss_pct.toFixed(2)}%`
                              : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
                {lotsPageCount > 1 && (
                  <div className="pagination">
                    <button
                      type="button"
                      onClick={() => setLotsPage(p => Math.max(0, p - 1))}
                      disabled={lotsPage === 0}
                    >{t.tablePrev}</button>
                    <span>{t.tablePaginationInfo(lotsPage * LOTS_PAGE_SIZE + 1, Math.min((lotsPage + 1) * LOTS_PAGE_SIZE, sortedLots.length), sortedLots.length)}</span>
                    <button
                      type="button"
                      onClick={() => setLotsPage(p => Math.min(lotsPageCount - 1, p + 1))}
                      disabled={lotsPage >= lotsPageCount - 1}
                    >{t.tableNext}</button>
                  </div>
                )}
              </div>
            )}
          </div>

        </>
      )}

      {/* ── Import wizard modal ── */}
      {importOpen && createPortal(
        <div
          className="modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="fid-import-title"
        >
          <div className="modal">

            <div className="modal-header">
              <span className="modal-title" id="fid-import-title">{t.fidelityImportTitle}</span>
              <button
                className="modal-close"
                type="button"
                onClick={closeImport}
                aria-label={t.modalClose}
              >✕</button>
            </div>

            <div className="modal-body">

              {/* Step 1: Upload CSV */}
              {wizStep === 'upload' && (
                <div className="inv-wizard__body">
                  <span className="inv-wizard__logo" aria-hidden="true">📂</span>
                  <h2 className="inv-wizard__title">{t.fidelityImportTitle}</h2>
                  <p className="inv-wizard__desc">{t.fidelityImportStep1Hint}</p>
                  <div className="inv-wizard__token-field">
                    <label className="inv-wizard__token-label">
                      CSV
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
                      <label className="backup-file-label">
                        <span className="btn-primary">{t.fidelityImportCta}</span>
                        <input
                          ref={fileInputRef}
                          id="fid-csv-file"
                          type="file"
                          accept=".csv"
                          className="backup-file-input"
                          onChange={e => setImportFile(e.target.files?.[0] ?? null)}
                        />
                      </label>
                      {importFile && (
                        <span className="kpi-sub" style={{ fontSize: '0.82rem' }}>
                          {importFile.name}
                        </span>
                      )}
                    </div>
                  </div>
                  {importError && (
                    <div className="inv-wizard__error-banner" role="alert">
                      <span className="inv-wizard__error-banner-icon" aria-hidden="true">⚠️</span>
                      <span>{importError}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Step 2: Preview */}
              {wizStep === 'preview' && importPreview && (
                <div>
                  <p style={{ marginBottom: 12, fontWeight: 600 }}>
                    {t.fidelityImportPreviewTitle}
                  </p>
                  <p className="kpi-sub" style={{ marginBottom: 16 }}>
                    {t.fidelityImportNewLots(importPreview.new_lots.length)}
                    {importPreview.duplicate_count > 0
                      ? ` · ${t.fidelityImportDuplicates(importPreview.duplicate_count)}`
                      : ''}
                  </p>
                  {importPreview.new_lots.length > 0 && (
                    <div className="inv-holdings-table-wrap" style={{ maxHeight: 320, overflowY: 'auto', marginBottom: 16 }}>
                      <table className="inv-holdings-table">
                        <thead>
                          <tr>
                            <th>{t.fidelityColDate}</th>
                            <th>{t.fidelityColSource}</th>
                            <th className="inv-th-num">{t.fidelityColShares}</th>
                            <th className="inv-th-num">{t.fidelityColCostPerShare}</th>
                            <th className="inv-th-num">{t.fidelityColTotalCost}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {importPreview.new_lots.map((lot, i) => (
                            <tr key={i}>
                              <td>{formatDDMMYYYY(lot.purchase_date)}</td>
                              <td>
                                <span
                                  className={`fid-source-badge fid-source-badge--${lot.share_source.toLowerCase()}`}
                                  tabIndex={0}
                                  onMouseEnter={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip, x: r.left + r.width / 2, y: r.top }) }}
                                  onFocus={e => { const r = e.currentTarget.getBoundingClientRect(); setOpenTip({ text: lot.share_source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip, x: r.left + r.width / 2, y: r.top }) }}
                                  onMouseLeave={() => setOpenTip(null)}
                                  onBlur={() => setOpenTip(null)}
                                >
                                  {lot.share_source}
                                </span>
                              </td>
                              <td className="inv-td-num">
                                {new Intl.NumberFormat(locale, {
                                  minimumFractionDigits: 3,
                                  maximumFractionDigits: 3,
                                }).format(lot.shares)}
                              </td>
                              <td className="inv-td-num">{formatCurrency(lot.cost_basis_per_share_eur)}</td>
                              <td className="inv-td-num">{formatCurrency(lot.cost_basis_total_eur)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {importError && (
                    <div className="inv-wizard__error-banner" role="alert">
                      <span className="inv-wizard__error-banner-icon" aria-hidden="true">⚠️</span>
                      <span>{importError}</span>
                    </div>
                  )}
                </div>
              )}

              {/* Step 3: Confirming */}
              {wizStep === 'confirming' && (
                <div className="spinner-wrap">
                  <div className="spinner" role="status" aria-label={t.fidelityImportConfirmingBtn} />
                  <p className="spinner-label">{t.fidelityImportConfirmingBtn}</p>
                </div>
              )}

              {/* Step 4: Done */}
              {wizStep === 'done' && importResult && (
                <div className="inv-wizard__success">
                  <span className="inv-wizard__success-icon" aria-hidden="true">✅</span>
                  <h2 className="inv-wizard__success-title">{t.fidelityImportSuccessTitle}</h2>
                  <p className="inv-wizard__success-desc">
                    {t.fidelityImportSuccessSub(importResult.inserted, importResult.duplicates)}
                  </p>
                </div>
              )}

            </div>

            {/* Footer buttons */}
            <div className="modal-footer">
              {wizStep === 'upload' && (
                <>
                  <button className="btn-secondary" type="button" onClick={closeImport}>
                    {t.modalBtnCancel}
                  </button>
                  <button
                    className="btn-primary"
                    type="button"
                    disabled={!importFile || importLoading}
                    onClick={handlePreview}
                  >
                    {importLoading ? t.loading : t.fidelityImportConfirmBtn}
                  </button>
                </>
              )}
              {wizStep === 'preview' && (
                <>
                  <button className="btn-secondary" type="button" onClick={() => setWizStep('upload')}>
                    {t.wizardBack}
                  </button>
                  <button className="btn-primary" type="button" onClick={handleConfirm}>
                    {t.fidelityImportConfirmBtn}
                  </button>
                </>
              )}
              {wizStep === 'done' && (
                <button className="btn-primary" type="button" onClick={closeImport}>
                  {t.wizardClose}
                </button>
              )}
            </div>

          </div>
        </div>,
        document.body,
      )}

      {openTip && createPortal(
        <div
          role="tooltip"
          style={{
            position: 'fixed',
            left: openTip.x,
            top: openTip.y - 10,
            transform: 'translate(-50%, -100%)',
            zIndex: 4000,
            pointerEvents: 'none',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            borderRadius: '8px',
            boxShadow: '0 4px 16px rgba(0,0,0,0.16)',
            padding: '10px 12px',
            maxWidth: '240px',
            width: 'max-content',
            fontSize: '12px',
            lineHeight: 1.5,
            color: 'var(--text-muted)',
            textAlign: 'left',
            fontWeight: 400,
            whiteSpace: 'normal',
          }}
        >
          {openTip.text}
        </div>,
        document.body,
      )}

    </main>
  )
}
