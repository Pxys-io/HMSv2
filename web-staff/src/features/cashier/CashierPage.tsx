import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../api/client'
import { Button, Card, EmptyState, StatusBadge, inputClass } from '../../components/ui'

type UninvoicedVisit = {
  visit_id: number
  patient_name: string | null
  patient_phone: string | null
  doctor_name: string | null
  type_name: string
  ended_at: string | null
  price_preview: number | null
}

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
  items: { id: number; description: string; unit_price: number; qty: number; line_total: number }[]
  subtotal: number
  tax_rate: number
  tax_total: number
  vat_inclusive: boolean
  vat_exempt: boolean
  vat_number: string
  payments: { id: number; amount: number; method: string; is_refund: boolean }[]
  discounts: { id: number; kind: string; value: number }[]
  syndicate_due: number
}

type BillingPermissions = {
  role: string
  cashier_can_adjust_pricing: boolean
  discount_cap_secretary_pct: number
}

export default function CashierPage() {
  const [payTarget, setPayTarget] = useState<Invoice | null>(null)
  const [itemsTarget, setItemsTarget] = useState<Invoice | null>(null)
  const queryClient = useQueryClient()

  const uninvoiced = useQuery({
    queryKey: ['uninvoiced'],
    queryFn: () => get<UninvoicedVisit[]>('/api/cashier/uninvoiced'),
    refetchInterval: 10000,
  })

  async function invoiceVisit(visitId: number) {
    await post(`/api/invoices/from-visit/${visitId}`, {}, crypto.randomUUID())
    queryClient.invalidateQueries({ queryKey: ['uninvoiced'] })
    queryClient.invalidateQueries({ queryKey: ['invoices'] })
  }

  const permissions = useQuery({
    queryKey: ['billing-permissions'],
    queryFn: () => get<BillingPermissions>('/api/billing/permissions'),
  })

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
        <div className="border-b border-border p-3">
          <h2 className="text-sm font-semibold text-ink-600">
            Completed visits — invoice them ({uninvoiced.data?.length ?? 0})
          </h2>
          <p className="mt-1 text-xs text-ink-400">
            Invoices are created here by the reception/cashier — visits complete invoice-less.
          </p>
        </div>
        <div className="divide-y divide-border">
          {(uninvoiced.data ?? []).map((u) => (
            <div key={u.visit_id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink-900">{u.patient_name}</p>
                <p className="text-xs text-ink-400">
                  {u.doctor_name} · {u.type_name} · {u.patient_phone}
                </p>
              </div>
              <span className="font-mono text-sm text-ink-600">
                {u.price_preview !== null ? `${u.price_preview.toFixed(2)} EGP` : '—'}
              </span>
              <Button size="sm" onClick={() => void invoiceVisit(u.visit_id)}>
                Invoice
              </Button>
            </div>
          ))}
          {(uninvoiced.data ?? []).length === 0 && (
            <p className="p-6 text-center text-sm text-ink-400">
              No completed visits waiting for an invoice
            </p>
          )}
        </div>
      </Card>

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
              <Button size="sm" variant="secondary" onClick={() => setItemsTarget(inv)}>
                Items
              </Button>
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
      {itemsTarget && (
        <ItemsModal
          invoice={itemsTarget}
          canAdjust={permissions.data?.cashier_can_adjust_pricing ?? false}
          onClose={() => setItemsTarget(null)}
          onChanged={() => queryClient.invalidateQueries({ queryKey: ['invoices'] })}
        />
      )}
    </div>
  )
}

function ItemsModal({
  invoice,
  canAdjust,
  onClose,
  onChanged,
}: {
  invoice: Invoice
  canAdjust: boolean
  onClose: () => void
  onChanged: () => void
}) {
  const [editingId, setEditingId] = useState<number | null>(null)
  const [priceText, setPriceText] = useState('')
  const [qtyText, setQtyText] = useState('')
  const [error, setError] = useState('')

  async function save(itemId: number) {
    const payload: Record<string, number> = {}
    if (priceText !== '') payload.unit_price = Number(priceText)
    if (qtyText !== '') payload.qty = Number(qtyText)
    if (!Object.keys(payload).length) {
      setEditingId(null)
      return
    }
    try {
      await patch(`/api/invoices/${invoice.id}/items/${itemId}`, payload)
      setEditingId(null)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-ink-900">Invoice items</h2>
            <p className="font-mono text-xs text-ink-400">{invoice.number}</p>
          </div>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600" aria-label="Close">
            ✕
          </button>
        </div>
        {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        {!canAdjust && (
          <p className="mb-3 rounded-md bg-amber-50 p-2 text-xs text-amber-800">
            Price editing is disabled for cashiers — an admin can enable it in Settings.
          </p>
        )}
        <div className="space-y-2">
          {invoice.items.map((item) => (
            <div key={item.id} className="flex items-center gap-3 rounded-md border border-border p-2 text-sm">
              <span className="min-w-0 flex-1 truncate text-ink-900">{item.description}</span>
              {editingId === item.id ? (
                <>
                  <input
                    className={inputClass + ' w-24'}
                    type="number"
                    step="0.01"
                    placeholder="Price"
                    value={priceText}
                    onChange={(e) => setPriceText(e.target.value)}
                    autoFocus
                  />
                  <input
                    className={inputClass + ' w-20'}
                    type="number"
                    step="0.01"
                    placeholder="Qty"
                    value={qtyText}
                    onChange={(e) => setQtyText(e.target.value)}
                  />
                  <Button size="sm" onClick={() => void save(item.id)}>
                    Save
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditingId(null)}>
                    ✕
                  </Button>
                </>
              ) : (
                <>
                  <span className="font-mono text-ink-600">
                    {item.qty} × {item.unit_price.toFixed(2)} = {item.line_total.toFixed(2)}
                  </span>
                  {canAdjust && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setEditingId(item.id)
                        setPriceText(String(item.unit_price))
                        setQtyText(String(item.qty))
                      }}
                    >
                      Edit
                    </Button>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
        <div className="mt-4 flex justify-end gap-4 border-t border-border pt-3 text-sm">
          <span className="text-ink-600">Subtotal: <b className="font-mono">{invoice.subtotal.toFixed(2)}</b></span>
          {invoice.tax_rate > 0 && (
            <span className="text-ink-600">
              VAT {invoice.tax_rate}%{invoice.vat_inclusive ? ' (incl.)' : ''}:{' '}
              <b className="font-mono">{invoice.tax_total.toFixed(2)}</b>
            </span>
          )}
          <span className="text-ink-600">Total: <b className="font-mono">{invoice.total.toFixed(2)}</b></span>
          <span className="text-ink-600">Patient due: <b className="font-mono">{invoice.patient_due.toFixed(2)}</b></span>
        </div>
      </div>
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
