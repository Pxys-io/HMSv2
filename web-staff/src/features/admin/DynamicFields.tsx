import { useQuery } from '@tanstack/react-query'
import { get } from '../../api/client'
import { inputClass } from '../../components/ui'
import {
  AnnotationInput,
  AudioRecorder,
  FileInput,
  PhotoInput,
} from '../patients/FormAssetInputs'

type FieldDef = {
  id: number
  key: string
  label: string
  label_ar: string | null
  type: string
  options: string[] | null
  is_required: boolean
  template_file_id?: number | null
}

export function useFieldSchema(entity: 'patient' | 'visit') {
  return useQuery({
    queryKey: ['field-schema', entity],
    queryFn: () => get<{ fields: FieldDef[] }>(`/api/custom-fields/schema?entity=${entity}`),
  })
}

export function DynamicFields({
  entity,
  value,
  onChange,
  uploadUrl,
}: {
  entity: 'patient' | 'visit'
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  uploadUrl?: string | null
}) {
  const schema = useFieldSchema(entity)
  const fields = schema.data?.fields ?? []
  if (fields.length === 0) return null

  function set(key: string, v: unknown) {
    onChange({ ...value, [key]: v })
  }

  return (
    <div className="mt-3 space-y-2 border-t border-border pt-3">
      <p className="text-xs font-semibold text-ink-600">
        {entity === 'visit' ? 'Extra fields' : 'Patient fields'}
      </p>
      {fields.map((f) => (
        <div key={f.key}>
          <label className="mb-1 block text-xs text-ink-600">
            {f.label_ar || f.label}
            {f.is_required && <span className="text-danger"> *</span>}
          </label>
          {f.type === 'photo' && (
            <PhotoInput value={value[f.key]} onChange={(v) => set(f.key, v)} uploadUrl={uploadUrl ?? null} />
          )}
          {f.type === 'file' && (
            <FileInput value={value[f.key]} onChange={(v) => set(f.key, v)} uploadUrl={uploadUrl ?? null} />
          )}
          {f.type === 'annotation' && (
            <AnnotationInput
              value={value[f.key]}
              onChange={(v) => set(f.key, v)}
              uploadUrl={uploadUrl ?? null}
              templateFileId={f.template_file_id}
            />
          )}
          {f.type === 'audio' && (
            <AudioRecorder value={value[f.key]} onChange={(v) => set(f.key, v)} uploadUrl={uploadUrl ?? null} />
          )}
          {f.type === 'text' && (
            <input
              className={inputClass}
              value={String(value[f.key] ?? '')}
              onChange={(e) => set(f.key, e.target.value)}
            />
          )}
          {f.type === 'textarea' && (
            <textarea
              className={inputClass}
              rows={2}
              value={String(value[f.key] ?? '')}
              onChange={(e) => set(f.key, e.target.value)}
            />
          )}
          {f.type === 'number' && (
            <input
              className={inputClass}
              type="number"
              value={String(value[f.key] ?? '')}
              onChange={(e) => set(f.key, e.target.value === '' ? null : Number(e.target.value))}
            />
          )}
          {f.type === 'date' && (
            <input
              className={inputClass}
              type="date"
              value={String(value[f.key] ?? '')}
              onChange={(e) => set(f.key, e.target.value || null)}
            />
          )}
          {f.type === 'boolean' && (
            <input
              type="checkbox"
              checked={Boolean(value[f.key])}
              onChange={(e) => set(f.key, e.target.checked)}
            />
          )}
          {f.type === 'select' && (
            <select
              className={inputClass}
              value={String(value[f.key] ?? '')}
              onChange={(e) => set(f.key, e.target.value || null)}
            >
              <option value="">—</option>
              {(f.options ?? []).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          )}
          {f.type === 'multiselect' && (
            <div className="flex flex-wrap gap-1">
              {(f.options ?? []).map((o) => {
                const selected = Array.isArray(value[f.key]) && (value[f.key] as string[]).includes(o)
                return (
                  <button
                    key={o}
                    type="button"
                    onClick={() => {
                      const current = Array.isArray(value[f.key]) ? (value[f.key] as string[]) : []
                      set(
                        f.key,
                        selected ? current.filter((x) => x !== o) : [...current, o],
                      )
                    }}
                    className={`rounded-full border px-2 py-0.5 text-xs ${
                      selected ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-border'
                    }`}
                  >
                    {o}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export type { FieldDef }
