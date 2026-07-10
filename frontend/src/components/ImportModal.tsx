import { useState, useRef, useMemo, useEffect } from 'react'
import type {
  Account, Category, Tag,
  ImportTransaction, PreviewResponse, ConfirmRequest, ImportResult,
} from '../api/types'
import { previewImport, confirmImport } from '../api/client'
import { useT, type Dict, paletteColor } from '../i18n'
import ImportPreviewTable, { type EditRow } from './ImportPreviewTable'
import RuleFormModal from './RuleFormModal'

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
  }
}


export default function ImportModal({ accounts, categories, allTags, onClose, onSuccess, initialFiles }: Props) {
  const { t } = useT()
  const nextKey = useRef(0)

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
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set())
  const [createRuleRow, setCreateRuleRow] = useState<EditRow | null>(null)
  const [ruleToast, setRuleToast] = useState<string | null>(null)


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
              rows: txns.map(tx => ({ ...tx, _key: nextKey.current++ })),
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
          ibanMap.set(iban, { iban, masked: p.detected_account_masked ?? iban, name: '', touched: false })
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

  function handleResolveContinue() {
    setResolveAttempted(true)
    if (!canProceedResolve) return
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

  // ── Row editing ───────────────────────────────────────────────────────────
  function updateRow(fileIdx: number, key: number, patch: Partial<Omit<EditRow, '_key'>>) {
    setFileItems(prev => prev.map((fi, i) =>
      i === fileIdx
        ? { ...fi, rows: fi.rows.map(r => r._key === key ? { ...r, ...patch } : r) }
        : fi
    ))
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

        const payload: ConfirmRequest = {
          account_name: accountName,
          source_filename: fi.file.name,
          transactions: fi.rows.map(toImportTxn),
          ...(Object.keys(tag_colors).length > 0 ? { tag_colors } : {}),
          ...(accountNumber ? { account_number: accountNumber } : {}),
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
    const pct = total > 0 ? (done / total) * 100 : 0
    return (
      <div className="batch-progress-wrap">
        {initialFiles.length > SOFT_CAP && (
          <div className="batch-cap-warning">
            ⚠ {t.batchCapWarning(initialFiles.length)}
          </div>
        )}
        <div className="batch-progress-label" aria-live="polite">
          {t.batchFileProgress(Math.min(done + 1, total), total)}
        </div>
        <div className="batch-progress-bar-wrap" role="progressbar" aria-valuenow={done} aria-valuemax={total}>
          <div className="batch-progress-bar-track">
            <div className="batch-progress-bar-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <ul className="batch-file-list">
          {fileItems.map((fi, i) => (
            <li key={i} className="batch-file-row">
              <span className="batch-file-icon">
                {fi.extractStatus === 'running' && <span className="btn-spinner" style={{ display: 'inline-block' }} />}
                {fi.extractStatus === 'done'    && '✔'}
                {fi.extractStatus === 'error'   && '✗'}
                {fi.extractStatus === 'pending' && '○'}
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
                          <ImportPreviewTable
                            rows={fi.rows}
                            fileKey={`file-${fileIdx}-${fi_i}`}
                            accounts={accounts}
                            categories={categories}
                            allTags={allTags}
                            suggestedColors={Object.fromEntries((fi.preview?.suggested_tags ?? []).map(s => [s.name, s.color]))}
                            onUpdateRow={(key, patch) => updateRow(fileIdx, key, patch)}
                            onDeleteRow={key => deleteRow(fileIdx, key)}
                            onAddBlankRow={() => addBlankRow(fileIdx, resolvedName)}
                            onCreateRule={row => setCreateRuleRow(row)}
                            showYearWarning={yearWarning}
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
    const pct = total > 0 ? (done / total) * 100 : 0
    return (
      <div className="batch-progress-wrap">
        <div className="batch-progress-label" aria-live="polite">
          {t.batchFileProgress(Math.min(done + 1, total), total)}
        </div>
        <div className="batch-progress-bar-wrap" role="progressbar" aria-valuenow={done} aria-valuemax={total}>
          <div className="batch-progress-bar-track">
            <div className="batch-progress-bar-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <ul className="batch-file-list">
          {fileItems.map((fi, i) => {
            if (fi.extractStatus !== 'done') return null
            return (
              <li key={i} className="batch-file-row">
                <span className="batch-file-icon">
                  {fi.confirmStatus === 'running' && <span className="btn-spinner" style={{ display: 'inline-block' }} />}
                  {fi.confirmStatus === 'done'    && '✔'}
                  {fi.confirmStatus === 'error'   && '✗'}
                  {fi.confirmStatus === 'pending' && '○'}
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
