import { useState, useEffect } from 'react'
import SneakerCard from '../components/SneakerCard'
import FilterBar from '../components/FilterBar'
import { useAuth } from '../auth/AuthContext'

const PAGE_SIZE = 24

/**
 * Catalog
 * -------
 * Browse page — fetches the full sneaker catalog from the API and displays it
 * as a searchable, filterable, paginated grid. All filtering happens
 * client-side; only PAGE_SIZE cards are rendered at a time. A purchase or
 * bid credits the logged-in viewer's wardrobe; SneakerCard itself prompts
 * a logged-out viewer to log in before either action is available.
 */
export default function Catalog() {
  const { user } = useAuth()
  const [allSneakers, setAllSneakers] = useState([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState(null)
  const [query, setQuery]             = useState('')
  const [filters, setFilters]         = useState({
    brand:    '',
    profile:  '',
    in_stock: null,
  })
  const [page, setPage] = useState(1)

  // Fetch catalog once on mount
  useEffect(() => {
    fetch('/api/sneakers')
      .then(r => {
        if (!r.ok) throw new Error('Failed to load catalog')
        return r.json()
      })
      .then(data => {
        setAllSneakers(data)
        setLoading(false)
      })
      .catch(err => {
        setError(err.message)
        setLoading(false)
      })
  }, [])

  // Reset to page 1 whenever search or filters change
  useEffect(() => {
    setPage(1)
  }, [query, filters.brand, filters.profile, filters.in_stock])

  function handleFilterChange(key, value) {
    setFilters(prev => ({ ...prev, [key]: value }))
  }

  // Apply search + filters client-side
  const visible = allSneakers.filter(s => {
    if (query) {
      const target = (s.name + s.brand + (s.colorway || '')).toLowerCase()
      if (!target.includes(query.toLowerCase())) return false
    }
    if (filters.brand   && s.brand   !== filters.brand)   return false
    if (filters.profile && s.profile !== filters.profile) return false
    if (filters.in_stock != null && s.in_stock !== filters.in_stock) return false
    return true
  })

  const totalPages  = Math.max(1, Math.ceil(visible.length / PAGE_SIZE))
  const safePage    = Math.min(page, totalPages)
  const pageStart   = (safePage - 1) * PAGE_SIZE
  const pageItems   = visible.slice(pageStart, pageStart + PAGE_SIZE)

  // Build the page number list: always show first, last, current ±2, with ellipsis
  function buildPageRange(current, total) {
    const delta   = 2
    const range   = []
    const around  = new Set([
      1, total,
      ...Array.from({ length: delta * 2 + 1 }, (_, i) => current - delta + i),
    ])
    let prev = 0
    for (const p of [...around].sort((a, b) => a - b)) {
      if (p < 1 || p > total) continue
      if (p - prev > 1) range.push('…')
      range.push(p)
      prev = p
    }
    return range
  }

  const pageRange = buildPageRange(safePage, totalPages)

  function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function goTo(p) {
    setPage(p)
    scrollToTop()
  }

  return (
    <div className="container">
      {/* Header */}
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 24 }}>
          <div>
            <h1 className="page-title">Explore</h1>
            <p className="page-subtitle">
              {allSneakers.length > 0
                ? `${allSneakers.length.toLocaleString()} sneakers from the StockX catalog`
                : 'Loading catalog…'}
            </p>
          </div>

          {/* Search */}
          <div className="search-bar">
            <span className="search-icon">
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
                <path
                  d="M10 6.5a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0ZM9.2 10.26l2.77 2.77a.75.75 0 0 0 1.06-1.06L10.26 9.2A5 5 0 1 0 9.2 10.26Z"
                  fill="currentColor"
                />
              </svg>
            </span>
            <input
              className="search-input"
              type="text"
              placeholder="Search by name, brand, or colorway..."
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Filters */}
      <FilterBar filters={filters} onFilterChange={handleFilterChange} />

      {/* Results meta */}
      {!loading && !error && (
        <div className="results-meta-row">
          <p className="results-meta">
            {visible.length.toLocaleString()} {visible.length === 1 ? 'result' : 'results'}
            {query && ` for "${query}"`}
          </p>
          {totalPages > 1 && (
            <p className="results-meta">
              Page {safePage} of {totalPages}
            </p>
          )}
        </div>
      )}

      {/* Loading / error */}
      {loading && (
        <p className="results-meta" style={{ paddingTop: 40 }}>Loading catalog...</p>
      )}
      {error && (
        <p style={{ color: '#A84040', padding: '40px 0', fontSize: 14 }}>
          {error} — is the API server running?
        </p>
      )}

      {/* Grid */}
      {!loading && !error && (
        <>
          <div className="sneaker-grid">
            {visible.length === 0 ? (
              <div className="empty-state">
                <p className="empty-state-title">No sneakers found</p>
                <p className="empty-state-sub">Try adjusting your search or filters</p>
              </div>
            ) : (
              pageItems.map(s => <SneakerCard key={s.name} sneaker={s} username={user?.username || null} />)
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                className="page-btn page-btn-nav"
                onClick={() => goTo(safePage - 1)}
                disabled={safePage === 1}
              >
                ← Prev
              </button>

              <div className="page-numbers">
                {pageRange.map((item, i) =>
                  item === '…' ? (
                    <span key={`ellipsis-${i}`} className="page-ellipsis">…</span>
                  ) : (
                    <button
                      key={item}
                      className={'page-btn' + (item === safePage ? ' active' : '')}
                      onClick={() => goTo(item)}
                    >
                      {item}
                    </button>
                  )
                )}
              </div>

              <button
                className="page-btn page-btn-nav"
                onClick={() => goTo(safePage + 1)}
                disabled={safePage === totalPages}
              >
                Next →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
