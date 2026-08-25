import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/**
 * Nav
 * ---
 * Fixed top navigation bar.
 * Uses NavLink so the active page link is highlighted. Shows the logged-in
 * username (with an admin tag) and a log out control, or a log in link.
 */
export default function Nav() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <nav className="nav">
      <div className="nav-inner">
        <span className="nav-logo">Sneaker Agent</span>
        <div className="nav-links">
          <NavLink
            to="/"
            end
            className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
          >
            Catalog
          </NavLink>
          <NavLink
            to="/advisor"
            className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
          >
            AI Advisor
          </NavLink>
          {user?.is_admin && (
            <NavLink
              to="/evals"
              className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
            >
              Evals
            </NavLink>
          )}

          {user ? (
            <span className="nav-account">
              <span className="nav-account-name">{user.username}</span>
              {user.is_admin && <span className="nav-admin-tag">admin</span>}
              <button className="nav-logout-btn" onClick={handleLogout}>
                Log out
              </button>
            </span>
          ) : (
            <NavLink
              to="/login"
              className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
            >
              Log in
            </NavLink>
          )}
        </div>
      </div>
    </nav>
  )
}
