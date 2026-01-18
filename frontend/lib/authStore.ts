/**
 * Zustand Store for Authentication
 *
 * Manages user authentication state, tokens, and auth operations.
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ===== TYPES =====

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  is_verified: boolean
  created_at: string
}

export interface Tokens {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginResponse {
  user: User
  tokens: Tokens
}

interface AuthState {
  // State
  user: User | null
  tokens: Tokens | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null

  // Actions
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName?: string) => Promise<void>
  logout: () => Promise<void>
  refreshTokens: () => Promise<boolean>
  clearError: () => void
  setLoading: (loading: boolean) => void

  // Token helpers
  getAccessToken: () => string | null
  isTokenExpired: () => boolean
}

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'

// Token expiry buffer (refresh 5 minutes before expiry)
const TOKEN_EXPIRY_BUFFER = 5 * 60 * 1000

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      user: null,
      tokens: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      // ===== ACTIONS =====

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null })

        try {
          const response = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
          })

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}))
            throw new Error(errorData.detail || 'Login failed')
          }

          const data: LoginResponse = await response.json()

          // Calculate token expiry time
          const expiresAt = Date.now() + (data.tokens.expires_in * 1000)

          set({
            user: data.user,
            tokens: { ...data.tokens, expires_in: expiresAt },
            isAuthenticated: true,
            isLoading: false,
            error: null
          })

        } catch (error: any) {
          set({
            isLoading: false,
            error: error.message || 'Login failed',
            isAuthenticated: false,
            user: null,
            tokens: null
          })
          throw error
        }
      },

      register: async (email: string, password: string, fullName?: string) => {
        set({ isLoading: true, error: null })

        try {
          const response = await fetch(`${API_BASE}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email,
              password,
              full_name: fullName || null
            })
          })

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}))
            throw new Error(errorData.detail || 'Registration failed')
          }

          // Registration successful, now auto-login
          set({ isLoading: false })
          await get().login(email, password)

        } catch (error: any) {
          set({
            isLoading: false,
            error: error.message || 'Registration failed'
          })
          throw error
        }
      },

      logout: async () => {
        const { tokens } = get()

        set({ isLoading: true })

        try {
          if (tokens?.refresh_token) {
            await fetch(`${API_BASE}/api/auth/logout`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: tokens.refresh_token })
            })
          }
        } catch (error) {
          console.warn('Logout API call failed:', error)
        } finally {
          set({
            user: null,
            tokens: null,
            isAuthenticated: false,
            isLoading: false,
            error: null
          })
        }
      },

      refreshTokens: async () => {
        const { tokens } = get()

        if (!tokens?.refresh_token) {
          return false
        }

        try {
          const response = await fetch(`${API_BASE}/api/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: tokens.refresh_token })
          })

          if (!response.ok) {
            // Refresh failed, logout user
            set({
              user: null,
              tokens: null,
              isAuthenticated: false
            })
            return false
          }

          const newTokens: Tokens = await response.json()
          const expiresAt = Date.now() + (newTokens.expires_in * 1000)

          set({
            tokens: { ...newTokens, expires_in: expiresAt }
          })

          return true

        } catch (error) {
          console.error('Token refresh failed:', error)
          set({
            user: null,
            tokens: null,
            isAuthenticated: false
          })
          return false
        }
      },

      clearError: () => set({ error: null }),

      setLoading: (loading: boolean) => set({ isLoading: loading }),

      // ===== TOKEN HELPERS =====

      getAccessToken: () => {
        const { tokens, isTokenExpired, refreshTokens } = get()

        if (!tokens?.access_token) {
          return null
        }

        // Check if token is about to expire
        if (isTokenExpired()) {
          // Trigger refresh in background
          refreshTokens()
        }

        return tokens.access_token
      },

      isTokenExpired: () => {
        const { tokens } = get()

        if (!tokens?.expires_in) {
          return true
        }

        // expires_in is stored as the absolute expiry timestamp
        return Date.now() > (tokens.expires_in - TOKEN_EXPIRY_BUFFER)
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        tokens: state.tokens,
        isAuthenticated: state.isAuthenticated
      })
    }
  )
)

// ===== HELPER FUNCTIONS =====

/**
 * Get auth headers for API requests
 */
export function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().getAccessToken()

  if (token) {
    return { 'Authorization': `Bearer ${token}` }
  }

  return {}
}

/**
 * Check if user is authenticated (can be used outside React components)
 */
export function isAuthenticated(): boolean {
  return useAuthStore.getState().isAuthenticated
}
