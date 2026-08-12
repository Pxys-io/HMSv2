import { useAuthStore } from '../auth/store'

export default function Can({
  perm,
  children,
}: {
  perm: string
  children: React.ReactNode
}) {
  const permissions = useAuthStore((s) => s.user?.permissions)
  const role = useAuthStore((s) => s.user?.role)
  if (role === 'admin') return <>{children}</>
  if (!permissions?.includes(perm)) return null
  return <>{children}</>
}
