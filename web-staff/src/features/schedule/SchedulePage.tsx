import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../api/client'
import { Button, Card, Modal, inputClass } from '../../components/ui'
import { WEEKDAYS } from '../admin/DoctorsTab'

type Shift = { id: number; weekday: number; start_time: string; end_time: string; is_active: boolean }

export default function SchedulePage() {
  const queryClient = useQueryClient()
  const [shiftOpen, setShiftOpen] = useState(false)
  const [blockOpen, setBlockOpen] = useState(false)

  const me = useQuery({ queryKey: ['me'], queryFn: () => get<{ id: number }>('/api/auth/me') })
  const doctors = useQuery({
    queryKey: ['doctors'],
    queryFn: () => get<{ items: { id: number; staff_user_id: number }[] }>('/api/doctors'),
    select: (d) => d.items,
  })
  const myDoctor = doctors.data?.find((d) => d.staff_user_id === me.data?.id)

  const shifts = useQuery({
    queryKey: ['my-schedules', myDoctor?.id],
    queryFn: () => get<Shift[]>(`/api/doctors/${myDoctor!.id}/schedules`),
    enabled: Boolean(myDoctor),
  })
  const blocks = useQuery({
    queryKey: ['my-blocks', myDoctor?.id],
    queryFn: () =>
      get<{ id: number; date_from: string; date_to: string; reason: string | null }[]>(
        `/api/doctors/${myDoctor!.id}/blocks`,
      ),
    enabled: Boolean(myDoctor),
  })

  if (!myDoctor) return <p className="text-sm text-ink-400">No doctor profile linked to your account</p>

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">My schedule</h1>
        <div className="flex-1" />
        <Button variant="secondary" onClick={() => setBlockOpen(true)}>
          + Block day
        </Button>
        <Button onClick={() => setShiftOpen(true)}>+ Shift</Button>
      </div>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold text-ink-600">Weekly shifts</h2>
        <div className="space-y-2">
          {(shifts.data ?? []).map((s) => (
            <div key={s.id} className="flex items-center gap-3 rounded-md border border-border p-2 text-sm">
              <span className="w-12 font-semibold text-ink-900">{WEEKDAYS[s.weekday]}</span>
              <span className="font-mono">
                {s.start_time} – {s.end_time}
              </span>
              <div className="flex-1" />
              <button
                onClick={async () => {
                  await patch(`/api/schedules/${s.id}`, { is_active: !s.is_active })
                  queryClient.invalidateQueries({ queryKey: ['my-schedules'] })
                }}
                className={`text-xs ${s.is_active ? 'text-success' : 'text-ink-400'}`}
              >
                {s.is_active ? 'active' : 'inactive'} — toggle
              </button>
            </div>
          ))}
          {(shifts.data ?? []).length === 0 && (
            <p className="text-sm text-ink-400">No shifts — patients cannot book you.</p>
          )}
        </div>
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold text-ink-600">Blocked days</h2>
        <div className="space-y-2">
          {(blocks.data ?? []).map((b) => (
            <div key={b.id} className="flex items-center gap-3 rounded-md border border-border p-2 text-sm">
              <span className="font-mono">
                {b.date_from} → {b.date_to}
              </span>
              <span className="flex-1 text-xs text-ink-400">{b.reason ?? ''}</span>
            </div>
          ))}
          {(blocks.data ?? []).length === 0 && (
            <p className="text-sm text-ink-400">No blocked days</p>
          )}
        </div>
      </Card>

      {shiftOpen && (
        <Modal open onClose={() => setShiftOpen(false)} title="New shift">
          <ShiftForm
            doctorId={myDoctor.id}
            onDone={() => {
              setShiftOpen(false)
              queryClient.invalidateQueries({ queryKey: ['my-schedules'] })
            }}
          />
        </Modal>
      )}
      {blockOpen && (
        <Modal open onClose={() => setBlockOpen(false)} title="Block days">
          <BlockForm
            doctorId={myDoctor.id}
            onDone={() => {
              setBlockOpen(false)
              queryClient.invalidateQueries({ queryKey: ['my-blocks'] })
            }}
          />
        </Modal>
      )}
    </div>
  )
}

export function ShiftForm({ doctorId, onDone }: { doctorId: number; onDone: () => void }) {
  const [weekday, setWeekday] = useState('0')
  const [start, setStart] = useState('17:00')
  const [end, setEnd] = useState('21:00')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post(`/api/doctors/${doctorId}/schedules`, {
        weekday: Number(weekday),
        start_time: start,
        end_time: end,
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div>
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <select className={inputClass} value={weekday} onChange={(e) => setWeekday(e.target.value)}>
        {WEEKDAYS.map((d, i) => (
          <option key={d} value={i}>
            {d}
          </option>
        ))}
      </select>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <input type="time" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />
        <input type="time" className={inputClass} value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <div className="mt-4 flex justify-end">
        <Button onClick={submit}>Add shift</Button>
      </div>
    </div>
  )
}

export function BlockForm({ doctorId, onDone }: { doctorId: number; onDone: () => void }) {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post(`/api/doctors/${doctorId}/blocks`, {
        date_from: dateFrom,
        date_to: dateTo,
        reason: reason || undefined,
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div>
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input type="date" className={inputClass} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
      <input type="date" className={inputClass + ' mt-2'} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="mt-4 flex justify-end">
        <Button onClick={submit} disabled={!dateFrom || !dateTo}>
          Block
        </Button>
      </div>
    </div>
  )
}
