import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from '../../api/client'
import { Button, Card, Modal, inputClass } from '../../components/ui'

type VisitType = { id: number; name: string; name_ar: string; duration_minutes: number; default_price: number; color: string | null }
type DoctorRow = { id: number; full_name: string | null; specialty: string; billing_mode: string }
type PriceRow = { id: number; visit_type_id: number; doctor_id: number | null; price: number }

export function PricingTab() {
  const queryClient = useQueryClient()
  const [typeOpen, setTypeOpen] = useState(false)
  const [saved, setSaved] = useState('')

  const types = useQuery({ queryKey: ['admin-visit-types'], queryFn: () => get<VisitType[]>('/api/visit-types') })
  const doctors = useQuery({
    queryKey: ['admin-doctors'],
    queryFn: () => get<{ items: DoctorRow[] }>('/api/doctors?page_size=100'),
    select: (d) => d.items,
  })
  const prices = useQuery({ queryKey: ['admin-prices'], queryFn: () => get<PriceRow[]>('/api/pricing') })

  async function saveCell(visitTypeId: number, doctorId: number | null, price: number) {
    await put('/api/pricing', { rows: [{ visit_type_id: visitTypeId, doctor_id: doctorId, price }] })
    queryClient.invalidateQueries({ queryKey: ['admin-prices'] })
    setSaved('Saved ' + new Date().toLocaleTimeString())
  }

  const typeRows = types.data ?? []
  const doctorRows = doctors.data ?? []
  const priceRows = prices.data ?? []

  const priceFor = (visitTypeId: number, doctorId: number | null) =>
    priceRows.find((p) => p.visit_type_id === visitTypeId && p.doctor_id === doctorId)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Pricing</h1>
        <div className="flex-1" />
        {saved && <span className="text-xs text-success">{saved}</span>}
        <Button onClick={() => setTypeOpen(true)}>+ Visit type</Button>
      </div>

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-start text-xs text-ink-400">
              <th className="p-2 text-start">Visit type</th>
              <th className="p-2 text-start">Duration</th>
              <th className="p-2 text-start">Clinic default</th>
              {doctorRows.map((d) => (
                <th key={d.id} className="p-2 text-start">
                  {d.full_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {typeRows.map((vt) => (
              <tr key={vt.id}>
                <td className="p-2 font-medium text-ink-900">
                  {vt.name}
                  <span className="ms-1 text-xs text-ink-400">({vt.name_ar})</span>
                </td>
                <td className="p-2 text-ink-600">{vt.duration_minutes} min</td>
                <td className="p-2">
                  <PriceCell value={priceFor(vt.id, null)?.price ?? vt.default_price} onSave={(v) => saveCell(vt.id, null, v)} />
                </td>
                {doctorRows.map((d) => (
                  <td key={d.id} className="p-2">
                    <PriceCell value={priceFor(vt.id, d.id)?.price} onSave={(v) => saveCell(vt.id, d.id, v)} />
                  </td>
                ))}
              </tr>
            ))}
            {typeRows.length === 0 && (
              <tr>
                <td colSpan={3 + doctorRows.length} className="p-6 text-center text-ink-400">
                  No visit types — add one
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <Card className="p-4">
        <h2 className="text-sm font-semibold text-ink-600">Waiting-room display tokens</h2>
        <p className="mt-1 text-xs text-ink-400">
          Generate a TV token per doctor (shown once; rotation invalidates the old one).
        </p>
        <div className="mt-3 space-y-2">
          {doctorRows.map((d) => (
            <DisplayTokenRow key={d.id} doctor={d} />
          ))}
        </div>
      </Card>

      {typeOpen && <VisitTypeModal onClose={() => setTypeOpen(false)} onDone={() => queryClient.invalidateQueries()} />}
    </div>
  )
}

function PriceCell({ value, onSave }: { value: number | undefined; onSave: (v: number) => void }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(value === undefined ? '' : String(value))

  if (!editing) {
    return (
      <button
        onClick={() => {
          setText(value === undefined ? '' : String(value))
          setEditing(true)
        }}
        className={`rounded border border-transparent px-2 py-1 text-start font-mono hover:border-border ${
          value === undefined ? 'text-ink-400' : 'text-ink-900'
        }`}
      >
        {value === undefined ? '—' : value}
      </button>
    )
  }
  return (
    <input
      type="number"
      step="0.01"
      className="w-24 rounded border border-brand-600 px-2 py-1 font-mono text-sm"
      value={text}
      autoFocus
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        const v = Number(text)
        if (!Number.isNaN(v) && text !== '') {
          onSave(v)
        }
        setEditing(false)
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
      }}
    />
  )
}

function DisplayTokenRow({ doctor }: { doctor: DoctorRow }) {
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  async function generate() {
    try {
      const result = await post<{ token: string }>(`/api/doctors/${doctor.id}/display-token`, {})
      setToken(result.token)
      setError('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="w-40 truncate text-ink-900">{doctor.full_name}</span>
      <Button size="sm" variant="secondary" onClick={generate}>
        Generate token
      </Button>
      {token && (
        <span className="flex-1 truncate rounded bg-slate-100 px-2 py-1 font-mono text-xs">
          {token} <span className="text-ink-400">(shown once — copy now)</span>
        </span>
      )}
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  )
}

function VisitTypeModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [nameAr, setNameAr] = useState('')
  const [duration, setDuration] = useState('20')
  const [price, setPrice] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post('/api/visit-types', {
        name,
        name_ar: nameAr,
        duration_minutes: Number(duration),
        default_price: Number(price),
      })
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New visit type">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Name (EN)" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Name (AR)" value={nameAr} onChange={(e) => setNameAr(e.target.value)} />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <input className={inputClass} type="number" placeholder="Duration (min)" value={duration} onChange={(e) => setDuration(e.target.value)} />
        <input className={inputClass} type="number" step="0.01" placeholder="Default price" value={price} onChange={(e) => setPrice(e.target.value)} />
      </div>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !nameAr || price === ''}>
          Create
        </Button>
      </div>
    </Modal>
  )
}
