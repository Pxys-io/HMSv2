import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { get, patch, post, put } from '../../api/client'
import { Button, Card, EmptyState, StatusBadge, inputClass } from '../../components/ui'
import { DynamicFields } from '../admin/DynamicFields'

type Patient = {
  id: number
  code: string
  full_name: string
  full_name_ar: string | null
  gender: string | null
  birth_date: string | null
  age: number | null
  phone: string
  phone_alt: string | null
  address: string | null
  has_allergies: boolean
  has_chronic_conditions: boolean
  custom_data: Record<string, unknown> | null
  tags: { id: number; name: string }[] | null
  no_show_count: number
  is_archived: boolean
}

type Appointment = {
  id: number
  booking_ref: string
  doctor_id: number
  visit_type_id: number
  date: string
  start_time: string | null
  status: string
}

type Invoice = {
  id: number
  number: string
  total: number
  patient_due: number
  status: string
  issued_at: string | null
}

export default function PatientDetailPage() {
  const { profileId } = useParams()
  const id = Number(profileId)
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editCustom, setEditCustom] = useState<Record<string, unknown>>({})

  const patient = useQuery({
    queryKey: ['patient', id],
    queryFn: () => get<Patient>(`/api/patients/${id}`),
    enabled: Number.isFinite(id),
  })

  const appointments = useQuery({
    queryKey: ['patient-appointments', id],
    queryFn: () => get<{ items: Appointment[] }>(`/api/patients/${id}/appointments?page_size=50`),
    enabled: Number.isFinite(id),
  })

  const invoices = useQuery({
    queryKey: ['patient-invoices', id],
    queryFn: () => get<{ items: Invoice[] }>(`/api/invoices?patient_id=${id}&page_size=50`),
    enabled: Number.isFinite(id),
  })

  const visit = useQuery({
    queryKey: ['patient-timeline', id],
    queryFn: () =>
      get<{ id: number; status: string; attachments_count: number }[]>(`/api/patients/${id}/timeline`),
    enabled: Number.isFinite(id),
  })

  if (patient.isLoading) return <p className="text-sm text-ink-400">Loading patient…</p>
  if (patient.isError || !patient.data)
    return <p className="text-sm text-danger">Patient not found</p>

  const p = patient.data
  const timeline = visit.data ?? []
  const openVisit = timeline.find((v) => v.status === 'open')

  async function saveProfile() {
    await patch(`/api/patients/${id}/demographics`, {
      full_name: editName,
      phone: editPhone,
      custom_data: Object.keys(editCustom).length ? editCustom : undefined,
    })
    setEditing(false)
    patient.refetch()
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">{p.full_name}</h1>
        <span className="font-mono text-sm text-ink-400">{p.code}</span>
        {p.no_show_count > 0 && (
          <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700">
            {p.no_show_count} no-shows
          </span>
        )}
        <div className="flex-1" />
        {openVisit && (
          <Link to={`/patients/${id}/exam?entry=`}>
            <Button>Continue open visit</Button>
          </Link>
        )}
        <Link to={`/patients/${id}/exam`}>
          <Button variant="secondary">New visit</Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Profile</h2>
          {editing ? (
            <div className="mt-3 space-y-2">
              <input className={inputClass} value={editName} onChange={(e) => setEditName(e.target.value)} />
              <input className={inputClass} value={editPhone} onChange={(e) => setEditPhone(e.target.value)} />
              <div className="flex gap-2">
                <Button size="sm" onClick={saveProfile}>
                  Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="mt-3 space-y-1 text-sm">
              <p className="text-ink-600">
                <span className="font-medium text-ink-900">{p.full_name}</span>{' '}
                {p.age !== null && `· ${p.age} y`}
              </p>
              <p className="font-mono text-ink-400">{p.phone}</p>
              <p className="text-ink-600">Gender: {p.gender ?? '—'}</p>
              {p.address && <p className="text-ink-600">{p.address}</p>}
              {p.has_allergies && (
                <p className="rounded-md bg-red-50 p-2 text-red-700">⚠ Allergies on record</p>
              )}
              {p.has_chronic_conditions && (
                <p className="rounded-md bg-amber-50 p-2 text-amber-700">⚠ Chronic conditions on record</p>
              )}
              <DynamicFields entity="patient" value={editCustom} onChange={setEditCustom} />
              <button
                onClick={() => {
                  setEditing(true)
                  setEditName(p.full_name)
                  setEditPhone(p.phone)
                  setEditCustom(p.custom_data ?? {})
                }}
                className="mt-2 text-sm text-brand-700 underline"
              >
                Edit
              </button>
            </div>
          )}
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Appointments</h2>
          <div className="mt-3 space-y-2">
            {(appointments.data?.items ?? []).slice(0, 10).map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                <div>
                  <p className="font-medium text-ink-900">{a.date}</p>
                  <p className="font-mono text-xs text-ink-400">
                    {a.start_time ?? 'day'} · {a.booking_ref}
                  </p>
                </div>
                <StatusBadge status={a.status} />
              </div>
            ))}
            {(appointments.data?.items ?? []).length === 0 && (
              <EmptyState message="No appointments" />
            )}
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Tags</h2>
          <div className="mt-3 flex flex-wrap gap-1">
            {(p.tags ?? []).map((t) => (
              <span key={t.id} className="rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-700">
                {t.name}
              </span>
            ))}
            {(!p.tags || p.tags.length === 0) && (
              <span className="text-xs text-ink-400">No tags</span>
            )}
          </div>
          <TagEditor patientId={id} current={(p.tags ?? []).map((t) => t.id)} onChanged={() => patient.refetch()} />
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Activity</h2>
          <ActivityFeed patientId={id} />
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Invoices & files</h2>
          <div className="mt-3 space-y-2">
            {(invoices.data?.items ?? []).slice(0, 10).map((i) => (
              <div key={i.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                <span className="font-mono text-ink-900">{i.number}</span>
                <span className="font-mono text-ink-600">{i.total.toFixed(2)}</span>
                <StatusBadge status={i.status} />
              </div>
            ))}
            {(invoices.data?.items ?? []).length === 0 && (
              <p className="text-sm text-ink-400">No invoices</p>
            )}
          </div>
          <p className="mt-3 text-xs text-ink-400">
            {timeline.reduce((sum, v) => sum + (v.attachments_count ?? 0), 0)} attachment(s) across{' '}
            {timeline.length} visit(s)
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Communications</h2>
          <CommunicationsPanel patientId={id} />
        </Card>
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Growth & labs</h2>
          {p.birth_date ? (
            <GrowthChart patientId={id} birthDate={p.birth_date} />
          ) : (
            <p className="text-sm text-ink-400">
              Add a birth date to see WHO growth curves (0–5y).
            </p>
          )}
          <LabTrends patientId={id} />
        </Card>
      </div>
    </div>
  )
}



