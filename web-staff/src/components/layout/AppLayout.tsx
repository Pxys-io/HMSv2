import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { get } from '../../api/client'
import { setLocale } from '../../i18n'
import { useAuthStore } from '../../auth/store'

export type NotificationItem = {
  id: number
  type: string
  title: string
  body: string | null
  link: string | null
  read: boolean
  created_at: string | null
}

const NAV: { to: string; key: string; perm: string; icon: string }[] = [
  { to: '/board', key: 'board', perm: 'queue.view', icon: '▦' },
  { to: '/calendar', key: 'calendar', perm: 'appointment.view', icon: '📅' },
  { to: '/today', key: 'today', perm: 'queue.view', icon: '🩺' },
  { to: '/schedule', key: 'schedule', perm: 'queue.view', icon: '📆' },
  { to: '/patients', key: 'patients', perm: 'patient.view', icon: '👤' },
  { to: '/cashier', key: 'cashier', perm: 'billing.view', icon: '💵' },
  { to: '/finance', key: 'finance', perm: 'billing.expense', icon: '🧾' },
  { to: '/erp', key: 'erp', perm: 'ops.task', icon: '🗂️' },
  { to: '/recalls', key: 'recalls', perm: 'patient.view', icon: '⏰' },
  { to: '/chat', key: 'chat', perm: 'chat.view', icon: '💬' },
  { to: '/reports/daily', key: 'reports', perm: 'report.all', icon: '📊' },
  { to: '/audit', key: 'audit', perm: 'admin.audit', icon: '🔒' },
  { to: '/admin', key: 'admin', perm: 'admin.roles', icon: '⚙️' },
]

function useNotifications() {
  const [items, setItems] = useState<NotificationItem[]>([])
  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const rows = await get<NotificationItem[]>('/api/notifications?unread_only=true')
        if (active) setItems(rows)
      } catch {
        /* not authenticated yet */
      }
    }
    load()
    const timer = setInterval(load, 15000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])
  return items
}

export default function AppLayout() {
  const { t, i18n } = useTranslation()
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const notifications = useNotifications()
  const [openTasks, setOpenTasks] = useState(0)
  useEffect(() => {
    let active = true
    const load = async () => {
      try {
        const rows = await get<{ items: unknown[] }>('/api/tasks?status=open')
        if (active) setOpenTasks(rows.items.length)
      } catch {
        /* not authenticated yet */
      }
    }
    load()
    const timer = setInterval(load, 60000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  const nav = NAV.filter(
    (item) => user && (user.role === 'admin' || user.permissions?.includes(item.perm)),
  )

  return (
    <div className="flex h-screen bg-bg">
      <aside
        className={`flex shrink-0 flex-col border-e border-border bg-surface transition-all ${
          collapsed ? 'w-14' : 'w-56'
        }`}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span className="text-lg">🏥</span>
          {!collapsed && <span className="font-bold text-ink-900">HMSv2</span>}
        </div>
        <nav className="flex-1 overflow-y-auto p-2">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `mb-1 flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                  isActive
                    ? 'bg-brand-50 font-semibold text-brand-700'
                    : 'text-ink-600 hover:bg-slate-100'
                }`
              }
            >
              <span className="w-5 text-center">{item.icon}</span>
              {!collapsed && t(`nav.${item.key}`)}
              {item.key === 'erp' && openTasks > 0 && (
                <span className="ml-auto rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                  {openTasks}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border p-3">
          {user && (
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-50 text-sm font-bold text-brand-700">
                {user.full_name[0]}
              </div>
              {!collapsed && (
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink-900">{user.full_name}</p>
                  <p className="text-xs capitalize text-ink-400">{user.role}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-4 border-b border-border bg-surface px-4">
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="rounded-md p-1.5 text-ink-600 hover:bg-slate-100"
            aria-label="Toggle sidebar"
          >
            {collapsed ? '▸' : '◂'}
          </button>
          <div className="flex-1 text-sm text-ink-400">{t('common.quickSearch')}</div>
          <button
            onClick={() => navigate('/chat')}
            className="relative rounded-md p-1.5 text-ink-600 hover:bg-slate-100"
            aria-label="Notifications"
          >
            🔔
            {notifications.length > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
                {notifications.length}
              </span>
            )}
          </button>
          <button
            onClick={() => void setLocale(i18n.language === 'ar' ? 'en' : 'ar')}
            className="rounded-md px-2 py-1 text-sm text-ink-600 hover:bg-slate-100"
          >
            {i18n.language === 'ar' ? 'EN' : 'عربي'}
          </button>
          <Link
            to="/login"
            onClick={() => useAuthStore.getState().logout()}
            className="rounded-md px-2 py-1 text-sm text-ink-600 hover:bg-slate-100"
          >
            {t('common.signOut')}
          </Link>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto p-4">
          <Outlet key={location.pathname} />
        </main>
      </div>
    </div>
  )
}
