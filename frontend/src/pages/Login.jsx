import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/**
 * Login
 * -----
 * Username/password login form. On success, redirects to wherever the
 * user was headed before being sent here (or the catalog by default).
 */
export default function Login() {
  const { login } = useAuth()
  const navigate   = useNavigate()
  const location    = useLocation()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState(null)
  const [loading,  setLoading]  = useState(false)

  const redirectTo = location.state?.from || '/'

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(username.trim(), password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container" style={{ maxWidth: 400 }}>
      <div className="page-header">
        <h1 className="page-title">Log in</h1>
        <p className="page-subtitle">
          Demo accounts: john / alice / demo / admin — password matches username
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-section">
          <span className="form-section-label">Username</span>
          <input
            className="price-input"
            style={{ width: '100%' }}
            type="text"
            autoFocus
            value={username}
            onChange={e => setUsername(e.target.value)}
          />
        </div>

        <div className="form-section">
          <span className="form-section-label">Password</span>
          <input
            className="price-input"
            style={{ width: '100%' }}
            type="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <p style={{ color: '#A84040', fontSize: 13, marginBottom: 16 }}>{error}</p>
        )}

        <button
          type="submit"
          className="submit-btn"
          disabled={loading || !username.trim() || !password}
        >
          {loading ? 'Logging in…' : 'Log in'}
        </button>
      </form>
    </div>
  )
}
