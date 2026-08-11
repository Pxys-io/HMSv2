import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, StatusBadge } from '../../components/ui'

type QueueEntry = {
  id: number
  seq: number
  patient_name: string | null
  patient_profile_id: number
  status: string
  visit_type_id: number | null
}

export default function TodayPage() {
  const queryClient = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => get<{ id: number }>('/api/auth/me'),
  })
  const doctors = useQuery({
    queryKey: ['doctors'],
    queryFn: () => get<{ items: { id: number; staff_user_id: number }[] }>('/api/doctors'),
    select: (d) => d.items,
  })
  const myDoctor = doctors.data?.find((d) => d.staff_user_id === me.data?.id)
  const today = new Date().toISOString().slice(0, 10)

  const board = useQuery({
    queryKey: ['today-board', myDoctor?.id],
    queryFn: () =>
      get<{ entries: QueueEntry[] }>(`/api/queue?doctor_id=${myDoctor!.id}&date=${today}`),
    enabled: Boolean(myDoctor),
    refetchInterval: 5000,
  })

  const entries = board.data?.entries ?? []

  async function action(path: string) {
    await post(path, {}, crypto.randomUUID())
    queryClient.invalidateQueries({ queryKey: ['today-board'] })
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ink-900">Today's queue</h1>
      <div className="flex flex-wrap gap-4">
        {(['waiting', 'called', 'in_room', 'completed'] as const).map((status) => (
          <Card key={status} className="w-64 p-3">
            <h2 className="mb-2 text-sm font-semibold capitalize text-ink-600">
              {status} ({entries.filter((e) => e.status === status).length})
            </h2>
            <div className="space-y-2">
              {entries
                .filter((e) => e.status === status)
                .map((e) => (
                  <div key={e.id} className="rounded-md border border-border p-2">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-lg font-bold text-brand-700">#{e.seq}</span>
                      <StatusBadge status={e.status} />
                    </div>
                    <p className="mt-1 text-sm font-medium text-ink-900">{e.patient_name}</p>
                    {e.status === 'waiting' && (
                      <div className="mt-2 flex gap-1">
                        <Button size="sm" onClick={() => action(`/api/queue/${e.id}/call`)}>
                          Call
                        </Button>
                      </div>
                    )}
                    {e.status === 'called' && (
                      <Link to={`/patients/${e.patient_profile_id}/exam?entry=${e.id}`}>
                        <Button size="sm" className="mt-2 w-full">
                          Start visit
                        </Button>
                      </Link>
                    )}
                    {e.status === 'in_room' && (
                      <Link to={`/patients/${e.patient_profile_id}/exam?entry=${e.id}`}>
                        <Button size="sm" variant="secondary" className="mt-2 w-full">
                          Open exam
                        </Button>
                      </Link>
                    )}
                  </div>
                ))}
              {entries.filter((e) => e.status === status).length === 0 && (
                <EmptyState message="None" />
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
