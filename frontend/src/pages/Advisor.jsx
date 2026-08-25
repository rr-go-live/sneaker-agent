import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import SneakerCard    from '../components/SneakerCard'
import LogPane        from '../components/LogPane'
import SneakerPicker  from '../components/SneakerPicker'
import { useAuth }    from '../auth/AuthContext'

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
 * natural language query the orchestrator can route correctly. There is no
 * budget/price concept — the user can search for and add any sneaker
 * regardless of cost.
 *
 * Args:
 *   brands        (string[])  — selected brand filters
 *   colors        (string[])  — selected colorway filters
 *   profile       (string)    — silhouette profile preference
 *   wardrobeNames (string[])  — names of sneakers already owned
 *   interestedText (string)   — free-text description of what the user wants
 *
 * Returns:
 *   string: natural language query
 */
function buildQuery(brands, colors, profile, wardrobeNames, interestedText) {
  const parts = []

  if (wardrobeNames.length > 0) {
    parts.push(`I want to upgrade my sneaker rotation. I already own: ${wardrobeNames.join(', ')}.`)
  } else {
    parts.push("I'm looking for new sneakers to add to my collection.")
  }

  const description = interestedText.trim()
  if (description) {
    parts.push(`Here is what I'm looking for in my own words: "${description}". Please evaluate whether anything in the catalog fits this and my style, and suggest the best matching options.`)
  }

  if (brands.length > 0)  parts.push(`I prefer ${brands.join(' or ')}.`)
  if (colors.length > 0)  parts.push(`I like ${colors.join(' or ')} colorways.`)
  if (profile !== 'any')  parts.push(`I prefer ${profile}-top silhouettes.`)

  return parts.join(' ')
}

/**
 * Advisor
 * -------
 * AI-driven recommendation page. The preference form is converted into a
 * natural language query which runs through the full LangGraph multi-agent
 * pipeline (orchestrator → sneaker_agent → critique_agent → logistics_agent).
 * There is no budget concept — any sneaker can be searched for and added
 * regardless of cost; retail/market price is still shown as reference data.
 *
 * Agent steps stream in via SSE and are rendered as a live pipeline
 * visualization. Recommendation cards appear once the pipeline completes.
 */
export default function Advisor() {
  const { user, loading: authLoading } = useAuth()
  const navigate = useNavigate()

  // Redirect to login if not signed in — AI Advisor requires an account so
  // the pipeline knows who's shopping. Sends the user back here afterward.
  useEffect(() => {
    if (!authLoading && !user) {
      navigate('/login', { state: { from: '/advisor' }, replace: true })
    }
  }, [authLoading, user, navigate])

  // Form state
  const [selectedBrands,  setSelectedBrands]  = useState([])
  const [selectedColors,  setSelectedColors]  = useState([])
  const [profile,         setProfile]         = useState('any')
  const [wardrobeItems,   setWardrobeItems]   = useState(DEFAULT_WARDROBE)
  const [interestedText,  setInterestedText]  = useState('')

  // User profile state
  const [username, setUsername] = useState('')

  // Pipeline state
  const [loading,   setLoading]   = useState(false)
  const [steps,     setSteps]     = useState([])   // [{node, label, summary, next}]
  const [sneakers,  setSneakers]  = useState([])
  const [error,     setError]     = useState(null)
  const [activeTab, setActiveTab] = useState('wardrobe')

  // Auto-switch to sneakers tab when results arrive
  useEffect(() => {
    if (sneakers.length > 0) setActiveTab('sneakers')
  }, [sneakers.length])

  /**
   * enrichWardrobe
   * ---------------
   * The user profile endpoint only returns wardrobe sneaker names. Looks
   * each one up against the catalog so the Wardrobe tab can render real
   * cards (photo, price, market data) instead of bare name stubs.
   *
   * Args:
   *   names (string[]) — wardrobe sneaker names from the profile
   *
   * Returns:
   *   Promise<object[]> — full catalog entries, one per name (falls back
   *   to a bare {name} stub if a name has no exact catalog match)
   */
  async function enrichWardrobe(names) {
    return Promise.all(
      names.map(async name => {
        try {
          const res = await fetch(`/api/sneakers?q=${encodeURIComponent(name)}`)
          if (res.ok) {
            const matches = await res.json()
            const exact = matches.find(s => s.name === name)
            if (exact) return exact
          }
        } catch {
          // fall through to the stub below
        }
        return { name, brand: '', retail_price: null }
      })
    )
  }

  async function loadProfile(name) {
    try {
      const res = await fetch(`/api/users/${encodeURIComponent(name)}`)
      if (!res.ok) return
      const data = await res.json()
      if (data.wardrobe?.length) {
        const enriched = await enrichWardrobe(data.wardrobe)
        setWardrobeItems(enriched)
      }
      setActiveTab('wardrobe')
    } catch {
      // no wardrobe on the account yet — keep the default wardrobe
    }
  }

  // Once logged in, load that account's wardrobe so the form reflects
  // who's shopping.
  useEffect(() => {
    if (user && !username) {
      setUsername(user.username)
      loadProfile(user.username)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

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
      input:    buildQuery(selectedBrands, selectedColors, profile, wardrobeNames, interestedText),
      wardrobe: wardrobeNames,
      brands:   selectedBrands,
      colors:   selectedColors,
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

  // Avoid flashing the form before the redirect-to-login effect above fires.
  if (authLoading || !user) {
    return <div className="container" />
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">AI Advisor</h1>
        <p className="page-subtitle">
          Four agents work together to build your perfect rotation
        </p>
      </div>

      <div className="advisor-layout">

        {/* ── Left: Preference form ── */}
        <form className="advisor-form" onSubmit={handleSubmit}>

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

          {/* Tab bar */}
          <div className="result-tabs">
            <button
              className={'result-tab' + (activeTab === 'wardrobe' ? ' active' : '')}
              onClick={() => setActiveTab('wardrobe')}
            >
              Wardrobe{wardrobeItems.length > 0 ? ` (${wardrobeItems.length})` : ''}
            </button>
            <button
              className={'result-tab' + (activeTab === 'logging' ? ' active' : '')}
              onClick={() => setActiveTab('logging')}
            >
              Reasoning
            </button>
            <button
              className={'result-tab' + (activeTab === 'sneakers' ? ' active' : '')}
              onClick={() => setActiveTab('sneakers')}
            >
              Suggestions{sneakers.length > 0 ? ` (${sneakers.length})` : ''}
            </button>
          </div>

          {/* Wardrobe tab */}
          {activeTab === 'wardrobe' && (
            <>
              {wardrobeItems.length > 0 ? (
                <div className="rec-grid">
                  {wardrobeItems.map(s => (
                    <SneakerCard key={s.name} sneaker={s} username={username || null} ownedView />
                  ))}
                </div>
              ) : (
                <div className="results-panel-empty" style={{ minHeight: 200 }}>
                  <p className="results-panel-empty-title">No wardrobe items yet</p>
                  <p className="results-panel-empty-sub">
                    Search the catalog to add what you already own
                  </p>
                </div>
              )}
            </>
          )}

          {/* Reasoning tab */}
          {activeTab === 'logging' && (
            <LogPane steps={steps} loading={loading} />
          )}

          {/* Suggestions tab */}
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
