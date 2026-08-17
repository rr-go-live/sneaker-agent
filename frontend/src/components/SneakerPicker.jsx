import { useState, useEffect, useRef } from 'react'

/**
 * SneakerPicker
 * -------------
 * Search-based catalog picker. A text input queries /api/sneakers?q=… live;
 * matching results appear in a dropdown. Clicking a result adds it to the
 * selected list which renders as removable chips above the input.
 *
 * Already-selected items are shown with a checkmark in the dropdown and
 * cannot be added twice.
 *
 * Props:
 *   items       (array)    — currently selected sneakers [{name, brand, retail_price}]
 *   onAdd       (function) — called with a sneaker object when user adds one
 *   onRemove    (function) — called with the sneaker name string when user removes one
 *   placeholder (string)   — input placeholder text
 *   maxItems    (number)   — optional cap on selections (default: unlimited)
 */
export default function SneakerPicker({ items, onAdd, onRemove, placeholder, maxItems }) {
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState([])
  const [open,    setOpen]    = useState(false)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  // Debounced catalog search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    const q = query.trim()
    if (!q) {
      setResults([])
      setOpen(false)
      return
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await fetch(`/api/sneakers?q=${encodeURIComponent(q)}`)
        if (res.ok) {
          const data = await res.json()
          setResults(data.slice(0, 8))
          setOpen(true)
        }
      } finally {
        setLoading(false)
      }
    }, 280)
  }, [query])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const selectedNames = new Set(items.map(i => i.name))
  const atMax = maxItems != null && items.length >= maxItems

  function handleSelect(sneaker) {
    if (selectedNames.has(sneaker.name) || atMax) return
    onAdd(sneaker)
    setQuery('')
    setResults([])
    setOpen(false)
  }

  return (
    <div className="sneaker-picker" ref={containerRef}>
      {/* Selected chips */}
      {items.length > 0 && (
        <div className="picker-chips">
          {items.map(item => (
            <span key={item.name} className="picker-chip">
              <span className="picker-chip-brand">{item.brand}</span>
              {item.name}
              <button
                type="button"
                className="picker-chip-remove"
                onClick={() => onRemove(item.name)}
                aria-label={`Remove ${item.name}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Search input */}
      {!atMax && (
        <div className="picker-input-wrap">
          <input
            className="picker-input"
            type="text"
            placeholder={placeholder || 'Search catalog…'}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onFocus={() => results.length > 0 && setOpen(true)}
          />
          {loading && <span className="picker-spinner" />}
        </div>
      )}

      {/* Dropdown */}
      {open && results.length > 0 && (
        <div className="picker-dropdown">
          {results.map(s => {
            const already = selectedNames.has(s.name)
            return (
              <button
                key={s.name}
                type="button"
                className={'picker-result' + (already ? ' already' : '')}
                onClick={() => handleSelect(s)}
                disabled={already}
              >
                <span className="picker-result-name">{s.name}</span>
                <span className="picker-result-meta">
                  {already && <span className="picker-check">✓</span>}
                  <span className="picker-result-brand">{s.brand}</span>
                  <span className="picker-result-price">${s.retail_price}</span>
                </span>
              </button>
            )
          })}
        </div>
      )}

      {open && !loading && query.trim() && results.length === 0 && (
        <div className="picker-dropdown picker-no-results">
          No matches for "{query}"
        </div>
      )}
    </div>
  )
}
