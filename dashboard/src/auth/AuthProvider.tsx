import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { apiGet, apiPost, refreshSession, setAccessToken, setSessionExpiredHandler } from '../api/client'
import type { TokenResponse, UserSummary } from '../api/types'

type AuthState =
  | { status: 'checking' }
  | { status: 'loggedOut'; notice?: string }
  | { status: 'loggedIn'; user: UserSummary }

interface AuthApi {
  state: AuthState
  login: (identifier: string, password: string) => Promise<void>
  changePassword: (current: string, next: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthApi | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'checking' })

  useEffect(() => {
    setSessionExpiredHandler(() =>
      setState({ status: 'loggedOut', notice: 'Your session has expired. Please log in again.' }),
    )
    // Page (re)loaded: the HttpOnly cookie may still hold a valid session.
    ;(async () => {
      if (await refreshSession()) {
        try {
          setState({ status: 'loggedIn', user: await apiGet<UserSummary>('/auth/me') })
          return
        } catch {
          // fall through
        }
      }
      setState({ status: 'loggedOut' })
    })()
    return () => setSessionExpiredHandler(null)
  }, [])

  const login = useCallback(async (identifier: string, password: string) => {
    const r = await apiPost<TokenResponse>('/auth/login', { identifier, password, client_type: 'WEB' })
    setAccessToken(r.access_token)
    setState({ status: 'loggedIn', user: r.user })
  }, [])

  const changePassword = useCallback(async (current: string, next: string) => {
    const r = await apiPost<TokenResponse>('/auth/change-password', {
      current_password: current,
      new_password: next,
      client_type: 'WEB',
    })
    setAccessToken(r.access_token)
    setState({ status: 'loggedIn', user: r.user })
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiPost('/auth/logout')
    } finally {
      setAccessToken(null)
      setState({ status: 'loggedOut' })
    }
  }, [])

  const api = useMemo(() => ({ state, login, changePassword, logout }), [state, login, changePassword, logout])
  return <AuthContext.Provider value={api}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

export function useCurrentUser(): UserSummary {
  const { state } = useAuth()
  if (state.status !== 'loggedIn') throw new Error('Not logged in')
  return state.user
}
