import { useEffect, useState } from 'react'

export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

export function OfflineBanner() {
  const online = useOnline()
  if (online) return null
  return (
    <div className="sticky top-0 z-30 w-full bg-amber-500 px-4 py-1.5 text-center text-sm font-semibold text-white">
      Offline — clinical data is not cached; mutations are disabled until you reconnect.
    </div>
  )
}

export async function downscaleImage(file: File, maxEdge = 2048): Promise<File> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * scale)
  canvas.height = Math.round(bitmap.height * scale)
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', 0.85),
  )
  bitmap.close()
  return new File([blob ?? file], 'photo.jpg', { type: 'image/jpeg' })
}

export function CameraCapture({
  onCaptured,
  label = 'Capture',
}: {
  onCaptured: (file: File) => void
  label?: string
}) {
  const [busy, setBusy] = useState(false)
  async function handle(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true)
    try {
      // HEIC from iOS converts automatically on input; anything else we
      // downscale client-side for fast clinic-Wi-Fi uploads (PWA4).
      const prepared = file.type === 'image/jpeg' || file.type === 'image/png'
        ? await downscaleImage(file)
        : file
      onCaptured(prepared)
    } finally {
      setBusy(false)
      e.target.value = ''
    }
  }
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 rounded-md bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
      📷 {busy ? 'Processing…' : label}
      <input
        type="file"
        accept="image/*,application/pdf"
        capture="environment"
        className="hidden"
        onChange={handle}
      />
    </label>
  )
}
