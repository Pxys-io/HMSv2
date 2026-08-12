import { describe, expect, it } from 'vitest'
import i18n, { setLocale } from './i18n'

// Guards every ERP/patient translation key used by the new Phase-14 UI:
// a key that renders back as `ns.key` means the label is missing (the
// "lab-orders vs labOrders" class of bug).
const ERP_KEYS = [
  'erp.tabs.tasks',
  'erp.tabs.referrals',
  'erp.tabs.lab-orders',
  'erp.tabs.duplicates',
  'erp.tabs.inventory',
  'erp.tabs.hr',
  'erp.task.add',
  'erp.task.done',
  'erp.task.delete',
  'erp.task.newTask',
  'erp.task.priority',
  'erp.task.due',
  'erp.referral.outcome',
  'erp.referral.record',
  'erp.lab.update',
  'erp.dup.rescan',
  'erp.dup.merge',
  'erp.dup.notDuplicates',
  'erp.inventory.addProduct',
  'erp.inventory.name',
  'erp.inventory.opening',
  'erp.inventory.price',
  'erp.inventory.cost',
  'erp.inventory.stockIn',
  'erp.hr.apply',
  'erp.hr.generate',
  'erp.hr.clockIn',
  'erp.hr.clockOut',
  'erp.hr.approve',
  'erp.hr.reject',
  'patient.tags',
  'patient.activity',
  'patient.communications',
  'patient.growthLabs',
  'patient.log',
  'patient.addTag',
  'patient.newTag',
  'patient.create',
  'patient.noActivity',
  'patient.noTags',
  'patient.addBirthDate',
  'nav.finance',
  'nav.erp',
]

describe('phase-14 i18n keys', () => {
  it.each(['en', 'ar'])('resolves every ERP/patient key in %s', async (locale) => {
    await setLocale(locale)
    for (const key of ERP_KEYS) {
      const rendered = i18n.t(key)
      expect(rendered, `${locale}: missing translation for ${key}`).not.toBe(key)
      expect(rendered, `${locale}: empty translation for ${key}`).not.toBe('')
    }
  })
})
