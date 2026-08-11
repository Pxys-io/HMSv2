import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { get, idemKey, post } from '../api/client'
import { useAuthStore } from '../auth/store'

type Doctor = { id: number; full_name: string; specialty: string; booking_mode: string }
type DayAvailability = {
  mode: string
  date: string
  slots: { start: string; end: string; remaining: number }[] | null
  remaining: number | null
  reason: string | null
}
type Profile = { id: number; full_name: string; code: string }

function nextDays(count: number): string[] {
  const out: string[] = []
  const now = new Date()
  for (let i = 1; i <= count; i++) {
    const d = new Date(now.getTime() + i * 86400000)
    out.push(d.toISOString().slice(0, 10))
  }
  return out
}

export default function BookingPage() {
  const [params] = useSearchParams()
  const [step, setStep] = useState(params.get('doctor') ? 2 : 1)
  const [doctorId, setDoctorId] = useState<number | null>(
    params.get('doctor') ? Number(params.get('doctor')) : null,
  )
  const [day, setDay] = useState<string>('')
  const [slot, setSlot] = useState<string>('')
  const [profileId, setProfileId] = useState<number | null>(null)
  const [confirmed, setConfirmed] = useState<string | null>(null)
  const [error, setError] = useState('')

  const patient = useAuthStore((s) => s.patient)
  const doctors = useQuery({
    queryKey: ['public-doctors'],
    queryFn: () => get<Doctor[]>('/api/public/doctors'),
  })
  const profiles = useQuery({
    queryKey: ['my-profiles'],
    queryFn: () => get<Profile[]>('/api/public/profiles'),
    enabled: Boolean(patient),
  })

  const selectedDoctor = doctors.data?.find((d) => d.id === doctorId)
  const days = nextDays(14)
  const availability = useQuery({
    queryKey: ['availability', doctorId, day],
    queryFn: () =>
      get<{ days: DayAvailability[] }>(
        `/api/public/doctors/${doctorId}/availability?from=${day}&to=${day}&visit_type_id=1`,
      ),
    enabled: Boolean(doctorId && day),
  })

  useEffect(() => {
    if (!day && days.length) setDay(days[0])
  }, [])

  async function confirm() {
    if (!doctorId || !day || !profileId) {
      setError('Please complete all steps')
      return
    }
    try {
      const appt = await post<{ booking_ref: string }>(
        '/api/public/appointments',
        {
          profile_id: profileId,
          doctor_id: doctorId,
          visit_type_id: 1,
          date: day,
          start_time: slot || null,
        },
        idemKey(),
      )
      setConfirmed(appt.booking_ref)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Booking failed')
    }
  }

  if (confirmed) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-3xl">✓</div>
        <h1 className="mt-4 text-2xl font-bold text-ink-900">Appointment booked!</h1>
        <p className="mt-2 font-mono text-brand-700">{confirmed}</p>
        <p className="mt-4 text-sm text-ink-600">
          A confirmation email is on its way. You can manage this booking from{' '}
          <Link to="/account" className="text-brand-700 underline">
            My visits
          </Link>.
        </p>
      </div>
    )
  }

  const dayData = availability.data?.days[0]

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      <div className="mb-8 flex items-center justify-center gap-2 text-sm">
        {['Doctor', 'Time', 'Details'].map((label, i) => (
          <div key={label} className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold ${
                step >= i + 1 ? 'bg-brand-600 text-white' : 'bg-slate-200 text-slate-500'
              }`}
            >
              {i + 1}
            </span>
            <span className={step >= i + 1 ? 'font-medium text-ink-900' : 'text-ink-400'}>{label}</span>
            {i < 2 && <span className="mx-1 text-ink-300">→</span>}
          </div>
        ))}
      </div>

      {error && <p className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      {step === 1 && (
        <div className="grid gap-3 md:grid-cols-2">
          {doctors.data?.map((d) => (
            <button
              key={d.id}
              onClick={() => {
                setDoctorId(d.id)
                setStep(2)
              }}
              className="rounded-xl border border-border bg-surface p-4 text-start hover:border-brand-600"
            >
              <p className="font-bold text-ink-900">{d.full_name}</p>
              <p className="text-sm text-brand-700">{d.specialty}</p>
              <p className="mt-1 text-xs text-ink-400">
                {d.booking_mode === 'day_queue' ? 'Day booking' : 'Time slots'}
              </p>
            </button>
          ))}
        </div>
      )}

      {step === 2 && selectedDoctor && (
        <div>
          <h2 className="font-bold text-ink-900">
            {selectedDoctor.full_name} —{' '}
            {selectedDoctor.booking_mode === 'day_queue'
              ? 'pick a day'
              : 'pick a day and time'}
          </h2>
          <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
            {days.map((d) => (
              <button
                key={d}
                onClick={() => setDay(d)}
                className={`shrink-0 rounded-lg border px-3 py-2 text-sm ${
                  day === d ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-border'
                }`}
              >
                {new Date(d + 'T12:00').toLocaleDateString('en', { weekday: 'short', day: 'numeric', month: 'short' })}
              </button>
            ))}
          </div>

          {selectedDoctor.booking_mode === 'slots' && (
            <div className="mt-4 grid grid-cols-3 gap-2 md:grid-cols-4">
              {dayData?.slots?.map((s) => (
                <button
                  key={s.start}
                  onClick={() => setSlot(s.start)}
                  className={`rounded-md border px-3 py-2 text-sm font-mono ${
                    slot === s.start
                      ? 'border-brand-600 bg-brand-600 text-white'
                      : 'border-border hover:border-brand-600'
                  }`}
                >
                  {s.start}
                </button>
              ))}
              {dayData?.reason === 'no_shift' && (
                <p className="col-span-full text-sm text-ink-400">No availability this day</p>
              )}
              {dayData?.reason === 'capacity' && (
                <p className="col-span-full text-sm text-amber-600">This day is fully booked</p>
              )}
            </div>
          )}
          {selectedDoctor.booking_mode === 'day_queue' && (
            <p className="mt-4 rounded-md bg-brand-50 p-3 text-sm text-brand-700">
              Booking is per day — patients are seen in order of arrival on the day.
            </p>
          )}

          <div className="mt-6 flex gap-2">
            <button
              onClick={() => setStep(1)}
              className="rounded-md border border-border px-4 py-2 text-sm text-ink-600"
            >
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={selectedDoctor.booking_mode === 'slots' && !slot}
              className="rounded-md bg-brand-600 px-6 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
            >
              Continue
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          <h2 className="font-bold text-ink-900">Who is this for?</h2>
          {patient ? (
            <div className="mt-4 space-y-2">
              <button
                onClick={async () => {
                  const created = await post<Profile>(
                    '/api/public/profiles',
                    { full_name: patient.full_name, phone: patient.phone ?? '0000000000' },
                    idemKey(),
                  )
                  profiles.refetch()
                  setProfileId(created.id)
                }}
                className="mb-2 w-full rounded-lg border border-brand-600 bg-brand-50 p-3 text-start"
              >
                <p className="font-medium text-brand-700">Book for yourself</p>
                <p className="text-xs text-ink-500">
                  {patient.full_name} · {patient.phone ?? 'no phone on file'}
                </p>
              </button>
              {profiles.data?.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setProfileId(p.id)}
                  className={`flex w-full items-center justify-between rounded-lg border p-3 ${
                    profileId === p.id ? 'border-brand-600 bg-brand-50' : 'border-border'
                  }`}
                >
                  <span className="font-medium text-ink-900">{p.full_name}</span>
                  <span className="font-mono text-xs text-ink-400">{p.code}</span>
                </button>
              ))}
              {profiles.data?.length === 0 && (
                <p className="text-sm text-ink-400">
                  No profiles yet — book for yourself or add a family member.
                </p>
              )}
              <AddProfile onAdded={(id) => setProfileId(id)} />
            </div>
          ) : (
            <p className="mt-4 rounded-md bg-amber-50 p-3 text-sm text-amber-800">
              You need an account to book. <Link to="/login" className="font-semibold underline">Sign in</Link>{' '}
              or <Link to="/register" className="font-semibold underline">create one</Link> first.
            </p>
          )}

          {selectedDoctor && (
            <div className="mt-6 rounded-xl border border-border bg-surface p-4">
              <p className="font-bold text-ink-900">{selectedDoctor.full_name}</p>
              <p className="text-sm text-ink-600">
                {day} {slot ? `at ${slot}` : '(day booking)'}
              </p>
            </div>
          )}

          <div className="mt-6 flex gap-2">
            <button
              onClick={() => setStep(2)}
              className="rounded-md border border-border px-4 py-2 text-sm text-ink-600"
            >
              Back
            </button>
            <button
              onClick={confirm}
              disabled={!profileId}
              className="rounded-md bg-brand-600 px-6 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
            >
              Confirm booking
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function AddProfile({ onAdded }: { onAdded: (id: number) => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')

  async function submit() {
    const profile = await post<Profile>('/api/public/profiles', { full_name: name, phone }, idemKey())
    setOpen(false)
    setName('')
    setPhone('')
    onAdded(profile.id)
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="mt-2 text-sm text-brand-700 underline">
        + Add family member
      </button>
    )
  }
  return (
    <div className="mt-2 rounded-lg border border-border p-3">
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
