import { t } from '../i18n'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { LoopsResponse } from '../types/api'
import api from '../utils/api'
import RiskBadge from '../components/RiskBadge'

export default function LoopsView() {
  const [data, setData] = useState<LoopsResponse | null>(null)
  const [maxLength, setMaxLength] = useState(6)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const res = await api.get(`/analytics/loops?max_length=${maxLength}`)
        setData(res.data)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [maxLength])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{t('Circular Trading Loops')}</h1>
          <p className="text-sm text-text-secondary mt-1">
            {t('Invoice cycles detected in the transaction graph (A→B→C→A). Red edges in the network view mark these paths.')}
          </p>
        </div>
        <select
          className="input"
          value={maxLength}
          onChange={(e) => setMaxLength(Number(e.target.value))}
        >
          {[3, 4, 5, 6, 8].map((n) => (
            <option key={n} value={n}>{t('Max length:')} {n}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="panel p-4 space-y-3">
          {[0, 1].map((i) => <div key={i} className="skeleton h-24" />)}
        </div>
      ) : (
        <div className="space-y-3">
          {data?.loops.map((loop, i) => {
            const first = loop.companies[0]
            return (
              <div key={i} className="panel p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <span className="px-2 py-0.5 rounded-full bg-risk-critical/15 text-risk-critical text-micro font-bold">
                      {loop.length}{t('-hop cycle')}
                    </span>
                    <span className="font-mono text-data">₹{Number(loop.total_amount || 0).toLocaleString('en-IN')}</span>
                  </div>
                  <Link
                    to={`/entity/${first?.cin || first?.id}/network`}
                    className="text-sm text-accent-ring hover:underline"
                  >
                    {t('Open in network →')}
                  </Link>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {loop.companies.map((c, j) => (
                    <span key={j} className="flex items-center gap-1.5">
                      <Link
                        to={`/entity/${c.cin || c.id}/network`}
                        className="mono-id text-[12px] px-2 py-1 rounded bg-raised hover:bg-accent/20 hover:text-accent-ring"
                        title={c.name}
                      >
                        {c.name || c.cin}
                      </Link>
                      {j < loop.companies.length - 1 && <span className="text-risk-critical text-xs">→</span>}
                    </span>
                  ))}
                  <span className="text-risk-critical text-xs ml-1">↺</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {loop.companies.slice(0, 5).map((c, j) => (
                    <span key={j}><RiskBadge score={c.risk_score} /></span>
                  ))}
                </div>
              </div>
            )
          })}
          {data?.loops.length === 0 && (
            <div className="panel p-12 text-center text-text-secondary">
              {t('No circular loops detected at this length. Run')} <span className="mono-id">{t('POST /analytics/structural')}</span> {t('or ingest more transaction data.')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}