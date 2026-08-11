import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from '../../api/client'
import { Button, Card, EmptyState, inputClass } from '../../components/ui'

type Conversation = {
  id: number
  status: string
  subject: string | null
  patient_account_id: number | null
  guest_name: string | null
  guest_contact: string | null
  assigned_to: number | null
  last_message_preview: string | null
  unread_staff: number
  unread_patient: number
}

type Message = {
  id: number
  sender_type: string
  body: string
  created_at: string | null
}

export default function ChatPage() {
  const [activeId, setActiveId] = useState<number | null>(null)
  const [draft, setDraft] = useState('')
  const queryClient = useQueryClient()

  const conversations = useQuery({
    queryKey: ['conversations'],
    queryFn: () => get<Conversation[]>('/api/chat/conversations?status=open'),
    refetchInterval: 5000,
  })

  const messages = useQuery({
    queryKey: ['messages', activeId],
    queryFn: () => get<{ messages: Message[] }>(`/api/chat/conversations/${activeId}/messages`),
    enabled: activeId !== null,
    refetchInterval: 3000,
  })

  useEffect(() => {
    if (activeId === null && conversations.data?.length) setActiveId(conversations.data[0].id)
  }, [conversations.data, activeId])

  async function send() {
    if (!activeId || !draft.trim()) return
    await post(
      `/api/chat/conversations/${activeId}/messages`,
      { body: draft },
      crypto.randomUUID(),
    )
    setDraft('')
    queryClient.invalidateQueries({ queryKey: ['messages'] })
    queryClient.invalidateQueries({ queryKey: ['conversations'] })
  }

  const rows = conversations.data ?? []

  return (
    <div className="flex h-[calc(100vh-7rem)] gap-4">
      <Card className="w-72 shrink-0 overflow-y-auto">
        <div className="divide-y divide-border">
          {rows.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`w-full p-3 text-start ${activeId === c.id ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
            >
              <div className="flex items-center justify-between">
                <p className="truncate text-sm font-medium text-ink-900">
                  {c.guest_name ?? `Patient #${c.patient_account_id ?? ''}`}
                </p>
                {c.unread_staff > 0 && (
                  <span className="rounded-full bg-danger px-1.5 text-[10px] font-bold text-white">
                    {c.unread_staff}
                  </span>
                )}
              </div>
              <p className="truncate text-xs text-ink-400">{c.last_message_preview ?? c.subject}</p>
            </button>
          ))}
          {rows.length === 0 && <EmptyState message="No open conversations" />}
        </div>
      </Card>

      <Card className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 space-y-2 overflow-y-auto p-4">
          {(messages.data?.messages ?? []).map((m) => (
            <div
              key={m.id}
              className={`max-w-[70%] rounded-lg px-3 py-2 text-sm ${
                m.sender_type === 'secretary'
                  ? 'ms-auto bg-brand-600 text-white'
                  : 'bg-slate-100 text-ink-900'
              }`}
            >
              {m.body}
            </div>
          ))}
          {messages.data?.messages.length === 0 && (
            <p className="text-center text-sm text-ink-400">No messages yet</p>
          )}
        </div>
        <div className="flex gap-2 border-t border-border p-3">
          <input
            className={inputClass}
            placeholder="Reply…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
          />
          <Button onClick={send}>Send</Button>
        </div>
      </Card>
    </div>
  )
}
