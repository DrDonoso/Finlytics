import { useState, useEffect, useMemo } from 'react'
import type { Rule, DescriptionMode, Category, Tag } from '../api/types'
import {
  getRules, updateRule, deleteRule,
  getCategories, getTags,
} from '../api/client'
import { useT, categoryLabel } from '../i18n'
import RuleFormModal from '../components/RuleFormModal'

export default function RulesPage() {
  const { t, lang } = useT()
  const [rules, setRules] = useState<Rule[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [availableTags, setAvailableTags] = useState<Tag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Rule form modal
  const [ruleModalOpen, setRuleModalOpen]     = useState(false)
  const [ruleModalTarget, setRuleModalTarget] = useState<Rule | undefined>(undefined)

  // Delete confirm
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  const sortedRules = useMemo(
    () => [...rules].sort((a, b) =>
      a.priority !== b.priority ? a.priority - b.priority : a.id - b.id
    ),
    [rules],
  )

  const dynamicEs = useMemo(
    () => Object.fromEntries(
      categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])
    ),
    [categories],
  )

  useEffect(() => {
    setLoading(true)
    Promise.all([getRules(), getCategories(), getTags()])
      .then(([r, c, tg]) => {
        setRules(r)
        setCategories(c)
        setAvailableTags(tg)
        setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  function openAdd() {
    setRuleModalTarget(undefined)
    setRuleModalOpen(true)
    setConfirmDeleteId(null)
  }

  function openEdit(rule: Rule) {
    setRuleModalTarget(rule)
    setRuleModalOpen(true)
    setConfirmDeleteId(null)
  }

  function closeModal() {
    setRuleModalOpen(false)
    setRuleModalTarget(undefined)
  }

  function handleRuleSaved(rule: Rule) {
    setRules(prev => {
      const idx = prev.findIndex(r => r.id === rule.id)
      return idx >= 0
        ? prev.map(r => r.id === rule.id ? rule : r)
        : [...prev, rule]
    })
    closeModal()
  }

  // no-op: form lives in RuleFormModal

  async function handleToggleEnabled(rule: Rule) {
    try {
      const updated = await updateRule(rule.id, { enabled: !rule.enabled })
      setRules(prev => prev.map(r => r.id === rule.id ? updated : r))
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleDelete(id: number) {
    setDeleting(true)
    setError(null)
    try {
      await deleteRule(id)
      setRules(prev => prev.filter(r => r.id !== id))
      setConfirmDeleteId(null)
      if (ruleModalTarget?.id === id) closeModal()
    } catch (e) {
      setError(String(e))
    } finally {
      setDeleting(false)
    }
  }

  function modeLabel(mode: DescriptionMode): string {
    switch (mode) {
      case 'contains':    return t.rulesModeContains
      case 'starts_with': return t.rulesModeStartsWith
      case 'exact':       return t.rulesModeExact
      case 'regex':       return t.rulesModeRegex
    }
  }

  return (
    <>
      <main className="settings-page">
        <div className="settings-container">
          <h1 className="settings-heading">{t.navRules}</h1>
          <div className="card settings-card rules-card">
        <h2 className="settings-section-title">{t.rulesTitle}</h2>

        {error && <div className="import-error" style={{ marginBottom: 16 }}>{error}</div>}

        <div className="settings-add-form">
          <button className="btn-primary" type="button" onClick={openAdd}>
            {t.rulesAddBtn}
          </button>
        </div>
        {/* ── List ─────────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      ) : rules.length === 0 ? (
        <div className="state-box">
          <span className="icon">⚙️</span>
          <span>{t.rulesEmpty}</span>
        </div>
      ) : (
        <div className="rules-list-wrap">
          <table className="rules-table">
            <thead>
              <tr>
                <th>{t.rulesColEnabled}</th>
                <th>{t.rulesColName}</th>
                <th>{t.rulesColPattern}</th>
                <th>{t.rulesColCategory}</th>
                <th>{t.rulesColMerchant}</th>
                <th>{t.rulesColTags}</th>
                <th>{t.rulesColPriority}</th>
                <th>{t.rulesColActions}</th>
              </tr>
            </thead>
            <tbody>
              {sortedRules.map(rule => {
                if (confirmDeleteId === rule.id) {
                  return (
                    <tr key={rule.id} className="rules-row-confirm">
                      <td colSpan={8}>
                        <div className="rules-delete-confirm-row">
                          <span className="settings-delete-confirm">
                            {t.rulesDeleteConfirm(rule.name)}
                          </span>
                          <button
                            type="button"
                            className="btn-row-icon btn-row-cancel"
                            style={{ color: 'var(--expense)', borderColor: 'transparent' }}
                            onClick={() => handleDelete(rule.id)}
                            disabled={deleting}
                          >✓</button>
                          <button
                            type="button"
                            className="btn-row-icon btn-row-edit"
                            onClick={() => setConfirmDeleteId(null)}
                            disabled={deleting}
                          >✕</button>
                        </div>
                      </td>
                    </tr>
                  )
                }

                return (
                  <tr key={rule.id} className={rule.enabled ? '' : 'rules-row-disabled'}>
                    <td className="rules-td-enabled">
                      <input
                        type="checkbox"
                        className="rules-checkbox"
                        checked={rule.enabled}
                        onChange={() => handleToggleEnabled(rule)}
                        title={t.rulesFieldEnabled}
                      />
                    </td>
                    <td className="rules-td-name">{rule.name}</td>
                    <td className="rules-td-pattern">
                      <span className="rules-mode-badge">{modeLabel(rule.description_mode)}</span>
                      <span className="rules-pattern-value">{rule.description_value}</span>
                    </td>
                    <td className="rules-td-category">
                      {rule.set_category
                        ? categoryLabel(rule.set_category, lang, dynamicEs)
                        : <span className="rules-null">—</span>}
                    </td>
                    <td className="rules-td-merchant">
                      {rule.set_merchant !== null
                        ? rule.set_merchant
                        : <span className="rules-null">—</span>}
                    </td>
                    <td className="rules-td-tags">
                      {rule.add_tags.length > 0
                        ? rule.add_tags.map(tag => (
                          <span key={tag} className="tag-chip tag-chip-sm">{tag}</span>
                        ))
                        : <span className="rules-null">—</span>}
                    </td>
                    <td className="rules-td-priority">{rule.priority}</td>
                    <td className="rules-td-actions">
                      <div className="td-actions">
                        <button
                          type="button"
                          className="btn-row-icon btn-row-edit"
                         onClick={() => openEdit(rule)}
                          title={t.rulesBtnEdit}
                        >✎</button>
                        <button
                          type="button"
                          className="btn-row-icon btn-row-delete"
                          onClick={() => {
                             setConfirmDeleteId(rule.id)
                             if (ruleModalTarget?.id === rule.id) closeModal()
                           }}
                          title={t.rulesBtnDelete}
                        >🗑</button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
        </div>
        </div>
      </main>

      {ruleModalOpen && (
        <RuleFormModal
          editingRule={ruleModalTarget}
          categories={categories}
          availableTags={availableTags}
          onSave={handleRuleSaved}
          onClose={closeModal}
        />
      )}
    </>
  )
}
