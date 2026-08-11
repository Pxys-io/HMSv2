import { useEffect, useState } from 'react'
import { Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { get } from './api/client'
import { useAuthStore } from './auth/store'
import PublicLayout from './layouts/PublicLayout'
import LandingPage from './pages/LandingPage'
import BookingPage from './pages/BookingPage'
import LoginPage, { RegisterPage } from './pages/AuthPages'
import AccountPage from './pages/AccountPage'
import ChatWidget from './components/ChatWidget'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const patient = useAuthStore((s) => s.patient)
  const navigate = useNavigate()
  const [checked, setChecked] = useState(!!patient)

  useEffect(() => {
    if (patient) {
      setChecked(true)
      return
    }
    ;(async () => {
      try {
        const me = await get<{ id: number; full_name: string; email: string | null; phone: string | null }>(
          '/api/public/auth/me',
        )
        useAuthStore
          .getState()
          .setSession({ id: me.id, full_name: me.full_name, email: me.email, phone: me.phone, locale: 'ar' }, '')
      } catch {
        navigate('/login', { replace: true })
      } finally {
        setChecked(true)
      }
    })()
  }, [patient, navigate])

  if (!checked) return null
  return <>{patient ? children : null}</>
}

export default function App() {
  const location = useLocation()
  const isBookRoute = location.pathname.startsWith('/book')

  return (
    <>
      <Routes>
        <Route path="/" element={<PublicLayout />}>
          <Route index element={<LandingPage />} />
          <Route path="book" element={<BookingPage />} />
          <Route path="login" element={<LoginPage />} />
          <Route path="register" element={<RegisterPage />} />
          <Route
            path="account"
            element={
              <RequireAuth>
                <AccountPage />
              </RequireAuth>
            }
          />
        </Route>
      </Routes>
      {!isBookRoute && <ChatWidget />}
    </>
  )
}
