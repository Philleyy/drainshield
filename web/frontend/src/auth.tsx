import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, ApiError, type User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  refresh: () => Promise<User | null>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const { user } = await api<{ user: User }>('/auth/me')
      setUser(user)
      return user
    } catch (e) {
      if (!(e instanceof ApiError) || e.status === 401) setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const signOut = useCallback(async () => {
    try { await api('/auth/logout', { method: 'POST', body: {} }) } finally { setUser(null) }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  return <AuthContext.Provider value={{ user, loading, refresh, signOut }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}

/** Pages behind sign-in. Someone on a temporary password is sent to change it first. */
export function RequireUser({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="center-screen">Loading…</div>
  if (!user) return <Navigate to={`/signin?next=${encodeURIComponent(location.pathname)}`} replace />
  if (user.must_change_password && location.pathname !== '/account/password')
    return <Navigate to="/account/password" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return <>{children}</>
}
