import { useQuery } from '@tanstack/react-query'

type Health = { status: string; version: string; env: string }

function HealthBadge() {
  const { data, isError, isLoading } = useQuery<Health>({
    queryKey: ['health'],
    queryFn: async () => {
      const res = await fetch('/api/health')
      if (!res.ok) throw new Error('health check failed')
      return res.json()
    },
  })

  if (isLoading) return <span className="text-ink-400">checking API…</span>
  if (isError || !data)
    return <span className="text-danger">API unreachable — is the backend running on :8000?</span>
  return (
    <span className="text-success">
      API {data.status} · v{data.version} · {data.env}
    </span>
  )
}

export default function App() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg">
      <div className="rounded-xl border border-border bg-surface p-8 text-center shadow-sm">
        <h1 className="text-2xl font-bold text-ink-900">HMSv2 — Public Site</h1>
        <p className="mt-2 text-sm text-ink-600">
          Phase 01 scaffold — patient-facing site placeholder.
        </p>
        <div className="mt-4 text-sm">
          <HealthBadge />
        </div>
      </div>
    </div>
  )
}
