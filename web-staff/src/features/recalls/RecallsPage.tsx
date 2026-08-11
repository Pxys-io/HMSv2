import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'

type RecallRow = {
  visit_id: number
  patient_profile_id: number
  patient_name: string
  phone: string
  doctor_name: string | null
  follow_up_due: string
  days_overdue: number
  days_until_due: number
  last_visit_summary: string | null
  no_show_count: number
}

export default function RecallsPage() {
  const [dismissDays, setDismissDays] = useState<Record<number, number>>({})
  const queryClient = useQueryClient()

  const recalls = useQuery({
    queryKey: ['recalls'],
    queryFn: () => get<RecallRow[]>('/api/recalls'),
    refetchInterval: 15000,
  })

  async function dismiss(visitId: number) {
    const days = dismissDays[visitId] ?? 30
    await post(`/api/recalls/${visitId}/dismiss?days=${days}`, {})
    queryClient.invalidateQueries({ queryKey: ['recalls'] })
  }

  const rows = recalls.data ?? []

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ink-900">Recalls — follow-up due</h1>
      <Card>
        <div className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.visit_id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <Link to={`/patients/${r.patient_profile_id}`} className="font-medium text-ink-900 hover:underline">
                  {r.patient_name}
                </Link>
                <p className="text-xs text-ink-400">
                  {r.phone} · Dr. {r.doctor_name ?? '—'}
                  {r.no_show_count > 0 ? ` · ${r.no_show_count} no-shows` : ''}
                </p>
                {r.last_visit_summary && (
                  <p className="mt-1 text-xs text-ink-600">{r.last_visit_summary}</p>
                )}
              </div>
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                  r.days_overdue > 0
                    ? 'bg-red-50 text-red-700'
                    : 'bg-amber-50 text-amber-700'
                }`}
              >
                {r.days_overdue > 0 ? `${r.days_overdue}d overdue` : `in ${r.days_until_due}d`}
              </span>
              <input
                type="number"
                min={1}
                className={inputClass + ' w-20'}
                placeholder="30"
                value={dismissDays[r.visit_id] ?? ''}
                onChange={(e) =>
                  setDismissDays({ ...dismissDays, [r.visit_id]: Number(e.target.value) })
                }
              />
              <Button size="sm" variant="secondary" onClick={() => dismiss(r.visit_id)}>
                Snooze
              </Button>
              <a
                href={`https://wa.me/${r.phone.replace(/\D/g, '')}`}
                target="_blank"
                rel="noreferrer"
              >
                <Button size="sm">WhatsApp</Button>
              </a>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No follow-ups due" />}
        </div>
      </Card>
    </div>
  )
}
