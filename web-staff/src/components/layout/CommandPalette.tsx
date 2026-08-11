import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { get } from '../../api/client'

type SearchResult = {
  id: number
  code: string
  full_name: string
  phone: string
  age: number | null
  gender: string | null
  no_show_count: number
  syndicate_name: string | null
}

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [selected, setSelected] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    setQuery('')
    setResults([])
    setSelected(0)
    const timer = setTimeout(() => {
      const input = document.querySelector('#palette-input') as HTMLInputElement | null
      input?.focus()
    }, 50)
    return () => clearTimeout(timer)
  }, [open])

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setResults([])
      return
    }
    const timer = setTimeout(async () => {
      try {
        const data = await get<{ results: SearchResult[] }>(
          `/api/search/patients?q=${encodeURIComponent(query)}&limit=8`,
        )
        setResults(data.results)
        setSelected(0)
      } catch {
        setResults([])
      }
    }, 150)
    return () => clearTimeout(timer)
  }, [query, open])

  function openPatient(id: number) {
    navigate(`/patients/${id}`)
    onClose()
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelected((s) => Math.min(s + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelected((s) => Math.max(s - 1, 0))
    } else if (e.key === 'Enter' && results[selected]) {
      openPatient(results[selected].id)
    } else if (e.key === 'Escape') {
      onClose()
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-10" onClick={onClose}>
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-e2"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          id="palette-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search patients by name, phone, or code…"
          className="w-full border-b border-border px-4 py-3 text-sm focus:outline-none"
        />
        <div className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 && query.trim().length >= 2 && (
            <p className="px-3 py-2 text-sm text-ink-400">No patients found</p>
          )}
          {results.map((r, i) => (
            <button
              key={r.id}
              onClick={() => openPatient(r.id)}
              onMouseEnter={() => setSelected(i)}
              className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-start text-sm ${
                i === selected ? 'bg-brand-50' : ''
              }`}
            >
              <span>
                <span className="font-medium text-ink-900">{r.full_name}</span>
                <span className="ms-2 font-mono text-xs text-ink-400">{r.code}</span>
              </span>
              <span className="text-xs text-ink-400">
                {r.phone}
                {r.no_show_count > 0 ? ` · ${r.no_show_count} no-shows` : ''}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
