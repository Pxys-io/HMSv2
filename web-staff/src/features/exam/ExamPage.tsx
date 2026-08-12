import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { fetchBlob, get, patch, post, put, uploadFile } from '../../api/client'
import { toast } from 'sonner'
import { Button, Card, Field, Modal, StatusBadge, inputClass } from '../../components/ui'
import { CameraCapture } from '../../components/pwa'
import { DynamicFields } from '../admin/DynamicFields'

type VisitTypeRow = {
  id: number
  name: string
  name_ar: string
  category: string
  duration_minutes: number
  default_price: number
}

type Visit = {
  id: number
  status: string
  record_version: number
  visit_type_id: number | null
  custom_type_name: string | null
  chief_complaint: string | null
  history: string | null
  vitals: Record<string, number | null> | null
  clinical_exam: string | null
  findings: string | null
  labs: string | null
  imaging: string | null
  plan: string | null
  notes_next_visit: string | null
  notes_private: string | null
  custom_data: Record<string, unknown> | null
  follow_up_weeks: number | null
  follow_up_due: string | null
  started_at: string | null
  ended_at: string | null
  doctor_id: number | null
  diagnoses: { kind: string; label: string; icd10_code: string | null }[]
  prescription: { id: number; notes: string | null; items: PrescriptionItem[] } | null
  attachments: { id: number; kind: string; title: string | null; mime: string; scan_status: string }[]
  patient: { full_name: string; code: string; phone: string } | null
}

type PrescriptionItem = {
  id: number
  medication_id: number | null
  free_text: string | null
  dose: string
  frequency: string
  duration: string
  route: string | null
  instructions: string | null
  quantity: string | null
}

type TimelineCard = {
  id: number
  date: string
  doctor_name: string | null
  status: string
  visit_type_id?: number
  [key: string]: unknown
}

type FormSection = {
  key: string
  label_en: string
  label_ar: string
  type: string
  required: boolean
  enabled: boolean
  options?: string[] | null
}

// Built-in section keys are fixed visit columns; the exam form renders the
// order/labels/enabled flags from /api/visit-form/sections (admin-designed).
const BUILTIN_KEYS = [
  'chief_complaint', 'history', 'clinical_exam', 'findings',
  'labs', 'imaging', 'plan', 'notes_next_visit',
] as const

function buildFields(draft: Record<string, unknown>): Record<string, unknown> {
  const fields: Record<string, unknown> = {}
  for (const key of BUILTIN_KEYS) {
    const value = draft[key]
    if (typeof value === 'string' && value.trim() === '') {
      fields[key] = null
    } else if (value !== undefined) {
      fields[key] = value
    }
  }
  if (draft.follow_up_weeks !== undefined) {
    fields.follow_up_weeks = draft.follow_up_weeks === '' ? null : Number(draft.follow_up_weeks)
  }
  const custom = draft.custom_data as Record<string, unknown> | undefined
  if (custom && Object.keys(custom).length > 0) {
    fields.custom_data = custom
  }
  const vitals = draft.vitals as Record<string, unknown> | undefined
  if (vitals && Object.values(vitals).some((v) => v !== null && v !== undefined)) {
    fields.vitals = vitals
  }
  return fields
}

