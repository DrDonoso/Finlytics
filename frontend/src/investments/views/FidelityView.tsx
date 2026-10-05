import { useState, useMemo, useRef } from 'react'
import type { FocusEvent, MouseEvent } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { useQueryClient } from '@tanstack/react-query'
import type {
  FidelityLot,
  FidelityImportPreview, FidelityImportConfirmResult,
} from '../../api/types'
import {
  fidelityImportPreview as callImportPreview,
  fidelityImportConfirm as callImportConfirm,
} from '../../api/client'
import { queryKeys, useFidelityEvolution, useFidelityKpis, useFidelityLots } from '../../api/queries'
import { useT, langLocale } from '../../i18n'
import { IS_DEMO } from '../../demo/config'
import { useNotifications } from '../../contexts/NotificationsContext'
import { IconLoading, IconAlert, IconBriefcase, IconChartLine, IconReceipt, IconClose, IconFolder, IconCheck, IconArrowLeft, IconArrowRight } from '../../components/icons'
import SortableTh from '../../components/SortableTh'
import Money, { Percent, Private } from '../../components/Money'
import CardHeader from '../../components/CardHeader'
import Modal from '../../components/Modal'

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
const NO_LOTS: FidelityLot[] = []

interface Tip { text: string; x: number; y: number }

