import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get, put, uploadFile } from '../../api/client'
import { Button, Card, inputClass } from '../../components/ui'
import { toast } from 'sonner'

type FieldRow = {
  key: string
  labelEn: string
  labelAr: string
  type: string
  required: boolean
  enabled: boolean
  width: string
  group: string
  help: string
  optionsText: string
  min: string
  max: string
  pattern: string
  template_file_id: number | null
}

const TYPES = [
  'text', 'tel', 'textarea', 'number', 'date', 'select', 'multiselect',
  'boolean', 'photo', 'file', 'annotation', 'audio',
]

const TYPE_HELP: Record<string, string> = {
  photo: 'Open camera / upload photo',
  file: 'Upload any file',
  annotation: 'Doctor draws on an uploaded template',
  audio: 'Record conversation with pause/continue',
}

function emptyRow(i: number): FieldRow {
  return {
    key: `field_${Date.now()}_${i}`, labelEn: '', labelAr: '', type: 'text',
    required: false, enabled: true, width: 'full', group: 'Other', help: '',
    optionsText: '', min: '', max: '', pattern: '', template_file_id: null,
  }
}

type ApiField = {
  key: string
  label_en?: string | null
  label_ar?: string | null
  type?: string
  required?: boolean
  enabled?: boolean
  width?: string
  group?: string
  help?: string | null
  options?: string[] | null
  min?: number | null
  max?: number | null
  pattern?: string | null
  template_file_id?: number | null
}

