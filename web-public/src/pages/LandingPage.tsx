import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '../api/client'

type Branding = {
  name: { en: string; ar: string }
  address: { en: string; ar: string }
  phones: string[]
  hours: { en: string; ar: string }
  location_url: string
  about: { en: string; ar: string }
  services: { en: string[]; ar: string[] }
}

type Doctor = {
  id: number
  full_name: string
  specialty: string
  title: string | null
  bio: string | null
  booking_mode: string
}

export default function LandingPage() {
  const { t, i18n } = useTranslation()
  const locale = i18n.language === 'ar' ? 'ar' : 'en'

  const branding = useQuery({
    queryKey: ['branding'],
    queryFn: () => get<Branding>('/api/public/branding'),
  })
  const doctors = useQuery({
    queryKey: ['public-doctors'],
    queryFn: () => get<Doctor[]>('/api/public/doctors'),
  })

  const b = branding.data
  const name = b?.name[locale] || b?.name.en || 'Clinic'
  const services = b?.services[locale]?.length ? b.services[locale] : b?.services.en ?? []
  const about = b?.about[locale] || b?.about.en || ''

  return (
    <div>
      <section className="bg-gradient-to-b from-brand-50 to-white">
        <div className="mx-auto max-w-6xl px-4 py-20 text-center">
          <h1 className="text-4xl font-bold text-ink-900 md:text-5xl">{name}</h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-ink-600">
            {about || t('hero.subtitle')}
          </p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <Link
              to="/book"
              className="rounded-lg bg-brand-600 px-8 py-3 text-base font-semibold text-white shadow-sm hover:bg-brand-700"
            >
              {t('nav.bookNow')}
            </Link>
            {b?.phones[0] && (
              <a
                href={`tel:${b.phones[0]}`}
                className="rounded-lg border border-border bg-surface px-8 py-3 text-base font-medium text-ink-700 hover:bg-slate-50"
              >
                📞 {b.phones[0]}
              </a>
            )}
          </div>
        </div>
      </section>

      {services.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-12">
          <h2 className="text-2xl font-bold text-ink-900">
            {locale === 'ar' ? 'خدماتنا' : 'Our services'}
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {services.map((s) => (
              <div key={s} className="rounded-xl border border-border bg-surface p-5">
                <p className="font-medium text-ink-900">{s}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold text-ink-900">
          {locale === 'ar' ? 'أطباؤنا' : 'Our doctors'}
        </h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {doctors.data?.map((d) => (
            <div key={d.id} className="rounded-xl border border-border bg-surface p-5">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-lg font-bold text-brand-700">
                {d.full_name[0]}
              </div>
              <h3 className="mt-3 font-bold text-ink-900">{d.full_name}</h3>
              <p className="text-sm text-brand-700">
                {d.title ? `${d.title} · ` : ''}
                {d.specialty}
              </p>
              {d.bio && <p className="mt-2 text-sm text-ink-600">{d.bio}</p>}
              <Link
                to={`/book?doctor=${d.id}`}
                className="mt-4 inline-block rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
              >
                {locale === 'ar' ? `احجز مع ${d.full_name.split(' ')[0]}` : `Book with ${d.full_name.split(' ')[0]}`}
              </Link>
            </div>
          ))}
          {doctors.data?.length === 0 && (
            <p className="text-ink-400">{locale === 'ar' ? 'لا يوجد أطباء متاحون حالياً' : 'No doctors available right now'}</p>
          )}
        </div>
      </section>

      <section className="bg-surface py-12">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl font-bold text-ink-900">
            {locale === 'ar' ? 'كيف يعمل الحجز' : 'How booking works'}
          </h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[
              ['1', locale === 'ar' ? 'اختر طبيبك' : 'Choose your doctor', locale === 'ar' ? 'اختر التخصص المناسب لاحتياجاتك.' : 'Pick the specialist that fits your needs.'],
              ['2', locale === 'ar' ? 'اختر الموعد' : 'Pick a time', locale === 'ar' ? 'شاهد المواعيد المتاحة واختر ما يناسبك.' : 'See real availability and choose what suits you.'],
              ['3', locale === 'ar' ? 'أكد الحجز' : 'Confirm', locale === 'ar' ? 'احصل على رقم الحجز فوراً — ونحن نتولى الباقي.' : 'Get a booking reference instantly — we handle the rest.'],
            ].map(([n, title, body]) => (
              <div key={n} className="rounded-xl border border-border bg-bg p-5">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white">
                  {n}
                </span>
                <h3 className="mt-3 font-bold text-ink-900">{title}</h3>
                <p className="mt-1 text-sm text-ink-600">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12 text-center">
        <h2 className="text-2xl font-bold text-ink-900">
          {locale === 'ar' ? 'تفضل بزيارتنا' : 'Visit us'}
        </h2>
        <p className="mt-2 text-ink-600">
          {b?.address[locale] || b?.address.en}
          {b?.hours[locale] ? ` — ${b.hours[locale]}` : ''}
        </p>
        <Link
          to="/book"
          className="mt-6 inline-block rounded-lg bg-brand-600 px-8 py-3 font-semibold text-white hover:bg-brand-700"
        >
          {locale === 'ar' ? 'احجز موعدك' : 'Book your appointment'}
        </Link>
      </section>
    </div>
  )
}
