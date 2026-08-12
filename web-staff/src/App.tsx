import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { registerSW } from 'virtual:pwa-register'
import { OfflineBanner } from './components/pwa'
import { get } from './api/client'
import { useAuthStore } from './auth/store'
import LoginPage from './auth/LoginPage'
import AppLayout from './components/layout/AppLayout'
import CommandPalette from './components/layout/CommandPalette'
import AuditPage from './features/audit/AuditPage'
import AdminPage from './features/admin/AdminPage'
import SchedulePage from './features/schedule/SchedulePage'
import BoardPage from './features/board/BoardPage'
import CalendarPage from './features/calendar/CalendarPage'
import CashierPage from './features/cashier/CashierPage'
import ChatPage from './features/chat/ChatPage'
import ExamPage from './features/exam/ExamPage'
import PatientDetailPage from './features/patients/PatientDetailPage'
import PatientsPage from './features/patients/PatientsPage'
import RecallsPage from './features/recalls/RecallsPage'
import ReportsPage from './features/reports/ReportsPage'
import TodayPage from './features/today/TodayPage'

function HomeRedirect() {
  const role = useAuthStore((s) => s.user?.role)
  const to =
    role === 'doctor' ? '/today' : role === 'admin' ? '/reports/daily' : '/board'
  return <Navigate to={to} replace />
}

function RequireAuth({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const [checked, setChecked] = useState(!!user)

  useEffect(() => {
    if (user) {
      setChecked(true)
      return
    }
    ;(async () => {
      try {
        const me = await get<{
          id: number
          email: string
          full_name: string
          role: string
          permissions?: string[]
        }>('/api/auth/me')
        useAuthStore.getState().setSession(
          {
            id: me.id,
            email: me.email,
            full_name: me.full_name,
            full_name_ar: null,
            phone: null,
            role: me.role,
            permissions: me.permissions,
          },
          '',
        )
      } catch {
        navigate('/login', { replace: true })
      } finally {
        setChecked(true)
      }
    })()
  }, [user, navigate])

  if (!checked) return null
  return <>{user ? children : <Navigate to="/login" replace />}</>
}

function RequireRole({ roles, children }: { roles: string[]; children: React.ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (!user || !roles.includes(user.role)) return <Navigate to="/" replace />
  return <>{children}</>
}

export default function App() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [updateAvailable, setUpdateAvailable] = useState(false)

  useEffect(() => {
    registerSW({
      onNeedRefresh() {
        setUpdateAvailable(true)
      },
    })
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <OfflineBanner />
      <Toaster position="top-left" />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<HomeRedirect />} />
          <Route
            path="board"
            element={
              <RequireRole roles={['admin', 'secretary']}>
                <BoardPage />
              </RequireRole>
            }
          />
          <Route
            path="calendar"
            element={
              <RequireRole roles={['admin', 'secretary']}>
                <CalendarPage />
              </RequireRole>
            }
          />
          <Route
            path="today"
            element={
              <RequireRole roles={['doctor']}>
                <TodayPage />
              </RequireRole>
            }
          />
          <Route path="admin/users" element={<Navigate to="/admin" replace />} />
          <Route path="patients" element={<PatientsPage />} />
          <Route path="patients/:profileId" element={<PatientDetailPage />} />
          <Route path="patients/:profileId/exam" element={<ExamPage />} />
          <Route
            path="cashier"
            element={
              <RequireRole roles={['admin', 'secretary']}>
                <CashierPage />
              </RequireRole>
            }
          />
          <Route path="recalls" element={<RecallsPage />} />
          <Route
            path="chat"
            element={
              <RequireRole roles={['admin', 'secretary']}>
                <ChatPage />
              </RequireRole>
            }
          />
          <Route
            path="reports/daily"
            element={
              <RequireRole roles={['admin']}>
                <ReportsPage />
              </RequireRole>
            }
          />
          <Route
            path="schedule"
            element={
              <RequireRole roles={['doctor']}>
                <SchedulePage />
              </RequireRole>
            }
          />
          <Route
            path="audit"
            element={
              <RequireRole roles={['admin']}>
                <AuditPage />
              </RequireRole>
            }
          />
          <Route
            path="admin"
            element={
              <RequireRole roles={['admin']}>
                <AdminPage />
              </RequireRole>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      {updateAvailable && (
        <button
          onClick={() => window.location.reload()}
          className="fixed bottom-4 end-4 z-50 rounded-md bg-brand-600 px-3 py-2 text-sm font-semibold text-white shadow-e2"
        >
          New version available — refresh
        </button>
      )}
    </>
  )
}
