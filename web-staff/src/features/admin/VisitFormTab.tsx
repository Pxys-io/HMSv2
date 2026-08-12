import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get, put } from '../../api/client'
import { Button, Card, inputClass } from '../../components/ui'
import { toast } from 'sonner'

type FormSection = {
  key: string
  label_en: string
  label_ar: string
  type: string
  required: boolean
  enabled: boolean
  options?: string[] | null
}

type SectionRow = FormSection & { labelEn: string; labelAr: string }

export function VisitFormTab() {
  const { data } = useQuery({
    queryKey: ['visit-form'],
    queryFn: () => get<{ sections: FormSection[]; builtin_keys: string[] }>('/api/visit-form/sections'),
  })
  const [rows, setRows] = useState<SectionRow[]>([])
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (data && rows.length === 0) {
      setRows(
        data.sections.map((s) => ({
          ...s,
          labelEn: s.label_en,
          labelAr: s.label_ar || '',
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

  const update = (i: number, patch: Partial<SectionRow>) => {
    const next = [...rows]
    next[i] = { ...next[i], ...patch }
    setRows(next)
    setDirty(true)
  }

  const save = async () => {
    const sections = rows.map((r) => ({
      key: r.key,
      label_en: r.labelEn,
      label_ar: r.labelAr,
      type: r.type,
      required: r.required,
      enabled: r.enabled,
      options: r.options ?? undefined,
    }))
    await put('/api/visit-form/sections', { sections })
    setDirty(false)
    toast.success('Visit form saved')
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-ink-600">Visit form designer</h2>
          <p className="text-xs text-ink-400">
            Order, rename, hide, or mark required. Extra fields are added under{' '}
            <span className="font-medium">Custom fields → Visits</span>.
          </p>
        </div>
        <Button onClick={() => void save()} disabled={!dirty}>
          Save
        </Button>
      </div>

      <div className="space-y-2">
        {rows.map((row, i) => (
          <div
            key={row.key}
            className={`rounded-lg border p-2 ${row.enabled ? 'border-border' : 'border-dashed opacity-60'}`}
          >
            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <button className="text-xs text-ink-400" onClick={() => move(i, -1)}>
                  ▲
                </button>
                <button className="text-xs text-ink-400" onClick={() => move(i, 1)}>
                  ▼
                </button>
              </div>
              <span className="w-44 shrink-0 font-mono text-xs text-ink-500">{row.key}</span>
              <input
                className={inputClass + ' flex-1'}
                value={row.labelEn}
                placeholder="EN label"
                onChange={(e) => update(i, { labelEn: e.target.value })}
              />
              <input
                className={inputClass + ' w-44'}
                value={row.labelAr}
                placeholder="AR label"
                dir="rtl"
                onChange={(e) => update(i, { labelAr: e.target.value })}
              />
              <label className="flex items-center gap-1 text-xs text-ink-600">
                <input
                  type="checkbox"
                  checked={row.enabled}
                  onChange={(e) => update(i, { enabled: e.target.checked })}
                />
                show
              </label>
              <label className="flex items-center gap-1 text-xs text-ink-600">
                <input
                  type="checkbox"
                  checked={row.required}
                  onChange={(e) => update(i, { required: e.target.checked })}
                />
                required
              </label>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