export default function ExamPage() {
  const { profileId } = useParams()
  const [params] = useSearchParams()
  const entryId = params.get('entry')
  const viewVisitId = params.get('visit_id')
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const versionRef = useRef(0)
  const lastSavedRef = useRef('')

  const [draft, setDraft] = useState<Record<string, unknown>>({})
  const setVersion = (v: number) => {
    versionRef.current = v
  }
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'conflict'>('idle')
  const [rxDraft, setRxDraft] = useState<{ notes: string | null; items: Omit<PrescriptionItem, 'id'>[] }>({
    notes: null,
    items: [],
  })
  const [ddLabels, setDdLabels] = useState('')
  const [finalLabels, setFinalLabels] = useState('')
  const [mobileTab, setMobileTab] = useState<'history' | 'exam' | 'rx'>('exam')
  const [typeOpen, setTypeOpen] = useState(false)
  const [customProcedure, setCustomProcedure] = useState('')
  const [typeError, setTypeError] = useState('')

  const formConfig = useQuery({
    queryKey: ['visit-form'],
    queryFn: () => get<{ sections: FormSection[] }>('/api/visit-form/sections'),
  })
  const activeSections = (formConfig.data?.sections ?? []).filter(
    (section) => section.enabled && (BUILTIN_KEYS as readonly string[]).includes(section.key)
  )
  const visitTypes = useQuery({
    queryKey: ['visit-types'],
    queryFn: () => get<VisitTypeRow[]>('/api/visit-types'),
  })

  async function changeType(visitTypeId: number | null, customName: string) {
    if (!visit.data) return
    setTypeError('')
    try {
      const updated = await patch<Visit>(
        `/api/visits/${visit.data.id}`,
        {
          visit_type_id: visitTypeId,
          custom_type_name: customName || null,
          record_version: versionRef.current,
        },
        crypto.randomUUID(),
      )
      versionRef.current = updated.record_version
      setVersion(updated.record_version)
      setTypeOpen(false)
      visit.refetch()
    } catch (err) {
      setTypeError(err instanceof Error ? err.message : 'failed')
    }
  }


  const visit = useQuery({
    queryKey: ['visit', profileId, entryId, viewVisitId],
    queryFn: async () => {
      if (viewVisitId) {
        // Browsing an old (usually completed) visit from the timeline.
        return get<Visit>(`/api/visits/${Number(viewVisitId)}`)
      }
      if (entryId) {
        // From the queue: the visit already exists or is created here
        // (service re-enters idempotently).
        return post<Visit>(
          '/api/visits',
          { queue_entry_id: Number(entryId) },
          crypto.randomUUID(),
        )
      }
      // Patient screen "New visit": continue an open visit, otherwise create
      // an adhoc one with the patient's last visit type (or the first type).
      const visits = await get<TimelineCard[]>(`/api/patients/${profileId}/timeline`)
      const openVisit = visits.find((v) => v.status === 'open')
      if (openVisit) return get<Visit>(`/api/visits/${openVisit.id}`)
      let visitTypeId = visits[0]?.visit_type_id
      if (!visitTypeId) {
        const types = await get<{ id: number }[]>('/api/visit-types')
        visitTypeId = types[0]?.id
      }
      if (!visitTypeId) throw new Error('no visit type configured')
      return post<Visit>(
        '/api/visits',
        { patient_profile_id: Number(profileId), visit_type_id: visitTypeId },
        crypto.randomUUID(),
      )
    },
    enabled: Boolean(profileId),
  })
  const readOnly = visit.data?.status === 'completed' || Boolean(viewVisitId)

  useEffect(() => {
    if (visit.data) {
      setVersion(visit.data.record_version)
      versionRef.current = visit.data.record_version
      lastSavedRef.current = JSON.stringify(buildFields({
        chief_complaint: visit.data.chief_complaint ?? '',
        history: visit.data.history ?? '',
        clinical_exam: visit.data.clinical_exam ?? '',
        findings: visit.data.findings ?? '',
        labs: visit.data.labs ?? '',
        imaging: visit.data.imaging ?? '',
        plan: visit.data.plan ?? '',
        notes_next_visit: visit.data.notes_next_visit ?? '',
        follow_up_weeks: visit.data.follow_up_weeks ?? '',
      }))
      setDraft({
        chief_complaint: visit.data.chief_complaint ?? '',
        history: visit.data.history ?? '',
        clinical_exam: visit.data.clinical_exam ?? '',
        findings: visit.data.findings ?? '',
        labs: visit.data.labs ?? '',
        imaging: visit.data.imaging ?? '',
        plan: visit.data.plan ?? '',
        notes_next_visit: visit.data.notes_next_visit ?? '',
        follow_up_weeks: visit.data.follow_up_weeks ?? '',
      })
      if (visit.data.prescription) {
        setRxDraft({
          notes: visit.data.prescription.notes,
          items: visit.data.prescription.items,
        })
      }
      const dds = visit.data.diagnoses.filter((d) => d.kind === 'differential').map((d) => d.label)
      const finals = visit.data.diagnoses.filter((d) => d.kind === 'final').map((d) => d.label)
      setDdLabels(dds.join('\n'))
      setFinalLabels(finals.join('\n'))
    }
  }, [visit.data])

  // autosave debounce: only fires when the draft differs from the last
  // saved snapshot, so it never loops and never races into 409s.
  useEffect(() => {
    if (!visit.data || readOnly || saveState === 'saving') return
    const timer = setTimeout(async () => {
      const fields = buildFields(draft)
      const snapshot = JSON.stringify(fields)
      if (snapshot === lastSavedRef.current) return
      setSaveState('saving')
      try {
        const updated = await patch<Visit>(
          `/api/visits/${visit.data.id}`,
          { ...fields, record_version: versionRef.current },
          crypto.randomUUID(),
        )
        versionRef.current = updated.record_version
        setVersion(updated.record_version)
        lastSavedRef.current = snapshot
        setSaveState('saved')
      } catch {
        setSaveState('conflict')
      }
    }, 800)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, visit.data?.id, readOnly])

  async function complete() {
    if (!visit.data) return
    try {
      await post(`/api/visits/${visit.data.id}/complete`, {}, crypto.randomUUID())
      toast.success('Visit completed')
      queryClient.invalidateQueries({ queryKey: ['visit'] })
      navigate(`/patients/${profileId}`)
    } catch {
      /* toast already shown */
    }
  }

  async function saveDiagnoses() {
    if (!visit.data) return
    const items = [
      ...ddLabels
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .map((label) => ({ kind: 'differential', label })),
      ...finalLabels
        .split('\n')
        .map((l) => l.trim())
        .filter(Boolean)
        .map((label) => ({ kind: 'final', label })),
    ]
    const result = await put<{ record_version: number }>(
      `/api/visits/${visit.data.id}/diagnoses`,
      { items, record_version: versionRef.current },
      crypto.randomUUID(),
    )
    if (result.record_version) setVersion(result.record_version)
    queryClient.invalidateQueries({ queryKey: ['visit'] })
  }

  async function saveRx() {
    if (!visit.data) return
    const result = await put<{ record_version: number }>(
      `/api/visits/${visit.data.id}/prescription`,
      { notes: rxDraft.notes, items: rxDraft.items, record_version: versionRef.current },
      crypto.randomUUID(),
    )
    if (result.record_version) setVersion(result.record_version)
    queryClient.invalidateQueries({ queryKey: ['visit'] })
  }

  if (visit.isLoading) return <p className="text-sm text-ink-400">Loading visit…</p>
  if (visit.isError || !visit.data)
    return <p className="text-sm text-danger">Could not load the visit</p>

  const v = visit.data

  return (
    <div className="flex h-full flex-col gap-4 lg:flex-row">
      {/* mobile tabs (PWA5) */}
      <div className="flex gap-1 rounded-md border border-border bg-surface p-1 lg:hidden">
        {(['history', 'exam', 'rx'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setMobileTab(tab)}
            className={`flex-1 rounded px-2 py-1.5 text-xs font-medium capitalize ${
              mobileTab === tab ? 'bg-brand-600 text-white' : 'text-ink-600'
            }`}
          >
            {tab === 'history' ? 'History' : tab === 'exam' ? 'Exam' : 'Rx & Files'}
          </button>
        ))}
      </div>

      {/* history timeline */}
      <Card className={`w-72 shrink-0 overflow-y-auto p-3 ${mobileTab === 'history' ? 'block' : 'hidden'} lg:block`}>
        <h2 className="mb-2 text-sm font-semibold text-ink-600">History</h2>
        <Timeline profileId={Number(profileId)} />
      </Card>

      {/* exam form — wrapper always visible; content toggles by mobile tab */}
      <div className="min-w-0 flex-1 space-y-4 overflow-y-auto">
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface p-3">
          <div>
            <p className="font-bold text-ink-900">{v.patient?.full_name ?? 'Patient'}</p>
            <p className="font-mono text-xs text-ink-400">
              {v.patient?.code} · {v.patient?.phone}
            </p>
          </div>
          <Button size="sm" variant="secondary" onClick={() => setTypeOpen(true)}>
            Type: {v.custom_type_name ?? visitTypes.data?.find((t) => t.id === v.visit_type_id)?.name_ar ?? '—'}
          </Button>
          <div className="flex items-center gap-2">
            <span
              className={`text-xs ${
                saveState === 'conflict'
                  ? 'font-semibold text-danger'
                  : saveState === 'saving'
                    ? 'text-ink-400'
                    : 'text-success'
              }`}
            >
              {saveState === 'conflict'
                ? 'Conflict — review'
                : saveState === 'saving'
                  ? 'Saving…'
                  : saveState === 'saved'
                    ? 'Saved'
                    : ''}
            </span>
            {!readOnly && (
              <Button onClick={complete} variant="secondary">
                Complete visit
              </Button>
            )}
            {readOnly && (
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-ink-500">
                Read-only — old visit
              </span>
            )}
          </div>
        </div>

        {readOnly ? (
          <VisitSummary visit={v} />
        ) : (
        <div className={`space-y-4 ${mobileTab === 'rx' ? 'hidden' : 'block'} lg:block`}>
        {v.status === 'completed' && (
          <p className="rounded-md bg-green-50 p-2 text-sm text-green-800">
            This visit is completed. Corrections are allowed within the 24h window.
          </p>
        )}

        <Card className="p-3">
          <Field label="Vitals">
            <div className="grid grid-cols-4 gap-2">
              {(['bp_sys', 'bp_dia', 'hr', 'temp', 'spo2'] as const).map((key) => (
                <VitalInput
                  key={key}
                  name={key}
                  value={(draft.vitals as Record<string, number | null> | undefined)?.[key] ?? null}
                  flag={vitalsFlag(draft, key)}
                  onChange={(v) => setDraft({ ...draft, vitals: { ...(draft.vitals as Record<string, number | null> | undefined), [key]: v } })}
                />
              ))}
            </div>
          </Field>
        </Card>

        {activeSections.map((section) => (
          <Card key={section.key} className="p-3">
            <Field label={label(section)}>
              <textarea
                rows={section.key === 'chief_complaint' ? 2 : 3}
                className={inputClass}
                value={(draft[section.key] as string) ?? ''}
                onChange={(e) => setDraft({ ...draft, [section.key]: e.target.value })}
              />
            </Field>
          </Card>
        ))}
        {!readOnly && (
          <DynamicFields
            entity="visit"
            value={(draft.custom_data as Record<string, unknown>) ?? {}}
            onChange={(next) => setDraft({ ...draft, custom_data: next })}
          />
        )}

        <Card className="p-3">
          <Field label="Follow-up in weeks">
            <input
              type="number"
              min={1}
              max={208}
              className={inputClass + ' w-32'}
              value={(draft.follow_up_weeks as string) ?? ''}
              onChange={(e) => setDraft({ ...draft, follow_up_weeks: e.target.value })}
            />
          </Field>
        </Card>

        <Card className="p-3">
          <h3 className="mb-2 text-sm font-semibold text-ink-600">Diagnoses</h3>
          {!readOnly && (
            <Icd10Picker
              onPick={(label, kind) => {
                if (kind === 'dd') {
                  setDdLabels((prev) => (prev ? prev + '\n' : '') + label)
                } else {
                  setFinalLabels((prev) => (prev ? prev + '\n' : '') + label)
                }
              }}
            />
          )}
          <div className="mt-2 grid grid-cols-2 gap-3">
            <Field label="Differential (one per line)">
              <textarea className={inputClass} rows={3} disabled={readOnly} value={ddLabels} onChange={(e) => setDdLabels(e.target.value)} />
            </Field>
            <Field label="Final (one per line)">
              <textarea className={inputClass} rows={3} disabled={readOnly} value={finalLabels} onChange={(e) => setFinalLabels(e.target.value)} />
            </Field>
          </div>
          {!readOnly && (
            <Button className="mt-2" variant="secondary" onClick={saveDiagnoses}>
              Save diagnoses
            </Button>
          )}
        </Card>
        </div>
        )}

        <div className={`space-y-4 ${mobileTab === 'rx' ? 'block' : 'hidden'} lg:block`}>
        <Card className="p-3">
          <h3 className="mb-2 text-sm font-semibold text-ink-600">Prescription</h3>
          {rxDraft.items.map((item, i) => (
            <div key={i} className="mb-2 grid grid-cols-5 gap-2">
              <input
                className={inputClass + ' col-span-2'}
                placeholder="Drug"
                disabled={readOnly}
                value={item.free_text ?? ''}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, free_text: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              />
              <input
                className={inputClass}
                placeholder="Dose"
                disabled={readOnly}
                value={item.dose}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, dose: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              />
              <input
                className={inputClass}
                placeholder="Frequency"
                disabled={readOnly}
                value={item.frequency}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, frequency: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              />
              <input
                className={inputClass}
                placeholder="Duration"
                disabled={readOnly}
                value={item.duration}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, duration: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              />
              <select
                className={inputClass}
                disabled={readOnly}
                value={item.route ?? ''}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, route: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              >
                <option value="">Route…</option>
                {ROUTES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
          ))}
          <Button
            variant="secondary"
            onClick={() =>
              setRxDraft({
                ...rxDraft,
                items: [...rxDraft.items, { medication_id: null, free_text: '', dose: '', frequency: '', duration: '', route: '', instructions: null, quantity: null }],
              })
            }
          >
            + Item
          </Button>
          <textarea
            className={inputClass + ' mt-2'}
            rows={2}
            disabled={readOnly}
            placeholder="Prescription notes (optional)"
            value={rxDraft.notes ?? ''}
            onChange={(e) => setRxDraft({ ...rxDraft, notes: e.target.value })}
          />
          <div className="mt-2 flex gap-2">
            {!readOnly && (
              <Button className="ms-0" onClick={saveRx}>
                Save prescription
              </Button>
            )}
            <Button variant="secondary" onClick={() => void printRx(visit.data.id)}>
              Print
            </Button>
          </div>
        </Card>

        <Attachments visitId={v.id} />
        </div>
      </div>
      {typeOpen && (
        <VisitTypePicker
          types={visitTypes.data ?? []}
          currentTypeId={v.visit_type_id}
          currentCustom={v.custom_type_name ?? ''}
          customName={customProcedure}
          setCustomName={setCustomProcedure}
          error={typeError}
          onSelect={(typeId, customName) => void changeType(typeId, customName)}
          onClose={() => setTypeOpen(false)}
        />
      )}
    </div>
  )
}

