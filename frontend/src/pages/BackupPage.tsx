import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { useT } from '../i18n'
import type { Dict } from '../i18n'
import { exportBackup, importBackup } from '../api/client'
import type { BackupDocument, BackupExportSelection, BackupImportSummary } from '../api/types'

const BACKUP_SECTIONS: Array<{ key: keyof BackupExportSelection; label: keyof Dict; icon: string }> = [
  { key: 'transactions', label: 'backupSectionTransactions', icon: '📋' },
  { key: 'accounts', label: 'backupSectionAccounts', icon: '🏦' },
  { key: 'categories', label: 'backupSectionCategories', icon: '🗂️' },
  { key: 'tags', label: 'backupSectionTags', icon: '🏷️' },
  { key: 'rules', label: 'backupSectionRules', icon: '🧩' },
  { key: 'investments', label: 'backupSectionInvestments', icon: '💰' },
]

const BACKUP_SECTION_ICON_BY_KEY = Object.fromEntries(
  BACKUP_SECTIONS.map(section => [section.key, section.icon]),
) as Record<keyof BackupExportSelection, string>

const DEFAULT_SELECTION: BackupExportSelection = {
  accounts: true,
  categories: true,
  tags: true,
  transactions: true,
  rules: true,
  investments: true,
}

function isBackupDocument(data: unknown): data is BackupDocument {
  return Boolean(
    data
    && typeof data === 'object'
    && 'finlytics_backup_version' in data
    && 'exported_at' in data,
  )
}

