import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from '../../api/client'
import { Button, Card, EmptyState, Modal, inputClass } from '../../components/ui'

type Role = {
  id: number
  name: string
  name_ar: string | null
  is_system: boolean
  is_active: boolean
  permissions: string[]
}

type PermissionGroup = {
  group: string
  permissions: { id: number; code: string; label: string; label_ar: string }[]
}

export function RolesTab() {
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editRole, setEditRole] = useState<Role | null>(null)

  const roles = useQuery({ queryKey: ['admin-roles'], queryFn: () => get<Role[]>('/api/roles') })
  const catalog = useQuery({
    queryKey: ['permission-catalog'],
    queryFn: () => get<{ groups: PermissionGroup[] }>('/api/permissions'),
  })
  const rows = roles.data ?? []

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Roles & permissions</h1>
        <div className="flex-1" />
        <Button onClick={() => setCreateOpen(true)}>+ Custom role</Button>
      </div>
      <Card className="mt-3">
        <div className="divide-y divide-border">
          {rows.map((r) => (
            <div key={r.id} className="flex items-center gap-4 p-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink-900">
                  {r.name}
                  {r.is_system && (
                    <span className="ms-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                      system
                    </span>
                  )}
                </p>
                <p className="text-xs text-ink-400">{r.permissions.length} permissions</p>
              </div>
              <Button size="sm" variant="secondary" onClick={() => setEditRole(r)}>
                Permissions
              </Button>
            </div>
          ))}
          {rows.length === 0 && <EmptyState message="No roles" />}
        </div>
      </Card>

      {createOpen && (
        <CreateRoleModal onClose={() => setCreateOpen(false)} onDone={() => queryClient.invalidateQueries()} />
      )}
      {editRole && (
        <RolePermissionsModal
          role={editRole}
          groups={catalog.data?.groups ?? []}
          onClose={() => setEditRole(null)}
          onDone={() => queryClient.invalidateQueries()}
        />
      )}
    </div>
  )
}

function CreateRoleModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState('')
  const [nameAr, setNameAr] = useState('')
  const [error, setError] = useState('')

  async function submit() {
    try {
      await post('/api/roles', { name, name_ar: nameAr || undefined })
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <Modal open onClose={onClose} title="New custom role">
      {error && <p className="mb-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
      <input className={inputClass} placeholder="Role name (e.g. cashier)" value={name} onChange={(e) => setName(e.target.value)} />
      <input className={inputClass + ' mt-2'} placeholder="Name (AR)" value={nameAr} onChange={(e) => setNameAr(e.target.value)} />
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button onClick={submit} disabled={name.length < 2}>
          Create
        </Button>
      </div>
    </Modal>
  )
}

function RolePermissionsModal({
  role,
  groups,
  onClose,
  onDone,
}: {
  role: Role
  groups: PermissionGroup[]
  onClose: () => void
  onDone: () => void
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set(role.permissions))
  const [error, setError] = useState('')

  function toggle(code: string) {
    const next = new Set(selected)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    setSelected(next)
  }

  async function save() {
    setError('')
    try {
      // map codes to ids from the catalog
      const idByCode = new Map<string, number>()
      for (const g of groups) for (const p of g.permissions) idByCode.set(p.code, p.id)
      const ids = [...selected].map((c) => idByCode.get(c)!).filter(Boolean)
      await put(`/api/roles/${role.id}/permissions`, { permission_ids: ids })
      onDone()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div
        className="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-e2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border p-4">
          <div>
            <h2 className="text-base font-bold text-ink-900">Permissions — {role.name}</h2>
            <p className="text-xs text-ink-400">
              {role.is_system ? 'System roles can be adjusted; names are fixed.' : 'Custom role'}
            </p>
          </div>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600" aria-label="Close">
            ✕
          </button>
        </div>
        {error && <p className="px-4 pt-2 text-sm text-red-600">{error}</p>}
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {groups.map((g) => (
            <div key={g.group}>
              <p className="mb-2 text-xs font-semibold uppercase text-ink-400">{g.group}</p>
              <div className="grid grid-cols-2 gap-1">
                {g.permissions.map((p) => (
                  <label key={p.code} className="flex cursor-pointer items-center gap-2 rounded p-1 text-sm hover:bg-slate-50">
                    <input type="checkbox" checked={selected.has(p.code)} onChange={() => toggle(p.code)} />
                    <span className="text-ink-700">{p.label}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="flex justify-end gap-2 border-t border-border p-3">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save}>Save permissions</Button>
        </div>
      </div>
    </div>
  )
}
