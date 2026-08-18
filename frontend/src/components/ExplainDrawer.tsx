import { ExplainResponse } from '../types/api'
import RiskBadge from './RiskBadge'
import { Link } from 'react-router-dom'

export default function ExplainDrawer({ data, entityId, onClose }: {
  data: ExplainResponse
  entityId: string
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose}>
      <div
        className="absolute right-0 top-0 h-full w-[480px] max-w-full panel-raised rounded-l-xl border-r-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <div className="micro-label">Explainability</div>
            <h2 className="text-lg font-semibold mt-0.5">Why flagged?</h2>
          </div>
          <button onClick={onClose} className="text-text-secondary hover:text-text-primary text-xl leading-none" aria-label="Close">✕</button>
        </div>

        <div className="px-6 py-5 space-y-6 overflow-y-auto h-[calc(100%-61px)]">
          <div className="flex items-center gap-3">
            <RiskBadge score={data.entity?.risk_score} />
            <span className="mono-id truncate">{data.entity?.name || data.entity?.cin}</span>
          </div>

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

          {data.evidence.cycles.length > 0 && (
            <div>
              <div className="micro-label mb-2">Detected loops</div>
              {data.evidence.cycles.map((cycle, i) => (
                <div key={i} className="panel p-3 mb-2">
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-risk-critical font-semibold">{cycle.hop_count}-hop cycle</span>
                    <span className="font-mono">₹{Number(cycle.total_amount || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <div className="font-mono text-[11px] text-text-secondary truncate">
                    {cycle.members?.map((m: any) => m.name).join(' → ')}
                  </div>
                </div>
              ))}
            </div>
          )}

          {data.evidence.shared_directors.length > 0 && (
            <div>
              <div className="micro-label mb-2">Shared directors</div>
              {data.evidence.shared_directors.map((sd, i) => (
                <div key={i} className="text-xs text-text-primary mb-1">
                  <span className="font-semibold">{sd.director}</span> — also director of{' '}
                  <span className="mono-id">{sd.companies?.join(', ')}</span>
                </div>
              ))}
            </div>
          )}

          {data.evidence.shared_addresses.length > 0 && (
            <div>
              <div className="micro-label mb-2">Shared registered addresses</div>
              {data.evidence.shared_addresses.map((sa, i) => (
                <div key={i} className="text-xs text-text-primary mb-1">
                  <span className="font-mono">{sa.address}</span> ({sa.state}) — {sa.companies?.join(', ')}
                </div>
              ))}
            </div>
          )}

          <Link
            to={`/entity/${entityId}/network`}
            onClick={onClose}
            className="btn-secondary w-full"
          >
            View full network →
          </Link>
        </div>
      </div>
    </div>
  )
}