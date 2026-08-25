import { useEffect, useRef } from 'react'

/**
 * Soft tint per agent, matching the app's badge convention
 * (light background + saturated text, drawn from the brand palette).
 */
const AGENT_COLORS = {
  orchestrator:    { bg: '#EEECE8', text: '#5B5F66', dot: '#8C9196' },
  inventory_agent: { bg: '#F5F0ED', text: '#8C6B5A', dot: '#B8987F' },
  sneaker_agent:   { bg: '#F5F1DC', text: '#7A7245', dot: '#C4BA72' },
  critique_agent:  { bg: '#F3E8E4', text: '#A6604B', dot: '#CB8F78' },
  logistics_agent: { bg: '#EEF1E6', text: '#6E7D52', dot: '#9EB6A8' },
}

const DEFAULT_AGENT_COLOR = { bg: '#F1EFEA', text: '#8C9196', dot: '#C0BCB2' }

/**
 * LogPane
 * -------
 * Vertical timeline of agent steps. Each entry shows the agent, what it
 * did, and — when available — the plain-English reasoning behind that
 * decision, so the user can follow the LLM's logic rather than just a
 * routing trace.
 *
 * Props:
 *   steps   [{node, label, summary, reasoning, next}] — completed steps in order
 *   loading (bool) — true while the pipeline is still running
 */
export default function LogPane({ steps, loading }) {
  const bottomRef = useRef(null)

  // Auto-scroll to latest entry
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [steps.length, loading])

  if (steps.length === 0 && !loading) {
    return (
      <div className="results-panel-empty" style={{ minHeight: 320 }}>
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none"
          stroke="#B8BDA7" strokeWidth="1.5">
          <path d="M8 10h8M8 14h5M21 12c0 4.97-4.03 9-9 9-1.5 0-2.9-.37-4.14-1.02L3 21l1.1-3.66A8.96 8.96 0 013 12c0-4.97 4.03-9 9-9s9 4.03 9 9z"
            strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <p className="results-panel-empty-title">Agent reasoning appears here</p>
        <p className="results-panel-empty-sub">
          Each step will show what the agent decided and why
        </p>
      </div>
    )
  }

  return (
    <div className="log-pane">
      {steps.map((step, i) => {
        const ac       = AGENT_COLORS[step.node] || DEFAULT_AGENT_COLOR
        const isLast   = i === steps.length - 1
        const hasNext  = Boolean(step.next)
        const showLine = i < steps.length - 1 || loading

        return (
          <div
            key={`${step.node}-${i}`}
            className="log-step"
            style={{ animationDelay: `${i * 50}ms` }}
          >
            <div className="log-step-rail">
              <span className="log-step-dot" style={{ background: ac.dot }} />
              {showLine && <span className="log-step-line" />}
            </div>

            <div className="log-step-body">
              <div className="log-step-header">
                <span
                  className="log-step-badge"
                  style={{ background: ac.bg, color: ac.text }}
                >
                  {step.label}
                </span>
                <span className="log-step-summary">{step.summary || '…'}</span>
              </div>

              {step.reasoning && (
                <p className="log-step-reasoning">{step.reasoning}</p>
              )}

              {hasNext && (
                <span className="log-step-route">
                  Next: {step.next.replace(/_/g, ' ')}
                </span>
              )}
              {!hasNext && (!loading || !isLast) && (
                <span className="log-step-route log-step-route-done">
                  ✓ Pipeline complete
                </span>
              )}
            </div>
          </div>
        )
      })}

      {loading && (
        <div className="log-step" key="pending">
          <div className="log-step-rail">
            <span className="log-step-dot log-step-dot-pending" />
          </div>
          <div className="log-step-body">
            <span className="log-step-pending-text">Thinking…</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
