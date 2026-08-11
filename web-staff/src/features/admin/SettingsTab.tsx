import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { get, put } from '../../api/client'
import { Button, Card, inputClass } from '../../components/ui'

type Settings = Record<string, unknown>

export function SettingsTab() {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<Settings | null>(null)
  const [saved, setSaved] = useState('')
  const [error, setError] = useState('')

  const settings = useQuery({
    queryKey: ['admin-settings'],
    queryFn: () => get<Settings>('/api/settings'),
  })

  if (settings.data && values === null && !settings.isFetching) {
    setValues(settings.data)
  }

  async function save() {
    setError('')
    try {
      await put('/api/settings', values ?? {})
      queryClient.invalidateQueries({ queryKey: ['admin-settings'] })
      setSaved('Saved ' + new Date().toLocaleTimeString())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed')
    }
  }

  const set = (key: string, value: unknown) => setValues({ ...(values ?? {}), [key]: value })
  const str = (key: string) => String(values?.[key] ?? '')
  const dict = (key: string, locale: 'en' | 'ar') => {
    const value = values?.[key]
    return typeof value === 'object' && value !== null ? String((value as Record<string, unknown>)[locale] ?? '') : ''
  }
  const num = (key: string) => String(values?.[key] ?? '')

  if (!values) return <p className="text-sm text-ink-400">Loading settings…</p>

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-ink-900">Clinic settings</h1>
        <div className="flex-1" />
        {saved && <span className="text-xs text-success">{saved}</span>}
        <Button onClick={save}>Save</Button>
      </div>
      {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <Card className="space-y-3 p-4">
        <h2 className="text-sm font-semibold text-ink-600">Clinic info</h2>
        <div className="grid grid-cols-2 gap-2">
          <input className={inputClass} placeholder="Name (EN)" value={dict('clinic.name', 'en')} onChange={(e) => set('clinic.name', { ...(values['clinic.name'] as object), en: e.target.value })} />
          <input className={inputClass} placeholder="Name (AR)" value={dict('clinic.name', 'ar')} onChange={(e) => set('clinic.name', { ...(values['clinic.name'] as object), ar: e.target.value })} />
          <input className={inputClass} placeholder="Address (EN)" value={dict('clinic.address', 'en')} onChange={(e) => set('clinic.address', { ...(values['clinic.address'] as object), en: e.target.value })} />
          <input className={inputClass} placeholder="Address (AR)" value={dict('clinic.address', 'ar')} onChange={(e) => set('clinic.address', { ...(values['clinic.address'] as object), ar: e.target.value })} />
        </div>
        <input
          className={inputClass}
          placeholder="Phones (comma separated)"
          value={(values['clinic.phones'] as string[])?.join(', ') ?? ''}
          onChange={(e) => set('clinic.phones', e.target.value.split(',').map((s) => s.trim()).filter(Boolean))}
        />
        <input className={inputClass} placeholder="Hours text (EN)" value={dict('clinic.hours_text', 'en')} onChange={(e) => set('clinic.hours_text', { ...(values['clinic.hours_text'] as object), en: e.target.value })} />
        <input className={inputClass} placeholder="Hours text (AR)" value={dict('clinic.hours_text', 'ar')} onChange={(e) => set('clinic.hours_text', { ...(values['clinic.hours_text'] as object), ar: e.target.value })} />
        <input className={inputClass} placeholder="Map location URL" value={str('clinic.location_url')} onChange={(e) => set('clinic.location_url', e.target.value)} />
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="text-sm font-semibold text-ink-600">Rules</h2>
        <div className="grid grid-cols-3 gap-2">
          <label className="text-xs text-ink-600">
            Secretary discount cap (%)
            <input className={inputClass + ' mt-1'} type="number" value={num('billing.discount_cap_secretary_pct')} onChange={(e) => set('billing.discount_cap_secretary_pct', Number(e.target.value))} />
          </label>
          <label className="text-xs text-ink-600">
            Booking horizon (days)
            <input className={inputClass + ' mt-1'} type="number" value={num('booking.horizon_days')} onChange={(e) => set('booking.horizon_days', Number(e.target.value))} />
          </label>
          <label className="text-xs text-ink-600">
            Country code (WhatsApp)
            <input className={inputClass + ' mt-1'} value={str('clinic.country_code')} onChange={(e) => set('clinic.country_code', e.target.value)} />
          </label>
        </div>
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="text-sm font-semibold text-ink-600">WhatsApp reminder templates</h2>
        <textarea className={inputClass} rows={3} placeholder="AR template" value={str('reminder.whatsapp_template_ar')} onChange={(e) => set('reminder.whatsapp_template_ar', e.target.value)} />
        <textarea className={inputClass} rows={3} placeholder="EN template" value={str('reminder.whatsapp_template_en')} onChange={(e) => set('reminder.whatsapp_template_en', e.target.value)} />
        <p className="text-xs text-ink-400">
          Placeholders: {'{patient_name}'} {'{doctor_name}'} {'{date}'} {'{time_or_day}'} {'{clinic_name}'} {'{clinic_phone}'}
        </p>
      </Card>

      <Card className="space-y-3 p-4">
        <h2 className="text-sm font-semibold text-ink-600">Public site content</h2>
        <textarea className={inputClass} rows={2} placeholder="About (EN)" value={dict('public.about', 'en')} onChange={(e) => set('public.about', { ...(values['public.about'] as object), en: e.target.value })} />
        <textarea className={inputClass} rows={2} placeholder="About (AR)" value={dict('public.about', 'ar')} onChange={(e) => set('public.about', { ...(values['public.about'] as object), ar: e.target.value })} />
        <input className={inputClass} placeholder="Services (EN, comma separated)" value={(values['public.services'] as { en?: string[] })?.en?.join(', ') ?? ''} onChange={(e) => set('public.services', { ...(values['public.services'] as object), en: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })} />
      </Card>
    </div>
  )
}
