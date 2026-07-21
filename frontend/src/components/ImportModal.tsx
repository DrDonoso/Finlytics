import { useState, useRef, useMemo, useEffect } from 'react'
import type {
  Account, Category, Tag,
  ImportTransaction, PreviewResponse, ConfirmRequest, ImportResult,
  ImportQualitySignal,
  ImportQualityRowFlag,
} from '../api/types'
import { previewImport, confirmImport, checkDuplicates } from '../api/client'
import { useT, type Dict, paletteColor } from '../i18n'
import ImportPreviewTable, { type EditRow } from './ImportPreviewTable'
import RuleFormModal from './RuleFormModal'
import { computeLiveImportQuality, type LiveImportQuality } from './importQuality'

const SOFT_CAP = 12
const HARD_CAP = 24

type BatchPhase = 'cap-exceeded' | 'extracting' | 'resolve' | 'preview' | 'confirming' | 'summary'
type ExtractStatus = 'pending' | 'running' | 'done' | 'error'
type ConfirmStatus = 'pending' | 'running' | 'done' | 'error'

interface FileItem {
  file: File
  extractStatus: ExtractStatus
  preview: PreviewResponse | null
  rows: EditRow[]
  extractError: string | null
  resolvedAccountName: string  // for no-IBAN files: user-typed/selected account
  confirmStatus: ConfirmStatus
  confirmResult: ImportResult | null
  confirmError: string | null
}

interface NewIbanEntry {
  iban: string
  masked: string
  name: string
  touched: boolean
  openingBalance: string
}

interface AccountGroup {
  key: string
  displayName: string
  maskedIban: string | null
  fileIndices: number[]
}

interface Props {
  accounts:     Account[]
  categories:   Category[]
  allTags:      Tag[]
  onClose:      () => void
  onSuccess:    (result: ImportResult) => void
  initialFiles: File[]
}

function friendlyError(e: unknown, t: Dict): string {
  const msg = e instanceof Error ? e.message : String(e)
  if (msg.includes('503')) return t.error503
  if (msg.includes('400')) return t.error400
  if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('network')) {
    return t.errorNetwork
  }
  return t.errorUnexpected(msg)
}

