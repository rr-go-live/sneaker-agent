import { createContext, useContext, useEffect, useState } from 'react'

const AuthContext = createContext(null)

/**
 * AuthProvider
 * ------------
 * Wraps the app and tracks the logged-in user via the session cookie set
 * by the backend. Checks /api/auth/me once on mount to restore session
 * state after a page refresh.
 *
 * Provides:
 *   user     ({username, is_admin} | null)
 *   loading  (bool) — true while the initial /me check is in flight
 *   login    (username, password) => Promise<user>  — throws on failure
 *   logout   () => Promise<void>
 */
export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/auth/me', { credentials: 'include' })
      .then(r => (r.ok ? r.json() : null))
      .then(setUser)
      .finally(() => setLoading(false))
  }, [])

  async function login(username, password) {
    const res = await fetch('/api/auth/login', {
      method:      'POST',
      headers:     { 'Content-Type': 'application/json' },
      credentials: 'include',
      body:        JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new Error(body.detail || 'Login failed')
    }
    const data = await res.json()
    setUser(data)
    return data
  }

  async function logout() {
    await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

/**
 * useAuth
 * -------
 * Hook to read the current auth state and login/logout actions.
 */
export function useAuth() {
  return useContext(AuthContext)
}
