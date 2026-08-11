import { create } from 'zustand'

export type StaffUser = {
  id: number
  email: string
  full_name: string
  full_name_ar: string | null
  phone: string | null
  role: 'admin' | 'doctor' | 'secretary'
  must_change_password?: boolean
}

type AuthState = {
  user: StaffUser | null
  accessToken: string | null
  setSession: (user: StaffUser, accessToken: string) => void
  setAccessToken: (token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  setSession: (user, accessToken) => set({ user, accessToken }),
  setAccessToken: (accessToken) => set({ accessToken }),
  logout: () => set({ user: null, accessToken: null }),
}))
