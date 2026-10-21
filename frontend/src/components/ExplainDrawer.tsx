import { useState } from 'react'
import { ExplainResponse } from '../types/api'
import RiskBadge from './RiskBadge'
import { Link, useNavigate } from 'react-router-dom'
import api from '../utils/api'
import { RISK_THRESHOLDS } from '../config/risk'

/** Mini-subgraph of ONLY the evidence: the invoice loop rendered as a ring of
 *  companies with directed edges, plus a marker on edges that are part of the
 *  detected cycle. Self-contained inline SVG (no D3 sim needed). */
function EvidenceMiniGraph({ companyNames }: { companyNames: string[] }) {
  const n = companyNames.length
  if (n < 2) return null
  const size = 220
  const cx = size / 2
  const cy = size / 2
  const r = 78
  const nodes = companyNames.map((name, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    return { name, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
  })
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full h-52" role="img" aria-label="Evidence subgraph">
      <defs>
        <marker id="ev-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#ef4444" />
        </marker>
      </defs>
      {nodes.map((a, i) => {
        const b = nodes[(i + 1) % n]
        return (
          <line
            key={`e${i}`}
            x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke="#ef4444" strokeWidth={2} markerEnd="url(#ev-arrow)"
          />
        )
      })}
      {nodes.map((p, i) => (
        <g key={`n${i}`}>
          <circle cx={p.x} cy={p.y} r={13} fill="#1f2937" stroke="#ef4444" strokeWidth={1.5} />
          <text x={p.x} y={p.y + 3} textAnchor="middle" fontSize="8" fill="#e5e7eb">
            {i + 1}
          </text>
        </g>
      ))}
    </svg>
  )
}

