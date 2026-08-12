import { useEffect, useRef, useState } from 'react'
import { fetchBlob, uploadFile } from '../../api/client'
import { Button, inputClass } from '../../components/ui'

export type AssetValue = {
  file_id: number
  mime?: string
  name?: string
}

export function assetValue(v: unknown): AssetValue | null {
  if (v && typeof v === 'object' && 'file_id' in v) return v as AssetValue
  return null
}

async function uploadAsset(
  uploadUrl: string | null,
  file: Blob,
  name: string,
): Promise<AssetValue> {
  if (!uploadUrl) throw new Error('Save the record first, then add files')
  const form = new FormData()
  form.append('file', file, name)
  const body = await uploadFile<{ file_id: number; mime: string }>(uploadUrl, form)
  return { file_id: body.file_id, mime: body.mime, name }
}

function PreviewThumb({ fileId, className }: { fileId: number; className?: string }) {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    let active = true
    fetchBlob(`/api/files/${fileId}?thumb=true`)
      .then((blob) => {
        if (active) setUrl(URL.createObjectURL(blob))
      })
      .catch(() => {
        /* quarantine or missing */
      })
    return () => {
      active = false
    }
  }, [fileId])
  if (!url) return <div className={className + ' bg-slate-100'} />
  return <img src={url} alt="" className={className} />
}

function AssetShell({
  onRemove,
  children,
}: {
  onRemove?: () => void
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border p-2">
      <div className="min-w-0 flex-1">{children}</div>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 text-xs text-red-600 underline"
        >
          remove
        </button>
      )}
    </div>
  )
}

export function PhotoInput({
  value,
  onChange,
  uploadUrl,
}: {
  value: unknown
  onChange: (v: AssetValue | null) => void
  uploadUrl: string | null
}) {
  const current = assetValue(value)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pick = async (file: File | null) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      onChange(await uploadAsset(uploadUrl, file, file.name))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'upload failed')
    } finally {
      setBusy(false)
    }
  }
  if (!uploadUrl) {
    return <p className="text-xs text-ink-400">Photos can be added after the record is saved.</p>
  }
  return (
    <div className="space-y-1">
      {current ? (
        <AssetShell onRemove={() => onChange(null)}>
          <PreviewThumb fileId={current.file_id} className="h-16 w-24 rounded object-cover" />
        </AssetShell>
      ) : (
        <div className="flex items-center gap-2">
          <label className="rounded-md bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-100">
            {busy ? 'Uploading…' : '📷 Camera'}
            <input
              type="file"
              accept="image/*"
              capture="environment"
              className="hidden"
              onChange={(e) => void pick(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="rounded-md border border-border px-3 py-1.5 text-xs text-ink-600 hover:bg-slate-50">
            Upload
            <input
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => void pick(e.target.files?.[0] ?? null)}
            />
          </label>
        </div>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

export function FileInput({
  value,
  onChange,
  uploadUrl,
}: {
  value: unknown
  onChange: (v: AssetValue | null) => void
  uploadUrl: string | null
}) {
  const current = assetValue(value)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  if (!uploadUrl) {
    return <p className="text-xs text-ink-400">Files can be added after the record is saved.</p>
  }
  return (
    <div className="space-y-1">
      {current ? (
        <AssetShell onRemove={() => onChange(null)}>
          <span className="text-xs text-ink-700">{current.name ?? `file #${current.file_id}`}</span>
        </AssetShell>
      ) : (
        <label className="inline-block rounded-md border border-border px-3 py-1.5 text-xs text-ink-600 hover:bg-slate-50">
          {busy ? 'Uploading…' : '⬆ Upload file'}
          <input
            type="file"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              setBusy(true)
              setError('')
              try {
                onChange(await uploadAsset(uploadUrl, file, file.name))
              } catch (err) {
                setError(err instanceof Error ? err.message : 'upload failed')
              } finally {
                setBusy(false)
              }
            }}
          />
        </label>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

const COLORS = ['#dc2626', '#2563eb', '#16a34a', '#f59e0b', '#111827', '#ffffff']

export function AnnotationInput({
  value,
  onChange,
  uploadUrl,
  templateFileId,
}: {
  value: unknown
  onChange: (v: AssetValue | null) => void
  uploadUrl: string | null
  templateFileId: number | null | undefined
}) {
  const current = assetValue(value)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const drawing = useRef(false)
  const last = useRef<{ x: number; y: number } | null>(null)
  const [color, setColor] = useState(COLORS[0])
  const [size, setSize] = useState(3)
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [baseReady, setBaseReady] = useState(false)

  useEffect(() => {
    if (!editing || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const url = current ? `/api/files/${current.file_id}` : templateFileId ? `/api/form-assets/template/${templateFileId}` : null
    if (!url) {
      setBaseReady(true)
      return
    }
    fetchBlob(url)
      .then((blob) => URL.createObjectURL(blob))
      .then((objUrl) => {
        const img = new Image()
        img.onload = () => {
          canvas.width = img.width
          canvas.height = img.height
          ctx.drawImage(img, 0, 0)
          setBaseReady(true)
        }
        img.src = objUrl
      })
      .catch(() => setBaseReady(true))
  }, [editing, current, templateFileId])

  const pos = (e: React.MouseEvent | React.TouchEvent) => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const rect = canvas.getBoundingClientRect()
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
    return {
      x: ((clientX - rect.left) / rect.width) * canvas.width,
      y: ((clientY - rect.top) / rect.height) * canvas.height,
    }
  }

  const start = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    drawing.current = true
    last.current = pos(e)
  }
  const move = (e: React.MouseEvent | React.TouchEvent) => {
    if (!drawing.current) return
    e.preventDefault()
    const p = pos(e)
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!p || !canvas || !ctx) return
    ctx.strokeStyle = color
    ctx.lineWidth = size
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()
    ctx.moveTo(last.current?.x ?? p.x, last.current?.y ?? p.y)
    ctx.lineTo(p.x, p.y)
    ctx.stroke()
    last.current = p
  }
  const end = () => {
    drawing.current = false
    last.current = null
  }

  const save = () => {
    const canvas = canvasRef.current
    if (!canvas) return
    canvas.toBlob(async (blob) => {
      if (!blob || !uploadUrl) return
      setBusy(true)
      try {
        onChange(await uploadAsset(uploadUrl, blob, 'annotation.png'))
        setEditing(false)
      } catch {
        /* ignore */
      } finally {
        setBusy(false)
      }
    }, 'image/png')
  }

  const clear = () => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }

  if (!uploadUrl) {
    return <p className="text-xs text-ink-400">Annotation can be added after the record is saved.</p>
  }

  if (editing) {
    return (
      <div className="space-y-2">
        <div className="max-h-72 overflow-auto rounded-lg border border-border">
          <canvas
            ref={canvasRef}
            className="block max-w-full touch-none"
            onMouseDown={start}
            onMouseMove={move}
            onMouseUp={end}
            onMouseLeave={end}
            onTouchStart={start}
            onTouchMove={move}
            onTouchEnd={end}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setColor(c)}
              className={`h-5 w-5 rounded-full border ${color === c ? 'ring-2 ring-brand-500' : ''}`}
              style={{ background: c }}
            />
          ))}
          <input
            type="range"
            min={1}
            max={12}
            value={size}
            onChange={(e) => setSize(Number(e.target.value))}
            className="w-20"
          />
          <Button size="sm" variant="secondary" onClick={clear}>
            Clear
          </Button>
          <Button size="sm" onClick={save} disabled={busy || !baseReady}>
            {busy ? 'Saving…' : 'Save annotation'}
          </Button>
          <button
            type="button"
            className="text-xs text-ink-400 underline"
            onClick={() => setEditing(false)}
          >
            cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {current ? (
        <AssetShell onRemove={() => onChange(null)}>
          <PreviewThumb fileId={current.file_id} className="h-16 w-24 rounded object-cover" />
        </AssetShell>
      ) : (
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
          ✏️ Annotate
        </Button>
      )}
      {current && (
        <button
          type="button"
          className="block text-xs text-brand-700 underline"
          onClick={() => setEditing(true)}
        >
          Redraw
        </button>
      )}
    </div>
  )
}

