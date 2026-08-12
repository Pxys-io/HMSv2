import { useState } from 'react'
import { useAuthStore } from '../../auth/store'
import { CustomFieldsTab } from './CustomFieldsTab'
import { DoctorsTab } from './DoctorsTab'
import { RolesTab } from './RolesTab'
import { PricingTab } from './PricingTab'
import { SettingsTab } from './SettingsTab'
import { StaffTab } from './StaffTab'
import { VisitFormTab } from './VisitFormTab'
import { SyndicatesTab } from './SyndicatesTab'

const TABS = [
  { id: 'staff', label: 'Staff' },
  { id: 'doctors', label: 'Doctors' },
  { id: 'roles', label: 'Roles' },
  { id: 'custom-fields', label: 'Custom fields' },
  { id: 'pricing', label: 'Pricing' },
  { id: 'syndicates', label: 'Syndicates' },
  { id: 'visit-form', label: 'Visit form' },
  { id: 'settings', label: 'Settings' },
]

export default function AdminPage() {
  const [tab, setTab] = useState('staff')
  const role = useAuthStore((s) => s.user?.role)

  if (role !== 'admin') return null

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium capitalize ${
              tab === t.id ? 'bg-brand-600 text-white' : 'text-ink-600 hover:bg-slate-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === 'staff' && <StaffTab />}
      {tab === 'doctors' && <DoctorsTab />}
      {tab === 'roles' && <RolesTab />}
      {tab === 'custom-fields' && <CustomFieldsTab />}
      {tab === 'pricing' && <PricingTab />}
      {tab === 'syndicates' && <SyndicatesTab />}
      {tab === 'settings' && <SettingsTab />}
      {tab === 'visit-form' && <VisitFormTab />}
    </div>
  )
}