export default function ExplainDrawer({ data, entityId, onClose }: {
  data: ExplainResponse
  entityId: string
  onClose: () => void
}) {
  const navigate = useNavigate()
  const [exporting, setExporting] = useState(false)
  const evidence = data.evidence
  const cycle = evidence.cycles?.[0]
  const decom = evidence.risk_decomposition || {}
  const eway = evidence.eway_mismatches || []

  // Journey A step 8: from the explainability drawer, open a case for this
  // entity and go straight to the print-ready export preview.
  const exportCase = async () => {
    setExporting(true)
    try {
      const score = data.entity?.risk_score
      const res = await api.post('/cases', {
        title: `Investigation: ${data.entity?.name || data.entity?.cin || entityId}`,
        description: `Case opened from the explainability drawer for entity ${data.entity?.cin || entityId} with risk score ${score ?? 'n/a'}`,
        company_cin: data.entity?.cin,
        priority: score && score >= RISK_THRESHOLDS.high ? 2 : score && score >= RISK_THRESHOLDS.medium ? 1 : 0,
      })
      onClose()
      navigate(`/case/${res.data.id}/export`)
    } catch (err) {
      console.error(err)
      alert('Failed to open case')
    } finally {
      setExporting(false)
    }
  }
  const decomRows: Array<[string, number | null | undefined]> = [
    ['Cycle membership', decom.cycle],
    ['Shared director', decom.shared_director],
    ['Shared address', decom.shared_address],
    ['e-Way Bill mismatch', decom.eway_mismatch],
    ['Degree', decom.degree],
    ['PageRank', decom.pagerank],
    ['Betweenness', decom.betweenness],
  ]

  return (
    <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose}>
      <div
        className="absolute right-0 top-0 h-full w-[480px] max-w-full panel-raised rounded-l-xl border-r-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <div className="micro-label">Structural evidence</div>
            <h2 className="text-lg font-semibold mt-0.5">Why flagged?</h2>
          </div>
          <button onClick={onClose} className="text-text-secondary hover:text-text-primary text-xl leading-none" aria-label="Close">✕</button>
        </div>

        <div className="px-6 py-5 space-y-6 overflow-y-auto h-[calc(100%-61px)]">
          {/* Score */}
          <div className="flex items-center gap-3">
            <RiskBadge score={data.entity?.risk_score} />
            <span className="mono-id truncate">{data.entity?.name || data.entity?.cin}</span>
            {decom.source && (
              <span className="ml-auto text-[10px] uppercase tracking-wide text-text-secondary">{decom.source}</span>
            )}
          </div>

          {/* Reason */}
          <div>
            <div className="micro-label mb-2">Plain-language reason</div>
            <ul className="space-y-2">
              {data.reasons.map((reason, i) => (
                <li key={i} className="flex gap-2 text-sm text-text-primary leading-snug">
                  <span className="text-accent-ring mt-0.5">▸</span>
                  {reason}
                </li>
              ))}
            </ul>
          </div>

          {/* Mini-subgraph of the evidence only */}
          {cycle && cycle.companies?.length > 1 && (
            <div>
              <div className="micro-label mb-2">Evidence subgraph (invoice loop)</div>
              <div className="panel p-2">
                <EvidenceMiniGraph companyNames={cycle.companies.map((c) => c.name)} />
                <ol className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] text-text-secondary">
                  {cycle.companies.map((c, i) => (
                    <li key={c.cin} className="truncate">
                      <span className="text-text-primary font-semibold">{i + 1}.</span> {c.name}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}

          {/* Detected loops with real amounts + date span */}
          {cycle && (
            <div>
              <div className="micro-label mb-2">Detected loop</div>
              <div className="panel p-3">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-risk-critical font-semibold">
                    {cycle.hop_count}-hop invoice cycle across {cycle.company_count} companies
                  </span>
                  <span className="font-mono">₹{Number(cycle.total_invoice_amount || 0).toLocaleString('en-IN')}</span>
                </div>
                {cycle.date_span && (
                  <div className="text-[11px] text-text-secondary mb-2">
                    {cycle.date_span.first} → {cycle.date_span.last}
                    {cycle.date_span.span_days != null && <> · over {cycle.date_span.span_days} days</>}
                  </div>
                )}
                <div className="font-mono text-[11px] text-text-secondary truncate mb-2">
                  {cycle.companies?.map((m) => m.name).join(' → ')} → {cycle.companies?.[0]?.name}
                </div>
                {cycle.invoices?.length > 0 && (
                  <table className="w-full text-[10px] font-mono">
                    <tbody>
                      {cycle.invoices.map((inv, i) => (
                        <tr key={i} className="border-t border-border/50">
                          <td className="py-0.5 pr-2 text-text-secondary">{inv.invoice_no}</td>
                          <td className="py-0.5 pr-2 text-text-primary">₹{Number(inv.amount || 0).toLocaleString('en-IN')}</td>
                          <td className="py-0.5 text-text-secondary truncate">{inv.invoice_date}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}

          {/* Louvain community evidence */}
          {(evidence.communities?.length ?? 0) > 0 && (
            <div>
              <div className="micro-label mb-2">Fraud community (Louvain)</div>
              {evidence.communities!.map((cm, i) => (
                <div key={i} className="text-xs text-text-primary mb-1">
                  Community <span className="mono-id">{cm.community_id}</span> — {cm.member_count} companies
                </div>
              ))}
            </div>
          )}

          {(evidence.shared_directors?.length ?? 0) > 0 && (
            <div>
              <div className="micro-label mb-2">Shared directors</div>
              {evidence.shared_directors.map((sd, i) => (
                <div key={i} className="text-xs text-text-primary mb-1">
                  <span className="font-semibold">{sd.director}</span>
                  {sd.din && <span className="text-text-secondary"> (DIN {sd.din})</span>} — also director of{' '}
                  <span className="mono-id">{sd.companies?.join(', ')}</span>
                </div>
              ))}
            </div>
          )}

          {(evidence.shared_addresses?.length ?? 0) > 0 && (
            <div>
              <div className="micro-label mb-2">Shared registered addresses</div>
              {evidence.shared_addresses.map((sa, i) => (
                <div key={i} className="text-xs text-text-primary mb-1">
                  <span className="font-mono">{sa.address}</span> ({sa.state}) — {sa.companies?.join(', ')}
                </div>
              ))}
            </div>
          )}

          {eway.length > 0 && (
            <div>
              <div className="micro-label mb-2">e-Way Bill mismatch</div>
              <div className="panel p-3 space-y-1">
                {eway.map((m, i) => (
                  <div key={i} className="flex justify-between text-[11px] font-mono">
                    <span className="text-text-secondary truncate mr-2">{m.invoice_no || '—'}</span>
                    <span className="text-text-primary">₹{Number(m.amount || 0).toLocaleString('en-IN')}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Feature attribution for the risk score */}
          <div>
            <div className="micro-label mb-2">Risk decomposition</div>
            <div className="panel p-3 space-y-1">
              {decomRows.map(([label, val]) => (
                <div key={label} className="flex justify-between text-[11px]">
                  <span className="text-text-secondary">{label}</span>
                  <span className="font-mono text-text-primary">{val != null ? `+${Number(val).toFixed(1)}` : '—'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Link
              to={`/entity/${entityId}/network`}
              onClick={onClose}
              className="btn-secondary w-full"
            >
              View full network →
            </Link>
            <button
              onClick={exportCase}
              disabled={exporting}
              className="btn-primary w-full"
            >
              {exporting ? 'Opening…' : 'Export case →'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
