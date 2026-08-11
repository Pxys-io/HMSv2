import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { get } from './api/client'
import { useAuthStore } from './auth/store'
import LoginPage from './auth/LoginPage'
import AppLayout from './components/layout/AppLayout'
import CommandPalette from './components/layout/CommandPalette'
import AuditPage from './features/audit/AuditPage'
import AdminUsersPage from './features/admin/AdminUsersPage'
import BoardPage from './features/board/BoardPage'
import CalendarPage from './features/calendar/CalendarPage'
import CashierPage from './features/cashier/CashierPage'
import ChatPage from './features/chat/ChatPage'
import ExamPage from './features/exam/ExamPage'
import PatientsPage from './features/patients/PatientsPage'
import RecallsPage from './features/recalls/RecallsPage'
import ReportsPage from './features/reports/ReportsPage'
import TodayPage from './features/today/TodayPage'

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
        const me = await get<{ id: number; email: string; full_name: string; role: string }>(
          '/api/auth/me',
        )
        useAuthStore.getState().setSession(
          {
            id: me.id,
            email: me.email,
            full_name: me.full_name,
            full_name_ar: null,
            phone: null,
            role: me.role as 'admin' | 'doctor' | 'secretary',
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
          <Route index element={<Navigate to="/board" replace />} />
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
          <Route path="patients" element={<PatientsPage />} />
          <Route path="patients/:profileId" element={<div />} />
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
            path="audit"
            element={
              <RequireRole roles={['admin']}>
                <AuditPage />
              </RequireRole>
            }
          />
          <Route
            path="admin/users"
            element={
              <RequireRole roles={['admin']}>
                <AdminUsersPage />
              </RequireRole>
            }
          />
        </Route>
      </Routes>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </>
  )
}
