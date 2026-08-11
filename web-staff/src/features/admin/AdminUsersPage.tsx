import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type StaffRow = {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}

type DoctorRow = {
  id: number
  specialty: string
  title: string | null
  booking_mode: string
  billing_mode: string
  default_slot_minutes: number
  day_capacity: number | null
}

export default function AdminUsersPage() {
  const [createUserOpen, setCreateUserOpen] = useState(false)
  const [createDoctorOpen, setCreateDoctorOpen] = useState(false)
  const queryClient = useQueryClient()

  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => get<{ items: StaffRow[] }>('/api/users?page_size=100'),
    select: (d) => d.items,
  })
  const doctors = useQuery({
    queryKey: ['admin-doctors'],
    queryFn: () => get<{ items: DoctorRow[] }>('/api/doctors?page_size=100'),
    select: (d) => d.items,
  })

  const userRows = users.data ?? []
  const doctorRows = doctors.data ?? []

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold text-ink-900">Admin — staff</h1>
          <div className="flex-1" />
          <Button variant="secondary" onClick={() => setCreateDoctorOpen(true)}>
            + Doctor
          </Button>
          <Button onClick={() => setCreateUserOpen(true)}>+ Staff user</Button>
        </div>
        <Card className="mt-3">
          <div className="divide-y divide-border">
            {userRows.map((u) => (
              <div key={u.id} className="flex items-center gap-4 p-3">
                <span className="flex-1 font-medium text-ink-900">{u.full_name}</span>
                <span className="text-sm text-ink-600">{u.email}</span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                  {u.role}
                </span>
                <span className={`text-xs ${u.is_active ? 'text-success' : 'text-danger'}`}>
                  {u.is_active ? 'active' : 'inactive'}
                </span>
              </div>
            ))}
            {userRows.length === 0 && <EmptyState message="No staff users" />}
          </div>
        </Card>
      </div>

      <div>
        <h2 className="text-lg font-bold text-ink-900">Doctors</h2>
        <Card className="mt-3">
          <div className="divide-y divide-border">
            {doctorRows.map((d) => (
              <div key={d.id} className="flex items-center gap-4 p-3">
                <span className="flex-1 font-medium text-ink-900">
                  {d.title ? `${d.title} — ` : ''}
                  {d.specialty}
                </span>
                <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs capitalize text-brand-700">
                  {d.booking_mode.replace('_', ' ')}
                </span>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                  {d.billing_mode.replace('_', ' ')}
                </span>
                <span className="text-xs text-ink-400">
                  {d.default_slot_minutes} min slots
                  {d.day_capacity ? ` · ${d.day_capacity}/day` : ''}
                </span>
              </div>
            ))}
            {doctorRows.length === 0 && <EmptyState message="No doctors yet — create one" />}
          </div>
        </Card>
      </div>

      {createUserOpen && (
        <CreateUserModal
          onClose={() => setCreateUserOpen(false)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
      {createDoctorOpen && (
        <CreateDoctorModal
          onClose={() => setCreateDoctorOpen(false)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
    </div>
  )
}

function CreateUserModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('secretary')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post('/api/users', { email, password, full_name: name, role }, crypto.randomUUID())
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New staff user">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="password" placeholder="Password (min 8)" value={password} onChange={(e) => setPassword(e.target.value)} />
      <select className={inputClass + ' mt-2'} value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="secretary">Secretary</option>
        <option value="admin">Admin</option>
      </select>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !email || password.length < 8}>
          Create
        </Button>
      </div>
    </Modal>
  )
}

function CreateDoctorModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [specialty, setSpecialty] = useState('')
  const [title, setTitle] = useState('')
  const [bookingMode, setBookingMode] = useState('slots')
  const [slotMinutes, setSlotMinutes] = useState('20')
  const [dayCapacity, setDayCapacity] = useState('')
  const [billingMode, setBillingMode] = useState('per_visit')
  const [hourlyRate, setHourlyRate] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post(
        '/api/doctors',
        {
          email,
          password,
          full_name: name,
          specialty,
          title: title || undefined,
          booking_mode: bookingMode,
          default_slot_minutes: Number(slotMinutes),
          day_capacity: dayCapacity ? Number(dayCapacity) : undefined,
          billing_mode: billingMode,
          hourly_rate: billingMode === 'per_hour' && hourlyRate ? Number(hourlyRate) : undefined,
        },
        crypto.randomUUID(),
      )
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New doctor">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="password" placeholder="Password (min 8)" value={password} onChange={(e) => setPassword(e.target.value)} />
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
        <select className={inputClass} value={billingMode} onChange={(e) => setBillingMode(e.target.value)}>
          <option value="per_visit">Per visit</option>
          <option value="per_hour">Per hour</option>
        </select>
        {billingMode === 'per_hour' ? (
          <input
            className={inputClass}
            type="number"
            step="0.01"
            placeholder="Hourly rate (EGP)"
            value={hourlyRate}
            onChange={(e) => setHourlyRate(e.target.value)}
          />
        ) : (
          <input
            className={inputClass}
            type="number"
            placeholder="Day capacity (optional)"
            value={dayCapacity}
            onChange={(e) => setDayCapacity(e.target.value)}
          />
        )}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !email || password.length < 8 || specialty.length < 2}>
          Create doctor
        </Button>
      </div>
    </Modal>
  )
}
