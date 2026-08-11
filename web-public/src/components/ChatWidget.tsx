import { useEffect, useRef, useState } from 'react'
import { useAuthStore } from '../auth/store'
import { chatGet, getCsrf } from './chatCsrf'

type Message = { id: number; sender_type: string; body: string; created_at: string | null }

export default function ChatWidget() {
  const [open, setOpen] = useState(false)
  const [guestName, setGuestName] = useState('')
  const [guestContact, setGuestContact] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [guestStarted, setGuestStarted] = useState(false)
  const patient = useAuthStore((s) => s.patient)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    let active = true
    const poll = async () => {
      if (!conversationId && !guestStarted && !patient) return
      try {
        const data = await chatGet<{ messages: Message[] }>('/api/public/chat/messages')
        if (active && data.messages.length) {
          setMessages(data.messages)
        }
      } catch {
        /* no session yet */
      }
    }
    poll()
    const timer = setInterval(poll, 5000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [open, conversationId, guestStarted, patient])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function start() {
    const res = await fetch('/api/public/chat/start', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(getCsrf() ? { 'X-CSRF-Token': getCsrf() } : {}) },
      body: JSON.stringify({
        message: 'Hello 👋',
        guest_name: guestName || undefined,
        guest_contact: guestContact || undefined,
      }),
    })
    if (res.ok) {
      const body = await res.json()
      setConversationId(body.conversation_id)
      setGuestStarted(true)
    }
  }

  async function send() {
    if (!draft.trim()) return
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const csrf = getCsrf()
    if (csrf) headers['X-CSRF-Token'] = csrf
    const token = useAuthStore.getState().accessToken
    if (token) headers['Authorization'] = `Bearer ${token}`
    try {
      const res = await fetch('/api/public/chat/messages', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify({ body: draft }),
      })
      if (!res.ok) {
        // Session lost (404/401): reset to the guest form and keep the draft.
        setGuestStarted(false)
        setConversationId(null)
        return
      }
      setDraft('')
    } catch {
      setGuestStarted(false)
      setConversationId(null)
    }
  }

  const needsGuestForm = !patient && !guestStarted

  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-5 end-5 z-40 flex h-14 w-14 items-center justify-center rounded-full bg-brand-600 text-2xl text-white shadow-e2 hover:bg-brand-700"
        aria-label="Support chat"
      >
        {open ? '✕' : '💬'}
      </button>
      {open && (
        <div className="fixed bottom-24 end-5 z-40 flex h-[480px] w-[360px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-e2">
          <div className="bg-brand-600 p-3 text-white">
            <p className="font-bold">Support chat</p>
            <p className="text-xs opacity-80">We reply during working hours</p>
          </div>
          <div className="flex-1 space-y-2 overflow-y-auto p-3">
            {messages.map((m) => (
              <div
                key={m.id}
                className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                  m.sender_type === 'secretary'
                    ? 'bg-brand-600 text-white'
                    : 'bg-slate-100 text-ink-900'
                }`}
              >
                {m.body}
              </div>
            ))}
            {messages.length === 0 && (
              <p className="text-center text-sm text-ink-400">How can we help?</p>
            )}
            <div ref={bottomRef} />
          </div>
          <div className="border-t border-border p-3">
            {needsGuestForm ? (
              <div>
                <input
                  className="w-full rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="Your name"
                  value={guestName}
                  onChange={(e) => setGuestName(e.target.value)}
                />
                <input
                  className="mt-2 w-full rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="Your phone"
                  value={guestContact}
                  onChange={(e) => setGuestContact(e.target.value)}
                />
                <button
                  onClick={start}
                  disabled={!guestName || !guestContact}
                  className="mt-2 w-full rounded-md bg-brand-600 py-2 text-sm font-semibold text-white disabled:opacity-60"
                >
                  Start chat
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded-md border border-border px-3 py-2 text-sm"
                  placeholder="Type a message…"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && send()}
                />
                <button
                  onClick={send}
                  className="rounded-md bg-brand-600 px-3 text-sm font-semibold text-white"
                >
                  Send
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
