import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, Modal, StatusBadge, inputClass } from '../../components/ui'

type Appointment = {
  id: number
  booking_ref: string
  patient_name: string | null
  patient_phone: string | null
  doctor_id: number
  visit_type_id: number
  date: string
  start_time: string | null
  end_time: string | null
  status: string
}

export default function CalendarPage() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [bookOpen, setBookOpen] = useState(false)
  const queryClient = useQueryClient()

  const appointments = useQuery({
    queryKey: ['appointments', date],
    queryFn: () => get<{ items: Appointment[] }>(`/api/appointments?date=${date}&page_size=100`),
    select: (d) => d.items,
  })

  async function cancel(id: number, reason: string) {
    await post(`/api/appointments/${id}/cancel`, { reason }, crypto.randomUUID())
    queryClient.invalidateQueries({ queryKey: ['appointments'] })
  }

  async function noShow(id: number) {
    await post(`/api/appointments/${id}/no-show`, {}, crypto.randomUUID())
    queryClient.invalidateQueries({ queryKey: ['appointments'] })
  }

  const rows = appointments.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Calendar</h1>
        <input
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className={inputClass + ' w-44'}
        />
        <div className="flex-1" />
        <Button onClick={() => setBookOpen(true)}>+ New booking</Button>
      </div>

      <Card>
        <div className="divide-y divide-border">
          {rows.map((a) => (
            <div key={a.id} className="flex items-center gap-4 p-3">
              <span className="w-16 font-mono text-sm text-ink-900">
                {a.start_time ?? 'day'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink-900">{a.patient_name}</p>
                <p className="font-mono text-xs text-ink-400">
                  {a.booking_ref} · {a.patient_phone}
                </p>
              </div>
              <StatusBadge status={a.status} />
              {a.status === 'booked' && (
                <div className="flex gap-1">
                  <Button size="sm" variant="secondary" onClick={() => cancel(a.id, 'cancelled by reception')}>
                    Cancel
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => noShow(a.id)}>
                    No-show
                  </Button>
                </div>
              )}
            </div>
          ))}
          {rows.length === 0 && (
            <p className="p-8 text-center text-sm text-ink-400">No appointments on this day</p>
          )}
        </div>
      </Card>

      {bookOpen && (
        <BookingModal
          date={date}
          onClose={() => setBookOpen(false)}
          onDone={() => {
            setBookOpen(false)
            queryClient.invalidateQueries({ queryKey: ['appointments'] })
          }}
        />
      )}
    </div>
  )
}

function BookingModal({
  date,
  onClose,
  onDone,
}: {
  date: string
  onClose: () => void
  onDone: () => void
}) {
  const [profileId, setProfileId] = useState('')
  const [doctorId, setDoctorId] = useState('')
  const [visitTypeId, setVisitTypeId] = useState('')
  const [startTime, setStartTime] = useState('17:00')
  const [error, setError] = useState('')

  const doctors = useQuery({
    queryKey: ['doctors'],
    queryFn: () => get<{ items: { id: number; full_name: string; specialty: string }[] }>('/api/doctors'),
    select: (d) => d.items,
  })
  const visitTypes = useQuery({
    queryKey: ['visit-types'],
    queryFn: () => get<{ id: number; name: string }[]>('/api/visit-types'),
  })

  async function submit() {
    try {
      await post(
        '/api/appointments',
        {
          patient_profile_id: Number(profileId),
          doctor_id: Number(doctorId),
          visit_type_id: Number(visitTypeId),
          date,
          start_time: startTime,
        },
        crypto.randomUUID(),
      )
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New booking">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input
        className={inputClass}
        placeholder="Patient profile ID"
        value={profileId}
        onChange={(e) => setProfileId(e.target.value)}
      />
      <select className={inputClass + ' mt-2'} value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
        <option value="">Doctor…</option>
        {doctors.data?.map((d) => (
          <option key={d.id} value={d.id}>
            {d.full_name}
          </option>
        ))}
      </select>
      <select className={inputClass + ' mt-2'} value={visitTypeId} onChange={(e) => setVisitTypeId(e.target.value)}>
        <option value="">Visit type…</option>
        {visitTypes.data?.map((vt) => (
          <option key={vt.id} value={vt.id}>
            {vt.name}
          </option>
        ))}
      </select>
      <input type="time" className={inputClass + ' mt-2'} value={startTime} onChange={(e) => setStartTime(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!profileId || !doctorId || !visitTypeId}>
          Book
        </Button>
      </div>
    </Modal>
  )
}