function SourceBadge({ source, onTip }: { source: string; onTip: (tip: Tip | null) => void }) {
  const { t } = useT()
  const show = (e: MouseEvent<HTMLElement> | FocusEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect()
    onTip({
      text: source === 'SP' ? t.fidelitySourceSpTooltip : t.fidelitySourceDoTooltip,
      x: r.left + r.width / 2,
      y: r.top,
    })
  }
  return (
    <span
      className={`fid-source-badge fid-source-badge--${source.toLowerCase()}`}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a tooltip trigger: focus is how keyboard users reveal the explanation
      tabIndex={0}
      onMouseEnter={show}
      onFocus={show}
      onMouseLeave={() => onTip(null)}
      onBlur={() => onTip(null)}
    >
      {source}
    </span>
  )
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function FidelityView() {
  const { t, lang, formatCurrency, formatCompactCurrency, formatNumber } = useT()
  const locale = langLocale(lang)
  const { notifications } = useNotifications()

  // ── Data state ─────────────────────────────────────────────────────────────
  const queryClient    = useQueryClient()
  const kpisQuery      = useFidelityKpis()
  const evolutionQuery = useFidelityEvolution()
  const lotsQuery      = useFidelityLots()
  const kpis      = kpisQuery.data ?? null
  const evolution = evolutionQuery.data ?? null
  const lots      = lotsQuery.data?.lots ?? NO_LOTS
  const loading   = kpisQuery.isPending || evolutionQuery.isPending || lotsQuery.isPending
  const loadError = kpisQuery.error ?? evolutionQuery.error ?? lotsQuery.error
  const error     = loadError ? (loadError instanceof Error ? loadError.message : String(loadError)) : null

  // ── Lots table: sort + pagination ─────────────────────────────────────────
  const [lotsSortCol, setLotsSortCol] = useState<LotsSortCol>('date')
  const [lotsSortDir, setLotsSortDir] = useState<'asc' | 'desc'>('desc')
  const [lotsPage,    setLotsPage]    = useState(0)

  // ── Tooltip portal (same pattern as IndexaView) ───────────────────────────
  const [openTip, setOpenTip] = useState<Tip | null>(null)

  // ── Evolution chart state ──────────────────────────────────────────────────
  const [evPeriod, setEvPeriod] = useState<EvolutionPeriod>('All')

  // ── Import wizard state ────────────────────────────────────────────────────
  const [importOpen, setImportOpen]           = useState(false)
  const [wizStep, setWizStep]                 = useState<WizStep>('upload')
  const [importFile, setImportFile]           = useState<File | null>(null)
  const [importPreview, setImportPreview]     = useState<FidelityImportPreview | null>(null)
  const [importError, setImportError]         = useState<string | null>(null)
  const [importLoading, setImportLoading]     = useState(false)
  const [importResult, setImportResult]       = useState<FidelityImportConfirmResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  function lotsHeader(col: LotsSortCol, label: string) {
    return (
      <SortableTh
        label={label}
        active={col === lotsSortCol}
        direction={lotsSortDir}
        onSort={() => handleLotsSortClick(col)}
        className={col === 'date' || col === 'source' ? undefined : 'inv-th-num'}
      />
    )
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
      if (evPeriod !== 'All' && evPeriod.length === 4) return pt.date.startsWith(evPeriod)
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
    setOpenTip(null)
    resetImport()
    setImportOpen(true)
  }

  function closeImport() {
    setOpenTip(null)
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
      // The combined overview and the connection list move with the lots, so refresh the whole investments tree.
      void queryClient.invalidateQueries({ queryKey: ['investments'] })
      void queryClient.invalidateQueries({ queryKey: queryKeys.connections })
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
            <IconLoading size={18} />
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
            <IconAlert size={18} />
            <span>{t.invErrorLoading}: {error}</span>
          </div>
        </div>
      </main>
    )
  }

  const isEmpty = lots.length === 0 && kpis === null
  const importBusy = wizStep === 'confirming' || importLoading
  const tooltip = openTip && (
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
    </div>
  )

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <main className="dashboard">

      {/* Page header */}
      <div className="investments-header">
        <h1 className="investments-page-title">{t.fidelityTitle}</h1>
        {/* CSV import uploads a file and writes lots — not available in the demo. */}
        {!IS_DEMO && (
          <button className="btn-primary" type="button" onClick={openImport}>
            {t.fidelityImportBtn}
          </button>
        )}
      </div>

      {(() => {
        const activeEspp = notifications.find(n => n.source === 'espp')
        if (!activeEspp) return null
        const period = typeof activeEspp.title_args.period === 'string' ? activeEspp.title_args.period : null
        return (
          <div className="espp-reminder-banner" role="alert">
            <span><IconAlert size={15} /> {t.esppReminderBanner(period)}</span>
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
            <span className="investments-empty__icon" aria-hidden="true"><IconBriefcase size={28} /></span>
            <p className="investments-empty__text">{t.fidelityEmptyTitle}</p>
            {!IS_DEMO && (
              <button className="btn-primary" type="button" onClick={openImport}>
                {t.fidelityImportBtn}
              </button>
            )}
          </div>
        </div>

      ) : (
        <>
          {/* ── Account header strip ── */}
          <div className="inv-account-header">
            <div className="inv-account-header__left">
              <span className="inv-account-header__icon" aria-hidden="true"><IconBriefcase size={18} /></span>
              <span className="inv-account-header__label">Fidelity ESPP – MSFT</span>
              {kpis?.as_of_date && (
                <span className="inv-account-header__updated">
                  {t.fidelityAsOf(formatDDMMYYYY(kpis.as_of_date))}
                </span>
              )}
            </div>
            {kpis?.price_stale && (
              <span className="inv-account-header__updated inv-account-header__updated--stale" role="alert">
                <IconAlert size={14} /> {t.fidelityPriceStale}
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
                  ? <><Private>{new Intl.NumberFormat(locale, { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(kpis.total_shares)}</Private> MSFT</>
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
                {kpis != null ? <Money value={kpis.invested_eur} /> : '—'}
              </div>
            </div>

            {/* 3. Current value */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiCurrentValue}</div>
              <div className="kpi-value">
                {kpis?.current_value_eur != null ? <Money value={kpis.current_value_eur} /> : '—'}
              </div>
              {kpis?.msft_price_usd != null && kpis.usd_eur_rate != null && (
                <div className="kpi-sub">
                  {t.fidelityPriceInfo(
                    formatNumber(kpis.msft_price_usd, { decimals: 2 }),
                    formatNumber(kpis.usd_eur_rate, { decimals: 4 }),
                  )}
                </div>
              )}
            </div>

            {/* 4. Gain / Loss */}
            <div className="kpi-card">
              <div className="kpi-label">{t.fidelityKpiGainLoss}</div>
              <div className={`kpi-value${kpis?.gain_loss_eur != null ? (kpis.gain_loss_eur >= 0 ? ' net-pos' : ' net-neg') : ''}`}>
                {kpis?.gain_loss_eur != null
                  ? <Money value={kpis.gain_loss_eur} signed />
                  : '—'}
              </div>
              {kpis?.gain_loss_pct != null && (
                <div className={`kpi-sub${kpis.gain_loss_pct >= 0 ? ' kpi-sub--pos' : ' kpi-sub--neg'}`}>
                  <Percent value={kpis.gain_loss_pct} signed decimals={2} />
                </div>
              )}
            </div>

          </div>

          {/* ── Evolution chart ── */}
          <div className="card inv-evolution-card">

            <CardHeader
              className="inv-evolution-header"
              title={t.fidelityEvolutionTitle}
              action={
                <div className="inv-evolution-controls">
                  <div className="inv-period-selector">
                    {FIXED_PERIODS.map(p => (
                      <button
                        key={p.id}
                        type="button"
                        className={`inv-period-btn${evPeriod === p.id ? ' inv-period-btn--active' : ''}`}
                        aria-pressed={evPeriod === p.id}
                        onClick={() => setEvPeriod(p.id)}
                      >{p.label}</button>
                    ))}
                    {evolutionYears.map(y => (
                      <button
                        key={y}
                        type="button"
                        className={`inv-period-btn${evPeriod === y ? ' inv-period-btn--active' : ''}`}
                        aria-pressed={evPeriod === y}
                        onClick={() => setEvPeriod(y)}
                      >{y}</button>
                    ))}
                    <button
                      type="button"
                      className={`inv-period-btn${evPeriod === 'All' ? ' inv-period-btn--active' : ''}`}
                      aria-pressed={evPeriod === 'All'}
                      onClick={() => setEvPeriod('All')}
                    >{t.invPeriodAll}</button>
                  </div>
                </div>
              }
            />

            {evolutionData.length === 0 ? (
              <div className="state-box">
                <IconChartLine size={18} />
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
                        tickFormatter={(v: number) => formatCompactCurrency(v)}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        axisLine={false}
                        tickLine={false}
                        width="auto"
                      />
                      <Tooltip
                        contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                        labelStyle={{ color: 'var(--text)' }}
                        itemStyle={{ color: 'var(--text)' }}
                        labelFormatter={(label) => formatDDMMYYYY(String(label))}
                        formatter={(value, name) => [
                          formatCurrency(Number(value)),
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
            <CardHeader
              title={t.fidelityTitle}
              action={<span className="kpi-sub">{t.fidelityKpiSharesSub(lots.length)}</span>}
            />
            {lots.length === 0 ? (
              <div className="state-box">
                <IconReceipt size={18} />
                <span>{t.noDataPeriod}</span>
              </div>
            ) : (
              <div className="inv-holdings-table-wrap">
                <table className="inv-holdings-table">
                  <thead>
                    <tr>
                      {lotsHeader('date', t.fidelityColDate)}
                      {lotsHeader('source', t.fidelityColSource)}
                      {lotsHeader('shares', t.fidelityColShares)}
                      {lotsHeader('costPerShare', t.fidelityColCostPerShare)}
                      {lotsHeader('totalCost', t.fidelityColTotalCost)}
                      {lotsHeader('currentValue', t.fidelityColCurrentValue)}
                      {lotsHeader('gain', t.fidelityColGain)}
                      {lotsHeader('gainPct', t.fidelityColGainPct)}
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
                          <td><SourceBadge source={lot.share_source} onTip={setOpenTip} /></td>
                          <td className="inv-td-num">
                            <Private>{new Intl.NumberFormat(locale, {
                              minimumFractionDigits: 3,
                              maximumFractionDigits: 3,
                            }).format(lot.shares)}</Private>
                          </td>
                          <td className="inv-td-num"><Money value={lot.cost_basis_per_share_eur} /></td>
                          <td className="inv-td-num"><Money value={lot.cost_basis_total_eur} /></td>
                          <td className="inv-td-num">
                            {lot.current_value_eur != null ? <Money value={lot.current_value_eur} /> : '—'}
                          </td>
                          <td className={`inv-td-num ${gainCls}`}>
                            {lot.gain_loss_eur != null
                              ? <Money value={lot.gain_loss_eur} signed />
                              : '—'}
                          </td>
                          <td className={`inv-td-num ${gainCls}`}>
                            <Percent value={lot.gain_loss_pct} signed decimals={2} />
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
                    ><IconArrowLeft size={14} /> {t.tablePrev}</button>
                    <span>{t.tablePaginationInfo(lotsPage * LOTS_PAGE_SIZE + 1, Math.min((lotsPage + 1) * LOTS_PAGE_SIZE, sortedLots.length), sortedLots.length)}</span>
                    <button
                      type="button"
                      onClick={() => setLotsPage(p => Math.min(lotsPageCount - 1, p + 1))}
                      disabled={lotsPage >= lotsPageCount - 1}
                    >{t.tableNext} <IconArrowRight size={14} /></button>
                  </div>
                )}
              </div>
            )}
          </div>

        </>
      )}

      {/* ── Import wizard modal ── */}
      {importOpen && (
        <Modal onDismiss={closeImport} disabled={importBusy} labelledBy="fid-import-title">

            <div className="modal-header">
              <span className="modal-title" id="fid-import-title">{t.fidelityImportTitle}</span>
              <button
                className="modal-close"
                type="button"
                onClick={closeImport}
                disabled={importBusy}
                aria-label={t.modalClose}
              ><IconClose size={16} /></button>
            </div>

            <div className="modal-body">

              {/* Step 1: Upload CSV */}
              {wizStep === 'upload' && (
                <div className="inv-wizard__body">
                  <span className="inv-wizard__logo" aria-hidden="true"><IconFolder size={44} /></span>
                  <h2 className="inv-wizard__title">{t.fidelityImportTitle}</h2>
                  <p className="inv-wizard__desc">{t.fidelityImportStep1Hint}</p>
                  <div className="inv-wizard__token-field">
                    <span className="inv-wizard__token-label">CSV</span>
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
                      <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
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
                            // eslint-disable-next-line react/no-array-index-key -- one file may legitimately hold identical lots, so no field identifies a row; the preview never reorders
                            <tr key={i}>
                              <td>{formatDDMMYYYY(lot.purchase_date)}</td>
                              <td><SourceBadge source={lot.share_source} onTip={setOpenTip} /></td>
                              <td className="inv-td-num">
                                <Private>{new Intl.NumberFormat(locale, {
                                  minimumFractionDigits: 3,
                                  maximumFractionDigits: 3,
                                }).format(lot.shares)}</Private>
                              </td>
                              <td className="inv-td-num"><Money value={lot.cost_basis_per_share_eur} /></td>
                              <td className="inv-td-num"><Money value={lot.cost_basis_total_eur} /></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {importError && (
                    <div className="inv-wizard__error-banner" role="alert">
                      <span className="inv-wizard__error-banner-icon" aria-hidden="true"><IconAlert size={16} /></span>
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
                  <span className="inv-wizard__success-icon" aria-hidden="true"><IconCheck size={40} /></span>
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
                  <button className="btn-secondary" type="button" onClick={closeImport} disabled={importLoading}>
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

          {tooltip}
        </Modal>
      )}

      {!importOpen && tooltip && createPortal(tooltip, document.body)}

    </main>
  )
}
