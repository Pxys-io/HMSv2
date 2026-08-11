import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { get } from '../api/client'

type Doctor = {
  id: number
  full_name: string
  specialty: string
  title: string | null
  bio: string | null
  booking_mode: string
}

export default function LandingPage() {
  const { t } = useTranslation()
  const doctors = useQuery({
    queryKey: ['public-doctors'],
    queryFn: () => get<Doctor[]>('/api/public/doctors'),
  })

  return (
    <div>
      <section className="bg-gradient-to-b from-brand-50 to-white">
        <div className="mx-auto max-w-6xl px-4 py-20 text-center">
          <h1 className="text-4xl font-bold text-ink-900 md:text-5xl">{t('hero.title')}</h1>
          <p className="mx-auto mt-4 max-w-xl text-lg text-ink-600">{t('hero.subtitle')}</p>
          <div className="mt-8 flex items-center justify-center gap-4">
            <Link
              to="/book"
              className="rounded-lg bg-brand-600 px-8 py-3 text-base font-semibold text-white shadow-sm hover:bg-brand-700"
            >
              Book now
            </Link>
            <a
              href="tel:+201000000000"
              className="rounded-lg border border-border bg-surface px-8 py-3 text-base font-medium text-ink-700 hover:bg-slate-50"
            >
              📞 Call us
            </a>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="text-2xl font-bold text-ink-900">Our doctors</h2>
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
                Book with {d.full_name.split(' ')[0]}
              </Link>
            </div>
          ))}
          {doctors.data?.length === 0 && (
            <p className="text-ink-400">No doctors available right now</p>
          )}
        </div>
      </section>

      <section className="bg-surface py-12">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-2xl font-bold text-ink-900">How booking works</h2>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {[
              ['1', 'Choose your doctor', 'Pick the specialist that fits your needs.'],
              ['2', 'Pick a time', 'See real availability and choose what suits you.'],
              ['3', 'Confirm', 'Get a booking reference instantly — we handle the rest.'],
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
        <h2 className="text-2xl font-bold text-ink-900">Visit us</h2>
        <p className="mt-2 text-ink-600">123 Main Street, Cairo — parking available</p>
        <Link
          to="/book"
          className="mt-6 inline-block rounded-lg bg-brand-600 px-8 py-3 font-semibold text-white hover:bg-brand-700"
        >
          Book your appointment
        </Link>
      </section>
    </div>
  )
}
