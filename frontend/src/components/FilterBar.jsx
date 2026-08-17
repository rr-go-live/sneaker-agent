/**
 * FilterBar
 * ---------
 * Horizontal filter row for the catalog page.
 * Renders brand chips, profile chips, and an in-stock toggle.
 *
 * Props:
 *   filters       (object)   — current active filter values
 *   onFilterChange (function) — called with (key, value) when a filter changes
 */

const BRANDS   = ['Nike', 'Adidas', 'Jordan', 'New Balance']
const PROFILES = ['high', 'mid', 'low']

export default function FilterBar({ filters, onFilterChange }) {
  function toggleBrand(brand) {
    onFilterChange('brand', filters.brand === brand ? '' : brand)
  }

  function toggleProfile(profile) {
    onFilterChange('profile', filters.profile === profile ? '' : profile)
  }

  function toggleStock() {
    onFilterChange('in_stock', filters.in_stock ? null : true)
  }

  return (
    <div className="filter-bar">
      {/* Brand */}
      <div className="filter-group">
        <span className="filter-label">Brand</span>
        <div className="filter-chips">
          {BRANDS.map(b => (
            <button
              key={b}
              className={'chip' + (filters.brand === b ? ' active' : '')}
              onClick={() => toggleBrand(b)}
            >
              {b}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-divider" />

      {/* Profile */}
      <div className="filter-group">
        <span className="filter-label">Profile</span>
        <div className="filter-chips">
          {PROFILES.map(p => (
            <button
              key={p}
              className={'chip' + (filters.profile === p ? ' active' : '')}
              onClick={() => toggleProfile(p)}
            >
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-divider" />

      {/* In Stock */}
      <div className="filter-group">
        <button
          className={'chip' + (filters.in_stock ? ' stock-active' : '')}
          onClick={toggleStock}
        >
          In Stock Only
        </button>
      </div>
    </div>
  )
}
