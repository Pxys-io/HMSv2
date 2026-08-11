import { useAuthStore } from '../auth/store'

class ApiClientError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

function getCsrf(): string {
  const match = document.cookie.match(/(?:^|; )hmsv2_csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export function idemKey(): string {
  return crypto.randomUUID()
}

async function refreshAccessToken(): Promise<string | null> {
  const csrf = getCsrf()
  const res = await fetch('/api/public/auth/refresh', {
    method: 'POST',
    credentials: 'include',
    headers: csrf ? { 'X-CSRF-Token': csrf } : {},
  })
  if (!res.ok) return null
  const body = await res.json()
  return body.access_token
}

async function rawRequest(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
): Promise<Response> {
  const token = useAuthStore.getState().accessToken
  const csrf = getCsrf()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (csrf && method !== 'GET') headers['X-CSRF-Token'] = csrf

  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  if (res.status === 401 && token && retry) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      useAuthStore.getState().setSession(useAuthStore.getState().patient!, fresh)
      return rawRequest(method, path, body, false)
    }
    useAuthStore.getState().logout()
  }
  return res
}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await rawRequest(method, path, body)
  if (!res.ok) {
    let code = 'ERROR'
    let message = res.statusText
    try {
      const data = await res.json()
      if (data?.detail?.code) code = data.detail.code
      if (data?.detail?.message) message = data.detail.message
    } catch {
      /* non-JSON */
    }
    throw new ApiClientError(code, message, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const get = <T = unknown>(path: string) => api<T>('GET', path)
export const post = <T = unknown>(path: string, body?: unknown, idem?: string) =>
  api<T>('POST', idem ? path + (path.includes('?') ? '&' : '?') + '_idem=' + idem : path, body)

export type { ApiClientError }
