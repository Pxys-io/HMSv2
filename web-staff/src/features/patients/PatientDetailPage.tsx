import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { get, patch } from '../../api/client'
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
    </div>
  )
}