function VisitTypePicker({
  types,
  currentTypeId,
  currentCustom,
  customName,
  setCustomName,
  error,
  onSelect,
  onClose,
}: {
  types: VisitTypeRow[]
  currentTypeId: number | null
  currentCustom: string
  customName: string
  setCustomName: (v: string) => void
  error: string
  onSelect: (typeId: number | null, customName: string) => void
  onClose: () => void
}) {
  const groups: { id: string; label: string; ar: string; rows: VisitTypeRow[] }[] = [
    { id: 'new_visit', label: 'New visit', ar: 'كشف جديد', rows: types.filter((t) => t.category === 'new_visit') },
    { id: 'follow_up', label: 'Follow-up', ar: 'متابعة', rows: types.filter((t) => t.category === 'follow_up') },
    { id: 'procedure', label: 'Procedure', ar: 'إجراء', rows: types.filter((t) => t.category === 'procedure') },
  ]
  const active = (typeId: number) => typeId === currentTypeId && !currentCustom

  return (
    <Modal open onClose={onClose} title="Visit type">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <div className="space-y-4">
        {groups.map((group) => (
          <div key={group.id}>
            <p className="mb-2 text-xs font-semibold text-ink-600">
              {group.label} ({group.ar})
            </p>
            <div className="space-y-1">
              {group.rows.map((t) => (
                <button
                  key={t.id}
                  onClick={() => onSelect(t.id, '')}
                  className={`w-full rounded-md border px-3 py-2 text-start text-sm ${
                    active(t.id)
                      ? 'border-brand-600 bg-brand-50 text-brand-700'
                      : 'border-border hover:border-brand-600'
                  }`}
                >
                  {t.name} ({t.name_ar}) · {t.duration_minutes} min · {t.default_price}
                </button>
              ))}
              {group.rows.length === 0 && (
                <p className="text-xs text-ink-400">No {group.label.toLowerCase()} type configured</p>
              )}
            </div>
          </div>
        ))}

        <div>
          <p className="mb-2 text-xs font-semibold text-ink-600">Custom procedure</p>
          <div className="flex gap-2">
            <input
              className={inputClass}
              placeholder="Type a procedure name…"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
            />
            <Button
              onClick={() => customName.trim() && onSelect(currentTypeId, customName.trim())}
              disabled={!customName.trim()}
            >
              Use custom
            </Button>
          </div>
          {currentCustom && (
            <p className="mt-2 text-xs text-brand-700">Current: {currentCustom}</p>
          )}
        </div>
      </div>
    </Modal>
  )
}

