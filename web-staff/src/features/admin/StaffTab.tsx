import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, patch, post } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type StaffRow = {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}

export function StaffTab() {
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<StaffRow | null>(null)
  const queryClient = useQueryClient()

  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => get<{ items: StaffRow[] }>('/api/users?page_size=100'),
    select: (d) => d.items,
  })
  const rows = users.data ?? []

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Staff</h1>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Staff user</Button>
      </div>
      <Card className="mt-3">
        <div className="divide-y divide-border">
          {rows.map((u) => (
            <div key={u.id} className="flex items-center gap-4 p-3">
              <span className="flex-1 font-medium text-ink-900">{u.full_name}</span>
              <span className="text-sm text-ink-600">{u.email}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">
                {u.role}
              </span>
              <span className={`text-xs ${u.is_active ? 'text-success' : 'text-danger'}`}>
                {u.is_active ? 'active' : 'inactive'}
              </span>
              <Button size="sm" variant="secondary" onClick={() => setEditTarget(u)}>
                Edit
              </Button>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No staff users" />}
        </div>
      </Card>

      {createOpen && (
        <StaffModal
          onClose={() => setCreateOpen(false)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
      {editTarget && (
        <StaffModal
          target={editTarget}
          onClose={() => setEditTarget(null)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
    </div>
  )
}

function StaffModal({
  target,
  onClose,
  onDone,
}: {
  target?: StaffRow
  onClose: () => void
  onDone: () => void
}) {
  const [email, setEmail] = useState(target?.email ?? '')
  const [password, setPassword] = useState('')
  const [name, setName] = useState(target?.full_name ?? '')
  const [role, setRole] = useState(target?.role ?? 'secretary')
  const [isActive, setIsActive] = useState(target?.is_active ?? true)
  const [error, setError] = useState('')

  async function submit() {
    try {
      if (target) {
        await patch(`/api/users/${target.id}`, {
          full_name: name,
          email,
          role,
          is_active: isActive,
          password: password || undefined,
        })
      } else {
        await post('/api/users', { email, password, full_name: name, role })
      }
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title={target ? 'Edit staff user' : 'New staff user'}>
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      {!target && (
        <input
          className={inputClass + ' mt-2'}
          type="password"
          placeholder="Password (min 8)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      )}
      {target && (
        <input
          className={inputClass + ' mt-2'}
          type="password"
          placeholder="Reset password (optional)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      )}
      <select className={inputClass + ' mt-2'} value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="secretary">Secretary</option>
        <option value="admin">Admin</option>
        <option value="doctor">Doctor (creates doctor profile)</option>
      </select>
      {target && (
        <label className="mt-2 flex items-center gap-2 text-sm text-ink-600">
          <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
          Active
        </label>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !email || (!target && password.length < 8)}>
          {target ? 'Save' : 'Create'}
        </Button>
      </div>
    </Modal>
  )
}
