import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { armAutoRefresh, post } from '../api/client'
import { useAuthStore } from '../auth/store'

function useLoginForm() {
  const [emailOrPhone, setEmailOrPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const data = await post<{ access_token: string; user: { id: number; full_name: string; email: string | null; phone: string | null } }>(
        '/api/public/auth/login',
        { email_or_phone: emailOrPhone, password },
      )
      useAuthStore
        .getState()
        .setSession(
          { id: data.user.id, full_name: data.user.full_name, email: data.user.email, phone: data.user.phone, locale: 'ar' },
          data.access_token,
        )
      armAutoRefresh(data.access_token)
      navigate('/account')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    }
  }
  return { emailOrPhone, setEmailOrPhone, password, setPassword, error, submit }
}

export default function LoginPage() {
  const form = useLoginForm()
  return (
    <AuthShell title="Sign in" submit={form.submit} error={form.error}>
      <input
        className="w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Email or phone"
        value={form.emailOrPhone}
        onChange={(e) => form.setEmailOrPhone(e.target.value)}
        required
      />
      <input
        type="password"
        className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Password"
        value={form.password}
        onChange={(e) => form.setPassword(e.target.value)}
        required
      />
      <button
        type="submit"
        className="mt-5 w-full rounded-md bg-brand-600 py-2 text-sm font-semibold text-white hover:bg-brand-700"
      >
        Sign in
      </button>
      <p className="mt-4 text-center text-sm text-ink-600">
        New here?{' '}
        <Link to="/register" className="font-semibold text-brand-700">
          Create an account
        </Link>
      </p>
    </AuthShell>
  )
}

export function RegisterPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    try {
      const data = await post<{ access_token: string; user: { id: number; full_name: string } }>(
        '/api/public/auth/register',
        { full_name: fullName, email: email || undefined, phone: phone || undefined, password },
      )
      useAuthStore
        .getState()
        .setSession({ id: data.user.id, full_name: data.user.full_name, email: email || null, phone: phone || null, locale: 'ar' }, data.access_token)
      armAutoRefresh(data.access_token)
      navigate('/account')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    }
  }

  return (
    <AuthShell title="Create account" submit={submit} error={error}>
      <input
        className="w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        required
      />
      <input
        className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Email (optional)"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Phone (optional)"
        value={phone}
        onChange={(e) => setPhone(e.target.value)}
      />
      <input
        type="password"
        className="mt-3 w-full rounded-md border border-border px-3 py-2 text-sm"
        placeholder="Password (min 8)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />
      <button
        type="submit"
        className="mt-5 w-full rounded-md bg-brand-600 py-2 text-sm font-semibold text-white hover:bg-brand-700"
      >
        Create account
      </button>
      <p className="mt-4 text-center text-sm text-ink-600">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-brand-700">
          Sign in
        </Link>
      </p>
    </AuthShell>
  )
}

function AuthShell({
  title,
  submit,
  error,
  children,
}: {
  title: string
  submit: (e: React.FormEvent) => void
  error: string
  children: React.ReactNode
}) {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-sm items-center px-4 py-12">
      <form onSubmit={submit} className="w-full rounded-xl border border-border bg-surface p-6">
        <h1 className="text-xl font-bold text-ink-900">{title}</h1>
        {error && <p className="mt-3 rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}
        <div className="mt-4">{children}</div>
      </form>
    </div>
  )
}
