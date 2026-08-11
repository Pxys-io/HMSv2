import { useTranslation } from 'react-i18next'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { setLocale } from '../i18n'
import { useAuthStore } from '../auth/store'

export default function PublicLayout() {
  const { t, i18n } = useTranslation()
  const patient = useAuthStore((s) => s.patient)
  const logout = useAuthStore((s) => s.logout)

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="sticky top-0 z-20 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4">
          <Link to="/" className="text-xl font-bold text-brand-700">
            {patient ? '' : ''}🏥 Clinic
          </Link>
          <nav className="hidden gap-5 text-sm text-ink-600 md:flex">
            <Link to="/" className="hover:text-brand-700">{t('nav.home')}</Link>
            <Link to="/book" className="hover:text-brand-700">{t('nav.book')}</Link>
            <Link to="/account" className="hover:text-brand-700">{t('nav.myVisits')}</Link>
          </nav>
          <div className="flex-1" />
          {patient ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-ink-600">{patient.full_name}</span>
              <button
                onClick={logout}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-ink-600 hover:bg-slate-50"
              >
                {t('nav.signOut')}
              </button>
            </div>
          ) : (
            <>
              <button
                onClick={() => void setLocale(i18n.language === 'ar' ? 'en' : 'ar')}
                className="rounded-md px-2 py-1 text-sm text-ink-600 hover:bg-slate-100"
              >
                {i18n.language === 'ar' ? 'EN' : 'عربي'}
              </button>
              <Link
                to="/login"
                className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
              >
                {t('nav.signIn')}
              </Link>
            </>
          )}
          <NavLink
            to="/book"
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
          >
            {t('nav.bookNow')}
          </NavLink>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-border bg-surface">
        <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-ink-600 md:grid-cols-3">
          <div>
            <p className="font-semibold text-ink-900">Clinic</p>
            <p className="mt-1">123 Main Street, Cairo</p>
          </div>
          <div>
            <p className="font-semibold text-ink-900">Hours</p>
            <p className="mt-1">Sat–Thu 10:00 – 22:00 · Fri closed</p>
          </div>
          <div>
            <p className="font-semibold text-ink-900">Contact</p>
            <p className="mt-1">+20 100 000 0000 · info@clinic.example</p>
          </div>
        </div>
      </footer>
    </div>
  )
}
