import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { armAutoRefresh, post } from '../api/client'
import { useTranslation } from 'react-i18next'
import { useAuthStore } from './store'

export default function LoginPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const setSession = useAuthStore((s) => s.setSession)

  const homeFor = (role: string) =>
    role === 'doctor' ? '/today' : role === 'admin' ? '/reports/daily' : '/board'

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await post<{ access_token: string; user: { role: string; id: number; email: string; full_name: string } }>(
        '/api/auth/login',
        { email, password },
      )
      const user = {
        id: data.user.id,
        email: data.user.email,
        full_name: data.user.full_name,
        full_name_ar: null,
        phone: null,
        role: data.user.role as 'admin' | 'doctor' | 'secretary',
      }
      setSession(user, data.access_token)
      armAutoRefresh(data.access_token)
      navigate(homeFor(user.role), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-border bg-surface p-8 shadow-sm"
      >
        <h1 className="text-xl font-bold text-ink-900">{t('login.title')}</h1>
        <p className="mt-1 text-sm text-ink-600">{t('login.subtitle')}</p>
        {error && <p className="mt-4 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <label className="mt-5 block text-sm font-medium text-ink-600">{t('login.email')}</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-2 focus:outline-brand-600"
        />
        <label className="mt-4 block text-sm font-medium text-ink-600">{t('login.password')}</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          className="mt-1 w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-2 focus:outline-brand-600"
        />
        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full rounded-md bg-brand-600 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {loading ? t('common.loading') : t('common.signIn')}
        </button>
      </form>
    </div>
  )
}
