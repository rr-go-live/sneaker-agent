import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'

const DIMENSION_LABELS = {
  routing:           'Routing Accuracy',
  sneaker_validity:  'Sneaker Validity',
  failure_handling:  'Failure Handling',
  latency:           'Latency',
}

const DIMENSION_DESC = {
  routing:           'Orchestrator routes to the right first agent',
  sneaker_validity:  'Sneaker agent avoids hallucinating names',
  failure_handling:  'Error paths fail gracefully without crashing',
  latency:           'Full run completes within the time threshold',
}

/**
 * ScoreBar
 * --------
 * Animated horizontal bar for a 0–1 score value.
 *
 * Props:
 *   score (float)  0.0–1.0
 *   color (string) CSS color for the fill
 */
function ScoreBar({ score, color = 'var(--accent)' }) {
  const pct = Math.round(score * 100)
  return (
    <div className="eval-bar-track">
      <div
        className="eval-bar-fill"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  )
}

/**
 * scoreColor
 * ----------
 * Maps a 0–1 score to a semantic color string.
 */
function scoreColor(score) {
  if (score >= 0.9) return '#4A7C64'
  if (score >= 0.6) return '#C07844'
  return '#9E4040'
}

/**
 * latencyColor
 * ------------
 * Colors a latency number based on fast/slow thresholds.
 */
function latencyColor(seconds) {
  if (seconds < 15) return '#4A7C64'
  if (seconds < 30) return '#C07844'
  return '#9E4040'
}

/**
 * CaseCard
 * --------
 * Expandable card for a single test case result. Shows the summary row by
 * default; clicking expands it to reveal agent path, scorer breakdowns,
 * and the final agent output snippet.
 *
 * Props:
 *   result (object) — eval_case SSE event payload
 *   index  (number) — ordinal position (0-based), used for staggered animation
 */
