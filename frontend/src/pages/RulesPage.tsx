import { useState, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Rule, DescriptionMode } from '../api/types'
import { updateRule, deleteRule } from '../api/client'
import { useRules, useCategories, useTags, queryKeys } from '../api/queries'
import { errorMessage } from '../api/errors'
import { useT, categoryLabel } from '../i18n'
import RuleFormModal from '../components/RuleFormModal'
import { IconLoading, IconSettings, IconCheck, IconClose, IconPencil, IconTrash } from '../components/icons'

export default function RulesPage() {
  const { t, lang } = useT()
  const queryClient = useQueryClient()
  const rulesQuery = useRules()
  const categoriesQuery = useCategories()
  const tagsQuery = useTags()
  const EMPTY: never[] = useMemo(() => [], [])
  const rules = rulesQuery.data ?? EMPTY
  const categories = categoriesQuery.data ?? EMPTY
  const availableTags = tagsQuery.data ?? EMPTY
  const loading = rulesQuery.isPending || categoriesQuery.isPending || tagsQuery.isPending
  // Mutation errors only; load errors come from the queries.
  const [error, setError] = useState<string | null>(null)
  const firstQueryError = rulesQuery.error ?? categoriesQuery.error ?? tagsQuery.error
  const shownError = error ?? (firstQueryError ? errorMessage(firstQueryError, t) : null)

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

  function handleRuleSaved() {
    queryClient.invalidateQueries({ queryKey: queryKeys.rules })
    closeModal()
  }

  // no-op: form lives in RuleFormModal

  async function handleToggleEnabled(rule: Rule) {
    try {
      await updateRule(rule.id, { enabled: !rule.enabled })
      await queryClient.invalidateQueries({ queryKey: queryKeys.rules })
    } catch (e) {
      setError(errorMessage(e, t))
    }
  }

  async function handleDelete(id: number) {
    setDeleting(true)
    setError(null)
    try {
      await deleteRule(id)
      await queryClient.invalidateQueries({ queryKey: queryKeys.rules })
      setConfirmDeleteId(null)
      if (ruleModalTarget?.id === id) closeModal()
    } catch (e) {
      setError(errorMessage(e, t))
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

        {shownError && <div className="import-error" style={{ marginBottom: 16 }}>{shownError}</div>}

        <div className="settings-add-form">
          <button className="btn-primary" type="button" onClick={openAdd}>
            {t.rulesAddBtn}
          </button>
        </div>
        {/* ── List ─────────────────────────────────────────────────────────────── */}
      {loading ? (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : rules.length === 0 ? (
        <div className="state-box">
          <IconSettings size={18} />
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
                          ><IconCheck size={15} /></button>
                          <button
                            type="button"
                            className="btn-row-icon btn-row-edit"
                            onClick={() => setConfirmDeleteId(null)}
                            disabled={deleting}
                          ><IconClose size={15} /></button>
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
                        ><IconPencil size={15} /></button>
                        <button
                          type="button"
                          className="btn-row-icon btn-row-delete"
                          onClick={() => {
                             setConfirmDeleteId(rule.id)
                             if (ruleModalTarget?.id === rule.id) closeModal()
                           }}
                          title={t.rulesBtnDelete}
                        ><IconTrash size={15} /></button>
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
