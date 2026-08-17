import { useState, useEffect } from 'react'
import SneakerCard    from '../components/SneakerCard'
import LogPane        from '../components/LogPane'
import SneakerPicker  from '../components/SneakerPicker'

const COLOR_OPTIONS = [
  { label: 'Black',  value: 'black',  dot: '#2A2D30' },
  { label: 'White',  value: 'white',  dot: '#D8D4CE' },
  { label: 'Grey',   value: 'grey',   dot: '#8A8C88' },
  { label: 'Blue',   value: 'blue',   dot: '#6A8EA0' },
  { label: 'Red',    value: 'red',    dot: '#9E4040' },
  { label: 'Orange', value: 'orange', dot: '#C07844' },
  { label: 'Green',  value: 'green',  dot: '#7A9E8E' },
]

const BRAND_OPTIONS   = ['Nike', 'Adidas', 'Jordan', 'New Balance']
const PROFILE_OPTIONS = [
  { label: 'High Top', value: 'high' },
  { label: 'Mid',      value: 'mid'  },
  { label: 'Low Top',  value: 'low'  },
  { label: 'Any',      value: 'any'  },
]

// Maps node names to display labels matching api.py NODE_LABELS
const NODE_LABELS = {
  orchestrator:    'Orchestrator',
  financial_agent: 'Financial Agent',
  sneaker_agent:   'Sneaker Advisor',
  inventory_agent: 'Inventory Agent',
  critique_agent:  'Critique Agent',
  logistics_agent: 'Logistics Agent',
}

// Default demo wardrobe — real catalog entries
const DEFAULT_WARDROBE = [
  { name: 'Nike Dunk Low Retro White Black Panda (2021)', brand: 'Nike',        retail_price: 110 },
  { name: 'Jordan 4 Retro SB Pine Green',                brand: 'Jordan',       retail_price: 225 },
  { name: 'New Balance 550 White Green',                  brand: 'New Balance',  retail_price: 120 },
]

/**
 * buildQuery
 * ----------
 * Converts structured form fields plus wardrobe + interested items into a
 * natural language query the orchestrator can route correctly.
 *
 * Args:
 *   brands        (string[])  — selected brand filters
 *   colors        (string[])  — selected colorway filters
 *   profile       (string)    — silhouette profile preference
 *   maxPrice      (string)    — max budget string
 *   wardrobeNames (string[])  — names of sneakers already owned
 *   interestedText (string)   — free-text description of what the user wants
 *
 * Returns:
 *   string: natural language query
 */
function buildQuery(brands, colors, profile, maxPrice, wardrobeNames, interestedText) {
  const parts = []

  if (wardrobeNames.length > 0) {
    parts.push(`I want to upgrade my sneaker rotation. I already own: ${wardrobeNames.join(', ')}.`)
  } else {
    parts.push("I'm looking for new sneakers to add to my collection.")
  }

  const description = interestedText.trim()
  if (description) {
    parts.push(`Here is what I'm looking for in my own words: "${description}". Please evaluate whether anything in the catalog fits this, my style, and my budget, and suggest the best matching options.`)
  }

  if (brands.length > 0)  parts.push(`I prefer ${brands.join(' or ')}.`)
  if (colors.length > 0)  parts.push(`I like ${colors.join(' or ')} colorways.`)
  if (profile !== 'any')  parts.push(`I prefer ${profile}-top silhouettes.`)
  if (maxPrice)           parts.push(`My budget is $${maxPrice}.`)

  return parts.join(' ')
}

/**
 * Advisor
 * -------
 * AI-driven recommendation page. The preference form is converted into a
 * natural language query which runs through the full LangGraph multi-agent
 * pipeline (orchestrator → financial_agent → sneaker_agent → logistics_agent).
 *
 * Agent steps stream in via SSE and are rendered as a live pipeline
 * visualization. Recommendation cards appear once the pipeline completes.
 */
