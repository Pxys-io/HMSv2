import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, StatusBadge, inputClass } from '../../components/ui'

type Invoice = {
  id: number
  number: string
  patient_profile_id: number
  total: number
  patient_due: number
  paid_total: number
  refunded_total: number
  net_paid: number
  remaining: number
  status: string
  items: { id: number; description: string; unit_price: number; qty: number }[]
  payments: { id: number; amount: number; method: string; is_refund: boolean }[]
  discounts: { id: number; kind: string; value: number }[]
  syndicate_due: number
}

export default function CashierPage() {
  const [payTarget, setPayTarget] = useState<Invoice | null>(null)
  const queryClient = useQueryClient()

  const invoices = useQuery({
    queryKey: ['invoices'],
    queryFn: () =>
      get<{ items: Invoice[] }>(
        '/api/invoices?status=issued&status=partially_paid&page_size=100',
      ),
    select: (d) => d.items,
    refetchInterval: 10000,
  })

  async function recordPayment(amount: number, method: string, reference?: string) {
    if (!payTarget) return
    await post(
      `/api/invoices/${payTarget.id}/payments`,
      { amount, method, reference: reference || undefined },
      crypto.randomUUID(),
    )
    setPayTarget(null)
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
  }

  const rows = invoices.data ?? []

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ink-900">Cashier — to collect</h1>
      <Card>
        <div className="divide-y divide-border">
          {rows.map((inv) => (
            <div key={inv.id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold text-ink-900">{inv.number}</p>
                <p className="text-xs text-ink-400">
                  Patient #{inv.patient_profile_id} ·{' '}
                  {inv.items.map((i) => i.description).join(', ')}
                </p>
                {inv.syndicate_due > 0 && (
                  <p className="text-xs text-info">Syndicate covers {inv.syndicate_due.toFixed(2)}</p>
                )}
              </div>
              <div className="text-end">
                <p className="text-sm font-bold text-ink-900">{inv.total.toFixed(2)} EGP</p>
                <p className="text-xs text-ink-400">remaining {inv.remaining.toFixed(2)}</p>
              </div>
              <StatusBadge status={inv.status} />
              <Button onClick={() => setPayTarget(inv)} disabled={inv.remaining <= 0}>
                Pay
              </Button>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="Nothing to collect 🎉" />}
        </div>
      </Card>

      {payTarget && (
        <PayModal
          invoice={payTarget}
          onClose={() => setPayTarget(null)}
          onPay={recordPayment}
        />
      )}
    </div>
  )
}

const METHODS = ['cash', 'card', 'fawry', 'instapay', 'wallet', 'meeza']

function PayModal({
  invoice,
  onClose,
  onPay,
}: {
  invoice: Invoice
  onClose: () => void
  onPay: (amount: number, method: string, reference?: string) => Promise<void>
}) {
  const [amount, setAmount] = useState(String(invoice.remaining))
  const [method, setMethod] = useState('cash')
  const [reference, setReference] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await onPay(Number(amount), method, reference || undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl border border-border bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="mb-3 text-base font-bold text-ink-900">Collect payment</h2>
        <p className="font-mono text-sm text-ink-600">{invoice.number}</p>
        {error && <p className="mt-2 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <input
          type="number"
          step="0.01"
          className={inputClass + ' mt-3'}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <div className="mt-3 grid grid-cols-3 gap-2">
          {METHODS.map((m) => (
            <button
              key={m}
              onClick={() => setMethod(m)}
              className={`rounded-md border px-2 py-1.5 text-xs capitalize ${
                method === m ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-border text-ink-600'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
        {(method === 'instapay' || method === 'fawry') && (
          <input
            className={inputClass + ' mt-3'}
            placeholder="Reference"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit}>Confirm</Button>
        </div>
      </div>
    </div>
  )
}
