import { toast } from 'sonner'

import { useAuthStore } from '../auth/store'

type ApiError = { code: string; message: string }

export class ApiClientError extends Error {
  code: string
  status: number
  constructor(code: string, message: string, status: number) {
    super(message)
    this.code = code
    this.status = status
  }
}

async function getCsrf(): Promise<string> {
  const name = 'hmsv2_csrf'
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : ''
}

// Single-flight: concurrent 401s share ONE refresh so cookie rotation never
// races (a raced rotation would trip the reuse detector and kill the session).
let refreshPromise: Promise<string | null> | null = null

function tokenExpiryMs(accessToken: string): number | null {
  try {
    const payload = JSON.parse(atob(accessToken.split('.')[1]))
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

function scheduleProactiveRefresh(accessToken: string) {
  const exp = tokenExpiryMs(accessToken)
  if (!exp) return
  // Refresh 2 minutes before expiry; never sooner than 1 minute from now.
  const delay = Math.max(60_000, exp - Date.now() - 120_000)
  setTimeout(async () => {
    const fresh = await refreshAccessToken()
    if (fresh) useAuthStore.getState().setAccessToken(fresh)
  }, delay)
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise
  refreshPromise = (async () => {
    const csrf = await getCsrf()
    const res = await fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
      headers: csrf ? { 'X-CSRF-Token': csrf } : {},
    })
    if (!res.ok) return null
    const body = await res.json()
    scheduleProactiveRefresh(body.access_token)
    return body.access_token as string
  })()
  try {
    return await refreshPromise
  } finally {
    refreshPromise = null
  }
}

async function rawRequest(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
): Promise<Response> {
  const token = useAuthStore.getState().accessToken
  const csrf = await getCsrf()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (csrf && method !== 'GET') headers['X-CSRF-Token'] = csrf

  const res = await fetch(path, {
    method,
    credentials: 'include',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  // 401 -> try the refresh cookie once (also restores sessions after a
  // page reload, when the in-memory access token is gone).
  if (res.status === 401 && retry) {
    const fresh = await refreshAccessToken()
    if (fresh) {
      useAuthStore.getState().setAccessToken(fresh)
      return rawRequest(method, path, body, false)
    }
    useAuthStore.getState().logout()
  }
  return res
}

export async function api<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  let res: Response
  try {
    res = await rawRequest(method, path, body)
  } catch {
    toast.error('Network error — check your connection', { id: `net:${method}:${path}` })
    throw new ApiClientError('NETWORK', 'Network error — check your connection', 0)
  }
  if (!res.ok) {
    let code = 'ERROR'
    let message = res.statusText
    try {
      const data = await res.json()
      if (data?.detail?.code) code = data.detail.code
      if (data?.detail?.message) message = data.detail.message
    } catch {
      /* non-JSON error body */
    }
    // Surface failures to the user instead of failing silently: mutations
    // always toast; GETs toast on 5xx/network (404s on reads are normal,
    // e.g. "payroll not generated yet"). Toasts are deduped per endpoint so
    // background polls can't spam.
    if (method !== 'GET' || res.status >= 500) {
      toast.error(message || res.statusText, { id: `${method}:${path}:${code}` })
    }
    throw new ApiClientError(code, message, res.status)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const get = <T = unknown>(path: string) => api<T>('GET', path)
export const del = <T = unknown>(path: string) => api<T>('DELETE', path)

export function idemKey(): string {
  return crypto.randomUUID()
}

function withKey(path: string, key: string): string {
  return path + (path.includes('?') ? '&' : '?') + '_idem=' + key
}

export const post = <T = unknown>(path: string, body?: unknown, idem?: string) =>
  api<T>('POST', idem ? withKey(path, idem) : path, body)
export const patch = <T = unknown>(path: string, body?: unknown, idem?: string) =>
  api<T>('PATCH', idem ? withKey(path, idem) : path, body)
export const put = <T = unknown>(path: string, body?: unknown, idem?: string) =>
  api<T>('PUT', idem ? withKey(path, idem) : path, body)

/** Call after login/register to arm the pre-expiry refresh timer. */
export function armAutoRefresh(accessToken: string) {
  scheduleProactiveRefresh(accessToken)
}

export type { ApiError }
