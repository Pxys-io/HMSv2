import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const en = {
  nav: { home: 'Home', book: 'Book', myVisits: 'My visits', signIn: 'Sign in', bookNow: 'Book now', signOut: 'Sign out' },
  hero: { title: 'Your health, our priority', subtitle: 'Book your appointment online in under a minute. Experienced doctors, modern equipment, and care that puts you first.' },
  bookCta: 'Book now',
  callUs: '📞 Call us',
}

const ar: typeof en = {
  nav: { home: 'الرئيسية', book: 'احجز', myVisits: 'مواعيدي', signIn: 'تسجيل الدخول', bookNow: 'احجز الآن', signOut: 'تسجيل الخروج' },
  hero: { title: 'صحتك أولويتنا', subtitle: 'احجز موعدك أونلاين في أقل من دقيقة. أطباء ذوو خبرة، أجهزة حديثة، ورعاية تضعك في المقام الأول.' },
  bookCta: 'احجز الآن',
  callUs: '📞 اتصل بنا',
}

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: localStorage.getItem('hmsv2_lang') ?? 'ar',
  fallbackLng: 'ar',
  interpolation: { escapeValue: false },
})

export async function setLocale(locale: string) {
  localStorage.setItem('hmsv2_lang', locale)
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
  await i18n.changeLanguage(locale)
}

void setLocale(i18n.language)

export default i18n
