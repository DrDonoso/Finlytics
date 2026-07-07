import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useT } from '../i18n'
import { exportBackup, importBackup } from '../api/client'
import type { BackupImportSummary } from '../api/types'

export default function BackupPage() {
  const { t } = useT()

  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importSummary, setImportSummary] = useState<BackupImportSummary | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleExport() {
    setExporting(true)
    setExportError(null)
    try {
      const data = await exportBackup()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      const now = new Date()
      const dateStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
      a.href = url
      a.download = `finlytics-backup-${dateStr}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      setExportError(String(e))
    } finally {
      setExporting(false)
    }
  }

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    setImportError(null)
    setImportSummary(null)

    let data: unknown
    try {
      const text = await file.text()
      data = JSON.parse(text)
    } catch {
      setImportError(t.backupErrorInvalidJson)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    if (!data || typeof data !== 'object' || !('finlytics_backup_version' in data)) {
      setImportError(t.backupErrorInvalidShape)
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    if (!window.confirm(t.backupImportConfirm)) {
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }

    setImporting(true)
    try {
      const summary = await importBackup(data)
      setImportSummary(summary)
    } catch (e) {
      setImportError(String(e))
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <div className="backup-page card settings-card">
      <h2 className="settings-section-title">{t.backupPageTitle}</h2>
      <p className="backup-intro">{t.backupIntro}</p>

      {/* ── Export ─────────────────────────────────────────────────────────── */}
      <div className="backup-section">
        <h3 className="backup-section-title">{t.backupExportTitle}</h3>
        <div className="backup-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleExport}
            disabled={exporting}
          >
            {exporting ? t.backupExporting : t.backupExportBtn}
          </button>
        </div>
        {exportError && <div className="import-error" style={{ marginTop: 8 }}>{exportError}</div>}
      </div>

      {/* ── Import ─────────────────────────────────────────────────────────── */}
      <div className="backup-section">
        <h3 className="backup-section-title">{t.backupImportTitle}</h3>
        <div className="backup-actions">
          <label className="backup-file-label">
            <span className={`btn-primary${importing ? ' disabled' : ''}`}>
              {importing ? t.backupImporting : t.backupImportBtn}
            </span>
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,application/json"
              className="backup-file-input"
              onChange={handleFileChange}
              disabled={importing}
            />
          </label>
        </div>
        {importError && <div className="import-error" style={{ marginTop: 8 }}>{importError}</div>}
        {importSummary && (
          <div className="backup-summary">
            <h4 className="backup-summary-title">{t.backupSummaryTitle}</h4>
            <ul className="backup-summary-list">
              <li>{t.backupSummaryAccountsCreated}: <strong>{importSummary.accounts_created}</strong></li>
              <li>{t.backupSummaryAccountsExisting}: <strong>{importSummary.accounts_existing}</strong></li>
              <li>{t.backupSummaryCategoriesCreated}: <strong>{importSummary.categories_created}</strong></li>
              <li>{t.backupSummaryCategoriesUpdated}: <strong>{importSummary.categories_updated}</strong></li>
              <li>{t.backupSummaryTagsCreated}: <strong>{importSummary.tags_created}</strong></li>
              <li>{t.backupSummaryTagsUpdated}: <strong>{importSummary.tags_updated}</strong></li>
              <li>{t.backupSummaryTxInserted}: <strong>{importSummary.transactions_inserted}</strong></li>
              <li>{t.backupSummaryTxDuplicates}: <strong>{importSummary.transactions_duplicates}</strong></li>
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