function Timeline({ profileId }: { profileId: number }) {
  const timeline = useQuery({
    queryKey: ['timeline', profileId],
    queryFn: () => get<TimelineCard[]>(`/api/patients/${profileId}/timeline`),
  })
  const cards = timeline.data ?? []
  return (
    <div className="space-y-2">
      {cards.map((card) => (
        <Link
          key={card.id}
          to={`/patients/${profileId}/exam?visit_id=${card.id}`}
          className="block rounded-md border border-border p-2 text-xs hover:bg-slate-50"
        >
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink-900">{card.date}</p>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] capitalize">
              {card.status}
            </span>
          </div>
          <p className="text-ink-400">{card.doctor_name ?? '—'}</p>
          {typeof card.chief_complaint === 'string' && (
            <p className="mt-1 text-ink-600">{card.chief_complaint}</p>
          )}
          {Array.isArray(card.diagnoses) && (
            <p className="mt-1 text-brand-700">{(card.diagnoses as string[]).join(' · ')}</p>
          )}
          {typeof card.plan === 'string' && (
            <p className="mt-1 text-ink-600">Plan: {card.plan}</p>
          )}
        </Link>
      ))}
    </div>
  )
}

function Attachments({ visitId }: { visitId: number }) {
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState('photo')
  const [thumbs, setThumbs] = useState<Record<number, string>>({})
  const visit = useQuery({ queryKey: ['visit-attachments', visitId], queryFn: () => get<Visit>(`/api/visits/${visitId}`) })
  const attachments = visit.data?.attachments ?? []

  useEffect(() => {
    let active = true
    for (const a of attachments) {
      if (!a.mime?.startsWith('image/') || thumbs[a.id]) continue
      fetchBlob(`/api/files/${a.id}?thumb=true`)
        .then((blob) => {
          if (active) setThumbs((prev) => ({ ...prev, [a.id]: URL.createObjectURL(blob) }))
        })
        .catch(() => {
          /* quarantined or still scanning — image will 409 until scanned */
        })
    }
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachments])

  async function upload(override?: File) {
    const target = override ?? file
    if (!target) return
    try {
      const form = new FormData()
      form.append('file', target)
      form.append('kind', kind)
      await uploadFile(`/api/visits/${visitId}/attachments`, form)
      toast.success('File uploaded')
      visit.refetch()
      setFile(null)
    } catch {
      /* toast already shown by uploadFile */
    }
  }

  return (
    <Card className="p-3">
      <h3 className="mb-2 text-sm font-semibold text-ink-600">Attachments</h3>
      <div className="flex flex-wrap items-center gap-2">
        <CameraCapture onCaptured={(f) => upload(f)} label="Camera" />
        <input type="file" accept="image/*,application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <select className={inputClass + ' w-32'} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="photo">Photo</option>
          <option value="lab">Lab</option>
          <option value="imaging">Imaging</option>
          <option value="report">Report</option>
        </select>
        <Button onClick={() => upload()} disabled={!file}>
          Upload
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {attachments.map((a) => (
          <a
            key={a.id}
            href={`/api/files/${a.id}`}
            target="_blank"
            rel="noreferrer"
            className="w-24 overflow-hidden rounded-md border border-border"
            title={`${a.title ?? a.mime} · ${a.scan_status}`}
          >
            {a.mime?.startsWith('image/') ? (
              thumbs[a.id] ? (
                <img src={thumbs[a.id]} alt={a.title ?? a.kind} className="h-20 w-full object-cover" />
              ) : (
                <div className="flex h-20 items-center justify-center text-xs text-ink-400">
                  loading…
                </div>
              )
            ) : (
              <div className="flex h-20 items-center justify-center text-xs text-ink-400">
                {a.mime === 'application/pdf' ? 'PDF' : 'FILE'}
              </div>
            )}
            <p className="truncate px-1 py-0.5 text-[10px] capitalize text-ink-600">{a.kind}</p>
          </a>
        ))}
        {attachments.length === 0 && <p className="text-xs text-ink-400">No attachments yet</p>}
      </div>
    </Card>
  )
}

