import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'
import { DynamicFields } from '../admin/DynamicFields'

type Patient = {
  id: number
  code: string
  full_name: string
  phone: string
  age: number | null
  gender: string | null
  no_show_count: number
  is_archived: boolean
}

export default function PatientsPage() {
  const [q, setQ] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const queryClient = useQueryClient()

  const patients = useQuery({
    queryKey: ['patients-search', q],
    queryFn: () => get<{ results: Patient[] }>(`/api/search/patients?q=${encodeURIComponent(q)}&limit=20`),
    enabled: q.trim().length >= 2,
  })

  const all = useQuery({
    queryKey: ['patients-list'],
    queryFn: () => get<{ results: Patient[] }>('/api/search/patients?q=00&limit=20'),
    enabled: q.trim().length < 2,
  })

  const rows: Patient[] =
    q.trim().length >= 2 ? (patients.data?.results ?? []) : ((all.data?.results ?? []) as Patient[])

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Patients</h1>
        <input
          className={inputClass + ' max-w-sm'}
          placeholder="Search by name, phone, or code…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ New patient</Button>
      </div>

      <Card>
        <div className="divide-y divide-border">
          {rows.map((p) => (
            <Link key={p.id} to={`/patients/${p.id}`} className="flex items-center gap-4 p-3 hover:bg-slate-50">
              <span className="font-mono text-xs text-ink-400">{p.code}</span>
              <span className="flex-1 font-medium text-ink-900">{p.full_name}</span>
              <span className="text-sm text-ink-600">{p.age ?? '—'} y</span>
              <span className="font-mono text-xs text-ink-400">{p.phone}</span>
              {p.no_show_count > 0 && (
                <span className="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-700">
                  {p.no_show_count} no-shows
                </span>
              )}
            </Link>
          ))}
          {rows.length === 0 && <EmptyState message="No patients found" />}
        </div>
      </Card>

      {createOpen && <CreatePatientModal onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />}
    </div>
  )
}

function CreatePatientModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [customData, setCustomData] = useState<Record<string, unknown>>({})
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post(
        '/api/patients',
        { full_name: name, phone, custom_data: Object.keys(customData).length ? customData : undefined },
        crypto.randomUUID(),
      )
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-4 text-base font-bold text-ink-900">New patient</h2>
        {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={inputClass + ' mt-2'} placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
        <DynamicFields entity="patient" value={customData} onChange={setCustomData} />
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name || !phone}>
            Create
          </Button>
        </div>
      </div>
    </div>
  )
}
