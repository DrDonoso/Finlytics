import { useState, useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import type { Tag } from '../api/types'
import { createTag, updateTag, deleteTag } from '../api/client'
import { useTags, queryKeys } from '../api/queries'
import { errorMessage } from '../api/errors'
import { useT, DEFAULT_TAG_COLOR, tagTextColor, paletteColor } from '../i18n'
import ColorSwatchPicker from '../components/ColorSwatchPicker'
import { IconLoading, IconTag, IconCheck, IconClose, IconPencil, IconTrash } from '../components/icons'

function tagLabel(tag: Tag): string {
  return tag.emoji ? `${tag.emoji} ${tag.name}` : tag.name
}

export default function SettingsPage() {
  const { t, lang } = useT()
  const queryClient = useQueryClient()
  const tagsQuery = useTags()
  const EMPTY: never[] = useMemo(() => [], [])
  const tags = tagsQuery.data ?? EMPTY
  const loading = tagsQuery.isPending
  // Sólo errores de las mutaciones; el de la carga lo aporta la consulta.
  const [error, setError] = useState<string | null>(null)
  const shownError = error ?? (tagsQuery.error ? errorMessage(tagsQuery.error, t) : null)

  // Add form
  const [addName,         setAddName]         = useState('')
  const [addColor,        setAddColor]        = useState(DEFAULT_TAG_COLOR)
  const [adding,          setAdding]          = useState(false)

  // Inline edit
  const [editId,    setEditId]    = useState<number | null>(null)
  const [editName,  setEditName]  = useState('')
  const [editColor, setEditColor] = useState('')
  const [saving,    setSaving]    = useState(false)

  // Delete confirm
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [deleting,        setDeleting]        = useState(false)

  const sortedTags = useMemo(
    () => [...tags].sort((a, b) => a.name.localeCompare(b.name, lang)),
    [tags, lang],
  )

  async function handleAdd() {
    if (!addName.trim()) return
    setAdding(true)
    setError(null)
    try {
      await createTag(addName.trim(), addColor)
      await queryClient.invalidateQueries({ queryKey: queryKeys.tags })
      setAddName('')
      setAddColor(DEFAULT_TAG_COLOR)
    } catch (e) {
      setError(errorMessage(e, t))
    } finally {
      setAdding(false)
    }
  }

  function startEdit(tag: Tag) {
    setEditId(tag.id)
    setEditName(tag.emoji ? `${tag.emoji} ${tag.name}` : tag.name)
    setEditColor(tag.color || DEFAULT_TAG_COLOR)
    setConfirmDeleteId(null)
  }

  async function handleSave() {
    if (editId === null) return
    setSaving(true)
    setError(null)
    try {
      await updateTag(editId, {
        name:  editName.trim() || undefined,
        color: editColor || undefined,
      })
      await queryClient.invalidateQueries({ queryKey: queryKeys.tags })
      setEditId(null)
    } catch (e) {
      setError(errorMessage(e, t))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: number) {
    setDeleting(true)
    setError(null)
    try {
      await deleteTag(id)
      await queryClient.invalidateQueries({ queryKey: queryKeys.tags })
      setConfirmDeleteId(null)
      if (editId === id) setEditId(null)
    } catch (e) {
      setError(errorMessage(e, t))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="card settings-card">
      <h2 className="settings-section-title">{t.settingsTagsTitle}</h2>

      {shownError && <div className="import-error" style={{ marginBottom: 16 }}>{shownError}</div>}

      {/* Add form */}
      <div className="settings-add-form">
        <div className="settings-add-title">{t.settingsTagsAddBtn}</div>
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
            placeholder={t.settingsTagsAddName}
            className="form-input settings-tag-name-input"
            disabled={adding}
            onKeyDown={e => { if (e.key === 'Enter') handleAdd() }}
          />
          <button
            className="btn-primary"
            onClick={handleAdd}
            disabled={adding || !addName.trim()}
          >
            {t.settingsTagsAddBtn}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="state-box">
          <IconLoading size={18} />
          <span>{t.loading}</span>
        </div>
      ) : tags.length === 0 ? (
        <div className="state-box">
          <IconTag size={18} />
          <span>{t.settingsTagsEmpty}</span>
        </div>
      ) : (
        <div className="settings-tags-list">
          {sortedTags.map(tag => {
            const color = tag.color || DEFAULT_TAG_COLOR
            const textC = tagTextColor(color)

            if (editId === tag.id) {
              return (
                <div key={tag.id} className="settings-tag-row settings-tag-row-editing">
                  <div className="settings-tag-edit-top">
                    <input
                      type="text"
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      className="form-input settings-tag-name-input"
                      disabled={saving}
                      autoFocus
                      placeholder={t.settingsTagsAddName}
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleSave()
                        if (e.key === 'Escape') setEditId(null)
                      }}
                    />
                    <div className="td-actions">
                      <button
                        className="btn-row-icon btn-row-save"
                        onClick={handleSave}
                        disabled={saving}
                        title={t.tableSaveRow}
                      ><IconCheck size={15} /></button>
                      <button
                        className="btn-row-icon btn-row-cancel"
                        onClick={() => setEditId(null)}
                        disabled={saving}
                        title={t.tableCancelEdit}
                      ><IconClose size={15} /></button>
                    </div>
                  </div>
                  <div className="settings-tag-edit-bottom">
                    <ColorSwatchPicker value={editColor} onChange={setEditColor} disabled={saving} />
                    <span
                      className="preview-tag-chip"
                      style={{ background: editColor, color: tagTextColor(editColor), borderColor: editColor + '88' }}
                    >
                      {editName.trim() || '…'}
                    </span>
                  </div>
                </div>
              )
            }

            if (confirmDeleteId === tag.id) {
              return (
                <div key={tag.id} className="settings-tag-row settings-tag-row-confirm">
                  <div className="settings-tag-swatch" style={{ background: color }} />
                  <span className="settings-delete-confirm">
                    {t.settingsTagsDeleteConfirm(tagLabel(tag))}
                  </span>
                  <div className="td-actions" style={{ marginLeft: 'auto' }}>
                    <button
                      className="btn-row-icon btn-row-cancel"
                      style={{ color: 'var(--expense)', borderColor: 'transparent' }}
                      onClick={() => handleDelete(tag.id)}
                      disabled={deleting}
                      title={t.settingsTagsDelete}
                    ><IconCheck size={15} /></button>
                    <button
                      className="btn-row-icon btn-row-edit"
                      onClick={() => setConfirmDeleteId(null)}
                      disabled={deleting}
                      title={t.tableCancelEdit}
                    ><IconClose size={15} /></button>
                  </div>
                </div>
              )
            }

            return (
              <div key={tag.id} className="settings-tag-row">
                <span
                  className="tag-chip"
                  style={{ background: color, color: textC, borderColor: color + '88' }}
                >
                  {tagLabel(tag)}
                </span>
                <span className="settings-count" style={{ marginLeft: 'auto' }}>{t.settingsCountLabel(tag.tx_count)}</span>
                <div className="td-actions">
                  <button
                    className="btn-row-icon btn-row-edit"
                    onClick={() => startEdit(tag)}
                    title={t.tableEditRow}
                  ><IconPencil size={15} /></button>
                  <button
                    className="btn-row-icon btn-row-delete"
                    onClick={() => { setConfirmDeleteId(tag.id); setEditId(null) }}
                    title={t.settingsTagsDelete}
                  ><IconTrash size={15} /></button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