function toImportTxn(row: EditRow): ImportTransaction {
  return {
    transaction_date:    row.transaction_date,
    amount:              row.amount,
    currency:            row.currency,
    description:         row.description,
    raw_line:            row.raw_line,
    category:            row.category,
    category_confidence: row.category_confidence,
    account_ref:         row.account_ref,
    balance_after:       row.balance_after,
    tags:                row.tags,
    merchant:            row.merchant,
    detail:              row.detail,
    allow_duplicate:     row.allow_duplicate ?? false,
  }
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      resolve(result.split(',')[1] ?? '')
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function qualitySignalLabel(t: Dict, code: string): string {
  return t.importQualitySignalLabels[code] ?? t.importQualityUnknownSignal
}

function qualitySeverityLabel(t: Dict, severity: string): string {
  if (severity === 'error') return t.importQualitySeverityError
  if (severity === 'warning') return t.importQualitySeverityWarning
  return t.importQualitySeverityInfo
}

function duplicateRowCount(liveQuality: LiveImportQuality): number {
  return liveQuality.duplicateRowKeys.size
}

function mergedQualitySignals(liveQuality: LiveImportQuality): ImportQualitySignal[] {
  const duplicateCount = duplicateRowCount(liveQuality)
  const sourceSignals = liveQuality.quality.signals
  const hasDuplicateSignal = sourceSignals.some(signal => signal.code === 'intra_batch_duplicate')
  const signals = sourceSignals.map(signal =>
    signal.code === 'intra_batch_duplicate' && duplicateCount > 0
      ? { ...signal, count: duplicateCount }
      : signal
  )
  if (!hasDuplicateSignal && duplicateCount > 0) {
    signals.push({ code: 'intra_batch_duplicate', severity: 'info', count: duplicateCount })
  }
  return signals
}

function applyDuplicateOverrides(liveQuality: LiveImportQuality, rows: EditRow[]): LiveImportQuality {
  const overriddenKeys = new Set(rows.filter(row => row.allow_duplicate).map(row => row._key))
  if (overriddenKeys.size === 0) return liveQuality

  let removedIntraBatch = 0
  const rowFlags = liveQuality.quality.row_flags.filter(flag => {
    const rowKey = rows[flag.row_index]?._key
    const remove = flag.code === 'intra_batch_duplicate' && rowKey != null && overriddenKeys.has(rowKey)
    if (remove) removedIntraBatch += 1
    return !remove
  })

  const rowFlagsByKey = new Map<number, ImportQualityRowFlag[]>()
  for (const flag of rowFlags) {
    const rowKey = rows[flag.row_index]?._key
    if (rowKey == null) continue
    rowFlagsByKey.set(rowKey, [...(rowFlagsByKey.get(rowKey) ?? []), flag])
  }

  const dbDuplicateRowKeys = new Set([...liveQuality.dbDuplicateRowKeys].filter(key => !overriddenKeys.has(key)))
  const duplicateRowKeys = new Set([...liveQuality.duplicateRowKeys].filter(key => !overriddenKeys.has(key)))
  const flaggedRowKeys = new Set(duplicateRowKeys)
  for (const flag of rowFlags) {
    const rowKey = rows[flag.row_index]?._key
    if (rowKey != null) flaggedRowKeys.add(rowKey)
  }

  return {
    ...liveQuality,
    quality: {
      ...liveQuality.quality,
      summary: {
        ...liveQuality.quality.summary,
        warning_count: Math.max(0, liveQuality.quality.summary.warning_count - removedIntraBatch),
        flagged_row_count: new Set(rowFlags.map(flag => flag.row_index)).size,
      },
      signals: liveQuality.quality.signals
        .map(signal => signal.code === 'intra_batch_duplicate'
          ? { ...signal, count: Math.max(0, signal.count - removedIntraBatch) }
          : signal
        )
        .filter(signal => signal.count > 0),
      row_flags: rowFlags,
    },
    rowFlagsByKey,
    dbDuplicateRowKeys,
    duplicateRowKeys,
    flaggedRowKeys,
  }
}

function ImportQualityPanel({ liveQuality, t }: { liveQuality: LiveImportQuality; t: Dict }) {
  const quality = liveQuality.quality

  const duplicateCount = duplicateRowCount(liveQuality)
  const parts = [
    t.importQualityWarnings(quality.summary.warning_count),
    t.importQualityErrors(quality.summary.error_count),
    t.importQualityInfo(quality.summary.info_count),
  ]
  if (duplicateCount > 0) parts.push(t.importQualityDuplicates(duplicateCount))
  const signals = mergedQualitySignals(liveQuality)

  return (
    <div
      style={{
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '8px 10px',
        marginBottom: 10,
        background: 'var(--surface)',
        fontSize: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
        <strong>{t.importQualityTitle}</strong>
        <span style={{ color: 'var(--text-muted)' }}>{parts.join(' · ')}</span>
      </div>
      {signals.length > 0 && (
        <details open style={{ marginTop: 6 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-muted)' }}>{t.importQualityDetails}</summary>
          <ul style={{ margin: '6px 0 0 16px', padding: 0, display: 'grid', gap: 3 }}>
            {signals.map(signal => (
              <li key={signal.code} title={t.importQualitySignalMessages[signal.code] ?? t.importQualityUnknownSignal}>
                <span>{qualitySignalLabel(t, signal.code)}</span>
                <span style={{ color: 'var(--text-muted)' }}> · {qualitySeverityLabel(t, signal.severity)} · {signal.count}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}


export default function ImportModal({ accounts, categories, allTags, onClose, onSuccess, initialFiles }: Props) {
  const { t } = useT()
  const nextKey = useRef(0)
  const dupDebounceTimers = useRef<(ReturnType<typeof setTimeout> | null)[]>([])
  const dupSeqCounters    = useRef<number[]>([])
  const runDupCheckRef    = useRef<(fileIdx: number) => void>(() => {})

  const [phase, setPhase] = useState<BatchPhase>(() =>
    initialFiles.length > HARD_CAP ? 'cap-exceeded' : 'extracting'
  )

  const [fileItems, setFileItems] = useState<FileItem[]>(() =>
    initialFiles.map(f => ({
      file: f,
      extractStatus: 'pending' as ExtractStatus,
      preview: null,
      rows: [],
      extractError: null,
      resolvedAccountName: '',
      confirmStatus: 'pending' as ConfirmStatus,
      confirmResult: null,
      confirmError: null,
    }))
  )

  const [newIbanEntries, setNewIbanEntries] = useState<NewIbanEntry[]>([])
  const [resolveAttempted, setResolveAttempted] = useState(false)
  const [noIbanNewMode, setNoIbanNewMode] = useState<Record<number, boolean>>({})
  const [noIbanOpeningBalance, setNoIbanOpeningBalance] = useState<Record<number, string>>({})
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set())
  const initializedOpenGroupKeys = useRef<Set<string>>(new Set())
  const [createRuleRow, setCreateRuleRow] = useState<EditRow | null>(null)
  const [ruleToast, setRuleToast] = useState<string | null>(null)

  const liveQualityByFile = useMemo(
    () => fileItems.map(fi => applyDuplicateOverrides(
      computeLiveImportQuality(
        fi.rows,
        fi.preview?.statement_year ?? null,
        fi.preview?.year_detected ?? true,
      ),
      fi.rows,
    )),
    [fileItems],
  )

  useEffect(() => {
    if (!ruleToast) return
    const id = setTimeout(() => setRuleToast(null), 4000)
    return () => clearTimeout(id)
  }, [ruleToast])

  // ── S2: Sequential extraction ─────────────────────────────────────────────
  useEffect(() => {
    if (phase !== 'extracting') return
    let cancelled = false

    async function runExtract() {
      const previews: (PreviewResponse | null)[] = new Array(initialFiles.length).fill(null)

      for (let i = 0; i < initialFiles.length; i++) {
        if (cancelled) break
        setFileItems(prev => prev.map((fi, idx) => idx === i ? { ...fi, extractStatus: 'running' } : fi))
        try {
          const p = await previewImport(initialFiles[i])
          if (cancelled) break
          previews[i] = p
          const txns = (p.transactions ?? []).map(tx => ({
            ...tx,
            account_ref: tx.account_ref || p.account_ref || '',
          }))
          setFileItems(prev => prev.map((fi, idx) =>
            idx === i ? {
              ...fi,
              extractStatus: 'done',
              preview: p,
              rows: txns.map((tx, rowIdx) => ({
                ...tx,
                _key: nextKey.current++,
                _originalCategory: tx.category,
                _qualityFlags: p.quality.row_flags.filter(flag => flag.row_index === rowIdx),
              })),
            } : fi
          ))
        } catch (e) {
          if (cancelled) break
          setFileItems(prev => prev.map((fi, idx) =>
            idx === i ? { ...fi, extractStatus: 'error', extractError: friendlyError(e, t) } : fi
          ))
        }
      }

      if (cancelled) return

      // Build newIbanEntries for unique new (unmatched) IBANs
      const ibanMap = new Map<string, NewIbanEntry>()
      for (const p of previews) {
        if (!p) continue
        const iban = p.detected_account_iban
        if (!iban || p.matched_account_id != null) continue
        if (!ibanMap.has(iban)) {
          ibanMap.set(iban, { iban, masked: p.detected_account_masked ?? iban, name: '', touched: false, openingBalance: '' })
        }
      }
      setNewIbanEntries([...ibanMap.values()])
      setPhase('resolve')
    }

    runExtract()
    return () => { cancelled = true }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Account resolution helpers ────────────────────────────────────────────
  function getResolvedAccount(fi: FileItem): { name: string; number: string | null } {
    const p = fi.preview
    if (!p) return { name: '', number: null }
    if (p.matched_account_id != null && p.matched_account_name) {
      return { name: p.matched_account_name, number: null }
    }
    if (p.detected_account_iban) {
      const entry = newIbanEntries.find(e => e.iban === p.detected_account_iban)
      return { name: entry?.name.trim() ?? '', number: p.detected_account_iban }
    }
    return { name: fi.resolvedAccountName.trim(), number: null }
  }

  const canProceedResolve = useMemo(() => {
    if (newIbanEntries.some(e => e.name.trim() === '')) return false
    for (const fi of fileItems) {
      if (fi.extractStatus !== 'done' || !fi.preview) continue
      if (fi.preview.matched_account_id != null) continue
      if (fi.preview.detected_account_iban) continue
      if (!fi.resolvedAccountName.trim()) return false
    }
    return true
  }, [newIbanEntries, fileItems])

  function runDuplicateCheckForFile(fileIdx: number) {
    const fi = fileItems[fileIdx]
    if (!fi || fi.extractStatus !== 'done' || !fi.preview) return
    if (fi.preview.detected_account_iban && fi.preview.matched_account_id == null) return
    const { name: accountName } = getResolvedAccount(fi)
    if (!accountName) return

    const seq = (dupSeqCounters.current[fileIdx] ?? 0) + 1
    dupSeqCounters.current[fileIdx] = seq

    checkDuplicates(accountName, fi.rows.map(r => ({
      transaction_date: r.transaction_date,
      amount:           r.amount,
      description:      r.description,
      detail:           r.detail ?? null,
    }))).then(res => {
      if (dupSeqCounters.current[fileIdx] !== seq) return
      setFileItems(prev => prev.map((item, idx) =>
        idx !== fileIdx ? item : {
          ...item,
          rows: item.rows.map((r, ri) => ({
            ...r,
            isDuplicate: r.allow_duplicate ? false : (res.is_duplicate[ri] ?? false),
          })),
        }
      ))
    }).catch(() => { /* degrade gracefully — leave rows unmarked */ })
  }
  runDupCheckRef.current = runDuplicateCheckForFile

  function handleResolveContinue() {
    setResolveAttempted(true)
    if (!canProceedResolve) return

    // Fire duplicate checks async — preview shows immediately; badges appear as results arrive.
    for (let i = 0; i < fileItems.length; i++) {
      runDuplicateCheckForFile(i)
    }

    setPhase('preview')
  }

  // ── Accordion groups (derived from resolved fileItems) ────────────────────
  const accountGroups = useMemo<AccountGroup[]>(() => {
    const groups = new Map<string, AccountGroup>()
    fileItems.forEach((fi, idx) => {
      if (fi.extractStatus !== 'done') return
      const { name } = getResolvedAccount(fi)
      const iban = fi.preview?.detected_account_iban
      const key = iban ?? `manual:${idx}`
      const maskedIban = fi.preview?.detected_account_masked ?? null
      if (!groups.has(key)) {
        groups.set(key, { key, displayName: name || fi.file.name, maskedIban, fileIndices: [] })
      }
      groups.get(key)!.fileIndices.push(idx)
    })
    return [...groups.values()]
  }, [fileItems, newIbanEntries]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const newKeys = accountGroups
      .map(group => group.key)
      .filter(key => !initializedOpenGroupKeys.current.has(key))
    if (newKeys.length === 0) return

    newKeys.forEach(key => initializedOpenGroupKeys.current.add(key))
    setOpenGroups(prev => {
      const next = new Set(prev)
      newKeys.forEach(key => next.add(key))
      return next
    })
  }, [accountGroups])

  // ── Row editing ───────────────────────────────────────────────────────────
  function updateRow(fileIdx: number, key: number, patch: Partial<Omit<EditRow, '_key'>>) {
    const isDedupField = 'transaction_date' in patch || 'amount' in patch || 'description' in patch || 'detail' in patch
    setFileItems(prev => prev.map((fi, i) =>
      i === fileIdx
        ? {
            ...fi,
            rows: fi.rows.map(r =>
              r._key === key
                ? {
                    ...r,
                    ...patch,
                    ...((patch.allow_duplicate === true || (isDedupField && phase === 'preview')) ? { isDuplicate: false } : {}),
                  }
                : r
            ),
          }
        : fi
    ))
    if (isDedupField && phase === 'preview') {
      const existing = dupDebounceTimers.current[fileIdx]
      if (existing != null) clearTimeout(existing)
      dupDebounceTimers.current[fileIdx] = setTimeout(() => {
        dupDebounceTimers.current[fileIdx] = null
        runDupCheckRef.current(fileIdx)
      }, 400)
    }
  }

  function deleteRow(fileIdx: number, key: number) {
    setFileItems(prev => prev.map((fi, i) =>
      i === fileIdx ? { ...fi, rows: fi.rows.filter(r => r._key !== key) } : fi
    ))
  }

  function addBlankRow(fileIdx: number, accountRef: string) {
    const today = new Date().toISOString().slice(0, 10)
    setFileItems(prev => prev.map((fi, i) =>
      i === fileIdx
        ? {
            ...fi, rows: [...fi.rows, {
              _key: nextKey.current++,
              _originalCategory: 'Other',
              transaction_date: today,
              amount: -0.01,
              currency: 'EUR',
              description: '',
              raw_line: null,
              category: 'Other',
              category_confidence: null,
              account_ref: accountRef,
              balance_after: null,
              tags: [],
              merchant: null,
            }],
          }
        : fi
    ))
  }

  // ── S5: Confirm all ───────────────────────────────────────────────────────
  async function handleConfirmAll() {
    setPhase('confirming')
    const dbTagNames = new Set(allTags.map(tag => tag.name))
    const snapshot = fileItems

    for (let i = 0; i < snapshot.length; i++) {
      const fi = snapshot[i]
      if (fi.extractStatus !== 'done' || !fi.preview) continue

      const { name: accountName, number: accountNumber } = getResolvedAccount(fi)

      setFileItems(prev => prev.map((item, idx) =>
        idx === i ? { ...item, confirmStatus: 'running' } : item
      ))

      try {
        const suggestedMap = Object.fromEntries(
          (fi.preview!.suggested_tags ?? []).map(s => [s.name, s.color])
        )
        const tag_colors: Record<string, string> = {}
        for (const row of fi.rows) {
          for (const tagName of row.tags) {
            if (!dbTagNames.has(tagName) && !(tagName in tag_colors)) {
              tag_colors[tagName] = suggestedMap[tagName] ?? paletteColor(tagName)
            }
          }
        }

        let source_pdf_base64: string | undefined
        try { source_pdf_base64 = await readFileAsBase64(fi.file) } catch { /* degrade gracefully */ }

        // Resolve opening_balance for new accounts only
        let opening_balance: number | null = null
        if (fi.preview!.matched_account_id == null) {
          if (fi.preview!.detected_account_iban) {
            const ibanEntry = newIbanEntries.find(e => e.iban === fi.preview!.detected_account_iban)
            const raw = ibanEntry?.openingBalance.trim() ?? ''
            if (raw !== '') opening_balance = parseFloat(raw)
          } else if (noIbanNewMode[i]) {
            const raw = (noIbanOpeningBalance[i] ?? '').trim()
            if (raw !== '') opening_balance = parseFloat(raw)
          }
        }

        const payload: ConfirmRequest = {
          account_name: accountName,
          source_filename: fi.file.name,
          transactions: fi.rows.map(toImportTxn),
          ...(Object.keys(tag_colors).length > 0 ? { tag_colors } : {}),
          ...(accountNumber ? { account_number: accountNumber } : {}),
          ...(source_pdf_base64 ? { source_pdf_base64 } : {}),
          ...(opening_balance != null && !isNaN(opening_balance) ? { opening_balance } : {}),
        }

        const result = await confirmImport(payload)
        setFileItems(prev => prev.map((item, idx) =>
          idx === i ? { ...item, confirmStatus: 'done', confirmResult: result } : item
        ))
      } catch (e) {
        setFileItems(prev => prev.map((item, idx) =>
          idx === i ? { ...item, confirmStatus: 'error', confirmError: friendlyError(e, t) } : item
        ))
      }
    }

    setPhase('summary')
  }

  // ── S6: Close & notify parent ─────────────────────────────────────────────
  function handleClose() {
    const doneItems = fileItems.filter(fi => fi.confirmStatus === 'done' && fi.confirmResult)
    const aggregate: ImportResult = {
      import_run_id: 0,
      num_parsed: doneItems.length,
      num_inserted: doneItems.reduce((s, fi) => s + (fi.confirmResult?.num_inserted ?? 0), 0),
      num_duplicates: doneItems.reduce((s, fi) => s + (fi.confirmResult?.num_duplicates ?? 0), 0),
    }
    onSuccess(aggregate)
  }

  const isBlocking = phase === 'extracting' || phase === 'confirming'

  function getModalTitle(): string {
    switch (phase) {
      case 'cap-exceeded':  return t.modalTitleUpload
      case 'extracting':    return t.batchExtractingTitle
      case 'resolve':       return t.batchResolveTitle
      case 'preview':       return t.batchPreviewTitle
      case 'confirming':    return t.batchConfirmingTitle
      case 'summary':       return t.batchSummaryTitle
    }
  }

  // ── Phase renderers ───────────────────────────────────────────────────────

  function renderCapExceeded() {
    return (
      <div className="batch-cap-exceeded">
        <div className="batch-cap-exceeded-icon">🚫</div>
        <div className="batch-cap-exceeded-title">
          {t.batchCapBlocked(initialFiles.length)}
        </div>
        <div className="batch-cap-exceeded-body">
          {t.batchCapBlocked(initialFiles.length)}
        </div>
      </div>
    )
  }

  function renderExtracting() {
    const done = fileItems.filter(fi => fi.extractStatus === 'done' || fi.extractStatus === 'error').length
    const total = fileItems.length
    return (
      <div className="batch-progress-wrap">
        {initialFiles.length > SOFT_CAP && (
          <div className="batch-cap-warning">
            ⚠ {t.batchCapWarning(initialFiles.length)}
          </div>
        )}
        <div className="batch-extract-header">
          <div className="spinner spinner--sm" />
          <span className="batch-progress-label" aria-live="polite">
            {t.batchFileProgress(Math.min(done + 1, total), total)}
          </span>
        </div>
        <ul className="batch-file-list">
          {fileItems.map((fi, i) => (
            <li key={i} className="batch-file-row">
              <span className="batch-file-icon">
                {fi.extractStatus === 'running' && <div className="spinner spinner--sm" />}
                {fi.extractStatus === 'done'    && <span className="batch-file-icon--done">✔</span>}
                {fi.extractStatus === 'error'   && <span className="batch-file-icon--error">✗</span>}
                {fi.extractStatus === 'pending' && <span className="batch-file-icon--pending">○</span>}
              </span>
              <span className="batch-file-name">{fi.file.name}</span>
              {fi.extractStatus === 'error' && fi.extractError && (
                <span className="batch-file-error" title={fi.extractError}>{fi.extractError}</span>
              )}
            </li>
          ))}
        </ul>
      </div>
    )
  }

  function renderResolve() {
    // Collect unique auto-matched IBANs for display
    const matchedEntries: { masked: string; name: string }[] = []
    const seenMatched = new Set<string>()
    for (const fi of fileItems) {
      const p = fi.preview
      if (!p || fi.extractStatus !== 'done') continue
      if (p.matched_account_id != null && p.matched_account_name && p.detected_account_masked) {
        const key = p.detected_account_masked
        if (!seenMatched.has(key)) {
          seenMatched.add(key)
          matchedEntries.push({ masked: p.detected_account_masked, name: p.matched_account_name })
        }
      }
    }

    // No-IBAN files (need per-file manual input)
    const noIbanFiles = fileItems
      .map((fi, idx) => ({ fi, idx }))
      .filter(({ fi }) => fi.extractStatus === 'done' && fi.preview && !fi.preview.detected_account_iban)

    return (
      <div className="batch-resolve-section">
        <div className="batch-resolve-list">
          {matchedEntries.map((e, i) => (
            <div key={i} className="batch-resolve-matched-banner">
              ✓ {t.importDetectedAccount(e.masked, e.name)}
            </div>
          ))}

          {newIbanEntries.map((entry, i) => {
            const showErr = resolveAttempted && entry.name.trim() === ''
            return (
              <div key={entry.iban} className="batch-resolve-new-iban-group">
                <div className="batch-resolve-iban-banner">
                  {t.importNewAccountDetected(entry.masked)}
                </div>
                <div className="form-group" style={{ marginTop: 8 }}>
                  <label htmlFor={`iban-name-${i}`}>
                    {t.batchResolveNewIbanName} <span className="rules-required">*</span>
                  </label>
                  <input
                    id={`iban-name-${i}`}
                    type="text"
                    className={`form-input${showErr ? ' form-input--error' : ''}`}
                    placeholder={t.modalAccountPlaceholder}
                    value={entry.name}
                    onChange={e => setNewIbanEntries(prev =>
                      prev.map((en, j) => j === i ? { ...en, name: e.target.value, touched: true } : en)
                    )}
                    onBlur={() => setNewIbanEntries(prev =>
                      prev.map((en, j) => j === i ? { ...en, touched: true } : en)
                    )}
                    autoFocus={i === 0 && matchedEntries.length === 0}
                  />
                  {showErr && (
                    <span className="form-field-error">{t.modalAccountRequired}</span>
                  )}
                </div>
                <div className="form-group" style={{ marginTop: 8 }}>
                  <label htmlFor={`iban-opening-${i}`}>{t.importOpeningBalanceLabel}</label>
                  <input
                    id={`iban-opening-${i}`}
                    type="number"
                    step="0.01"
                    className="form-input"
                    placeholder="0.00"
                    value={entry.openingBalance}
                    onChange={e => setNewIbanEntries(prev =>
                      prev.map((en, j) => j === i ? { ...en, openingBalance: e.target.value } : en)
                    )}
                  />
                  <span className="form-field-hint" style={{ display: 'block', marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                    {t.importOpeningBalanceHelpText}
                  </span>
                  <span style={{ display: 'block', marginTop: 4, fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                    {t.importOpeningBalanceHint}
                  </span>
                </div>
              </div>
            )
          })}

          {noIbanFiles.map(({ fi, idx }) => {
            const isNew = noIbanNewMode[idx] ?? false
            const showErr = resolveAttempted && !fi.resolvedAccountName.trim()
            return (
              <div key={idx} className="batch-resolve-manual-group">
                <div className="batch-resolve-manual-label">
                  {t.batchResolveManualFile(fi.file.name)}
                </div>
                {accounts.length === 0 ? (
                  <div className="form-group">
                    <input
                      type="text"
                      className={`form-input${showErr ? ' form-input--error' : ''}`}
                      placeholder={t.modalAccountPlaceholder}
                      value={fi.resolvedAccountName}
                      onChange={e => setFileItems(prev =>
                        prev.map((item, i) => i === idx ? { ...item, resolvedAccountName: e.target.value } : item)
                      )}
                    />
                    {showErr && <span className="form-field-error">{t.modalAccountRequired}</span>}
                    <div style={{ marginTop: 8 }}>
                      <label htmlFor={`noiban-opening-${idx}`} style={{ fontSize: 13 }}>{t.importOpeningBalanceLabel}</label>
                      <input
                        id={`noiban-opening-${idx}`}
                        type="number"
                        step="0.01"
                        className="form-input"
                        placeholder="0.00"
                        style={{ marginTop: 4 }}
                        value={noIbanOpeningBalance[idx] ?? ''}
                        onChange={e => setNoIbanOpeningBalance(prev => ({ ...prev, [idx]: e.target.value }))}
                      />
                      <span style={{ display: 'block', marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                        {t.importOpeningBalanceHelpText}
                      </span>
                      <span style={{ display: 'block', marginTop: 2, fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                        {t.importOpeningBalanceHint}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="form-group">
                    <select
                      className={`form-input${showErr && !isNew ? ' form-input--error' : ''}`}
                      value={isNew ? '__new__' : fi.resolvedAccountName}
                      onChange={e => {
                        if (e.target.value === '__new__') {
                          setNoIbanNewMode(prev => ({ ...prev, [idx]: true }))
                          setFileItems(prev => prev.map((item, i) => i === idx ? { ...item, resolvedAccountName: '' } : item))
                        } else {
                          setNoIbanNewMode(prev => ({ ...prev, [idx]: false }))
                          setFileItems(prev => prev.map((item, i) => i === idx ? { ...item, resolvedAccountName: e.target.value } : item))
                        }
                      }}
                    >
                      <option value="">{t.modalAccountPlaceholder}</option>
                      {accounts.map(a => <option key={a.id} value={a.name}>{a.name}</option>)}
                      <option value="__new__">{t.modalAccountNew}</option>
                    </select>
                    {isNew && (
                      <>
                        <input
                          type="text"
                          className={`form-input${showErr ? ' form-input--error' : ''}`}
                          style={{ marginTop: 4 }}
                          placeholder={t.modalAccountPlaceholder}
                          value={fi.resolvedAccountName}
                          onChange={e => setFileItems(prev =>
                            prev.map((item, i) => i === idx ? { ...item, resolvedAccountName: e.target.value } : item)
                          )}
                          autoFocus
                        />
                        <div style={{ marginTop: 8 }}>
                          <label htmlFor={`noiban-opening-${idx}`} style={{ fontSize: 13 }}>{t.importOpeningBalanceLabel}</label>
                          <input
                            id={`noiban-opening-${idx}`}
                            type="number"
                            step="0.01"
                            className="form-input"
                            placeholder="0.00"
                            style={{ marginTop: 4 }}
                            value={noIbanOpeningBalance[idx] ?? ''}
                            onChange={e => setNoIbanOpeningBalance(prev => ({ ...prev, [idx]: e.target.value }))}
                          />
                          <span style={{ display: 'block', marginTop: 4, fontSize: 12, color: 'var(--text-muted)' }}>
                            {t.importOpeningBalanceHelpText}
                          </span>
                          <span style={{ display: 'block', marginTop: 2, fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                            {t.importOpeningBalanceHint}
                          </span>
                        </div>
                      </>
                    )}
                    {showErr && <span className="form-field-error">{t.modalAccountRequired}</span>}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  function renderPreview() {
    return (
      <div className="batch-accordion" role="list">
        {accountGroups.map(group => {
          const isOpen = openGroups.has(group.key)
          const groupFiles = group.fileIndices.map(i => fileItems[i])
          const totalTxns = groupFiles.reduce((s, fi) => s + fi.rows.length, 0)
          const dupCount = group.fileIndices.reduce((s, fileIdx) => s + duplicateRowCount(liveQualityByFile[fileIdx]), 0)
          const headerId = `group-hdr-${group.key}`
          const bodyId   = `group-body-${group.key}`
          return (
            <div key={group.key} className="batch-accordion-item" role="listitem">
              <button
                id={headerId}
                type="button"
                className="batch-accordion-header"
                aria-expanded={isOpen}
                aria-controls={bodyId}
                onClick={() => setOpenGroups(prev => {
                  const next = new Set(prev)
                  isOpen ? next.delete(group.key) : next.add(group.key)
                  return next
                })}
              >
                <span className={`batch-accordion-chevron${isOpen ? ' batch-accordion-chevron--open' : ''}`} aria-hidden="true">▶</span>
                <span className="batch-accordion-label">
                  <strong>{group.displayName}</strong>
                  {group.maskedIban && (
                    <span style={{ marginLeft: 8, fontWeight: 400, color: 'var(--text-muted)', fontSize: 13 }}>
                      {group.maskedIban}
                    </span>
                  )}
                </span>
                <span className="batch-accordion-meta">
                  {t.batchPreviewGroup(group.fileIndices.length, totalTxns)}
                  {dupCount > 0 && (
                    <span className="batch-dup-badge">{t.importDuplicateCount(dupCount)}</span>
                  )}
                </span>
              </button>

              {isOpen && (
                <div id={bodyId} className="batch-accordion-body" aria-labelledby={headerId}>
                  {group.fileIndices.map((fileIdx, fi_i) => {
                    const fi = fileItems[fileIdx]
                    const showSep = group.fileIndices.length > 1
                    const { name: resolvedName } = getResolvedAccount(fi)
                    const yearWarning = fi.preview
                      ? (fi.preview.year_detected === false || fi.preview.statement_year == null)
                      : false
                    return (
                      <div key={fileIdx}>
                        {showSep && (
                          <div className="batch-file-sep" aria-hidden="true">
                            {t.batchPreviewFileSep(fi.file.name)}
                          </div>
                        )}
                        <div className="batch-accordion-file-content">
                          <ImportQualityPanel liveQuality={liveQualityByFile[fileIdx]} t={t} />
                          <ImportPreviewTable
                            rows={fi.rows}
                            accounts={accounts}
                            categories={categories}
                            allTags={allTags}
                            suggestedColors={Object.fromEntries((fi.preview?.suggested_tags ?? []).map(s => [s.name, s.color]))}
                            onUpdateRow={(key, patch) => updateRow(fileIdx, key, patch)}
                            onDeleteRow={key => deleteRow(fileIdx, key)}
                            onAddBlankRow={() => addBlankRow(fileIdx, resolvedName)}
                            onCreateRule={row => setCreateRuleRow(row)}
                            showYearWarning={yearWarning}
                            liveQuality={liveQualityByFile[fileIdx]}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  function renderConfirming() {
    const done = fileItems.filter(fi => fi.confirmStatus === 'done' || fi.confirmStatus === 'error').length
    const total = fileItems.filter(fi => fi.extractStatus === 'done').length
    return (
      <div className="batch-progress-wrap">
        <div className="batch-extract-header">
          <div className="spinner spinner--sm" />
          <span className="batch-progress-label" aria-live="polite">
            {t.batchConfirmFileProgress(Math.min(done + 1, total), total)}
          </span>
        </div>
        <ul className="batch-file-list">
          {fileItems.map((fi, i) => {
            if (fi.extractStatus !== 'done') return null
            return (
              <li key={i} className="batch-file-row">
                <span className="batch-file-icon">
                  {fi.confirmStatus === 'running' && <div className="spinner spinner--sm" />}
                  {fi.confirmStatus === 'done'    && <span className="batch-file-icon--done">✔</span>}
                  {fi.confirmStatus === 'error'   && <span className="batch-file-icon--error">✗</span>}
                  {fi.confirmStatus === 'pending' && <span className="batch-file-icon--pending">○</span>}
                </span>
                <span className="batch-file-name">{fi.file.name}</span>
                {fi.confirmStatus === 'error' && fi.confirmError && (
                  <span className="batch-file-error" title={fi.confirmError}>{fi.confirmError}</span>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    )
  }

  function renderSummary() {
    const doneItems   = fileItems.filter(fi => fi.confirmStatus === 'done')
    const errorItems  = fileItems.filter(fi => fi.confirmStatus === 'error' || fi.extractStatus === 'error')
    const totalInserted = doneItems.reduce((s, fi) => s + (fi.confirmResult?.num_inserted ?? 0), 0)
    const totalDupes    = doneItems.reduce((s, fi) => s + (fi.confirmResult?.num_duplicates ?? 0), 0)

    return (
      <div className="batch-summary-section">
        <div className="batch-summary-title">{t.batchSummaryTitle}</div>
        <div className="batch-summary-totals">
          <div className="batch-summary-total-row">📄 <strong>{t.batchSummaryStmts(doneItems.length)}</strong></div>
          <div className="batch-summary-total-row">✅ <strong>{t.batchSummaryNewTx(totalInserted)}</strong></div>
          <div className="batch-summary-total-row">🔁 <strong>{t.batchSummaryDupes(totalDupes)}</strong></div>
          {errorItems.length > 0 && (
            <div className="batch-summary-total-row">❌ <strong>{t.batchSummaryErrors(errorItems.length)}</strong></div>
          )}
        </div>

        <div className="batch-detail-title">{t.previewColDesc}</div>
        <ul className="batch-detail-list">
          {fileItems.map((fi, i) => {
            if (fi.confirmStatus === 'done' && fi.confirmResult) {
              return (
                <li key={i} className="batch-detail-row batch-detail-row--done">
                  {t.batchSummaryFileDone(fi.file.name, fi.confirmResult.num_inserted, fi.confirmResult.num_duplicates)}
                </li>
              )
            }
            if (fi.confirmStatus === 'error') {
              return (
                <li key={i} className="batch-detail-row batch-detail-row--error">
                  {t.batchSummaryFileError(fi.file.name, fi.confirmError ?? '')}
                </li>
              )
            }
            if (fi.extractStatus === 'error') {
              return (
                <li key={i} className="batch-detail-row batch-detail-row--error">
                  {t.batchSummaryFileError(fi.file.name, fi.extractError ?? '')}
                </li>
              )
            }
            return null
          })}
        </ul>
      </div>
    )
  }

  // ── Footer buttons ────────────────────────────────────────────────────────
  function renderFooter() {
    if (phase === 'extracting' || phase === 'confirming') return null

    if (phase === 'cap-exceeded') {
      return <button className="btn-secondary" onClick={onClose}>{t.modalBtnCancel}</button>
    }

    if (phase === 'resolve') {
      return (
        <>
          <button className="btn-secondary" onClick={onClose}>{t.modalBtnCancel}</button>
          <button
            className="btn-primary"
            onClick={handleResolveContinue}
          >
            {t.modalBtnContinue}
          </button>
        </>
      )
    }

    if (phase === 'preview') {
      const totalTxns = fileItems.reduce((s, fi) => s + fi.rows.length, 0)
      return (
        <>
          <button className="btn-secondary" onClick={onClose}>{t.modalBtnCancel}</button>
          <button
            className="btn-primary"
            onClick={handleConfirmAll}
            disabled={totalTxns === 0}
          >
            {t.batchConfirmAllBtn(totalTxns)}
          </button>
        </>
      )
    }

    if (phase === 'summary') {
      return (
        <button className="btn-primary" onClick={handleClose}>
          {t.toastClose}
        </button>
      )
    }

    return null
  }

  // ── Render ────────────────────────────────────────────────────────────────
  const footer = renderFooter()
  return (
    <>
      <div className="modal-backdrop">
        <div className="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="batch-modal-title">

          <div className="modal-header">
            <h2 className="modal-title" id="batch-modal-title">{getModalTitle()}</h2>
            <button
              className="modal-close"
              onClick={onClose}
              disabled={isBlocking}
              aria-label={t.modalClose}
            >
              ✕
            </button>
          </div>

          <div className="modal-body">
            {phase === 'cap-exceeded' && renderCapExceeded()}
            {phase === 'extracting'   && renderExtracting()}
            {phase === 'resolve'      && renderResolve()}
            {phase === 'preview'      && renderPreview()}
            {phase === 'confirming'   && renderConfirming()}
            {phase === 'summary'      && renderSummary()}
          </div>

          {footer && (
            <div className="modal-footer">
              {footer}
            </div>
          )}

        </div>
      </div>

      {createRuleRow && (
        <RuleFormModal
          initialValues={{
            description_mode:  'contains',
            description_value: createRuleRow.description,
            set_category:      createRuleRow.category,
            set_merchant:      createRuleRow.merchant,
            add_tags:          createRuleRow.tags,
          }}
          categories={categories}
          availableTags={allTags}
          onSave={() => { setCreateRuleRow(null); setRuleToast(t.createRuleToast) }}
          onClose={() => setCreateRuleRow(null)}
        />
      )}

      {ruleToast && <div className="rule-toast">{ruleToast}</div>}
    </>
  )
}