export function AudioRecorder({
  value,
  onChange,
  uploadUrl,
}: {
  value: unknown
  onChange: (v: AssetValue | null) => void
  uploadUrl: string | null
}) {
  const current = assetValue(value)
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const [state, setState] = useState<'idle' | 'recording' | 'paused'>('idle')
  const [seconds, setSeconds] = useState(0)
  const [error, setError] = useState('')

  const stopTimer = () => {
    if (timer.current) {
      clearInterval(timer.current)
      timer.current = null
    }
  }

  useEffect(() => {
    return () => {
      rec.current?.stop()
      stopTimer()
    }
  }, [])

  const start = async () => {
    setError('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const media = new MediaRecorder(stream)
      chunks.current = []
      media.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data)
      }
      media.start()
      rec.current = media
      setState('recording')
      setSeconds(0)
      stopTimer()
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
    } catch {
      setError('Microphone unavailable')
    }
  }

  const pause = () => {
    if (rec.current && rec.current.state === 'recording') {
      rec.current.pause()
      setState('paused')
      stopTimer()
    }
  }

  const resume = () => {
    if (rec.current && rec.current.state === 'paused') {
      rec.current.resume()
      setState('recording')
      timer.current = setInterval(() => setSeconds((s) => s + 1), 1000)
    }
  }

  const stop = () => {
    const media = rec.current
    if (!media) return
    media.onstop = async () => {
      stopTimer()
      setState('idle')
      const blob = new Blob(chunks.current, { type: media.mimeType || 'audio/webm' })
      try {
        onChange(await uploadAsset(uploadUrl, blob, `recording-${Date.now()}.webm`))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'upload failed')
      }
      media.stream.getTracks().forEach((t) => t.stop())
    }
    media.stop()
  }

  const fmt = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

  if (!uploadUrl) {
    return <p className="text-xs text-ink-400">Audio can be added after the record is saved.</p>
  }

  return (
    <div className="space-y-1">
      {current ? (
        <AssetShell onRemove={() => onChange(null)}>
          <audio controls src={`/api/files/${current.file_id}`} className="h-8 w-full" />
        </AssetShell>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {state === 'idle' && (
            <Button size="sm" variant="secondary" onClick={() => void start()}>
              🎙 Record conversation
            </Button>
          )}
          {state === 'recording' && (
            <>
              <span className="flex items-center gap-1 text-xs font-semibold text-red-600">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-600" /> {fmt(seconds)}
              </span>
              <Button size="sm" variant="secondary" onClick={pause}>
                ⏸ Pause
              </Button>
              <Button size="sm" onClick={stop}>
                ⏹ Stop & save
              </Button>
            </>
          )}
          {state === 'paused' && (
            <>
              <span className="text-xs font-semibold text-amber-600">Paused {fmt(seconds)}</span>
              <Button size="sm" variant="secondary" onClick={resume}>
                ▶ Continue
              </Button>
              <Button size="sm" onClick={stop}>
                ⏹ Stop & save
              </Button>
            </>
          )}
        </div>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  )
}

export { inputClass }
