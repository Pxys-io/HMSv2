import type { ReactNode } from 'react'

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
}) {
  const styles = {
    primary: 'bg-brand-600 text-white hover:bg-brand-700',
    secondary: 'bg-surface border border-border text-ink-600 hover:bg-slate-50',
    ghost: 'text-ink-600 hover:bg-slate-100',
    danger: 'bg-danger text-white hover:bg-red-700',
  }[variant]
  const sizes = { sm: 'px-2 py-1 text-xs', md: 'px-3 py-2 text-sm', lg: 'px-4 py-2.5 text-base' }[size]
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md font-medium disabled:opacity-60 ${styles} ${sizes} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-border bg-surface ${className}`}>{children}</div>
}

const STATUS_STYLES: Record<string, string> = {
  booked: 'bg-status-booked text-status-booked-text',
  checked_in: 'bg-status-checked text-status-checked-text',
  called: 'bg-status-called text-status-called-text',
  in_room: 'bg-status-inroom text-status-inroom-text',
  inroom: 'bg-status-inroom text-status-inroom-text',
  waiting: 'bg-status-waiting text-status-waiting-text',
  completed: 'bg-status-completed text-status-completed-text',
  cancelled: 'bg-status-cancelled text-status-cancelled-text',
  no_show: 'bg-status-noshow text-status-noshow-text',
  left: 'bg-slate-200 text-slate-600',
  open: 'bg-blue-50 text-blue-700',
  issued: 'bg-slate-100 text-slate-600',
  partially_paid: 'bg-status-waiting text-status-waiting-text',
  paid: 'bg-status-inroom text-status-inroom-text',
  refunded: 'bg-status-noshow text-status-noshow-text',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[status] ?? 'bg-slate-100 text-slate-600'}`}
    >
      {status.replace('_', ' ')}
    </span>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-6" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-xl border border-border bg-surface p-5 shadow-e2"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-bold text-ink-900">{title}</h2>
          <button onClick={onClose} className="text-ink-400 hover:text-ink-600" aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Field({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-600">{label}</span>
      {children}
    </label>
  )
}

export const inputClass =
  'w-full rounded-md border border-border bg-surface px-3 py-2 text-sm focus:outline-2 focus:outline-brand-600'

export function EmptyState({ message, action }: { message: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <p className="text-sm text-ink-400">{message}</p>
      {action}
    </div>
  )
}