export function PatientFormTab() {
  const { data } = useQuery({
    queryKey: ['patient-form'],
    queryFn: () => get<{ fields: ApiField[] }>('/api/patient-form'),
  })
  const [rows, setRows] = useState<FieldRow[]>([])
  const [dirty, setDirty] = useState(false)
  const [templateBusy, setTemplateBusy] = useState<number | null>(null)

  useEffect(() => {
    if (data && rows.length === 0) {
      setRows(
        data.fields.map((f) => ({
          key: f.key,
          labelEn: f.label_en ?? '',
          labelAr: f.label_ar ?? '',
          type: f.type ?? 'text',
          required: Boolean(f.required),
          enabled: f.enabled !== false,
          width: f.width ?? 'full',
          group: f.group ?? 'Other',
          help: f.help ?? '',
          optionsText: Array.isArray(f.options) ? f.options.join('\n') : '',
          min: f.min != null ? String(f.min) : '',
          max: f.max != null ? String(f.max) : '',
          pattern: f.pattern ?? '',
          template_file_id: f.template_file_id ?? null,
        })),
      )
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  const move = (i: number, dir: -1 | 1) => {
    const next = [...rows]
    const j = i + dir
    if (j < 0 || j >= next.length) return
    ;[next[i], next[j]] = [next[j], next[i]]
    setRows(next)
    setDirty(true)
  }

  const update = (i: number, patch: Partial<FieldRow>) => {
    const next = [...rows]
    next[i] = { ...next[i], ...patch }
    setRows(next)
    setDirty(true)
  }

  const uploadTemplate = async (i: number, file: File) => {
    setTemplateBusy(i)
    try {
      const form = new FormData()
      form.append('file', file)
      const body = await uploadFile<{ template_file_id: number }>(
        '/api/form-assets/template',
        form,
      )
      update(i, { template_file_id: body.template_file_id })
      toast.success('Template uploaded')
    } catch {
      /* toast already shown */
    } finally {
      setTemplateBusy(null)
    }
  }

  const save = async () => {
    const fields = rows.map((r) => ({
      key: r.key.trim() || undefined,
      label_en: r.labelEn.trim(),
      label_ar: r.labelAr.trim(),
      type: r.type,
      required: r.required,
      enabled: r.enabled,
      width: r.width,
      group: r.group.trim() || 'Other',
      help: r.help.trim() || undefined,
      options: r.optionsText
        ? r.optionsText.split('\n').map((o) => o.trim()).filter(Boolean)
        : undefined,
      min: r.min === '' ? undefined : Number(r.min),
      max: r.max === '' ? undefined : Number(r.max),
      pattern: r.pattern.trim() || undefined,
      template_file_id: r.template_file_id,
    }))
    try {
      await put('/api/patient-form', { fields })
      setDirty(false)
      toast.success('Patient form saved')
    } catch {
      /* toast already shown */
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-ink-600">Patient form builder</h2>
          <p className="text-xs text-ink-400">
            Full intake form: groups, types, validation rules, photo/camera,
            file upload, annotated templates and audio recording.
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="ghost"
            onClick={() => {
              setRows([...rows, emptyRow(rows.length)])
              setDirty(true)
            }}
          >
            + Add field
          </Button>
          <Button onClick={() => void save()} disabled={!dirty}>
            Save
          </Button>
        </div>
      </div>

      <div className="space-y-3">
        {rows.map((row, i) => (
          <div
            key={`${row.key}-${i}`}
            className={`rounded-lg border p-3 ${row.enabled ? 'border-border' : 'border-dashed opacity-60'}`}
          >
            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <button className="text-xs text-ink-400" onClick={() => move(i, -1)}>▲</button>
                <button className="text-xs text-ink-400" onClick={() => move(i, 1)}>▼</button>
              </div>
              <span className="w-36 shrink-0 truncate font-mono text-xs text-ink-500" title={row.key}>
                {row.key}
              </span>
              <input
                className={inputClass + ' flex-1'}
                placeholder="EN label"
                value={row.labelEn}
                onChange={(e) => update(i, { labelEn: e.target.value })}
              />
              <input
                className={inputClass + ' w-40'}
                placeholder="AR label"
                dir="rtl"
                value={row.labelAr}
                onChange={(e) => update(i, { labelAr: e.target.value })}
              />
              <select
                className={inputClass + ' w-32'}
                value={row.type}
                onChange={(e) => update(i, { type: e.target.value })}
              >
                {TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button
                className="text-xs text-red-600 underline"
                onClick={() => {
                  setRows(rows.filter((_, j) => j !== i))
                  setDirty(true)
                }}
              >
                delete
              </button>
            </div>

            {TYPE_HELP[row.type] && (
              <p className="mt-1 text-[11px] text-brand-600">ℹ {TYPE_HELP[row.type]}</p>
            )}

            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-600">
              <input
                className={inputClass + ' w-36'}
                placeholder="Group"
                value={row.group}
                onChange={(e) => update(i, { group: e.target.value })}
              />
              <select
                className={inputClass + ' w-24'}
                value={row.width}
                onChange={(e) => update(i, { width: e.target.value })}
              >
                <option value="full">full width</option>
                <option value="half">half width</option>
              </select>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={row.required}
                  onChange={(e) => update(i, { required: e.target.checked })}
                />
                required
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => update(i, { enabled: e.target.checked })}
                />
                show
              </label>
              {row.type === 'annotation' && (
                <label className="flex items-center gap-1">
                  {row.template_file_id ? (
                    <span className="text-green-700">✓ template #{row.template_file_id}</span>
                  ) : null}
                  <span className="rounded-md border border-border px-2 py-1">
                    {templateBusy === i ? 'Uploading…' : '⬆ Template'}
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) void uploadTemplate(i, file)
                      }}
                    />
                  </span>
                </label>
              )}
            </div>

            {(row.type === 'select' || row.type === 'multiselect') && (
              <textarea
                className={inputClass + ' mt-2'}
                rows={2}
                placeholder={'Options (one per line)'}
                value={row.optionsText}
                onChange={(e) => update(i, { optionsText: e.target.value })}
              />
            )}

            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <input
                className={inputClass + ' w-64'}
                placeholder="Help text (optional)"
                value={row.help}
                onChange={(e) => update(i, { help: e.target.value })}
              />
              <input
                className={inputClass + ' w-20'}
                placeholder="Min"
                value={row.min}
                onChange={(e) => update(i, { min: e.target.value })}
              />
              <input
                className={inputClass + ' w-20'}
                placeholder="Max"
                value={row.max}
                onChange={(e) => update(i, { max: e.target.value })}
              />
              <input
                className={inputClass + ' w-56'}
                placeholder="Pattern (regex, e.g. ^01[0-9]{9}$)"
                value={row.pattern}
                onChange={(e) => update(i, { pattern: e.target.value })}
              />
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
