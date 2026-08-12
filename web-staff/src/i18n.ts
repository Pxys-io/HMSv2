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
    quickSearch: 'Quick search… ⌘K',
    waitingRoom: 'Waiting room',
    walkIn: '+ Walk-in',
  },
  nav: {
    board: 'Waiting room',
    calendar: 'Calendar',
    today: 'Today',
    schedule: 'Schedule',
    patients: 'Patients',
    cashier: 'Cashier',
    finance: 'Finance',
    erp: 'ERP',
    recalls: 'Recalls',
    chat: 'Support chat',
    reports: 'Reports',
    audit: 'Audit log',
    admin: 'Admin',
  },
  erp: {
    tabs: { tasks: 'Tasks', referrals: 'Referrals', 'lab-orders': 'Lab orders', duplicates: 'Duplicates', inventory: 'Inventory', hr: 'HR' },
    task: { add: 'Add', done: 'done', delete: 'delete', newTask: 'New task title', priority: 'Priority', due: 'Due' },
    referral: { outcome: 'Outcome', record: 'Record outcome' },
    lab: { update: 'Update' },
    dup: { rescan: 'Re-scan', merge: 'Merge', notDuplicates: 'Not duplicates' },
    inventory: { addProduct: 'Add product', name: 'Name', opening: 'Opening', price: 'Price', cost: 'Cost', stockIn: 'stock in' },
    hr: { apply: 'Apply', generate: 'Generate', clockIn: 'Clock in', clockOut: 'Clock out', approve: 'approve', reject: 'reject' },
  },
  patient: {
    tags: 'Tags',
    activity: 'Activity',
    communications: 'Communications',
    growthLabs: 'Growth & labs',
    log: 'Log',
    addTag: 'Add tag…',
    newTag: 'new tag',
    create: 'create',
    noActivity: 'No activity yet',
    noTags: 'No tags',
    addBirthDate: 'Add a birth date to see WHO growth curves (0–5y).',
  },  login: {
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
    quickSearch: 'بحث سريع… ⌘K',
    waitingRoom: 'قائمة الانتظار',
    walkIn: '+ بدون حجز',
  },
  nav: {
    board: 'قائمة الانتظار',
    calendar: 'التقويم',
    today: 'اليوم',
    schedule: 'جدول المواعيد',
    patients: 'المرضى',
    cashier: 'الكاشير',
    finance: 'المالية',
    erp: 'الإدارة التشغيلية',
    recalls: 'المتابعات',
    chat: 'دعم المحادثة',
    reports: 'التقارير',
    audit: 'سجل التدقيق',
    admin: 'الإدارة',
  },
  erp: {
    tabs: { tasks: 'المهام', referrals: 'التحويلات', 'lab-orders': 'طلبات التحاليل', duplicates: 'المكرر', inventory: 'المخزون', hr: 'الموارد البشرية' },
    task: { add: 'إضافة', done: 'تم', delete: 'حذف', newTask: 'عنوان مهمة جديدة', priority: 'الأولوية', due: 'الاستحقاق' },
    referral: { outcome: 'النتيجة', record: 'تسجيل النتيجة' },
    lab: { update: 'تحديث' },
    dup: { rescan: 'إعادة الفحص', merge: 'دمج', notDuplicates: 'ليسا مكررين' },
    inventory: { addProduct: 'إضافة منتج', name: 'الاسم', opening: 'الرصيد الافتتاحي', price: 'السعر', cost: 'التكلفة', stockIn: 'إضافة مخزون' },
    hr: { apply: 'تقديم', generate: 'توليد', clockIn: 'تسجيل دخول', clockOut: 'تسجيل خروج', approve: 'موافقة', reject: 'رفض' },
  },
  patient: {
    tags: 'الوسوم',
    activity: 'سجل النشاط',
    communications: 'التواصل',
    growthLabs: 'النمو والتحاليل',
    log: 'تسجيل',
    addTag: 'إضافة وسم…',
    newTag: 'وسم جديد',
    create: 'إنشاء',
    noActivity: 'لا يوجد نشاط بعد',
    noTags: 'لا توجد وسوم',
    addBirthDate: 'أضف تاريخ الميلاد لعرض منحنيات النمو (0–5 سنوات).',
  },  login: {
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
