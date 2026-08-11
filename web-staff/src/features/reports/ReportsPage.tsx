import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from '../../api/client'
import { Card, inputClass } from '../../components/ui'

function todayISO() {
  return new Date().toISOString().slice(0, 10)
}

export default function ReportsPage() {
  const [from, setFrom] = useState(todayISO())
  const [to, setTo] = useState(todayISO())

  const revenue = useQuery({
    queryKey: ['report-revenue', from, to],
    queryFn: () => get<{ rows: { date: string; method: string; net: number }[] }>(
      `/api/reports/daily-revenue?from=${from}&to=${to}`,
    ),
  })
  const share = useQuery({
    queryKey: ['report-share', from, to],
    queryFn: () =>
      get<{ rows: { doctor_name: string | null; visits: number; invoiced: number; collected: number }[] }>(
        `/api/reports/doctor-share?from=${from}&to=${to}`,
      ),
  })
  const syndicates = useQuery({
    queryKey: ['report-syndicates'],
    queryFn: () => get<{ rows: { name: string; accrued_balance: number; invoices: number }[] }>(
      '/api/reports/syndicate-balances',
    ),
  })

  const total = revenue.data?.rows.reduce((sum, r) => sum + r.net, 0) ?? 0

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Reports</h1>
        <input type="date" className={inputClass + ' w-40'} value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className={inputClass + ' w-40'} value={to} onChange={(e) => setTo(e.target.value)} />
        <a
          href={`/api/reports/daily-revenue?from=${from}&to=${to}&format=csv`}
          className="text-sm text-brand-700 hover:underline"
        >
          Export CSV
        </a>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Daily revenue</h2>
          <p className="mt-1 text-2xl font-bold text-ink-900">{total.toFixed(2)} EGP</p>
          <div className="mt-3 space-y-1">
            {revenue.data?.rows.map((r) => (
              <div key={r.date + r.method} className="flex justify-between text-sm">
                <span className="text-ink-600">
                  {r.date} · {r.method}
                </span>
                <span className="font-mono">{r.net.toFixed(2)}</span>
              </div>
            ))}
            {revenue.data?.rows.length === 0 && (
              <p className="text-sm text-ink-400">No payments in range</p>
            )}
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Doctor share</h2>
          <div className="mt-3 space-y-3">
            {share.data?.rows.map((r) => (
              <div key={r.doctor_name ?? 'x'}>
                <p className="text-sm font-medium text-ink-900">{r.doctor_name ?? '—'}</p>
                <p className="text-xs text-ink-400">
                  {r.visits} visits · invoiced {r.invoiced.toFixed(2)} · collected {r.collected.toFixed(2)}
                </p>
              </div>
            ))}
            {share.data?.rows.length === 0 && (
              <p className="text-sm text-ink-400">No visits in range</p>
            )}
          </div>
        </Card>

        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink-600">Syndicate balances</h2>
          <div className="mt-3 space-y-3">
            {syndicates.data?.rows.map((s) => (
              <div key={s.name} className="flex justify-between text-sm">
                <span className="text-ink-900">{s.name}</span>
                <span className="font-mono">{s.accrued_balance.toFixed(2)} EGP</span>
              </div>
            ))}
            {syndicates.data?.rows.length === 0 && (
              <p className="text-sm text-ink-400">No syndicates configured</p>
            )}
          </div>
        </Card>
      </div>
    </div>
  )
}
