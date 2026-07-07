import { useState, useEffect, useMemo } from 'react'
import type { Category } from '../api/types'
import { getCategories, updateCategory, createCategory } from '../api/client'
import { useT, categoryLabel, DEFAULT_TAG_COLOR } from '../i18n'

export default function CategoriesPage() {
  const { t, lang } = useT()
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Per-category: color being edited (before save) and save state
  const [pendingColors, setPendingColors] = useState<Record<number, string>>({})
  const [savingId, setSavingId] = useState<number | null>(null)
  const [savedId, setSavedId] = useState<number | null>(null)

  // Add form state
  const [addName,  setAddName]  = useState('')
  const [addColor, setAddColor] = useState(DEFAULT_TAG_COLOR)
  const [adding,   setAdding]   = useState(false)

  const dynamicEs = useMemo(
    () => Object.fromEntries(categories.filter(c => c.name_es).map(c => [c.name, c.name_es!])),
    [categories],
  )

  const sortedCategories = useMemo(
    () => [...categories].sort((a, b) =>
      categoryLabel(a.name, lang, dynamicEs).localeCompare(categoryLabel(b.name, lang, dynamicEs), lang)
    ),
    [categories, lang, dynamicEs],
  )

  useEffect(() => {
    setLoading(true)
    getCategories()
      .then(data => { setCategories(data); setLoading(false) })
      .catch(e  => { setError(String(e)); setLoading(false) })
  }, [])

  function getPendingColor(cat: Category): string {
    return pendingColors[cat.id] ?? cat.color ?? '#94a3b8'
  }

  async function handleColorChange(cat: Category, color: string) {
    setPendingColors(prev => ({ ...prev, [cat.id]: color }))
    setSavingId(cat.id)
    setSavedId(null)
    setError(null)
    try {
      const updated = await updateCategory(cat.id, { color })
      setCategories(prev => prev.map(c => c.id === cat.id ? updated : c))
      setPendingColors(prev => { const next = { ...prev }; delete next[cat.id]; return next })
      setSavedId(cat.id)
      setTimeout(() => setSavedId(id => id === cat.id ? null : id), 1800)
    } catch (e) {
      setError(String(e))
    } finally {
      setSavingId(id => id === cat.id ? null : id)
    }
  }

  async function handleAdd() {
    if (!addName.trim()) return
    setAdding(true)
    setError(null)
    try {
      const newCat = await createCategory(addName.trim(), addColor)
      setCategories(prev => [...prev, newCat])
      setAddName('')
      setAddColor(DEFAULT_TAG_COLOR)
    } catch (e) {
      setError(String(e))
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.settingsCatsTitle}</h2>

      {error && <div className="import-error" style={{ marginBottom: 16 }}>{error}</div>}

      {/* Add form */}
      <div className="settings-add-form">
        <div className="settings-add-title">{t.settingsCatsAddBtn}</div>
        <div className="settings-add-row">
          <input
            type="color"
            value={addColor}
            onChange={e => setAddColor(e.target.value)}
            className="tag-color-input"
            disabled={adding}
            title={t.settingsCatsAddColor}
          />
          <input
            type="text"
            value={addName}
            onChange={e => setAddName(e.target.value)}
            placeholder={t.settingsCatsAddName}
            className="form-input settings-tag-name-input"
            disabled={adding}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd() }}
          />
          <button
            className="btn-primary"
            onClick={handleAdd}
            disabled={adding || !addName.trim()}
          >
            {adding ? '…' : t.settingsCatsAddBtn}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="state-box">
          <span className="icon">⏳</span>
          <span>{t.loading}</span>
        </div>
      ) : categories.length === 0 ? (
        <div className="state-box">
          <span className="icon">🏷</span>
          <span>{t.settingsCatsEmpty}</span>
        </div>
      ) : (
        <div className="settings-cats-list">
          {sortedCategories.map(cat => {
            const currentColor = getPendingColor(cat)
            const isSaving = savingId === cat.id
            const justSaved = savedId === cat.id
            return (
              <div key={cat.id} className="settings-cat-row">
                <span
                  className="settings-cat-swatch"
                  style={{ background: currentColor, borderColor: currentColor + '55' }}
                />
                <span className="settings-cat-label">
                  {categoryLabel(cat.name, lang, dynamicEs)}
                </span>
                <span className="settings-count">{t.settingsCountLabel(cat.tx_count)}</span>
                <div className="settings-cat-actions">
                  {justSaved && (
                    <span className="settings-cat-saved">{t.settingsCatsSaved}</span>
                  )}
                  {isSaving && (
                    <span className="settings-cat-saving">…</span>
                  )}
                  <input
                    type="color"
                    value={currentColor}
                    onChange={e => handleColorChange(cat, e.target.value)}
                    className="tag-color-input"
                    disabled={isSaving}
                    title={currentColor}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
