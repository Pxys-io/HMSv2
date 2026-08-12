import { useQuery } from '@tanstack/react-query'
import { get } from '../../api/client'
import { inputClass } from '../../components/ui'
import {
  AnnotationInput,
  AudioRecorder,
  FileInput,
  PhotoInput,
} from './FormAssetInputs'

export type PatientFormField = {
  key: string
  label_en: string
  label_ar: string
  type: string
  required: boolean
  enabled: boolean
  options?: string[] | null
  width: string
  group: string
  help?: string | null
  default?: string | number | boolean | null
  min?: number | null
  max?: number | null
  pattern?: string | null
  template_file_id?: number | null
}

export function usePatientFormSchema() {
  return useQuery({
    queryKey: ['patient-form'],
    queryFn: () => get<{ fields: PatientFormField[]; fixed_keys: string[] }>('/api/patient-form'),
  })
}

export function splitPatientValues(
  fixedKeys: string[],
  values: Record<string, unknown>,
): { fixed: Record<string, unknown>; custom_data: Record<string, unknown> | undefined } {
  const fixed: Record<string, unknown> = {}
  const custom: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(values)) {
    if (v === '' || v === undefined || v === null) continue
    if (fixedKeys.includes(k)) fixed[k] = v
    else custom[k] = v
  }
  return { fixed, custom_data: Object.keys(custom).length ? custom : undefined }
}

export function fieldLabel(f: PatientFormField): string {
  return f.label_ar || f.label_en
}

function FieldInput({
  field,
  value,
  onChange,
  uploadUrl,
}: {
  field: PatientFormField
  value: unknown
  onChange: (v: unknown) => void
  uploadUrl?: string | null
}) {
  const cls = inputClass + (field.width === 'half' ? '' : ' w-full')
  switch (field.type) {
    case 'photo':
      return (
        <PhotoInput
          value={value}
          onChange={(v) => onChange(v)}
          uploadUrl={uploadUrl ?? null}
        />
      )
    case 'file':
      return (
        <FileInput
          value={value}
          onChange={(v) => onChange(v)}
          uploadUrl={uploadUrl ?? null}
        />
      )
    case 'annotation':
      return (
        <AnnotationInput
          value={value}
          onChange={(v) => onChange(v)}
          uploadUrl={uploadUrl ?? null}
          templateFileId={field.template_file_id}
        />
      )
    case 'audio':
      return (
        <AudioRecorder
          value={value}
          onChange={(v) => onChange(v)}
          uploadUrl={uploadUrl ?? null}
        />
      )
    case 'textarea':
      return (
        <textarea
          className={cls}
          rows={3}
          value={String(value ?? field.default ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'number':
      return (
        <input
          type="number"
          className={cls}
          value={
            value === null || value === undefined
              ? String(field.default ?? '')
              : Number(value)
          }
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      )
    case 'date':
      return (
        <input
          type="date"
          className={cls}
          value={String(value ?? field.default ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'tel':
      return (
        <input
          type="tel"
          className={cls}
          value={String(value ?? field.default ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
      )
    case 'boolean':
      return (
        <label className="flex items-center gap-2 text-sm text-ink-700">
          <input
            type="checkbox"
            checked={Boolean(value ?? field.default ?? false)}
            onChange={(e) => onChange(e.target.checked)}
          />
          {fieldLabel(field)}
        </label>
      )
    case 'select':
      return (
        <select
          className={cls}
          value={String(value ?? '')}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">—</option>
          {(field.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )
    case 'multiselect': {
      const current = (Array.isArray(value) ? value : []) as string[]
      return (
        <div className="flex flex-wrap gap-1">
          {(field.options ?? []).map((o) => (
            <button
              key={o}
              type="button"
              onClick={() =>
                onChange(
                  current.includes(o)
                    ? current.filter((x) => x !== o)
                    : [...current, o],
                )
              }
              className={`rounded-full px-2 py-1 text-xs ${
                current.includes(o)
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-100 text-ink-600'
              }`}
            >
              {o}
            </button>
          ))}
        </div>
      )
    }
    default:
      return (
        <input
          type="text"
          className={cls}
          value={String(value ?? field.default ?? '')}
          onChange={(e) => onChange(e.target.value)}
        />
      )
  }
}

export function PatientFormFields({
  values,
  onChange,
  uploadUrl,
}: {
  values: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  uploadUrl?: string | null
}) {
  const schema = usePatientFormSchema()
  const fields = (schema.data?.fields ?? []).filter((f) => f.enabled)

  function set(key: string, v: unknown) {
    onChange({ ...values, [key]: v })
  }

  const groups: Record<string, PatientFormField[]> = {}
  for (const f of fields) {
    ;(groups[f.group] ??= []).push(f)
  }

  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([group, groupFields]) => (
        <div key={group}>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
            {group}
          </p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            {groupFields.map((f) => (
              <div
                key={f.key}
                className={f.width === 'half' ? '' : 'col-span-2'}
              >
                <label className="mb-1 block text-xs text-ink-600">
                  {fieldLabel(f)}
                  {f.required && <span className="text-danger"> *</span>}
                </label>
                <FieldInput
                  field={f}
                  value={values[f.key]}
                  onChange={(v) => set(f.key, v)}
                  uploadUrl={uploadUrl}
                />
                {f.help && <p className="mt-0.5 text-[11px] text-ink-400">{f.help}</p>}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
