import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, uploadFile } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type FieldRow = {
  id: number
  entity: string
  key: string
  label: string
  label_ar: string | null
  type: string
  options: string[] | null
  is_required: boolean
  is_active: boolean
  order: number
}

const TYPES = ['text', 'textarea', 'number', 'date', 'select', 'multiselect',
  'boolean', 'photo', 'file', 'annotation', 'audio']

export function CustomFieldsTab() {
  const [entity, setEntity] = useState<'patient' | 'visit'>('patient')
  const [createOpen, setCreateOpen] = useState(false)
  const queryClient = useQueryClient()

  const fields = useQuery({
    queryKey: ['custom-fields', entity],
    queryFn: () => get<FieldRow[]>(`/api/custom-fields?entity=${entity}`),
  })
  const rows = fields.data ?? []

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Custom fields</h1>
        <select
          className={inputClass + ' w-32'}
          value={entity}
          onChange={(e) => setEntity(e.target.value as 'patient' | 'visit')}
        >
          <option value="patient">Patients</option>
          <option value="visit">Visits</option>
        </select>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Field</Button>
      </div>
      <p className="mt-2 text-xs text-ink-400">
        Zero-code extra fields rendered on the patient and exam forms. Deactivated fields stay
        readable but disappear from forms.
      </p>
      <Card className="mt-3">
        <div className="divide-y divide-border">
          {rows.map((f) => (
            <div key={f.id} className="flex items-center gap-4 p-3 text-sm">
              <span className="w-32 font-mono text-xs text-ink-400">{f.key}</span>
              <span className="flex-1 font-medium text-ink-900">
                {f.label}
                {f.label_ar ? <span className="ms-2 text-ink-400">{f.label_ar}</span> : null}
              </span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                {f.type}
              </span>
              {f.is_required && <span className="text-xs text-danger">required</span>}
              {!f.is_active && <span className="text-xs text-ink-400">(inactive)</span>}
              {f.is_active && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    await post(`/api/custom-fields/${f.id}/deactivate`, {})
                    queryClient.invalidateQueries({ queryKey: ['custom-fields'] })
                  }}
                >
                  Deactivate
                </Button>
              )}
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No custom fields for this entity" />}
        </div>
      </Card>

      {createOpen && (
        <FieldModal entity={entity} onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />
      )}
    </div>
  )
}

function FieldModal({
  entity,
  onClose,
  onDone,
}: {
  entity: string
  onClose: () => void
  onDone: () => void
}) {
  const [label, setLabel] = useState('')
  const [labelAr, setLabelAr] = useState('')
  const [type, setType] = useState('text')
  const [optionsText, setOptionsText] = useState('')
  const [required, setRequired] = useState(false)
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [templateBusy, setTemplateBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit() {
    setError('')
    try {
      await post('/api/custom-fields', {
        entity,
        label,
        label_ar: labelAr || undefined,
        type,
        options:
          type === 'select' || type === 'multiselect'
            ? optionsText.split(',').map((s) => s.trim()).filter(Boolean)
            : undefined,
        template_file_id: type === 'annotation' ? templateId : undefined,
        is_required: required,
      })
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New custom field">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Label (key auto-generated)" value={label} onChange={(e) => setLabel(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Label (AR)" value={labelAr} onChange={(e) => setLabelAr(e.target.value)} />
      <select className={inputClass + ' mt-2'} value={type} onChange={(e) => setType(e.target.value)}>
        {TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
      {type === 'annotation' && (
        <label className="mt-2 flex items-center gap-2 text-xs text-ink-600">
          <span className="rounded-md border border-border px-2 py-1">
            {templateBusy ? 'Uploading…' : templateId ? `✓ template #${templateId}` : '⬆ Template image'}
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                setTemplateBusy(true)
                try {
                  const form = new FormData()
                  form.append('file', file)
                  const body = await uploadFile<{ template_file_id: number }>(
                    '/api/form-assets/template',
                    form,
                  )
                  setTemplateId(body.template_file_id)
                } catch {
                  /* toast shown by client */
                } finally {
                  setTemplateBusy(false)
                }
              }}
            />
          </span>
        </label>
      )}
      {(type === 'select' || type === 'multiselect') && (
        <input
          className={inputClass + ' mt-2'}
          placeholder="Options (comma separated)"
          value={optionsText}
          onChange={(e) => setOptionsText(e.target.value)}
        />
      )}
      <label className="mt-2 flex items-center gap-2 text-sm text-ink-600">
        <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
        Required
      </label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={label.length < 2}>
          Create
        </Button>
      </div>
    </Modal>
  )
}
