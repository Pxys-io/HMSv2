import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type StaffRow = {
  id: number
  email: string
  full_name: string
  role: string
  is_active: boolean
}

export default function AdminUsersPage() {
  const [createOpen, setCreateOpen] = useState(false)
  const queryClient = useQueryClient()

  const users = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => get<{ items: StaffRow[] }>('/api/users?page_size=100'),
    select: (d) => d.items,
  })

  const rows = users.data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Admin — staff</h1>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Staff user</Button>
      </div>
      <Card>
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
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No staff users" />}
        </div>
      </Card>

      {createOpen && <CreateUserModal onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />}
    </div>
  )
}

function CreateUserModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('secretary')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post('/api/users', { email, password, full_name: name, role }, crypto.randomUUID())
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New staff user">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className={inputClass + ' mt-2'} type="password" placeholder="Password (min 8)" value={password} onChange={(e) => setPassword(e.target.value)} />
      <select className={inputClass + ' mt-2'} value={role} onChange={(e) => setRole(e.target.value)}>
        <option value="secretary">Secretary</option>
        <option value="admin">Admin</option>
      </select>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={!name || !email || password.length < 8}>
          Create
        </Button>
      </div>
    </Modal>
  )
}
