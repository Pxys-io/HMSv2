import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'

type AuditEvent = {
  id: number
  occurred_at: string
  actor_label: string
  action: string
  outcome: string
  entity_type: string | null
  entity_id: string | null
  before_json: Record<string, unknown> | null
  after_json: Record<string, unknown> | null
}

export default function AuditPage() {
  const [actionFilter, setActionFilter] = useState('')
  const [verifyResult, setVerifyResult] = useState<string | null>(null)

  const events = useQuery({
    queryKey: ['audit', actionFilter],
    queryFn: () =>
      get<{ items: AuditEvent[] }>(
        `/api/audit/events?page_size=100${actionFilter ? `&action_prefix=${actionFilter}` : ''}`,
      ),
    select: (d) => d.items,
  })

  async function verify() {
    const result = await post<{ ok: boolean; broken_at_id: number | null; unresolved_count: number }>(
      '/api/audit/verify',
      {},
    )
    setVerifyResult(
      result.ok
        ? `Chain OK — ${result.unresolved_count} unresolved intents`
        : `⚠ Broken at event #${result.broken_at_id}`,
    )
    events.refetch()
  }

  const rows = events.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Audit log</h1>
        <input
          className={inputClass + ' max-w-xs'}
          placeholder="Action prefix, e.g. appointment"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
        />
        <div className="flex-1" />
        <Button variant="secondary" onClick={verify}>
          Verify chain
        </Button>
      </div>
      {verifyResult && (
        <p
          className={`rounded-md p-2 text-sm ${
            verifyResult.startsWith('Chain')
              ? 'bg-green-50 text-green-800'
              : 'bg-red-50 text-red-700'
          }`}
        >
          {verifyResult}
        </p>
      )}
      <Card>
        <div className="divide-y divide-border">
          {rows.map((e) => (
            <div key={e.id} className="flex items-start gap-4 p-3 text-sm">
              <span className="w-20 shrink-0 font-mono text-xs text-ink-400">
                #{e.id}
              </span>
              <span className="w-40 shrink-0 font-mono text-xs text-ink-400">
                {new Date(e.occurred_at).toLocaleString()}
              </span>
              <span className="w-44 shrink-0 truncate text-ink-600">{e.actor_label}</span>
              <span className="w-48 shrink-0 font-mono text-xs text-ink-900">{e.action}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                {e.outcome}
              </span>
              <span className="shrink-0 text-xs text-ink-400">
                {e.entity_type ? `${e.entity_type}#${e.entity_id}` : ''}
              </span>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No audit events match" />}
        </div>
      </Card>
    </div>
  )
}