export default function BackupPage() {
  const { t } = useT()

  const [selection, setSelection] = useState<BackupExportSelection>(DEFAULT_SELECTION)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState<string | null>(null)
  const [importSummary, setImportSummary] = useState<BackupImportSummary | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const hasSelectedExportSection = Object.values(selection).some(Boolean)

  function toggleSection(key: keyof BackupExportSelection) {
    setSelection(prev => ({ ...prev, [key]: !prev[key] }))
  }

  async function handleExport() {
    if (!hasSelectedExportSection) {
      setExportError(t.backupSelectAtLeastOne)
      return
    }

    setExporting(true)
    setExportError(null)
    try {
      const data = await exportBackup(selection)
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

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    setImportError(null)
    setImportSummary(null)
    setSelectedFile(e.target.files?.[0] ?? null)
  }

  async function handleImport() {
    if (!selectedFile) return

    setImportError(null)
    setImportSummary(null)

    let data: unknown
    try {
      const text = await selectedFile.text()
      data = JSON.parse(text)
    } catch {
      setImportError(t.backupErrorInvalidJson)
      clearSelectedFile()
      return
    }

    if (!isBackupDocument(data)) {
      setImportError(t.backupErrorInvalidShape)
      clearSelectedFile()
      return
    }

    if (!window.confirm(t.backupImportConfirm)) {
      clearSelectedFile()
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
      clearSelectedFile()
    }
  }

  function clearSelectedFile() {
    setSelectedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function SummaryItem({ label, value, tone }: { label: string; value: number; tone: 'positive' | 'neutral' | 'update' }) {
    return (
      <li>
        {label}: <strong className={`backup-summary-count backup-summary-count--${tone}`}>{value}</strong>
      </li>
    )
  }

  function SectionIcon({ sectionKey }: { sectionKey: keyof BackupExportSelection }) {
    return <span className="nav-icon" aria-hidden="true">{BACKUP_SECTION_ICON_BY_KEY[sectionKey]}</span>
  }

  return (
    <div className="backup-page card settings-card">
      <h2 className="settings-section-title">{t.backupPageTitle}</h2>
      <p className="backup-intro">{t.backupIntro}</p>

      <div className="backup-section">
        <h3 className="backup-section-title">{t.backupExportTitle}</h3>
        <p className="backup-section-copy">{t.backupExportSectionIntro}</p>
        <div className="backup-checkbox-grid">
          {BACKUP_SECTIONS.map(section => (
            <label key={section.key} className="backup-checkbox">
              <input
                type="checkbox"
                checked={selection[section.key]}
                onChange={() => toggleSection(section.key)}
                disabled={exporting}
              />
              <SectionIcon sectionKey={section.key} />
              <span>{t[section.label] as string}</span>
            </label>
          ))}
        </div>
        <p className="backup-note">{t.backupIndexaTokenNote}</p>
        <div className="backup-actions">
          <button
            type="button"
            className="btn-primary"
            onClick={handleExport}
            disabled={exporting || !hasSelectedExportSection}
          >
            {exporting ? t.backupExporting : t.backupExportBtn}
          </button>
        </div>
        {exportError && <div className="import-error" style={{ marginTop: 8 }}>{exportError}</div>}
      </div>

      <div className="backup-section">
        <h3 className="backup-section-title">{t.backupImportTitle}</h3>
        <p className="backup-section-copy">{t.backupImportIntro}</p>
        <div className="backup-actions">
          <label className="backup-file-label">
            <span className={`btn-primary${importing ? ' disabled' : ''}`}>
              {t.backupImportBtn}
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
          <span className="backup-file-name">
            {selectedFile ? `${t.backupImportSelectedFile}: ${selectedFile.name}` : t.backupImportNoFile}
          </span>
          <button
            type="button"
            className="btn-primary"
            onClick={handleImport}
            disabled={importing || !selectedFile}
          >
            {importing ? t.backupImporting : t.backupImportSubmitBtn}
          </button>
        </div>
        {importError && <div className="import-error" style={{ marginTop: 8 }}>{importError}</div>}
        {importSummary && (
          <div className="backup-summary">
            <h4 className="backup-summary-title">{t.backupSummaryTitle}</h4>
            <div className="backup-summary-grid">
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="accounts" /> {t.backupSectionAccounts}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryAccountsCreated} value={importSummary.accounts_created} tone="positive" />
                  <SummaryItem label={t.backupSummaryAccountsExisting} value={importSummary.accounts_existing} tone="neutral" />
                </ul>
              </section>
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="categories" /> {t.backupSectionCategories}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryCategoriesCreated} value={importSummary.categories_created} tone="positive" />
                  <SummaryItem label={t.backupSummaryCategoriesUpdated} value={importSummary.categories_updated} tone="update" />
                </ul>
              </section>
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="tags" /> {t.backupSectionTags}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryTagsCreated} value={importSummary.tags_created} tone="positive" />
                  <SummaryItem label={t.backupSummaryTagsUpdated} value={importSummary.tags_updated} tone="update" />
                </ul>
              </section>
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="transactions" /> {t.backupSectionTransactions}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryTxInserted} value={importSummary.transactions_inserted} tone="positive" />
                  <SummaryItem label={t.backupSummaryTxDuplicates} value={importSummary.transactions_duplicates} tone="neutral" />
                </ul>
              </section>
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="rules" /> {t.backupSectionRules}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryRulesCreated} value={importSummary.rules_created} tone="positive" />
                  <SummaryItem label={t.backupSummaryRulesUpdated} value={importSummary.rules_updated} tone="update" />
                </ul>
              </section>
              <section className="backup-summary-section">
                <h5><SectionIcon sectionKey="investments" /> {t.backupSectionInvestments}</h5>
                <ul className="backup-summary-list">
                  <SummaryItem label={t.backupSummaryInvestmentConnectionsCreated} value={importSummary.investment_connections_created} tone="positive" />
                  <SummaryItem label={t.backupSummaryInvestmentConnectionsUpdated} value={importSummary.investment_connections_updated} tone="update" />
                  <SummaryItem label={t.backupSummaryEsppLotsInserted} value={importSummary.espp_lots_inserted} tone="positive" />
                  <SummaryItem label={t.backupSummaryEsppLotsDuplicates} value={importSummary.espp_lots_duplicates} tone="neutral" />
                  <SummaryItem label={t.backupSummaryPriceHistoryInserted} value={importSummary.price_history_inserted} tone="positive" />
                  <SummaryItem label={t.backupSummaryPriceHistoryDuplicates} value={importSummary.price_history_duplicates} tone="neutral" />
                </ul>
              </section>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
