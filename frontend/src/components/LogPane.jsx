import { useEffect, useRef } from 'react'

/**
 * Agent color accents for the log badge
 */
const AGENT_COLORS = {
  orchestrator:    { bg: '#2A3A30', text: '#7EC9A0' },
  financial_agent: { bg: '#2A3035', text: '#7AB8D4' },
  inventory_agent: { bg: '#2A2A38', text: '#9B8FD4' },
  sneaker_agent:   { bg: '#302A38', text: '#C49FD4' },
  critique_agent:  { bg: '#3A2A2A', text: '#D49F7A' },
  logistics_agent: { bg: '#2A3028', text: '#A8C97A' },
}

const DEFAULT_AGENT_COLOR = { bg: '#282828', text: '#A0A0A0' }

/**
 * LogPane
 * -------
 * Terminal-style streaming log panel. Each agent step appears as a block
 * with a timestamp, colored agent badge, the action summary, the agent's
 * own reasoning (why it made its decision), and the routing handoff.
 * New entries animate in and the pane auto-scrolls to the latest line.
 *
 * Props:
 *   steps   [{node, label, summary, reasoning, next}] — completed steps in order
 *   loading (bool) — true while the pipeline is still running
 */
export default function LogPane({ steps, loading }) {
  const bottomRef = useRef(null)

  // Auto-scroll to latest entry
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [steps.length, loading])

  if (steps.length === 0 && !loading) {
    return (
      <div className="log-pane log-pane-empty">
        <span className="log-cursor">▋</span>
        <span className="log-empty-text"> Waiting for pipeline to start…</span>
      </div>
    )
  }

  return (
    <div className="log-pane">
      {/* Static header */}
      <div className="log-header-row">
        <span className="log-header-text">sneaker-agent  pipeline log</span>
      </div>

      <div className="log-entries">
        {steps.map((step, i) => {
          const ac      = AGENT_COLORS[step.node] || DEFAULT_AGENT_COLOR
          const isLast  = i === steps.length - 1

          // Build the log lines for this step
          const lines = []

          // Routing line — what the previous agent handed off to
          if (i === 0) {
            lines.push({ type: 'system', text: '  Pipeline started' })
          }

          // The agent's own action line
          lines.push({ type: 'agent', text: step.summary || '...' })

          // The agent's reasoning — why it made this decision
          if (step.reasoning) {
            lines.push({ type: 'reasoning', text: step.reasoning })
          }

          // Routing forward
          if (step.next) {
            lines.push({ type: 'route', text: `  → routing to ${step.next.replace(/_/g, ' ')}` })
          } else if (!loading || !isLast) {
            lines.push({ type: 'route', text: '  → pipeline complete' })
          }

          return (
            <div
              key={`${step.node}-${i}`}
              className="log-entry"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              {/* Timestamp + badge */}
              <div className="log-entry-header">
                <span className="log-timestamp">{formatTime(i)}</span>
                <span
                  className="log-badge"
                  style={{ background: ac.bg, color: ac.text }}
                >
                  {step.label}
                </span>
              </div>

              {/* Lines */}
              {lines.map((line, li) => (
                <div
                  key={li}
                  className={`log-line log-line-${line.type}`}
                  style={isLast && li === lines.length - 1
                    ? { animation: 'logTypeIn 0.25s ease forwards' }
                    : undefined}
                >
                  {line.type === 'agent' && <span className="log-prompt">$</span>}
                  {line.type === 'reasoning' && <span className="log-think-label">reasoning</span>}
                  {line.text}
                </div>
              ))}
            </div>
          )
        })}

        {/* Running indicator */}
        {loading && (
          <div className="log-entry log-running" key="running">
            <span className="log-cursor-blink">▋</span>
            <span className="log-running-text"> processing…</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  )
}

/**
 * formatTime
 * ----------
 * Returns a fake incremental timestamp for display (HH:MM:SS.ms).
 * Uses current time offset by step index so it looks like a real log.
 *
 * Args:
 *   index (number): step index
 *
 * Returns:
 *   string: formatted timestamp
 */
function formatTime(index) {
  const now    = new Date()
  const offset = index * 2400   // ~2.4s per step
  const t      = new Date(now.getTime() - (Date.now() % 86400000) + offset)
  const hh     = String(t.getHours()).padStart(2, '0')
  const mm     = String(t.getMinutes()).padStart(2, '0')
  const ss     = String(t.getSeconds()).padStart(2, '0')
  const ms     = String(t.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms}`
}