export default function Advisor() {
  // Form state
  const [selectedBrands,  setSelectedBrands]  = useState([])
  const [selectedColors,  setSelectedColors]  = useState([])
  const [profile,         setProfile]         = useState('any')
  const [minPrice,        setMinPrice]        = useState('')
  const [maxPrice,        setMaxPrice]        = useState('')
  const [wardrobeItems,   setWardrobeItems]   = useState(DEFAULT_WARDROBE)
  const [interestedText,  setInterestedText]  = useState('')

  // User profile state
  const [username,      setUsername]      = useState('')
  const [profileStatus, setProfileStatus] = useState(null)   // 'loading' | 'loaded' | 'error'

  // Pipeline state
  const [loading,   setLoading]   = useState(false)
  const [steps,     setSteps]     = useState([])   // [{node, label, summary, next}]
  const [sneakers,  setSneakers]  = useState([])
  const [error,     setError]     = useState(null)
  const [activeTab, setActiveTab] = useState('logging')

  // Auto-switch to sneakers tab when results arrive
  useEffect(() => {
    if (sneakers.length > 0) setActiveTab('sneakers')
  }, [sneakers.length])

  async function loadProfile() {
    if (!username.trim()) return
    setProfileStatus('loading')
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(username.trim())}`)
      if (!res.ok) throw new Error('User not found')
      const data = await res.json()
      if (data.budget) setMaxPrice(String(data.budget))
      if (data.wardrobe?.length) {
        setWardrobeItems(data.wardrobe.map(name => ({ name, brand: '', retail_price: null })))
      }
      setProfileStatus('loaded')
    } catch {
      setProfileStatus('error')
    }
  }

  function toggleBrand(brand) {
    setSelectedBrands(prev =>
      prev.includes(brand) ? prev.filter(b => b !== brand) : [...prev, brand]
    )
  }

  function toggleColor(color) {
    setSelectedColors(prev =>
      prev.includes(color) ? prev.filter(c => c !== color) : [...prev, color]
    )
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setSteps([])
    setSneakers([])
    setError(null)
    setActiveTab('logging')

    const wardrobeNames  = wardrobeItems.map(i => i.name)

    const payload = {
      input:    buildQuery(selectedBrands, selectedColors, profile, maxPrice, wardrobeNames, interestedText),
      budget:   maxPrice ? parseFloat(maxPrice) : null,
      wardrobe: wardrobeNames,
    }

    try {
      const response = await fetch('/api/agent', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      })

      if (!response.ok) throw new Error(`Server error: ${response.status}`)

      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      let   buffer  = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6).trim()
          if (raw === '[DONE]') { setLoading(false); break }

          const event = JSON.parse(raw)

          if (event.type === 'agent_step') {
            setSteps(prev => [...prev, event])
          } else if (event.type === 'result') {
            setSneakers(event.sneakers || [])
            setLoading(false)
          } else if (event.type === 'error') {
            setError(event.message)
            setLoading(false)
          }
        }
      }
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const hasResult = sneakers.length > 0 || error
  const hasActivity = steps.length > 0 || loading

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">AI Advisor</h1>
        <p className="page-subtitle">
          Five agents work together to build your perfect rotation
        </p>
      </div>

      <div className="advisor-layout">

        {/* ── Left: Preference form ── */}
        <form className="advisor-form" onSubmit={handleSubmit}>

          {/* User profile loader */}
          <div className="form-section">
            <span className="form-section-label">Load Profile</span>
            <div className="profile-load-row">
              <input
                className="price-input"
                style={{ width: '100%' }}
                type="text"
                placeholder="Username (john, alice, demo…)"
                value={username}
                onChange={e => { setUsername(e.target.value); setProfileStatus(null) }}
                onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), loadProfile())}
              />
              <button
                type="button"
                className="profile-load-btn"
                onClick={loadProfile}
                disabled={!username.trim() || profileStatus === 'loading'}
              >
                {profileStatus === 'loading' ? '…' : 'Load'}
              </button>
            </div>
            {profileStatus === 'loaded' && (
              <p className="profile-status ok">Profile loaded — budget and wardrobe pre-filled</p>
            )}
            {profileStatus === 'error' && (
              <p className="profile-status err">User not found. Try: john, alice, demo</p>
            )}
          </div>

          <div className="form-section">
            <span className="form-section-label">Brand</span>
            <div className="form-chips">
              {BRAND_OPTIONS.map(b => (
                <button key={b} type="button"
                  className={'form-chip' + (selectedBrands.includes(b) ? ' selected' : '')}
                  onClick={() => toggleBrand(b)}
                >
                  {b}
                </button>
              ))}
            </div>
          </div>

          <div className="form-section">
            <span className="form-section-label">Colorway</span>
            <div className="form-chips">
              {COLOR_OPTIONS.map(c => (
                <button key={c.value} type="button"
                  className={'form-chip color-chip' + (selectedColors.includes(c.value) ? ' selected' : '')}
                  onClick={() => toggleColor(c.value)}
                >
                  <span className="color-dot" style={{
                    background: c.dot,
                    border: c.value === 'white' ? '1px solid #D0CCC6' : 'none',
                  }} />
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-section">
            <span className="form-section-label">Profile</span>
            <div className="profile-chips">
              {PROFILE_OPTIONS.map(p => (
                <button key={p.value} type="button"
                  className={'profile-chip' + (profile === p.value ? ' selected' : '')}
                  onClick={() => setProfile(p.value)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-section">
            <span className="form-section-label">Price Range</span>
            <div className="price-row">
              <input className="price-input" type="number" placeholder="Min $"
                min="0" value={minPrice} onChange={e => setMinPrice(e.target.value)} />
              <span className="price-sep">—</span>
              <input className="price-input" type="number" placeholder="Max $"
                min="0" value={maxPrice} onChange={e => setMaxPrice(e.target.value)} />
            </div>
          </div>

          <div className="form-section">
            <span className="form-section-label">Current Wardrobe</span>
            <p className="form-section-hint">
              What you already own — agents will avoid duplicates and find complementary styles.
            </p>
            <SneakerPicker
              items={wardrobeItems}
              onAdd={s => setWardrobeItems(prev => [...prev, s])}
              onRemove={name => setWardrobeItems(prev => prev.filter(i => i.name !== name))}
              placeholder="Search catalog to add a sneaker…"
            />
          </div>

          <div className="form-section">
            <span className="form-section-label">Interested In</span>
            <p className="form-section-hint">
              Describe what you're after in your own words — occasion, vibe,
              colors, specific models. The agents read this directly.
            </p>
            <textarea
              className="interested-textarea"
              value={interestedText}
              onChange={e => setInterestedText(e.target.value)}
              placeholder="e.g. I want a clean white low-top for everyday wear, ideally something that holds its resale value…"
              rows={3}
            />
          </div>

          <button type="submit" className="submit-btn" disabled={loading}>
            {loading ? 'Agents running...' : 'Find My Shoes'}
          </button>
        </form>

        {/* ── Right: Tabs + content ── */}
        <div className="results-panel">

          {/* Empty state — nothing running yet */}
          {!hasActivity && !hasResult && (
            <div className="results-panel-empty">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
                stroke="#B8BDA7" strokeWidth="1.5">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                  strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <p className="results-panel-empty-title">Your rotation appears here</p>
              <p className="results-panel-empty-sub">
                Set your preferences and let the agent pipeline find your next pair
              </p>
            </div>
          )}

          {/* Tab bar */}
          {(hasActivity || hasResult) && (
            <div className="result-tabs">
              <button
                className={'result-tab' + (activeTab === 'logging' ? ' active' : '')}
                onClick={() => setActiveTab('logging')}
              >
                Logging
              </button>
              <button
                className={'result-tab' + (activeTab === 'sneakers' ? ' active' : '')}
                onClick={() => setActiveTab('sneakers')}
              >
                Sneakers{sneakers.length > 0 ? ` (${sneakers.length})` : ''}
              </button>
            </div>
          )}

          {/* Logging tab */}
          {activeTab === 'logging' && (
            <LogPane steps={steps} loading={loading} />
          )}

          {/* Sneakers tab */}
          {activeTab === 'sneakers' && (
            <>
              {error && (
                <p style={{ color: '#A84040', fontSize: 14, padding: '16px 0' }}>
                  {error}
                </p>
              )}
              {sneakers.length > 0 ? (
                <div className="rec-grid">
                  {sneakers.map(s => (
                    <SneakerCard key={s.name} sneaker={s} username={username || null} />
                  ))}
                </div>
              ) : !loading && !error && (
                <div className="results-panel-empty" style={{ minHeight: 200 }}>
                  <p className="results-panel-empty-sub">
                    Recommendations appear here once the pipeline finishes.
                  </p>
                </div>
              )}
            </>
          )}

        </div>
      </div>
    </div>
  )
}
