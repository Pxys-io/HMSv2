import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { get, patch, post, put } from '../../api/client'
import { Button, Card, Field, inputClass } from '../../components/ui'
import { CameraCapture } from '../../components/pwa'

type Visit = {
  id: number
  status: string
  record_version: number
  chief_complaint: string | null
  history: string | null
  vitals: Record<string, number | null> | null
  clinical_exam: string | null
  findings: string | null
  labs: string | null
  imaging: string | null
  plan: string | null
  notes_next_visit: string | null
  follow_up_weeks: number | null
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
}

type TimelineCard = {
  id: number
  date: string
  doctor_name: string | null
  status: string
  visit_type_id?: number
  [key: string]: unknown
}

const SECTIONS = [
  ['chief_complaint', 'Chief complaint'],
  ['history', 'History'],
  ['clinical_exam', 'Clinical exam'],
  ['findings', 'Findings'],
  ['labs', 'Labs'],
  ['imaging', 'Imaging'],
  ['plan', 'Plan'],
  ['notes_next_visit', 'Notes for next visit'],
] as const

function buildFields(draft: Record<string, unknown>): Record<string, unknown> {
  const fields: Record<string, unknown> = {}
  for (const [key] of SECTIONS) {
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
  return fields
}

export default function ExamPage() {
  const { profileId } = useParams()
  const [params] = useSearchParams()
  const entryId = params.get('entry')
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

  const visit = useQuery({
    queryKey: ['visit', profileId, entryId],
    queryFn: async () => {
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
    if (!visit.data || saveState === 'saving') return
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
  }, [draft, visit.data?.id])

  async function complete() {
    if (!visit.data) return
    await post(`/api/visits/${visit.data.id}/complete`, {}, crypto.randomUUID())
    queryClient.invalidateQueries({ queryKey: ['visit'] })
    navigate(`/patients/${profileId}`)
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
            <Button onClick={complete} variant="secondary">
              Complete visit
            </Button>
          </div>
        </div>

        <div className={`space-y-4 ${mobileTab === 'rx' ? 'hidden' : 'block'} lg:block`}>
        {v.status === 'completed' && (
          <p className="rounded-md bg-green-50 p-2 text-sm text-green-800">
            This visit is completed. Corrections are allowed within the 24h window.
          </p>
        )}

        {SECTIONS.map(([key, label]) => (
          <Card key={key} className="p-3">
            <Field label={label}>
              <textarea
                rows={key === 'chief_complaint' ? 2 : 3}
                className={inputClass}
                value={(draft[key] as string) ?? ''}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              />
            </Field>
          </Card>
        ))}

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
          <div className="grid grid-cols-2 gap-3">
            <Field label="Differential (one per line)">
              <textarea className={inputClass} rows={3} value={ddLabels} onChange={(e) => setDdLabels(e.target.value)} />
            </Field>
            <Field label="Final (one per line)">
              <textarea className={inputClass} rows={3} value={finalLabels} onChange={(e) => setFinalLabels(e.target.value)} />
            </Field>
          </div>
          <Button className="mt-2" variant="secondary" onClick={saveDiagnoses}>
            Save diagnoses
          </Button>
        </Card>
        </div>

        <div className={`space-y-4 ${mobileTab === 'rx' ? 'block' : 'hidden'} lg:block`}>
        <Card className="p-3">
          <h3 className="mb-2 text-sm font-semibold text-ink-600">Prescription</h3>
          {rxDraft.items.map((item, i) => (
            <div key={i} className="mb-2 grid grid-cols-5 gap-2">
              <input
                className={inputClass + ' col-span-2'}
                placeholder="Drug"
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
                value={item.duration}
                onChange={(e) => {
                  const items = [...rxDraft.items]
                  items[i] = { ...item, duration: e.target.value }
                  setRxDraft({ ...rxDraft, items })
                }}
              />
            </div>
          ))}
          <Button
            variant="secondary"
            onClick={() =>
              setRxDraft({
                ...rxDraft,
                items: [...rxDraft.items, { medication_id: null, free_text: '', dose: '', frequency: '', duration: '' }],
              })
            }
          >
            + Item
          </Button>
          <Button className="ms-2" onClick={saveRx}>
            Save prescription
          </Button>
        </Card>

        <Attachments visitId={v.id} />
        </div>
      </div>
    </div>
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
        <div key={card.id} className="rounded-md border border-border p-2 text-xs">
          <p className="font-semibold text-ink-900">{card.date}</p>
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
        </div>
      ))}
    </div>
  )
}

function Attachments({ visitId }: { visitId: number }) {
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState('photo')
  const visit = useQuery({ queryKey: ['visit-attachments', visitId], queryFn: () => get<Visit>(`/api/visits/${visitId}`) })
  const attachments = visit.data?.attachments ?? []

  async function upload(override?: File) {
    const target = override ?? file
    if (!target) return
    const form = new FormData()
    form.append('file', target)
    form.append('kind', kind)
    await fetch(`/api/visits/${visitId}/attachments`, { method: 'POST', body: form })
    visit.refetch()
    setFile(null)
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
          <div key={a.id} className="rounded-md border border-border p-2 text-xs">
            <p className="font-medium capitalize text-ink-900">{a.kind}</p>
            <p className="text-ink-400">
              {a.title ?? a.mime} · {a.scan_status}
            </p>
          </div>
        ))}
        {attachments.length === 0 && <p className="text-xs text-ink-400">No attachments yet</p>}
      </div>
    </Card>
  )
}
