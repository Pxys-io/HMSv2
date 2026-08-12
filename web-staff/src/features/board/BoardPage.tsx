import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { get, idemKey, post } from '../../api/client'
import { Button, Card, EmptyState, StatusBadge, inputClass } from '../../components/ui'

type QueueEntry = {
  id: number
  seq: number
  patient_profile_id: number
  patient_name: string | null
  status: string
  checked_in_at: string | null
  called_at: string | null
  started_at: string | null
  booked_time: string | null
  late: boolean
  visit_type_id: number | null
}

type Board = {
  doctor_id: number
  date: string
  entries: QueueEntry[]
  booked_not_arrived: { id: number; booking_ref: string; patient_name: string | null; start_time: string | null }[]
}

type DoctorRow = { id: number; full_name: string; specialty: string }

function waitMinutes(since: string | null): number {
  if (!since) return 0
  return Math.max(0, Math.floor((Date.now() - new Date(since).getTime()) / 60000))
}

export default function BoardPage() {
  const { t } = useTranslation()
  const [doctorId, setDoctorId] = useState<number | null>(null)
  const [walkInOpen, setWalkInOpen] = useState(false)
  const queryClient = useQueryClient()

  const doctors = useQuery({
    queryKey: ['doctors'],
    queryFn: () => get<{ items: DoctorRow[] }>('/api/doctors'),
    select: (d) => d.items,
  })

  const today = new Date().toISOString().slice(0, 10)
  const board = useQuery({
    queryKey: ['board', doctorId, today],
    queryFn: () => get<Board>(`/api/queue?doctor_id=${doctorId}&date=${today}`),
    enabled: doctorId !== null,
    refetchInterval: 5000,
  })

  useEffect(() => {
    if (doctorId === null && doctors.data?.length) setDoctorId(doctors.data[0].id)
  }, [doctors.data, doctorId])

  async function mutate(path: string, body?: unknown) {
    await post(path, body ?? {}, idemKey())
    queryClient.invalidateQueries({ queryKey: ['board'] })
  }

  const entries = board.data?.entries ?? []
  const waiting = entries.filter((e) => e.status === 'waiting')
  const called = entries.filter((e) => e.status === 'called')
  const inRoom = entries.filter((e) => e.status === 'in_room')
  const done = entries.filter((e) => e.status === 'completed')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-lg font-bold text-ink-900">{t('common.waitingRoom')}</h1>
        <select
          className={inputClass + ' w-56'}
          value={doctorId ?? ''}
          onChange={(e) => setDoctorId(Number(e.target.value))}
        >
          {doctors.data?.map((d) => (
            <option key={d.id} value={d.id}>
              {d.full_name} — {d.specialty}
            </option>
          ))}
        </select>
        <div className="flex-1" />
        <Button onClick={() => setWalkInOpen(true)}>{t('common.walkIn')}</Button>
        <Button
          variant="secondary"
          onClick={async () => {
            if (!doctorId) return
            await mutate('/api/queue/call-next?doctor_id=' + doctorId + '&date=' + today)
          }}
        >
          Call next
        </Button>
      </div>

      {board.data && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
          <Card className="p-3">
            <h2 className="mb-2 text-sm font-semibold text-ink-600">Waiting ({waiting.length + called.length})</h2>
            <div className="space-y-2">
              {[...waiting, ...called].map((e) => (
                <div key={e.id} className="rounded-md border border-border p-2">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-lg font-bold text-brand-700">#{e.seq}</span>
                    <StatusBadge status={e.status} />
                  </div>
                  <p className="mt-1 text-sm font-medium text-ink-900">{e.patient_name}</p>
                  <div className="mt-1 flex items-center justify-between text-xs text-ink-400">
                    <span>
                      {waitMinutes(e.checked_in_at)} min{e.late ? ' · late' : ''}
                    </span>
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => mutate(`/api/queue/${e.id}/call`)}>
                        Call
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
              {waiting.length + called.length === 0 && <EmptyState message="No one waiting" />}
            </div>
          </Card>

          <Card className="p-3">
            <h2 className="mb-2 text-sm font-semibold text-ink-600">In room ({inRoom.length})</h2>
            <div className="space-y-2">
              {inRoom.map((e) => (
                <div key={e.id} className="rounded-md border border-success/30 bg-green-50 p-2">
                  <span className="font-mono text-lg font-bold text-success">#{e.seq}</span>
                  <p className="mt-1 text-sm font-medium text-ink-900">{e.patient_name}</p>
                  <p className="text-xs text-ink-400">
                    started {waitMinutes(e.started_at)} min ago
                  </p>
                </div>
              ))}
              {inRoom.length === 0 && <EmptyState message="No active visit" />}
            </div>
          </Card>

          <Card className="p-3">
            <h2 className="mb-2 text-sm font-semibold text-ink-600">Done ({done.length})</h2>
            <div className="space-y-1">
              {done.slice(-5).map((e) => (
                <div key={e.id} className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-ink-400">#{e.seq}</span>
                  <span className="text-ink-600">{e.patient_name}</span>
                </div>
              ))}
              {done.length === 0 && <EmptyState message="Nothing completed yet" />}
            </div>
          </Card>

          <Card className="p-3">
            <h2 className="mb-2 text-sm font-semibold text-ink-600">Booked, not arrived</h2>
            <div className="space-y-1">
              {(board.data.booked_not_arrived ?? []).map((b) => (
                <div key={b.id} className="flex items-center justify-between rounded-md border border-border p-2 text-sm">
                  <div>
                    <p className="font-medium text-ink-900">{b.patient_name}</p>
                    <p className="font-mono text-xs text-ink-400">{b.start_time ?? 'day booking'}</p>
                  </div>
                  <Button
                    size="sm"
                    onClick={() => mutate('/api/queue/check-in', { appointment_id: b.id })}
                  >
                    Check in
                  </Button>
                </div>
              ))}
              {board.data.booked_not_arrived.length === 0 && (
                <EmptyState message="All arrivals checked in" />
              )}
            </div>
          </Card>
        </div>
      )}

      {walkInOpen && (
        <WalkInModal
          doctorId={doctorId}
          onClose={() => setWalkInOpen(false)}
          onDone={() => {
            setWalkInOpen(false)
            queryClient.invalidateQueries({ queryKey: ['board'] })
          }}
        />
      )}
    </div>
  )
}

function WalkInModal({
  doctorId,
  onClose,
  onDone,
}: {
  doctorId: number | null
  onClose: () => void
  onDone: () => void
}) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [visitTypeId, setVisitTypeId] = useState('')
  const [error, setError] = useState('')
  const visitTypes = useQuery({
    queryKey: ['visit-types'],
    queryFn: () => get<{ id: number; name: string }[]>('/api/visit-types'),
  })

  async function submit() {
    try {
      const day = new Date().toISOString().slice(0, 10)
      await post('/api/queue/walk-in', {
        doctor_id: doctorId,
        visit_type_id: Number(visitTypeId),
        day,
        new_profile: { full_name: name, phone },
      })
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-base font-bold text-ink-900">New walk-in</h2>
        {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={inputClass + ' mt-2'} placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <select className={inputClass + ' mt-2'} value={visitTypeId} onChange={(e) => setVisitTypeId(e.target.value)}>
          <option value="">Visit type…</option>
          {visitTypes.data?.map((vt) => (
            <option key={vt.id} value={vt.id}>
              {vt.name}
            </option>
          ))}
        </select>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name || !phone || !visitTypeId}>
            Check in
          </Button>
        </div>
      </div>
    </div>
  )
}
