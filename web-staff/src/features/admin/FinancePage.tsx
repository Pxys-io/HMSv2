import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'

type Expense = {
  id: number
  category: string
  amount: number
  expense_date: string
  note: string | null
  paid_from: string
  created_by: number
  created_at: string | null
}

type Txn = {
  id: number
  kind: string
  amount: number
  note: string | null
  expense_id: number | null
  balance_after: number
  created_by: number
  created_at: string | null
}

type PettyCash = { balance: number; opening_balance: number; transactions: Txn[] }

type PnL = { month: string; revenue: number; refunds: number; expenses: number; net: number }

const CATEGORIES = ['office', 'medical', 'transport', 'staff', 'other']

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

export default function FinancePage() {
  const qc = useQueryClient()
  const [month, setMonth] = useState(todayStr().slice(0, 7))
  const [from, setFrom] = useState(todayStr())
  const [to, setTo] = useState(todayStr())
  const [cat, setCat] = useState('')
  const [busy, setBusy] = useState(false)

  const cash = useQuery({
    queryKey: ['petty-cash'],
    queryFn: () => get<PettyCash>('/api/petty-cash/balance'),
  })
  const expenses = useQuery({
    queryKey: ['expenses', from, to, cat],
    queryFn: () =>
      get<{ items: Expense[] }>(
        `/api/expenses?from=${from}&to=${to}${cat ? `&category=${cat}` : ''}`
      ),
  })
  const pnl = useQuery({
    queryKey: ['pnl', month],
    queryFn: () => get<PnL>(`/api/pnl?month=${month}`),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['petty-cash'] })
    qc.invalidateQueries({ queryKey: ['expenses'] })
    qc.invalidateQueries({ queryKey: ['pnl'] })
  }

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    try {
      await fn()
      refresh()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-ink-800">Finance — expenses, petty cash & P&L</h1>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="space-y-3 p-4">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-ink-600">Petty cash</h2>
            <div className="text-right">
              <div className="text-2xl font-bold text-brand-700">
                {cash.data ? cash.data.balance.toFixed(2) : '…'}
              </div>
              <div className="text-xs text-ink-400">opening {cash.data?.opening_balance.toFixed(2)}</div>
            </div>
          </div>
          <div className="flex gap-2">
            <input
              id="pc-in"
              type="number"
              min={0}
              placeholder="Amount"
              className={inputClass}
            />
            <Button
              disabled={busy}
              onClick={() => {
                const el = document.getElementById('pc-in') as HTMLInputElement
                const amount = Number(el.value)
                if (amount > 0)
                  run(() => post('/api/petty-cash/in', { amount, note: 'top up' }))
              }}
            >
              Top up
            </Button>
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                const el = document.getElementById('pc-in') as HTMLInputElement
                const amount = Number(el.value)
                if (amount > 0)
                  run(() => post('/api/petty-cash/out', { amount, note: 'withdrawal' }))
              }}
            >
              Withdraw
            </Button>
          </div>
          <div className="max-h-48 space-y-1 overflow-auto text-xs">
            {cash.data?.transactions.map((t) => (
              <div key={t.id} className="flex justify-between border-b border-border pb-1">
                <span className={t.kind === 'in' ? 'text-green-600' : 'text-red-600'}>
                  {t.kind === 'in' ? '+' : '−'} {t.amount.toFixed(2)} {t.note ?? ''}
                </span>
                <span className="text-ink-400">balance {t.balance_after.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </Card>

        <Card className="space-y-3 p-4">
          <h2 className="text-sm font-semibold text-ink-600">New expense</h2>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-ink-600">
              Category
              <select className={inputClass + ' mt-1'} id="ex-cat">
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs text-ink-600">
              Amount
              <input id="ex-amount" type="number" min={0} className={inputClass + ' mt-1'} />
            </label>
            <label className="text-xs text-ink-600">
              Date
              <input id="ex-date" type="date" defaultValue={todayStr()} className={inputClass + ' mt-1'} />
            </label>
            <label className="text-xs text-ink-600">
              Paid from
              <select id="ex-source" className={inputClass + ' mt-1'}>
                <option value="petty_cash">Petty cash</option>
                <option value="bank">Bank</option>
              </select>
            </label>
          </div>
          <input id="ex-note" placeholder="Note" className={inputClass} />
          <Button
            disabled={busy}
            onClick={() => {
              const amount = Number((document.getElementById('ex-amount') as HTMLInputElement).value)
              const expense_date = (document.getElementById('ex-date') as HTMLInputElement).value
              if (amount > 0 && expense_date)
                run(() =>
                  post('/api/expenses', {
                    category: (document.getElementById('ex-cat') as HTMLSelectElement).value,
                    amount,
                    expense_date,
                    note: (document.getElementById('ex-note') as HTMLInputElement).value || null,
                    paid_from: (document.getElementById('ex-source') as HTMLSelectElement).value,
                  })
                )
            }}
          >
            Record expense
          </Button>
        </Card>
      </div>

      <Card className="space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-ink-600">Expenses</h2>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className={inputClass + ' w-40'} />
          <span className="text-xs text-ink-400">→</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className={inputClass + ' w-40'} />
          <select value={cat} onChange={(e) => setCat(e.target.value)} className={inputClass + ' w-40'}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        {expenses.data && expenses.data.items.length === 0 ? (
          <EmptyState message="No expenses in this range" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-ink-500">
                <th className="py-1">Date</th>
                <th>Category</th>
                <th>Note</th>
                <th>Source</th>
                <th className="text-right">Amount</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {expenses.data?.items.map((e) => (
                <tr key={e.id} className="border-b border-border">
                  <td className="py-1">{e.expense_date}</td>
                  <td>{e.category}</td>
                  <td className="text-ink-500">{e.note ?? ''}</td>
                  <td>{e.paid_from === 'petty_cash' ? 'Petty cash' : 'Bank'}</td>
                  <td className="text-right font-mono">{e.amount.toFixed(2)}</td>
                  <td className="text-right">
                    <button
                      className="text-xs text-red-600 underline"
                      onClick={() => run(() => del(`/api/expenses/${e.id}`))}
                    >
                      delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink-600">P&L</h2>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className={inputClass + ' w-44'} />
        </div>
        {pnl.data && (
          <div className="grid grid-cols-4 gap-2 text-center">
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-ink-500">Revenue</div>
              <div className="font-bold text-green-600">{pnl.data.revenue.toFixed(2)}</div>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-ink-500">Refunds</div>
              <div className="font-bold text-amber-600">{pnl.data.refunds.toFixed(2)}</div>
            </div>
            <div className="rounded-lg bg-slate-50 p-3">
              <div className="text-xs text-ink-500">Expenses</div>
              <div className="font-bold text-red-600">{pnl.data.expenses.toFixed(2)}</div>
            </div>
            <div className="rounded-lg bg-brand-50 p-3">
              <div className="text-xs text-ink-500">Net</div>
              <div className="font-bold text-brand-700">{pnl.data.net.toFixed(2)}</div>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}
