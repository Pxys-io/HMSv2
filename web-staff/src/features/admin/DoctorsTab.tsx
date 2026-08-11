import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type DoctorRow = {
  id: number
  staff_user_id: number
  full_name: string | null
  email: string | null
  is_active: boolean | null
  specialty: string
  title: string | null
  bio: string | null
  booking_mode: string
  default_slot_minutes: number
  buffer_minutes: number
  day_capacity: number | null
  slot_capacity: number
  billing_mode: string
  hourly_rate: number | null
  is_bookable_online: boolean
  warnings?: string[]
}

type Shift = {
  id: number
  weekday: number
  start_time: string
  end_time: string
  effective_from: string | null
  effective_to: string | null
  is_active: boolean
}

type Block = { id: number; date_from: string; date_to: string; reason: string | null }

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function DoctorsTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<DoctorRow | null>(null)
  const [schedulesFor, setSchedulesFor] = useState<DoctorRow | null>(null)
  const queryClient = useQueryClient()

  const doctors = useQuery({
    queryKey: ['admin-doctors'],
    queryFn: () => get<{ items: DoctorRow[] }>('/api/doctors?page_size=100'),
    select: (d) => d.items,
  })
  const rows = doctors.data ?? []

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Doctors</h1>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Doctor</Button>
      </div>
      <Card className="mt-3">
        <div className="divide-y divide-border">
          {rows.map((d) => (
            <div key={d.id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink-900">
                  {d.full_name ?? '—'}
                  {!d.is_active && <span className="ms-2 text-xs text-danger">(inactive)</span>}
                </p>
                <p className="text-xs text-ink-400">
                  {d.title ? `${d.title} · ` : ''}
                  {d.specialty} · {d.email}
                </p>
              </div>
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs capitalize text-brand-700">
                {d.booking_mode.replace('_', ' ')}
              </span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                {d.billing_mode.replace('_', ' ')}
              </span>
              <Button size="sm" variant="ghost" onClick={() => setSchedulesFor(d)}>
                Schedules
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setEditTarget(d)}>
                Edit
              </Button>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No doctors yet — create one" />}
        </div>
      </Card>

      {createOpen && (
        <DoctorModal onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />
      )}
      {editTarget && (
        <DoctorModal
          target={editTarget}
          onClose={() => setEditTarget(null)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
      {schedulesFor && (
        <SchedulesPanel doctor={schedulesFor} onClose={() => setSchedulesFor(null)} />
      )}
    </div>
  )
}

function DoctorModal({
  target,
  onClose,
  onDone,
}: {
  target?: DoctorRow
  onClose: () => void
  onDone: () => void
}) {
  const [email, setEmail] = useState(target?.email ?? '')
  const [password, setPassword] = useState('')
  const [name, setName] = useState(target?.full_name ?? '')
  const [specialty, setSpecialty] = useState(target?.specialty ?? '')
  const [title, setTitle] = useState(target?.title ?? '')
  const [bookingMode, setBookingMode] = useState(target?.booking_mode ?? 'slots')
  const [slotMinutes, setSlotMinutes] = useState(String(target?.default_slot_minutes ?? 20))
  const [bufferMinutes, setBufferMinutes] = useState(String(target?.buffer_minutes ?? 0))
  const [dayCapacity, setDayCapacity] = useState(target?.day_capacity ? String(target.day_capacity) : '')
  const [billingMode, setBillingMode] = useState(target?.billing_mode ?? 'per_visit')
  const [hourlyRate, setHourlyRate] = useState(target?.hourly_rate ? String(target.hourly_rate) : '')
  const [bookable, setBookable] = useState(target?.is_bookable_online ?? true)
  const [error, setError] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])

  async function submit() {
    const payload = {
      full_name: name,
      email,
      password: password || undefined,
      specialty,
      title: title || undefined,
      booking_mode: bookingMode,
      default_slot_minutes: Number(slotMinutes),
      buffer_minutes: Number(bufferMinutes),
      day_capacity: dayCapacity ? Number(dayCapacity) : undefined,
      billing_mode: billingMode,
      hourly_rate: billingMode === 'per_hour' && hourlyRate ? Number(hourlyRate) : undefined,
      is_bookable_online: bookable,
    }
    try {
      if (target) {
        const result = await patch<DoctorRow>(`/api/doctors/${target.id}`, payload)
        setWarnings(result.warnings ?? [])
        if (result.warnings?.length) return
      } else {
        await post('/api/doctors', payload)
      }
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title={target ? 'Edit doctor' : 'New doctor'}>
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      {warnings.map((w) => (
        <p key={w} className="mb-3 rounded-md bg-amber-50 p-2 text-sm text-amber-800">
          ⚠ {w}
        </p>
      ))}
      <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input
        className={inputClass + ' mt-2'}
        type="password"
        placeholder={target ? 'Reset password (optional)' : 'Password (min 8)'}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <input className={inputClass} placeholder="Specialty" value={specialty} onChange={(e) => setSpecialty(e.target.value)} />
        <input className={inputClass} placeholder="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <select className={inputClass} value={bookingMode} onChange={(e) => setBookingMode(e.target.value)}>
          <option value="slots">Time slots</option>
          <option value="day_queue">Day + arrival queue</option>
        </select>
        <input
          className={inputClass}
          type="number"
          placeholder="Slot minutes"
          value={slotMinutes}
          onChange={(e) => setSlotMinutes(e.target.value)}
        />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <input
          className={inputClass}
          type="number"
          placeholder="Buffer minutes"
          value={bufferMinutes}
          onChange={(e) => setBufferMinutes(e.target.value)}
        />
        <input
          className={inputClass}
          type="number"
          placeholder="Day capacity (optional)"
          value={dayCapacity}
          onChange={(e) => setDayCapacity(e.target.value)}
        />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <select className={inputClass} value={billingMode} onChange={(e) => setBillingMode(e.target.value)}>
          <option value="per_visit">Per visit</option>
          <option value="per_hour">Per hour</option>
        </select>
        {billingMode === 'per_hour' && (
          <input
            className={inputClass}
            type="number"
            step="0.01"
            placeholder="Hourly rate (EGP)"
            value={hourlyRate}
            onChange={(e) => setHourlyRate(e.target.value)}
          />
        )}
      </div>
      <label className="mt-2 flex items-center gap-2 text-sm text-ink-600">
        <input type="checkbox" checked={bookable} onChange={(e) => setBookable(e.target.checked)} />
        Bookable online
      </label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !email || specialty.length < 2}>
          {target ? 'Save' : 'Create doctor'}
        </Button>
      </div>
    </Modal>
  )
}

function SchedulesPanel({ doctor, onClose }: { doctor: DoctorRow; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [shiftOpen, setShiftOpen] = useState(false)
  const [editShift, setEditShift] = useState<Shift | null>(null)
  const [blockOpen, setBlockOpen] = useState(false)

  const shifts = useQuery({
    queryKey: ['schedules', doctor.id],
    queryFn: () => get<Shift[]>(`/api/doctors/${doctor.id}/schedules`),
  })
  const blocks = useQuery({
    queryKey: ['blocks', doctor.id],
    queryFn: () => get<Block[]>(`/api/doctors/${doctor.id}/blocks`),
  })

  async function removeShift(id: number) {
    await del(`/api/schedules/${id}`)
    queryClient.invalidateQueries({ queryKey: ['schedules'] })
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-e2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-base font-bold text-ink-900">
            Schedules — {doctor.full_name}
          </h2>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600" aria-label="Close">
            ✕
          </button>
        </div>
        <div className="flex-1 space-y-6 overflow-y-auto p-4">
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-600">Weekly shifts</h3>
              <Button size="sm" onClick={() => setShiftOpen(true)}>
                + Shift
              </Button>
            </div>
            <div className="space-y-2">
              {(shifts.data ?? []).map((s) => (
                <div key={s.id} className="flex items-center gap-3 rounded-md border border-border p-2 text-sm">
                  <span className="w-12 font-semibold text-ink-900">{WEEKDAYS[s.weekday]}</span>
                  <span className="font-mono">
                    {s.start_time} – {s.end_time}
                  </span>
                  {!s.is_active && <span className="text-xs text-ink-400">(inactive)</span>}
                  <div className="flex-1" />
                  <Button size="sm" variant="ghost" onClick={() => setEditShift(s)}>
                    Edit
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void removeShift(s.id)}>
                    Delete
                  </Button>
                </div>
              ))}
              {(shifts.data ?? []).length === 0 && (
                <p className="text-sm text-ink-400">No shifts — the doctor is never bookable.</p>
              )}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-600">Blocked days</h3>
              <Button size="sm" onClick={() => setBlockOpen(true)}>
                + Block
              </Button>
            </div>
            <div className="space-y-2">
              {(blocks.data ?? []).map((b) => (
                <div key={b.id} className="flex items-center gap-3 rounded-md border border-border p-2 text-sm">
                  <span className="font-mono">
                    {b.date_from} → {b.date_to}
                  </span>
                  <span className="flex-1 text-xs text-ink-400">{b.reason ?? ''}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={async () => {
                      await del(`/api/blocks/${b.id}`)
                      queryClient.invalidateQueries({ queryKey: ['blocks'] })
                    }}
                  >
                    Delete
                  </Button>
                </div>
              ))}
              {(blocks.data ?? []).length === 0 && (
                <p className="text-sm text-ink-400">No blocked days</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {shiftOpen && (
        <ShiftModal
          doctorId={doctor.id}
          onClose={() => setShiftOpen(false)}
          onDone={() => {
            setShiftOpen(false)
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
          }}
        />
      )}
      {editShift && (
        <ShiftModal
          doctorId={doctor.id}
          shift={editShift}
          onClose={() => setEditShift(null)}
          onDone={() => {
            setEditShift(null)
            queryClient.invalidateQueries({ queryKey: ['schedules'] })
          }}
        />
      )}
      {blockOpen && (
        <BlockModal
          doctorId={doctor.id}
          onClose={() => setBlockOpen(false)}
          onDone={() => {
            setBlockOpen(false)
            queryClient.invalidateQueries({ queryKey: ['blocks'] })
          }}
        />
      )}
    </div>
  )
}

function ShiftModal({
  doctorId,
  shift,
  onClose,
  onDone,
}: {
  doctorId: number
  shift?: Shift
  onClose: () => void
  onDone: () => void
}) {
  const [weekday, setWeekday] = useState(String(shift?.weekday ?? 0))
  const [start, setStart] = useState(shift?.start_time ?? '17:00')
  const [end, setEnd] = useState(shift?.end_time ?? '21:00')
  const [isActive, setIsActive] = useState(shift?.is_active ?? true)
  const [error, setError] = useState('')

  async function submit() {
    const body = { weekday: Number(weekday), start_time: start, end_time: end, is_active: isActive }
    try {
      if (shift) {
        await patch(`/api/schedules/${shift.id}`, body)
      } else {
        await post(`/api/doctors/${doctorId}/schedules`, body)
      }
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title={shift ? 'Edit shift' : 'New shift'}>
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
      <label className="mt-2 flex items-center gap-2 text-sm text-ink-600">
        <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
        Active
      </label>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit}>Save</Button>
      </div>
    </Modal>
  )
}

function BlockModal({
  doctorId,
  onClose,
  onDone,
}: {
  doctorId: number
  onClose: () => void
  onDone: () => void
}) {
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post(`/api/doctors/${doctorId}/blocks`, { date_from: dateFrom, date_to: dateTo, reason: reason || undefined })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="Block days">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input type="date" className={inputClass} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
      <input type="date" className={inputClass + ' mt-2'} value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!dateFrom || !dateTo}>
          Save
        </Button>
      </div>
    </Modal>
  )
}
