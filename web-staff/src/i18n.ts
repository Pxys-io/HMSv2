import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const en = {
  common: {
    signIn: 'Sign in',
    signOut: 'Sign out',
    bookNow: 'Book now',
    cancel: 'Cancel',
    save: 'Save',
    back: 'Back',
    confirm: 'Confirm',
    loading: 'Loading…',
    saved: 'Saved',
    saving: 'Saving…',
    conflict: 'Conflict — review',
    search: 'Search',
    noResults: 'Nothing found',
  },
  nav: {
    board: 'Waiting room',
    calendar: 'Calendar',
    today: 'Today',
    patients: 'Patients',
    cashier: 'Cashier',
    recalls: 'Recalls',
    chat: 'Support chat',
    reports: 'Reports',
    audit: 'Audit log',
    admin: 'Admin',
  },
  login: {
    title: 'HMSv2',
    subtitle: 'Clinic staff workspace',
    email: 'Email',
    password: 'Password',
  },
}

const ar: typeof en = {
  common: {
    signIn: 'تسجيل الدخول',
    signOut: 'تسجيل الخروج',
    bookNow: 'احجز الآن',
    cancel: 'إلغاء',
    save: 'حفظ',
    back: 'رجوع',
    confirm: 'تأكيد',
    loading: 'جارٍ التحميل…',
    saved: 'تم الحفظ',
    saving: 'جارٍ الحفظ…',
    conflict: 'تعارض — راجع التغييرات',
    search: 'بحث',
    noResults: 'لا توجد نتائج',
  },
  nav: {
    board: 'قائمة الانتظار',
    calendar: 'التقويم',
    today: 'اليوم',
    patients: 'المرضى',
    cashier: 'الكاشير',
    recalls: 'المتابعات',
    chat: 'دعم المحادثة',
    reports: 'التقارير',
    audit: 'سجل التدقيق',
    admin: 'الإدارة',
  },
  login: {
    title: 'HMSv2',
    subtitle: 'مساحة عمل الطاقم',
    email: 'البريد الإلكتروني',
    password: 'كلمة المرور',
  },
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

setLocale(i18n.language)

export default i18n
