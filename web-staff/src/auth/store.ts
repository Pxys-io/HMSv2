import { create } from 'zustand'

export type StaffUser = {
  id: number
  email: string
  full_name: string
  full_name_ar: string | null
  phone: string | null
  role: string
  permissions?: string[]
  must_change_password?: boolean
}

type AuthState = {
  user: StaffUser | null
  accessToken: string | null
  setSession: (user: StaffUser, accessToken: string) => void
  setAccessToken: (token: string) => void
  setPermissions: (permissions: string[]) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  setSession: (user, accessToken) => set({ user, accessToken }),
  setAccessToken: (accessToken) => set({ accessToken }),
  setPermissions: (permissions) =>
    set((state) => ({ user: state.user ? { ...state.user, permissions } : state.user })),
  logout: () => set({ user: null, accessToken: null }),
}))
