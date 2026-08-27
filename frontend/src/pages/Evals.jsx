import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'

const DIMENSION_LABELS = {
  routing:           'Routing Accuracy',
  sneaker_validity:  'Sneaker Validity',
  expected_pick:     'Expected Pick',
  constraints:       'Constraint Fidelity',
  bid_outcome:       'Bid Fairness',
  failure_handling:  'Failure Handling',
  latency:           'Latency',
}

const DIMENSION_DESC = {
  routing:           'Orchestrator routes to the right first agent',
  sneaker_validity:  'Sneaker agent avoids hallucinating names',
  expected_pick:     'The one correct catalog item actually shows up in the picks',
  constraints:       'Every pick honors the brand, silhouette, price and year the user asked for',
  bid_outcome:       'Bid agent accepts/rejects in line with real market data',
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
 * AvailabilityTable
 * -----------------
 * Renders logistics_agent's stock rows as a table. The agent emits these as
 * structured data alongside its plain-text report, so nothing here has to
 * parse the report string.
 *
 * The StockX URL becomes a short labelled link rather than raw text — the
 * full URL is long enough to dominate the row and carries no information
 * the sneaker name doesn't already give.
 *
 * Props:
 *   rows        (array)  — availability rows from the eval_case payload
 *   retailTotal (number) — summed retail price, shown in the footer
 */
function AvailabilityTable({ rows, retailTotal }) {
  return (
    <div className="avail-wrap">
      <span className="eval-output-label">Availability</span>
      <div className="avail-scroll">
        <table className="avail-table">
          <thead>
            <tr>
              <th scope="col">Sneaker</th>
              <th scope="col">Brand</th>
              <th scope="col">Stock</th>
              <th scope="col" className="num">Retail</th>
              <th scope="col" className="num">Market</th>
              <th scope="col"><span className="sr-only">Listing</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.name}>
                <td className="avail-name">{row.name}</td>
                <td className="avail-brand">{row.brand || '—'}</td>
                <td>
                  {row.found ? (
                    <span className={'avail-stock ' + (row.in_stock ? 'in' : 'out')}>
                      {row.in_stock ? `In stock · ${row.quantity}` : 'Out of stock'}
                    </span>
                  ) : (
                    <span className="avail-stock unknown">Not in catalog</span>
                  )}
                </td>
                <td className="num">{row.retail == null ? '—' : `$${row.retail.toFixed(2)}`}</td>
                <td className="num">
                  {row.market == null ? '—' : (
                    <span className={row.market > row.retail ? 'avail-up' : undefined}>
                      ${row.market.toFixed(2)}
                    </span>
                  )}
                </td>
                <td>
                  {row.link && (
                    <a
                      className="avail-link"
                      href={row.link}
                      target="_blank"
                      rel="noreferrer noopener"
                    >
                      StockX ↗
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
          {retailTotal != null && (
            <tfoot>
              <tr>
                <td colSpan={3}>Estimated retail total</td>
                <td className="num">${retailTotal.toFixed(2)}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  )
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

          {/* Availability table, or the plain-text output when a case
              produced no stock rows (routing-only and bid cases) */}
          {result.availability?.length > 0 ? (
            <AvailabilityTable
              rows={result.availability}
              retailTotal={result.retail_total}
            />
          ) : result.output && (
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
 * PIPELINE_ORDER
 * --------------
 * The agent graph's real topology, in execution order. bid_agent is listed
 * last and rendered detached because it is not a graph node — bidding runs
 * standalone against one already-known sneaker.
 */
const PIPELINE_ORDER = [
  'orchestrator',
  'inventory_agent',
  'sneaker_agent',
  'critique_agent',
  'logistics_agent',
]

const LATENCY_PASS = 15
const LATENCY_WARN = 30

/**
 * computePipelineStats
 * --------------------
 * Aggregates per-node telemetry across every completed case in a run.
 *
 * Args:
 *   cases (array) — eval_case SSE payloads received so far
 *
 * Returns:
 *   { nodes: object, totalTime: number } — nodes keyed by agent name, each
 *   with visits, totalSeconds, and meanSeconds
 */
function computePipelineStats(cases) {
  const nodes = {}
  let totalTime = 0

  for (const result of cases) {
    const latencies = result.node_latencies || {}
    for (const nodeName of Object.keys(latencies)) {
      const seconds = latencies[nodeName]
      if (!nodes[nodeName]) {
        nodes[nodeName] = { name: nodeName, visits: 0, totalSeconds: 0 }
      }
      nodes[nodeName].visits += 1
      nodes[nodeName].totalSeconds += seconds
      totalTime += seconds
    }
  }

  for (const nodeName of Object.keys(nodes)) {
    const node = nodes[nodeName]
    node.meanSeconds = node.visits > 0 ? node.totalSeconds / node.visits : 0
  }

  return { nodes, totalTime }
}

/**
 * PipelineHealth
 * --------------
 * The dashboard's signature panel: the agent graph drawn as it actually
 * runs, each node carrying its own telemetry. Answers the question a
 * generic score card cannot — not "is the system healthy" but "which agent
 * is the problem".
 *
 * The share bar under each node is its portion of total pipeline runtime,
 * which is what makes a single slow agent obvious at a glance.
 *
 * Props:
 *   cases (array) — eval_case payloads received so far
 */
function PipelineHealth({ cases }) {
  const { nodes, totalTime } = computePipelineStats(cases)

  const graphNodes = PIPELINE_ORDER.filter(name => nodes[name])
  const hasBidAgent = Boolean(nodes['bid_agent'])

  if (graphNodes.length === 0 && !hasBidAgent) return null

  function renderNode(nodeName, detached) {
    const node  = nodes[nodeName]
    const share = totalTime > 0 ? node.totalSeconds / totalTime : 0
    const color = latencyColor(node.meanSeconds)

    return (
      <div className={'pipe-node' + (detached ? ' detached' : '')}>
        <span className="pipe-node-name">{nodeName}</span>
        <span className="pipe-node-mean" style={{ color }}>
          {node.meanSeconds.toFixed(2)}s
        </span>
        <div className="pipe-share-track">
          <div
            className="pipe-share-fill"
            style={{ width: `${Math.round(share * 100)}%`, background: color }}
          />
        </div>
        <span className="pipe-node-meta">
          {node.visits} {node.visits === 1 ? 'run' : 'runs'} · {Math.round(share * 100)}% of time
        </span>
      </div>
    )
  }

  return (
    <section className="pipe-panel">
      <div className="pipe-panel-head">
        <h2 className="pipe-panel-title">Pipeline health</h2>
        <p className="pipe-panel-sub">
          Mean time per agent across this run, and each agent's share of total runtime
        </p>
      </div>

      <div className="pipe-flow">
        {graphNodes.map((nodeName, i) => (
          <div key={nodeName} className="pipe-flow-item">
            {i > 0 && <span className="pipe-arrow" aria-hidden="true">→</span>}
            {renderNode(nodeName, false)}
          </div>
        ))}
      </div>

      {hasBidAgent && (
        <div className="pipe-detached">
          <span className="pipe-detached-label">Standalone — outside the graph</span>
          {renderNode('bid_agent', true)}
        </div>
      )}
    </section>
  )
}

/**
 * LatencyChart
 * ------------
 * Per-case runtime as horizontal bars against the same thresholds the
 * latency scorer uses, so a slow case is visible without expanding it.
 *
 * Props:
 *   cases (array) — eval_case payloads received so far
 */
function LatencyChart({ cases }) {
  if (cases.length === 0) return null

  const slowest = Math.max(...cases.map(c => c.total_latency), LATENCY_PASS)
  const scaleMax = Math.max(slowest * 1.05, LATENCY_PASS * 1.2)

  return (
    <section className="lat-panel">
      <div className="pipe-panel-head">
        <h2 className="pipe-panel-title">Runtime by case</h2>
        <p className="pipe-panel-sub">
          Dashed line marks the {LATENCY_PASS}s pass threshold
        </p>
      </div>

      <div className="lat-chart">
        <div
          className="lat-threshold"
          style={{
            left: `calc(var(--lat-left) + (100% - var(--lat-left) - var(--lat-right)) * ${LATENCY_PASS / scaleMax})`,
          }}
          aria-hidden="true"
        />
        {cases.map(result => (
          <div key={result.id} className="lat-row">
            <span className="lat-row-id">{result.id}</span>
            <div className="lat-row-track">
              <div
                className="lat-row-fill"
                style={{
                  width:      `${(result.total_latency / scaleMax) * 100}%`,
                  background: latencyColor(result.total_latency),
                }}
              />
            </div>
            <span
              className="lat-row-value"
              style={{ color: latencyColor(result.total_latency) }}
            >
              {result.total_latency.toFixed(1)}s
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

/**
 * verdictFor
 * ----------
 * Turns a pass rate into a plain status word. A word lands faster than a
 * percentage when the question is "do I need to look at this right now".
 *
 * Args:
 *   passed (number), total (number)
 *
 * Returns:
 *   { word: string, color: string }
 */
function verdictFor(passed, total) {
  if (total === 0) return { word: 'No data', color: 'var(--text-muted)' }
  const rate = passed / total
  if (rate === 1)    return { word: 'All passing', color: '#4A7C64' }
  if (rate >= 0.75)  return { word: 'Mostly passing', color: '#C07844' }
  return { word: 'Needs attention', color: '#9E4040' }
}

/**
 * Evals
 * -----
 * Admin evaluation dashboard. Streams eval results via SSE from
 * POST /api/evals/run and renders them as an instrument panel: a headline
 * verdict, per-agent pipeline telemetry, dimension scores, runtime
 * distribution, and the per-case detail list.
 */
export default function Evals() {
  const { user, loading: authLoading } = useAuth()
  const [running,       setRunning]       = useState(false)
  const [cases,         setCases]         = useState([])
  const [summary,       setSummary]       = useState(null)
  const [error,         setError]         = useState(null)
  const [runId,         setRunId]         = useState(0)   // force remount on new run
  const [scenarioInput, setScenarioInput] = useState('')

  async function startRun(body) {
    setRunning(true)
    setCases([])
    setSummary(null)
    setError(null)
    setRunId(id => id + 1)

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

  // Live totals so the headline is useful mid-run, not only after the
  // summary event lands.
  const livePassed = cases.filter(c => c.passed).length
  const liveTotal  = cases.length
  const liveScore  = liveTotal > 0
    ? cases.reduce((sum, c) => sum + c.overall_score, 0) / liveTotal
    : 0
  const liveTime   = cases.reduce((sum, c) => sum + c.total_latency, 0)
  const verdict    = verdictFor(livePassed, liveTotal)

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

      {/* ── Command bar: verdict + live metrics + controls ── */}
      <section className="eval-command">
        <div className="eval-command-main">
          <span className="eval-command-eyebrow">Agent evaluation</span>
          <h1 className="eval-verdict" style={{ color: verdict.color }}>
            {running && !hasResults ? 'Running…' : verdict.word}
          </h1>
          <p className="eval-command-sub">
            {hasResults
              ? `${liveTotal} case${liveTotal === 1 ? '' : 's'} scored across ${Object.keys(summary?.dimension_scores || {}).length || '—'} dimensions`
              : 'Run the harness to score routing, picks, constraints, bidding and latency'}
          </p>
        </div>

        <div className="eval-command-metrics">
          <div className="eval-metric">
            <span className="eval-metric-value">{Math.round(liveScore * 100)}%</span>
            <span className="eval-metric-label">Score</span>
          </div>
          <div className="eval-metric">
            <span className="eval-metric-value" style={{ color: verdict.color }}>
              {livePassed}/{liveTotal || '—'}
            </span>
            <span className="eval-metric-label">Passed</span>
          </div>
          <div className="eval-metric">
            <span className="eval-metric-value">{liveTime.toFixed(0)}s</span>
            <span className="eval-metric-label">Runtime</span>
          </div>
        </div>

        <div className="eval-command-actions">
          <button
            className="eval-run-btn"
            onClick={() => startRun({})}
            disabled={running}
          >
            {running ? 'Running…' : hasResults ? 'Run again' : 'Run evals'}
          </button>
          {running && (
            <span className="eval-progress-label">
              {cases.length} complete
            </span>
          )}
        </div>
      </section>

      {/* ── Custom scenario ── */}
      <div className="eval-scenario-panel">
        <span className="eval-scenario-label">Custom scenario</span>
        <p className="form-section-hint">
          Run any prompt through the full pipeline as a one-off. Scored only on
          dimensions that don't need a fixed expected outcome, so routing and
          validity checks are skipped.
        </p>
        <div className="eval-scenario-row">
          <input
            className="picker-input"
            type="text"
            placeholder="e.g. get me a low top jordan under 150 dollars"
            value={scenarioInput}
            onChange={e => setScenarioInput(e.target.value)}
            disabled={running}
          />
          <button
            className="eval-run-btn secondary"
            onClick={() => startRun({ custom_input: scenarioInput.trim() })}
            disabled={running || !scenarioInput.trim()}
          >
            Run scenario
          </button>
        </div>
      </div>

      {error && <p className="eval-error-banner">{error}</p>}

      {/* ── Signature: per-agent pipeline telemetry ── */}
      {hasResults && <PipelineHealth cases={cases} />}

      {/* ── Dimension scores ── */}
      {summary && (
        <section className="dim-panel">
          <div className="pipe-panel-head">
            <h2 className="pipe-panel-title">Scores by dimension</h2>
            <p className="pipe-panel-sub">
              Each dimension only counts the cases that actually exercise it
            </p>
          </div>
          <div className="dim-grid">
            {Object.entries(summary.dimension_scores).map(([dim, data]) => (
              <div key={dim} className="dim-card">
                <div className="dim-card-top">
                  <span className="dim-card-label">{DIMENSION_LABELS[dim] || dim}</span>
                  <span className="dim-card-score" style={{ color: scoreColor(data.avg) }}>
                    {Math.round(data.avg * 100)}%
                  </span>
                </div>
                <ScoreBar score={data.avg} color={scoreColor(data.avg)} />
                <p className="dim-card-desc">{DIMENSION_DESC[dim]}</p>
                <span className="dim-card-count">
                  {data.pass_count}/{data.total} cases passed
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Runtime distribution ── */}
      {hasResults && <LatencyChart cases={cases} />}

      {/* ── Per-case detail ── */}
      {hasResults && (
        <div className="eval-cases-list" key={runId}>
          <h2 className="pipe-panel-title" style={{ marginBottom: 12 }}>Test cases</h2>
          {cases.map((c, i) => (
            <CaseCard key={c.id} result={c} index={i} />
          ))}
        </div>
      )}

      {/* ── Empty state ── */}
      {!hasResults && !running && !error && (
        <div className="results-panel-empty" style={{ minHeight: 260 }}>
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
            stroke="#B8BDA7" strokeWidth="1.5">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"
              strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <p className="results-panel-empty-title">No results yet</p>
          <p className="results-panel-empty-sub">
            Run the evals to score the full agent pipeline, or try a custom scenario
          </p>
        </div>
      )}
    </div>
  )
}
