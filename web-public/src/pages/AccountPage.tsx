import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate } from 'react-router-dom'
import { get, idemKey, post } from '../api/client'
import { useAuthStore } from '../auth/store'

type Appointment = {
  id: number
  booking_ref: string
  doctor_id: number
  date: string
  start_time: string | null
  status: string
}

type Profile = { id: number; full_name: string; code: string }

export default function AccountPage() {
  const patient = useAuthStore((s) => s.patient)
  const queryClient = useQueryClient()

  const appointments = useQuery({
    queryKey: ['my-appointments'],
    queryFn: () => get<{ upcoming: Appointment[]; past: Appointment[] }>('/api/public/appointments'),
    enabled: Boolean(patient),
  })
  const profiles = useQuery({
    queryKey: ['my-profiles'],
    queryFn: () => get<Profile[]>('/api/public/profiles'),
    enabled: Boolean(patient),
  })

  if (!patient) return <Navigate to="/login" replace />

  const upcoming = appointments.data?.upcoming ?? []
  const past = appointments.data?.past ?? []

  async function cancel(id: number) {
    await post(`/api/public/appointments/${id}/cancel`, { reason: 'cancelled from account' }, idemKey())
    queryClient.invalidateQueries({ queryKey: ['my-appointments'] })
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-bold text-ink-900">My visits</h1>

      <h2 className="mt-8 font-semibold text-ink-600">Upcoming</h2>
      <div className="mt-3 space-y-3">
        {upcoming.map((a) => (
          <div key={a.id} className="flex items-center gap-4 rounded-xl border border-border bg-surface p-4">
            <div className="flex-1">
              <p className="font-medium text-ink-900">
                {new Date(a.date + 'T12:00').toLocaleDateString()}
                {a.start_time ? ` at ${a.start_time}` : ' — day booking'}
              </p>
              <p className="font-mono text-xs text-ink-400">{a.booking_ref}</p>
            </div>
            <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs capitalize text-blue-700">
              {a.status.replace('_', ' ')}
            </span>
            <button
              onClick={() => cancel(a.id)}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-red-600 hover:bg-red-50"
            >
              Cancel
            </button>
          </div>
        ))}
        {upcoming.length === 0 && <p className="text-sm text-ink-400">No upcoming visits</p>}
      </div>

      <h2 className="mt-8 font-semibold text-ink-600">Past</h2>
      <div className="mt-3 space-y-2">
        {past.slice(0, 10).map((a) => (
          <div key={a.id} className="flex items-center gap-4 rounded-lg border border-border bg-surface p-3">
            <span className="flex-1 text-sm text-ink-600">{a.date}</span>
            <span className="text-xs capitalize text-ink-400">{a.status.replace('_', ' ')}</span>
          </div>
        ))}
        {past.length === 0 && <p className="text-sm text-ink-400">No past visits</p>}
      </div>

      <h2 className="mt-8 font-semibold text-ink-600">Family</h2>
      <div className="mt-3 space-y-2">
        {profiles.data?.map((p) => (
          <div key={p.id} className="flex items-center gap-3 rounded-lg border border-border bg-surface p-3">
            <span className="flex-1 font-medium text-ink-900">{p.full_name}</span>
            <span className="font-mono text-xs text-ink-400">{p.code}</span>
          </div>
        ))}
        <AddMember onDone={() => queryClient.invalidateQueries({ queryKey: ['my-profiles'] })} />
      </div>
    </div>
  )
}

function AddMember({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')

  async function submit() {
    await post('/api/public/profiles', { full_name: name, phone }, idemKey())
    setOpen(false)
    setName('')
    setPhone('')
    onDone()
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="text-sm text-brand-700 underline">
        + Add family member
      </button>
    )
  }
  return (
    <div className="rounded-lg border border-border p-3">
      <input
        className="w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Full name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        className="mt-2 w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Phone"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
      />
      <button
        onClick={submit}
        disabled={!name || !phone}
        className="mt-2 rounded-md bg-brand-600 px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
      >
        Add
      </button>
    </div>
  )
}
