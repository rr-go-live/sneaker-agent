import { NavLink } from 'react-router-dom'

/**
 * Nav
 * ---
 * Fixed top navigation bar.
 * Uses NavLink so the active page link is highlighted.
 */
export default function Nav() {
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
          <NavLink
            to="/evals"
            className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}
          >
            Evals
          </NavLink>
        </div>
      </div>
    </nav>
  )
}