type PatientTagRow = { id: number; name: string }

function TagEditor({
  patientId,
  current,
  onChanged,
}: {
  patientId: number
  current: number[]
  onChanged: () => void
}) {
  const tags = useQuery({
    queryKey: ['tags'],
    queryFn: () => get<{ items: PatientTagRow[] }>('/api/tags'),
  })
  const [sel, setSel] = useState('')
  const [name, setName] = useState('')
  return (
    <div className="mt-3 flex gap-2">
      <select className={inputClass + ' text-xs'} value={sel} onChange={(e) => setSel(e.target.value)}>
        <option value="">Add tag…</option>
        {tags.data?.items
          .filter((t) => !current.includes(t.id))
          .map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
      </select>
      <Button
        size="sm"
        variant="secondary"
        onClick={async () => {
          if (!sel) return
          await put(`/api/patients/${patientId}/tags`, { tag_ids: [...current, Number(sel)] })
          setSel('')
          onChanged()
        }}
      >
        +
      </Button>
      <input className={inputClass + ' w-28 text-xs'} placeholder="new tag" value={name} onChange={(e) => setName(e.target.value)} />
      <Button
        size="sm"
        variant="ghost"
        onClick={async () => {
          if (!name.trim()) return
          await post('/api/tags', { name: name.trim() })
          setName('')
          tags.refetch()
        }}
      >
        create
      </Button>
    </div>
  )
}

type ActivityRow = { id: number; type: string; actor_label: string | null; data: Record<string, unknown>; created_at: string | null }

function ActivityFeed({ patientId }: { patientId: number }) {
  const feed = useQuery({
    queryKey: ['activity', patientId],
    queryFn: () => get<{ items: ActivityRow[] }>(`/api/patients/${patientId}/activity?limit=15`),
  })
  if (!feed.data || feed.data.items.length === 0) {
    return <p className="mt-3 text-sm text-ink-400">No activity yet</p>
  }
  return (
    <div className="mt-3 space-y-1 text-xs">
      {feed.data.items.map((e) => (
        <div key={e.id} className="flex justify-between gap-2 border-b border-border py-1">
          <span className="text-ink-600">
            {e.type} {e.actor_label ? `· ${e.actor_label}` : ''}
          </span>
          <span className="shrink-0 text-ink-400">
            {e.created_at ? new Date(e.created_at).toLocaleString().slice(0, 16) : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function CommunicationsPanel({ patientId }: { patientId: number }) {
  const qc = useQueryClient()
  const comms = useQuery({
    queryKey: ['communications', patientId],
    queryFn: () => get<{ items: { id: number; channel: string; summary: string; created_at: string | null }[] }>(`/api/patients/${patientId}/communications`),
  })
  const [summary, setSummary] = useState('')
  return (
    <div className="mt-3 space-y-2">
      <div className="flex gap-2">
        <input
          className={inputClass + ' text-xs'}
          placeholder="Log a call / note…"
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
        />
        <Button
          size="sm"
          onClick={async () => {
            if (!summary.trim()) return
            await post(`/api/patients/${patientId}/communications`, { channel: 'call', summary })
            setSummary('')
            qc.invalidateQueries({ queryKey: ['communications'] })
          }}
        >
          Log
        </Button>
      </div>
      {comms.data?.items.slice(0, 12).map((c) => (
        <div key={c.id} className="flex justify-between gap-2 border-b border-border py-1 text-xs">
          <span className="text-ink-600">
            <span className="rounded bg-slate-100 px-1.5 py-0.5">{c.channel}</span> {c.summary}
          </span>
          <span className="shrink-0 text-ink-400">
            {c.created_at ? new Date(c.created_at).toLocaleString().slice(0, 16) : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

function GrowthChart({ patientId }: { patientId: number; birthDate: string }) {
  const growth = useQuery({
    queryKey: ['growth', patientId],
    queryFn: () =>
      get<{
        metric: string
        unit: string
        curves: { ages: number[]; low: number[]; median: number[]; high: number[] }
        measurements: { date: string; value: number; age_months: number }[]
      }>('/api/patients/' + patientId + '/growth?metric=weight'),
  })
  if (!growth.data) return null
  const { curves } = growth.data
  const W = 300
  const H = 160
  const pad = 10
  const all = [...curves.low, ...curves.median, ...curves.high, ...growth.data.measurements.map((m) => m.value)]
  const min = Math.min(...all)
  const max = Math.max(...all)
  const span = max - min || 1
  const x = (age: number) => pad + (age / Math.max(curves.ages.at(-1) ?? 60, 1)) * (W - pad * 2)
  const y = (v: number) => H - pad - ((v - min) / span) * (H - pad * 2)
  const line = (vals: number[]) =>
    curves.ages.map((a, i) => `${x(a)},${y(vals[i])}`).join(' ')
  return (
    <div className="mt-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
        <polyline points={line(curves.low)} fill="none" stroke="#94a3b8" strokeWidth={1} />
        <polyline points={line(curves.median)} fill="none" stroke="#0d9488" strokeWidth={2} />
        <polyline points={line(curves.high)} fill="none" stroke="#94a3b8" strokeWidth={1} />
        {growth.data.measurements.map((m, i) => (
          <circle key={i} cx={x(m.age_months)} cy={y(m.value)} r={3} fill="#dc2626" />
        ))}
      </svg>
      <p className="text-xs text-ink-400">
        Weight (kg) · WHO bands: −2SD / median / +2SD ·{' '}
        {growth.data.measurements.length} measurement(s)
      </p>
    </div>
  )
}

type LabTrend = {
  name: string
  unit: string | null
  points: { date: string; value: number }[]
}

function LabTrends({ patientId }: { patientId: number }) {
  const [name, setName] = useState('')
  const trend = useQuery({
    queryKey: ['lab-trend', patientId, name],
    queryFn: () => get<LabTrend>(`/api/patients/${patientId}/lab-trends?name=${encodeURIComponent(name)}`),
    enabled: name.trim().length >= 2,
  })
  return (
    <div className="mt-4">
      <div className="flex gap-2">
        <input
          className={inputClass + ' text-xs'}
          placeholder="Lab trend, e.g. HbA1c"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      {trend.data && (
        <div className="mt-2 text-xs text-ink-600">
          {trend.data.name} {trend.data.unit ? `(${trend.data.unit})` : ''}:{' '}
          {trend.data.points.map((pt) => `${pt.value}@${pt.date}`).join(' → ') || 'no points'}
        </div>
      )}
    </div>
  )
}
