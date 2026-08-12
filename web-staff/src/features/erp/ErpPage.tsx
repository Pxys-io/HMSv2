import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, patch, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'

const TABS = ['tasks', 'referrals', 'lab-orders', 'duplicates', 'inventory', 'hr'] as const

type Task = {
  id: number
  title: string
  notes: string | null
  due_at: string | null
  assigned_to: number | null
  priority: string
  status: string
  is_mine: boolean
}

type Referral = {
  id: number
  patient_profile_id: number
  to_text: string
  place: string | null
  notes: string | null
  referral_date: string
  status: string
  outcome_text: string | null
  outcome_seen_at: string | null
}

type LabOrder = {
  id: number
  patient_profile_id: number
  lab_name: string
  tests: string[]
  order_date: string
  status: string
  notes: string | null
  results_attachment_id: number | null
}

type DupGroup = {
  id: number
  primary_profile_id: number
  profile_ids: number[]
  match_reason: string
  status: string
  profiles: { id: number; code: string; full_name: string; phone: string }[]
}

type Product = {
  id: number
  name: string
  strength: string | null
  unit: string
  price: number
  cost: number
  reorder_level: number
  expiry_date: string | null
  stock: number
}

export default function ErpPage() {
  const { t } = useTranslation()
  const [tab, setTab] = useState('tasks')

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
        {TABS.map((id) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize ${
              tab === id ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-slate-50'
            }`}
          >
            {t(`erp.tabs.${id}`)}
          </button>
        ))}
      </div>
      {tab === 'tasks' && <TasksTab />}
      {tab === 'referrals' && <ReferralsTab />}
      {tab === 'lab-orders' && <LabOrdersTab />}
      {tab === 'duplicates' && <DuplicatesTab />}
      {tab === 'inventory' && <InventoryTab />}
      {tab === 'hr' && <HrTab />}
    </div>
  )
}

function TasksTab() {
  const qc = useQueryClient()
  const tasks = useQuery({
    queryKey: ['tasks'],
    queryFn: () => get<{ items: Task[] }>('/api/tasks'),
  })
  return (
    <Card className="space-y-3 p-4">
      <h2 className="text-sm font-semibold text-ink-600">Tasks</h2>
      <ErrorBanner error={tasks.error} />
      <div className="flex gap-2">
        <input id="task-title" placeholder="New task title" className={inputClass} />
        <input id="task-due" type="date" className={inputClass + ' w-40'} />
        <select id="task-priority" className={inputClass + ' w-32'}>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <Button
          onClick={async () => {
            const title = (document.getElementById('task-title') as HTMLInputElement).value
            const due_at = (document.getElementById('task-due') as HTMLInputElement).value
            const priority = (document.getElementById('task-priority') as HTMLSelectElement).value
            if (!title.trim()) return
            await post('/api/tasks', { title, due_at: due_at || null, priority })
            qc.invalidateQueries({ queryKey: ['tasks'] })
          }}
        >
          Add
        </Button>
      </div>
      {tasks.data && tasks.data.items.length === 0 ? (
        <EmptyState message="No tasks" />
      ) : (
        <div className="space-y-2">
          {tasks.data?.items.map((t) => (
            <div key={t.id} className="flex items-center justify-between rounded-lg border border-border p-2">
              <div>
                <span className="text-sm font-medium">{t.title}</span>{' '}
                <span className="text-xs text-ink-400">
                  {t.priority} {t.due_at ? `· due ${t.due_at}` : ''}
                </span>
              </div>
              <div className="flex gap-2">
                {t.status !== 'done' && (
                  <button
                    className="text-xs text-brand-700 underline"
                    onClick={async () => {
                      await patch(`/api/tasks/${t.id}`, { status: 'done' })
                      qc.invalidateQueries({ queryKey: ['tasks'] })
                    }}
                  >
                    done
                  </button>
                )}
                <button
                  className="text-xs text-red-600 underline"
                  onClick={async () => {
                    await del(`/api/tasks/${t.id}`)
                    qc.invalidateQueries({ queryKey: ['tasks'] })
                  }}
                >
                  delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function ReferralsTab() {
  const qc = useQueryClient()
  const referrals = useQuery({
    queryKey: ['referrals'],
    queryFn: () => get<{ items: Referral[] }>('/api/referrals'),
  })
  return (
    <Card className="space-y-3 p-4">
      <h2 className="text-sm font-semibold text-ink-600">Referrals</h2>
      <ErrorBanner error={referrals.error} />
      {referrals.data && referrals.data.items.length === 0 ? (
        <EmptyState message="No referrals" />
      ) : (
        <div className="space-y-2">
          {referrals.data?.items.map((r) => (
            <div key={r.id} className="rounded-lg border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">
                  Patient #{r.patient_profile_id} → {r.to_text}
                </span>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{r.status}</span>
              </div>
              {r.place && <div className="text-xs text-ink-400">{r.place}</div>}
              {r.status !== 'seen' && r.status !== 'closed' && (
                <div className="mt-2 flex gap-2">
                  <input
                    id={`ref-outcome-${r.id}`}
                    placeholder="Outcome"
                    className={inputClass + ' text-xs'}
                  />
                  <Button
                    variant="secondary"
                    className="text-xs"
                    onClick={async () => {
                      const outcome = (
                        document.getElementById(`ref-outcome-${r.id}`) as HTMLInputElement
                      ).value
                      await patch(`/api/referrals/${r.id}`, {
                        outcome,
                        outcome_seen_at: new Date().toISOString().slice(0, 10),
                      })
                      qc.invalidateQueries({ queryKey: ['referrals'] })
                    }}
                  >
                    Record outcome
                  </Button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function LabOrdersTab() {
  const qc = useQueryClient()
  const orders = useQuery({
    queryKey: ['lab-orders'],
    queryFn: () => get<{ items: LabOrder[] }>('/api/lab-orders'),
  })
  return (
    <Card className="space-y-3 p-4">
      <h2 className="text-sm font-semibold text-ink-600">Lab orders</h2>
      <ErrorBanner error={orders.error} />
      {orders.data && orders.data.items.length === 0 ? (
        <EmptyState message="No lab orders" />
      ) : (
        <div className="space-y-2">
          {orders.data?.items.map((o) => (
            <div key={o.id} className="rounded-lg border border-border p-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-medium">
                  {o.lab_name} · {o.tests.join(', ')}
                </span>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{o.status}</span>
              </div>
              <div className="mt-2 flex gap-2">
                <select
                  id={`lab-status-${o.id}`}
                  className={inputClass + ' w-44 text-xs'}
                  defaultValue={o.status}
                >
                  <option value="pending">pending</option>
                  <option value="received">received</option>
                  <option value="results_attached">results attached</option>
                  <option value="done">done</option>
                </select>
                <Button
                  variant="secondary"
                  className="text-xs"
                  onClick={async () => {
                    const status = (
                      document.getElementById(`lab-status-${o.id}`) as HTMLSelectElement
                    ).value
                    await patch(`/api/lab-orders/${o.id}`, { status })
                    qc.invalidateQueries({ queryKey: ['lab-orders'] })
                  }}
                >
                  Update
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function DuplicatesTab() {
  const qc = useQueryClient()
  const groups = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => get<{ items: DupGroup[] }>('/api/duplicates'),
  })
  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink-600">Duplicate patients</h2>
      <ErrorBanner error={groups.error} />
        <Button
          variant="secondary"
          onClick={async () => {
            await post('/api/duplicates/refresh', {})
            qc.invalidateQueries({ queryKey: ['duplicates'] })
          }}
        >
          Re-scan
        </Button>
      </div>
      {groups.data && groups.data.items.length === 0 ? (
        <EmptyState message="No open duplicate groups" />
      ) : (
        <div className="space-y-2">
          {groups.data?.items.map((g) => (
            <div key={g.id} className="rounded-lg border border-border p-2 text-sm">
              <div className="text-xs text-ink-400">{g.match_reason}</div>
              {g.profiles.map((p) => (
                <div key={p.id} className="flex justify-between border-b border-border py-1">
                  <span>
                    {p.full_name} <span className="font-mono text-xs text-ink-400">{p.code}</span>
                  </span>
                  <span className="text-xs text-ink-400">{p.phone}</span>
                </div>
              ))}
              <div className="mt-2 flex gap-2">
                <Button
                  className="text-xs"
                  onClick={async () => {
                    await post(`/api/duplicates/${g.id}/accept`, {})
                    qc.invalidateQueries({ queryKey: ['duplicates'] })
                  }}
                >
                  Merge
                </Button>
                <Button
                  variant="secondary"
                  className="text-xs"
                  onClick={async () => {
                    await post(`/api/duplicates/${g.id}/reject`, {})
                    qc.invalidateQueries({ queryKey: ['duplicates'] })
                  }}
                >
                  Not duplicates
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function InventoryTab() {
  const qc = useQueryClient()
  const products = useQuery({
    queryKey: ['inventory'],
    queryFn: () => get<{ items: Product[] }>('/api/inventory/products'),
  })
  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ink-600">Products</h2>
      <ErrorBanner error={products.error} />
        <input id="inv-name" placeholder="Name" className={inputClass + ' w-44'} />
        <input id="inv-stock" type="number" min={0} placeholder="Opening" className={inputClass + ' w-28'} />
        <input id="inv-price" type="number" min={0} placeholder="Price" className={inputClass + ' w-24'} />
        <input id="inv-cost" type="number" min={0} placeholder="Cost" className={inputClass + ' w-24'} />
        <Button
          onClick={async () => {
            const name = (document.getElementById('inv-name') as HTMLInputElement).value
            if (!name.trim()) return
            await post('/api/inventory/products', {
              name,
              opening_stock: Number((document.getElementById('inv-stock') as HTMLInputElement).value || 0),
              price: Number((document.getElementById('inv-price') as HTMLInputElement).value || 0),
              cost: Number((document.getElementById('inv-cost') as HTMLInputElement).value || 0),
            })
            qc.invalidateQueries({ queryKey: ['inventory'] })
          }}
        >
          Add product
        </Button>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-ink-500">
            <th className="py-1">Product</th>
            <th>Cost</th>
            <th>Price</th>
            <th>Stock</th>
            <th>Low?</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {products.data?.items.map((p) => (
            <tr key={p.id} className="border-b border-border">
              <td className="py-1">
                {p.name} {p.strength ? <span className="text-xs text-ink-400">{p.strength}</span> : null}
              </td>
              <td className="font-mono">{p.cost.toFixed(2)}</td>
              <td className="font-mono">{p.price.toFixed(2)}</td>
              <td className="font-mono">{p.stock.toFixed(2)}</td>
              <td>{p.stock <= p.reorder_level ? <span className="text-red-600">⚠</span> : '—'}</td>
              <td className="text-right">
                <input
                  id={`inv-add-${p.id}`}
                  type="number"
                  min={0}
                  placeholder="+qty"
                  className={inputClass + ' w-20 text-xs'}
                />
                <button
                  className="ml-1 text-xs text-brand-700 underline"
                  onClick={async () => {
                    const qty = Number(
                      (document.getElementById(`inv-add-${p.id}`) as HTMLInputElement).value || 0
                    )
                    if (qty > 0) {
                      await post(`/api/inventory/products/${p.id}/stock`, { kind: 'in', qty })
                      qc.invalidateQueries({ queryKey: ['inventory'] })
                    }
                  }}
                >
                  stock in
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

function HrTab() {
  const qc = useQueryClient()
  const leaves = useQuery({
    queryKey: ['hr-leaves'],
    queryFn: () => get<{ items: { id: number; staff_user_id: number; leave_type: string; from_date: string; to_date: string; days: number; status: string }[] }>('/api/hr/leaves'),
  })
  const balances = useQuery({
    queryKey: ['hr-balances'],
    queryFn: () => get<{ year: number; balances: Record<string, number> }>('/api/hr/leave-balances'),
  })
  const month = new Date().toISOString().slice(0, 7)
  const payroll = useQuery({
    queryKey: ['hr-payroll', month],
    queryFn: () => get<{ month: string; status: string; items: { staff_user_id: number; gross: number; tax: number; net: number }[] }>(`/api/hr/payroll?month=${month}`),
    retry: false,
  })
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="space-y-3 p-4">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-ink-600">Leaves</h2>
          <input id="leave-from" type="date" className={inputClass + ' w-36'} />
          <input id="leave-to" type="date" className={inputClass + ' w-36'} />
          <Button
            onClick={async () => {
              await post('/api/hr/leaves', {
                leave_type: 'annual',
                from_date: (document.getElementById('leave-from') as HTMLInputElement).value,
                to_date: (document.getElementById('leave-to') as HTMLInputElement).value,
              })
              qc.invalidateQueries({ queryKey: ['hr-leaves'] })
              qc.invalidateQueries({ queryKey: ['hr-balances'] })
            }}
          >
            Apply
          </Button>
        </div>
        <div className="text-xs text-ink-500">
          Year {balances.data?.year}:{' '}
          {Object.entries(balances.data?.balances ?? {}).map(([k, v]) => (
            <span key={k} className="mr-2">
              {k}: {v}d
            </span>
          ))}
        </div>
        {leaves.data?.items.map((l) => (
          <div key={l.id} className="flex items-center justify-between rounded-lg border border-border p-2 text-sm">
            <span>
              {l.leave_type} · {l.from_date} → {l.to_date} ({l.days}d)
            </span>
            <div className="flex gap-2">
              <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">{l.status}</span>
              {l.status === 'pending' && (
                <>
                  <button
                    className="text-xs text-green-700 underline"
                    onClick={async () => {
                      await patch(`/api/hr/leaves/${l.id}`, { status: 'approved' })
                      qc.invalidateQueries({ queryKey: ['hr-leaves'] })
                      qc.invalidateQueries({ queryKey: ['hr-balances'] })
                    }}
                  >
                    approve
                  </button>
                  <button
                    className="text-xs text-red-600 underline"
                    onClick={async () => {
                      await patch(`/api/hr/leaves/${l.id}`, { status: 'rejected' })
                      qc.invalidateQueries({ queryKey: ['hr-leaves'] })
                    }}
                  >
                    reject
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-600">Payroll {month}</h2>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={async () => {
                await post('/api/hr/payroll/run', { month })
                qc.invalidateQueries({ queryKey: ['hr-payroll'] })
              }}
            >
              Generate
            </Button>
            <Button
              onClick={async () => {
                await post('/api/hr/attendance/clock-in', {})
                qc.invalidateQueries({ queryKey: ['hr-attendance'] })
              }}
            >
              Clock in
            </Button>
            <Button
              variant="secondary"
              onClick={async () => {
                await post('/api/hr/attendance/clock-out', {})
                qc.invalidateQueries({ queryKey: ['hr-attendance'] })
              }}
            >
              Clock out
            </Button>
          </div>
        </div>
        {payroll.data && payroll.data.items.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-ink-500">
                <th className="py-1">Staff</th>
                <th>Gross</th>
                <th>Tax</th>
                <th>Net</th>
              </tr>
            </thead>
            <tbody>
              {payroll.data.items.map((i) => (
                <tr key={i.staff_user_id} className="border-b border-border">
                  <td className="py-1">#{i.staff_user_id}</td>
                  <td className="font-mono">{i.gross.toFixed(2)}</td>
                  <td className="font-mono">{i.tax.toFixed(2)}</td>
                  <td className="font-mono font-semibold">{i.net.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  )
}

function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null
  const message =
    error instanceof Error ? error.message : 'Something went wrong'
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
      Failed to load: {message}
    </div>
  )
}
