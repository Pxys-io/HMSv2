import { create } from 'zustand'

type Patient = {
  id: number
  full_name: string
  email: string | null
  phone: string | null
  locale: string
}

type AuthState = {
  patient: Patient | null
  accessToken: string | null
  setSession: (patient: Patient, accessToken: string) => void
  setAccessToken: (accessToken: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  patient: null,
  accessToken: null,
  setSession: (patient, accessToken) => set({ patient, accessToken }),
  setAccessToken: (accessToken) => set({ accessToken }),
  logout: () => set({ patient: null, accessToken: null }),
}))