function CaseCard({ result, index }) {
  const [open, setOpen] = useState(false)

  const scoreValue = result.overall_score
  const color      = scoreColor(scoreValue)
  const latColor   = latencyColor(result.total_latency)

  return (
    <div
      className="eval-case-card"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Summary row — always visible */}
      <button className="eval-case-header" onClick={() => setOpen(o => !o)}>
        <div className="eval-case-left">
          <span className="eval-case-id">{result.id}</span>
          <span className="eval-case-name">{result.name}</span>
        </div>
        <div className="eval-case-right">
          <span className="eval-case-score" style={{ color }}>
            {Math.round(scoreValue * 100)}%
          </span>
          <span className="eval-case-latency" style={{ color: latColor }}>
            {result.total_latency.toFixed(1)}s
          </span>
          <span className={`eval-status-chip ${result.passed ? 'pass' : 'fail'}`}>
            {result.passed ? 'PASS' : 'FAIL'}
          </span>
          <span className="eval-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* Expanded detail */}
      {open && (
        <div className="eval-case-detail">
          <p className="eval-detail-description">{result.description}</p>

          <div className="eval-detail-meta">
            <div className="eval-meta-item">
              <span className="eval-meta-label">Input</span>
              <span className="eval-meta-value">"{result.input}"</span>
            </div>
            <div className="eval-meta-item">
              <span className="eval-meta-label">User</span>
              <span className="eval-meta-value">{result.user_name}</span>
            </div>
          </div>

          {/* Agent path */}
          {result.nodes_visited.length > 0 && (
            <div className="eval-path-row">
              {result.nodes_visited.map((node, i) => (
                <span key={i} className="eval-path-segment">
                  {i > 0 && <span className="eval-path-arrow">→</span>}
                  <span className="eval-path-node">
                    {node}
                    {result.node_latencies[node] != null && (
                      <span className="eval-node-time">
                        {result.node_latencies[node].toFixed(2)}s
                      </span>
                    )}
                  </span>
                </span>
              ))}
            </div>
          )}

          {/* Scorer results */}
          {Object.keys(result.scores).length > 0 && (
            <div className="eval-scorers">
              {Object.entries(result.scores).map(([dim, s]) => (
                <div key={dim} className="eval-scorer-row">
                  <span className={`eval-scorer-mark ${s.passed ? 'pass' : 'fail'}`}>
                    {s.passed ? '✓' : '✗'}
                  </span>
                  <span className="eval-scorer-label">
                    {DIMENSION_LABELS[dim] || dim}
                  </span>
                  <span className="eval-scorer-reason">{s.reason}</span>
                </div>
              ))}
            </div>
          )}

          {/* Output snippet */}
          {result.output && (
            <div className="eval-output-box">
              <span className="eval-output-label">Agent output</span>
              <p className="eval-output-text">
                {result.output.length > 300
                  ? result.output.slice(0, 300) + '…'
                  : result.output}
              </p>
            </div>
          )}

          {/* Error */}
          {result.error && (
            <p className="eval-error-text">Error: {result.error}</p>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * Evals
 * -----
 * Visual evaluation dashboard. Streams eval results via SSE from
 * POST /api/evals/run, displaying each test case card as it completes
 * and a dimension summary once all cases finish.
 */
export default function Evals() {
  const { user, loading: authLoading } = useAuth()
  const [running,        setRunning]        = useState(false)
  const [cases,          setCases]          = useState([])
  const [summary,        setSummary]        = useState(null)
  const [error,          setError]          = useState(null)
  const [runId,          setRunId]          = useState(0)   // force remount on new run
  const [scenarioInput,  setScenarioInput]  = useState('')
  const [runTotal,       setRunTotal]       = useState(7)

  async function startRun(body) {
    setRunning(true)
    setCases([])
    setSummary(null)
    setError(null)
    setRunId(id => id + 1)
    setRunTotal(body.custom_input ? 1 : 7)

    try {
      const res = await fetch('/api/evals/run', {
        method:      'POST',
        headers:     { 'Content-Type': 'application/json' },
        credentials: 'include',
        body:        JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)

      const reader  = res.body.getReader()
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
          if (raw === '[DONE]') { setRunning(false); break }

          const event = JSON.parse(raw)
          if (event.type === 'eval_case') {
            setCases(prev => [...prev, event])
          } else if (event.type === 'eval_summary') {
            setSummary(event)
            setRunning(false)
          } else if (event.type === 'error') {
            setError(event.message)
            setRunning(false)
          }
        }
      }
    } catch (err) {
      setError(err.message)
      setRunning(false)
    }
  }

  const hasResults = cases.length > 0

  // Avoid a flash of "access denied" while the initial /me session check is
  // still in flight, and hard-gate the page for anyone who isn't an admin —
  // the nav link is already hidden, but this page is reachable by direct URL.
  if (authLoading) {
    return <div className="container" />
  }

  if (!user?.is_admin) {
    return (
      <div className="container">
        <div className="page-header">
          <h1 className="page-title">Eval Dashboard</h1>
        </div>
        <div className="results-panel-empty" style={{ minHeight: 260 }}>
          <p className="results-panel-empty-title">Admin access required</p>
          <p className="results-panel-empty-sub">
            The eval dashboard is only available to admin accounts.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">Eval Dashboard</h1>
        <p className="page-subtitle">
          Run the agent harness against {7} test cases and see live scored results
        </p>
      </div>

      {/* Run button */}
      <div className="eval-run-row">
        <button
          className="submit-btn"
          style={{ width: 'auto', padding: '0 32px' }}
          onClick={() => startRun({})}
          disabled={running}
        >
          {running ? 'Running evals…' : hasResults ? 'Run Again' : 'Run Evals'}
        </button>
        {running && (
          <span className="eval-progress-label">
            {cases.length} / {runTotal} complete
          </span>
        )}
      </div>

      {/* Admin-only: run a free-text scenario instead of the fixed suite */}
      {user?.is_admin && (
        <div className="eval-scenario-panel">
          <span className="eval-scenario-label">Admin — custom scenario</span>
          <p className="form-section-hint">
            Run any prompt through the full pipeline as a one-off, with no fixed
            expected outcome. Scored only on dimensions that don't require one
            (e.g. latency) — routing/validity checks are skipped since
            there's nothing to compare against.
          </p>
          <div className="eval-scenario-row">
            <input
              className="picker-input"
              type="text"
              placeholder="e.g. find me a premium high-top statement sneaker"
              value={scenarioInput}
              onChange={e => setScenarioInput(e.target.value)}
              disabled={running}
            />
            <button
              className="submit-btn"
              style={{ width: 'auto', padding: '0 24px' }}
              onClick={() => startRun({ custom_input: scenarioInput.trim() })}
              disabled={running || !scenarioInput.trim()}
            >
              Run Scenario
            </button>
          </div>
        </div>
      )}

      {error && (
        <p style={{ color: '#9E4040', marginTop: 16, fontSize: 14 }}>{error}</p>
      )}

      {/* Dimension summary — shown once all cases finish */}
      {summary && (
        <div className="eval-summary-card">
          <div className="eval-summary-header">
            <div className="eval-summary-stat">
              <span className="eval-summary-value">
                {Math.round(summary.avg_score * 100)}%
              </span>
              <span className="eval-summary-label">Overall Score</span>
            </div>
            <div className="eval-summary-stat">
              <span className="eval-summary-value" style={{ color: summary.passed === summary.total ? '#4A7C64' : '#C07844' }}>
                {summary.passed}/{summary.total}
              </span>
              <span className="eval-summary-label">Cases Passed</span>
            </div>
            <div className="eval-summary-stat">
              <span className="eval-summary-value">{summary.total_time.toFixed(1)}s</span>
              <span className="eval-summary-label">Total Time</span>
            </div>
          </div>

          <div className="eval-dimensions">
            {Object.entries(summary.dimension_scores).map(([dim, data]) => (
              <div key={dim} className="eval-dimension-row">
                <div className="eval-dim-header">
                  <span className="eval-dim-label">{DIMENSION_LABELS[dim] || dim}</span>
                  <span className="eval-dim-desc">{DIMENSION_DESC[dim]}</span>
                  <span className="eval-dim-score" style={{ color: scoreColor(data.avg) }}>
                    {data.pass_count}/{data.total} passed · {Math.round(data.avg * 100)}%
                  </span>
                </div>
                <ScoreBar score={data.avg} color={scoreColor(data.avg)} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Test case cards — appear progressively */}
      {hasResults && (
        <div className="eval-cases-list" key={runId}>
          <h2 className="eval-section-title">Test Cases</h2>
          {cases.map((c, i) => (
            <CaseCard key={c.id} result={c} index={i} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!hasResults && !running && !error && (
        <div className="results-panel-empty" style={{ minHeight: 260 }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="#B8BDA7" strokeWidth="1.5">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"
              strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <p className="results-panel-empty-title">No eval results yet</p>
          <p className="results-panel-empty-sub">
            Click Run Evals to test the full agent pipeline against 7 automated cases
          </p>
        </div>
      )}
    </div>
  )
}
