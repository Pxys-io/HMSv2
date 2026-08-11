import { useAuthStore } from '../auth/store'

export function getCsrf(): string {
  const match = document.cookie.match(/(?:^|; )hmsv2_csrf=([^;]*)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function chatGet<T>(path: string): Promise<T> {
  const token = useAuthStore.getState().accessToken
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(path, { credentials: 'include', headers })
  if (!res.ok) throw new Error('chat request failed')
  return (await res.json()) as T
}
