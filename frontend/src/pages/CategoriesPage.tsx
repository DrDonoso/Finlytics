import { useState, useEffect, useMemo } from 'react'
import type { Category } from '../api/types'
import { getCategories, updateCategory, createCategory } from '../api/client'
import { useT, categoryLabel, DEFAULT_TAG_COLOR, paletteColor, tagTextColor } from '../i18n'
import ColorSwatchPicker from '../components/ColorSwatchPicker'
import { IconLoading, IconTag, IconCheck, IconClose, IconPencil } from '../components/icons'

export default function CategoriesPage() {
  const { t, lang } = useT()
  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Save state
  const [savingId, setSavingId] = useState<number | null>(null)
  const [savedId,  setSavedId]  = useState<number | null>(null)

  // Per-category inline color edit
  const [editCatId,    setEditCatId]    = useState<number | null>(null)
  const [editCatColor, setEditCatColor] = useState('')

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

  async function handleSaveCatColor() {
    if (editCatId === null) return
    const catId = editCatId
    const color = editCatColor
    setSavingId(catId)
    setSavedId(null)
    setError(null)
    try {
      const updated = await updateCategory(catId, { color })
      setCategories(prev => prev.map(c => c.id === catId ? updated : c))
      setSavedId(catId)
      setTimeout(() => setSavedId(id => id === catId ? null : id), 1800)
      setEditCatId(null)
    } catch (e) {
      setError(String(e))
    } finally {
      setSavingId(id => id === catId ? null : id)
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
          <span
            className="preview-tag-chip"
            style={{
              background: addColor,
              color: tagTextColor(addColor),
              borderColor: addColor + '88',
              opacity: addName.trim() ? 1 : 0.4,
              flexShrink: 0,
            }}
          >
            {addName.trim() || '…'}
          </span>
          <input
            type="text"
            value={addName}
            onChange={e => {
              const v = e.target.value
              setAddName(v)
              setAddColor(v.trim() ? paletteColor(v.trim().toLowerCase()) : DEFAULT_TAG_COLOR)
            }}
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
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : categories.length === 0 ? (
        <div className="state-box">
          <IconTag size={18} />
          <span>{t.settingsCatsEmpty}</span>
        </div>
      ) : (
        <div className="settings-cats-list">
          {sortedCategories.map(cat => {
            const isSaving = savingId === cat.id
            const justSaved = savedId === cat.id
            const catLabel = categoryLabel(cat.name, lang, dynamicEs)

            if (editCatId === cat.id) {
              return (
                <div key={cat.id} className="settings-cat-row settings-cat-row-editing">
                  <span className="settings-cat-label">{catLabel}</span>
                  <div className="settings-cat-edit-block">
                    <ColorSwatchPicker
                      value={editCatColor}
                      onChange={setEditCatColor}
                      disabled={isSaving}
                    />
                    <div className="settings-cat-edit-footer">
                      <span
                        className="preview-tag-chip"
                        style={{
                          background: editCatColor,
                          color: tagTextColor(editCatColor),
                          borderColor: editCatColor + '88',
                        }}
                      >
                        {catLabel}
                      </span>
                      <div className="settings-cat-actions">
                        {isSaving && <span className="settings-cat-saving">…</span>}
                        <button
                          className="btn-row-icon btn-row-save"
                          onClick={handleSaveCatColor}
                          disabled={isSaving}
                          title={t.tableSaveRow}
                        ><IconCheck size={15} /></button>
                        <button
                          className="btn-row-icon btn-row-cancel"
                          onClick={() => setEditCatId(null)}
                          disabled={isSaving}
                          title={t.tableCancelEdit}
                        ><IconClose size={15} /></button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            }

            return (
              <div key={cat.id} className="settings-cat-row">
                <span
                  className="settings-cat-swatch"
                  style={{ background: cat.color || '#94a3b8', borderColor: (cat.color || '#94a3b8') + '55' }}
                />
                <span className="settings-cat-label">{catLabel}</span>
                <span className="settings-count">{t.settingsCountLabel(cat.tx_count)}</span>
                <div className="settings-cat-actions">
                  {justSaved && <span className="settings-cat-saved">{t.settingsCatsSaved}</span>}
                  {isSaving && <span className="settings-cat-saving">…</span>}
                  <button
                    className="btn-row-icon btn-row-edit"
                    onClick={() => { setEditCatId(cat.id); setEditCatColor(cat.color || DEFAULT_TAG_COLOR) }}
                    disabled={isSaving}
                    title={t.tableEditRow}
                  ><IconPencil size={15} /></button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