export function Icd10Picker({
  onPick,
}: {
  onPick: (label: string, kind: 'dd' | 'final') => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['icd10', q],
    queryFn: () => get<{ items: { code: string; label_en: string; label_ar: string | null }[] }>(`/api/icd10?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
  })
  return (
    <div className="relative">
      <input
        className={inputClass}
        placeholder="ICD-10 search…"
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && data && data.items.length > 0 && (
        <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-surface shadow-lg">
          {data.items.map((item) => {
            const label = `${item.label_en} (${item.code})`
            return (
              <div
                key={item.code}
                className="flex items-center gap-2 border-b border-border px-3 py-2"
              >
                <span className="flex-1 text-sm">
                  <span className="font-mono text-brand-700">{item.code}</span>{' '}
                  {item.label_en}{' '}
                  {item.label_ar ? <span dir="rtl" className="text-ink-400">{item.label_ar}</span> : null}
                </span>
                <button
                  type="button"
                  className="rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onPick(label, 'dd')
                    setQ('')
                    setOpen(false)
                  }}
                >
                  DD
                </button>
                <button
                  type="button"
                  className="rounded-md bg-brand-600 px-2 py-1 text-xs font-medium text-white hover:bg-brand-700"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onPick(label, 'final')
                    setQ('')
                    setOpen(false)
                  }}
                >
                  Final
                </button>
              </div>
            )
          })}
        </div>
      )}
      {open && q.trim().length >= 2 && data && data.items.length === 0 && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-border bg-surface p-2 text-xs text-ink-400 shadow-lg">
          No ICD-10 matches
        </div>
      )}
    </div>
  )
}


const VITAL_LABELS: Record<string, string> = {
  bp_sys: 'BP sys',
  bp_dia: 'BP dia',
  hr: 'HR',
  temp: 'Temp',
  spo2: 'SpO2',
}

function vitalsFlag(
  draft: Record<string, unknown>,
  key: string
): 'low' | 'high' | 'normal' | null {
  const vitals = draft.vitals as Record<string, unknown> | undefined
  const value = vitals?.[key]
  if (value === null || value === undefined) return null
  const flag = vitals?.[`${key}_flag`]
  return flag === 'low' || flag === 'high' ? flag : 'normal'
}

function VitalInput({
  name,
  value,
  flag,
  onChange,
}: {
  name: string
  value: number | null
  flag: 'low' | 'high' | 'normal' | null
  onChange: (v: number | null) => void
}) {
  const cls =
    flag === 'high'
      ? ' border-red-400 bg-red-50'
      : flag === 'low'
        ? ' border-amber-400 bg-amber-50'
        : ''
  return (
    <label className="block text-xs text-ink-600">
      {VITAL_LABELS[name] ?? name}
      <input
        type="number"
        step="0.1"
        className={inputClass + ' mt-1' + cls}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
      />
      {flag === 'high' && <span className="text-red-600">high</span>}
      {flag === 'low' && <span className="text-amber-600">low</span>}
    </label>
  )
}


const ROUTES = ['oral', 'topical', 'sublingual', 'inhalation', 'IV', 'IM', 'SC',
  'eye', 'ear', 'nasal', 'rectal', 'vaginal']

function label(section: FormSection): string {
  return `${section.label_ar || section.label_en}${section.required ? ' *' : ''}`
}

async function printRx(visitId: number) {
  try {
    const { token } = await post<{ token: string }>(
      `/api/print/token?key=rx&entity_id=${visitId}`,
      {},
    )
    window.open(`/api/print/rx/${visitId}?token=${encodeURIComponent(token)}&locale=ar`, '_blank')
  } catch {
    /* toast already shown by the api client */
  }
}

const SUMMARY_SECTIONS: [keyof Visit, string][] = [
  ['chief_complaint', 'Chief complaint'],
  ['history', 'History'],
  ['clinical_exam', 'Clinical exam'],
  ['findings', 'Findings'],
  ['labs', 'Labs'],
  ['imaging', 'Imaging'],
  ['plan', 'Plan'],
  ['notes_next_visit', 'Notes for next visit'],
]



function VisitSummary({ visit }: { visit: Visit }) {
  const { data: formData } = useQuery({
    queryKey: ['visit-form'],
    queryFn: () => get<{ sections: FormSection[] }>('/api/visit-form/sections'),
  })
  const sectionLabel = (key: string, fallback: string) => {
    const found = (formData?.sections ?? []).find((section) => section.key === key)
    return found?.label_ar || found?.label_en || fallback
  }
  const vitals = (visit.vitals ?? {}) as Record<string, unknown>
  const differential = visit.diagnoses.filter((d) => d.kind === 'differential')
  const final = visit.diagnoses.filter((d) => d.kind === 'final')
  const sections = SUMMARY_SECTIONS.filter(
    ([key]) => typeof visit[key] === 'string' && (visit[key] as string).trim() !== ''
  )
  const vitalKeys = Object.keys(vitals).filter((k) => !k.endsWith('_flag'))

  return (
    <div className="space-y-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <p className="text-lg font-bold text-ink-900">{visit.patient?.full_name ?? 'Patient'}</p>
            <p className="font-mono text-xs text-ink-400">{visit.patient?.code ?? ''}</p>
          </div>
          <div className="flex-1" />
          <StatusBadge status={visit.status} />
          <Button size="sm" variant="secondary" onClick={() => void printRx(visit.id)}>
            Print Rx
          </Button>
        </div>
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-ink-500">
          <span>Started: {visit.started_at ? new Date(visit.started_at).toLocaleString() : '—'}</span>
          {visit.ended_at && <span>Ended: {new Date(visit.ended_at).toLocaleString()}</span>}
          {visit.follow_up_due && <span>Follow-up due: {visit.follow_up_due}</span>}
        </div>
      </Card>

      {vitalKeys.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Vitals</h2>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
            {vitalKeys.map((k) => {
              const flag = vitals[`${k}_flag`]
              const cls =
                flag === 'high'
                  ? 'text-red-600'
                  : flag === 'low'
                    ? 'text-amber-600'
                    : 'text-ink-900'
              return (
                <div key={k} className="rounded-lg bg-slate-50 p-2 text-center">
                  <p className="text-xs text-ink-500">{k}</p>
                  <p className={`font-mono text-sm font-semibold ${cls}`}>
                    {String(vitals[k] ?? '—')}
                    {flag === 'high' && ' ↑'}
                    {flag === 'low' && ' ↓'}
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {sections.map(([key, fallback]) => (
        <Card key={key} className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">{sectionLabel(key, fallback)}</h2>
          <p className="mt-2 whitespace-pre-wrap text-sm text-ink-800">{String(visit[key])}</p>
        </Card>
      ))}

      {visit.custom_data && Object.keys(visit.custom_data).length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Extra fields</h2>
          <dl className="mt-2 grid grid-cols-2 gap-2 text-sm">
            {Object.entries(visit.custom_data as Record<string, unknown>).map(([k, v]) => (
              <div key={k} className="rounded-lg bg-slate-50 p-2">
                <dt className="text-xs text-ink-500">{sectionLabel(k, k)}</dt>
                <dd className="text-ink-800">{String(v ?? '—')}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      {(differential.length > 0 || final.length > 0) && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Diagnoses</h2>
          {differential.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-amber-700">Differential</p>
              <ul className="list-inside list-disc text-sm text-ink-800">
                {differential.map((d, i) => (
                  <li key={i}>
                    {d.label}
                    {d.icd10_code ? <span className="font-mono text-xs text-ink-400"> ({d.icd10_code})</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {final.length > 0 && (
            <div className="mt-2">
              <p className="text-xs text-brand-700">Final</p>
              <ul className="list-inside list-disc text-sm text-ink-800">
                {final.map((d, i) => (
                  <li key={i}>
                    {d.label}
                    {d.icd10_code ? <span className="font-mono text-xs text-ink-400"> ({d.icd10_code})</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {visit.prescription && visit.prescription.items.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Prescription</h2>
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-ink-500">
                <th className="py-1">Drug</th>
                <th>Dose</th>
                <th>Frequency</th>
                <th>Duration</th>
                <th>Route</th>
                <th>Instructions</th>
              </tr>
            </thead>
            <tbody>
              {visit.prescription.items.map((item) => (
                <tr key={item.id} className="border-b border-border">
                  <td className="py-1 font-medium">{item.free_text ?? 'med'}</td>
                  <td>{item.dose}</td>
                  <td>{item.frequency}</td>
                  <td>{item.duration}</td>
                  <td>{item.route ?? '—'}</td>
                  <td>{item.instructions ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {visit.prescription.notes && (
            <p className="mt-2 text-sm text-ink-600">{visit.prescription.notes}</p>
          )}
        </Card>
      )}

      {visit.attachments.length > 0 && (
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Attachments</h2>
          <AttachmentsGrid attachments={visit.attachments} />
        </Card>
      )}

      {sections.length === 0 &&
        vitalKeys.length === 0 &&
        differential.length === 0 &&
        final.length === 0 &&
        (!visit.prescription || visit.prescription.items.length === 0) &&
        visit.attachments.length === 0 && (
          <Card className="p-4">
            <p className="text-sm text-ink-400">This visit has no recorded data.</p>
          </Card>
        )}
    </div>
  )
}

function AttachmentsGrid({
  attachments,
}: {
  attachments: { id: number; kind: string; title: string | null; mime: string }[]
}) {
  const [thumbs, setThumbs] = useState<Record<number, string>>({})
  useEffect(() => {
    let active = true
    for (const a of attachments) {
      if (!a.mime?.startsWith('image/') || thumbs[a.id]) continue
      fetchBlob(`/api/files/${a.id}?thumb=true`)
        .then((blob) => {
          if (active) setThumbs((prev) => ({ ...prev, [a.id]: URL.createObjectURL(blob) }))
        })
        .catch(() => {
          /* not scanned yet */
        })
    }
    return () => {
      active = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachments])
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {attachments.map((a) => (
        <a
          key={a.id}
          href={`/api/files/${a.id}`}
          target="_blank"
          rel="noreferrer"
          className="w-24 overflow-hidden rounded-md border border-border"
        >
          {a.mime?.startsWith('image/') && thumbs[a.id] ? (
            <img src={thumbs[a.id]} alt={a.title ?? a.kind} className="h-20 w-full object-cover" />
          ) : (
            <div className="flex h-20 items-center justify-center text-xs text-ink-400">
              {a.mime === 'application/pdf' ? 'PDF' : 'FILE'}
            </div>
          )}
          <p className="truncate px-1 py-0.5 text-[10px] capitalize text-ink-600">{a.kind}</p>
        </a>
      ))}
    </div>
  )
}
