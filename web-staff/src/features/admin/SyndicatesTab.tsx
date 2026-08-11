import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type Syndicate = { id: number; name: string; name_ar: string | null; code: string; contact_phone: string | null; contact_email: string | null; is_active: boolean }
type SyndicatePrice = { id: number; visit_type_id: number; doctor_id: number | null; syndicate_coverage: number; patient_share: number }
type VisitType = { id: number; name: string }

export function SyndicatesTab() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [pricesFor, setPricesFor] = useState<Syndicate | null>(null)

  const syndicates = useQuery({ queryKey: ['admin-syndicates'], queryFn: () => get<Syndicate[]>('/api/syndicates') })
  const rows = syndicates.data ?? []

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Syndicates & insurance</h1>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Syndicate</Button>
      </div>
      <Card className="mt-3">
        <div className="divide-y divide-border">
          {rows.map((s) => (
            <div key={s.id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink-900">
                  {s.name}
                  {s.name_ar ? <span className="ms-2 text-sm text-ink-400">{s.name_ar}</span> : null}
                </p>
                <p className="text-xs text-ink-400">
                  {s.code} · {s.contact_phone ?? '—'}
                </p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => setPricesFor(s)}>
                Contract prices
              </Button>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No syndicates yet" />}
        </div>
      </Card>

      {createOpen && <SyndicateModal onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />}
      {pricesFor && <ContractPricesModal syndicate={pricesFor} onClose={() => setPricesFor(null)} />}
    </div>
  )
}

function SyndicateModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [nameAr, setNameAr] = useState('')
  const [code, setCode] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post('/api/syndicates', { name, name_ar: nameAr || undefined, code, contact_phone: phone || undefined })
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New syndicate">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Name (AR)" value={nameAr} onChange={(e) => setNameAr(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Code" value={code} onChange={(e) => setCode(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Contact phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !code}>
          Create
        </Button>
      </div>
    </Modal>
  )
}

function ContractPricesModal({ syndicate, onClose }: { syndicate: Syndicate; onClose: () => void }) {
  const [saved, setSaved] = useState('')
  const types = useQuery({ queryKey: ['admin-visit-types'], queryFn: () => get<VisitType[]>('/api/visit-types') })
  const prices = useQuery({
    queryKey: ['syndicate-prices', syndicate.id],
    queryFn: () => get<SyndicatePrice[]>(`/api/syndicates/${syndicate.id}/prices`),
  })

  async function save(visitTypeId: number, coverage: number, share: number) {
    await put(`/api/syndicates/${syndicate.id}/prices`, {
      items: [{ visit_type_id: visitTypeId, syndicate_coverage: coverage, patient_share: share }],
    })
    prices.refetch()
    setSaved('Saved ' + new Date().toLocaleTimeString())
  }

  const priceFor = (visitTypeId: number) =>
    prices.data?.find((p) => p.visit_type_id === visitTypeId && p.doctor_id === null)

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div
        className="w-full max-w-xl rounded-xl border border-border bg-surface p-5 shadow-e2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-bold text-ink-900">Contract prices — {syndicate.name}</h2>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600" aria-label="Close">
            ✕
          </button>
        </div>
        {saved && <p className="mb-2 text-xs text-success">{saved}</p>}
        <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {(types.data ?? []).map((vt) => {
            const row = priceFor(vt.id)
            return (
              <div key={vt.id} className="flex items-center gap-3 rounded-md border border-border p-2">
                <span className="w-40 truncate text-sm font-medium text-ink-900">{vt.name}</span>
                <input
                  type="number"
                  step="0.01"
                  className={inputClass + ' flex-1'}
                  placeholder="Coverage (syndicate pays)"
                  defaultValue={row?.syndicate_coverage ?? ''}
                  onBlur={(e) => {
                    const coverage = Number(e.target.value)
                    if (!Number.isNaN(coverage) && e.target.value !== '') {
                      save(vt.id, coverage, row?.patient_share ?? 0)
                    }
                  }}
                />
                <input
                  type="number"
                  step="0.01"
                  className={inputClass + ' flex-1'}
                  placeholder="Patient share"
                  defaultValue={row?.patient_share ?? ''}
                  onBlur={(e) => {
                    const share = Number(e.target.value)
                    if (!Number.isNaN(share) && e.target.value !== '') {
                      save(vt.id, row?.syndicate_coverage ?? 0, share)
                    }
                  }}
                />
              </div>
            )
          })}
          {(types.data ?? []).length === 0 && (
            <p className="text-sm text-ink-400">No visit types yet</p>
          )}
        </div>
      </div>
    </div>
  )
}
