import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../utils/api'
import { StatsOverview, WorklistItem } from '../types/api'
import StatTile from '../components/StatTile'
import RiskBadge from '../components/RiskBadge'

export default function Dashboard() {
  const [stats, setStats] = useState<StatsOverview | null>(null)
  const [topRisks, setTopRisks] = useState<WorklistItem[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')

  useEffect(() => {
    const load = async () => {
      try {
        const [statsRes, workRes] = await Promise.all([
          api.get('/stats/overview'),
          api.get('/worklist?sort=risk_score&direction=desc&page=1&page_size=5'),
        ])
        setStats(statsRes.data)
        setTopRisks(workRes.data.items)
      } catch (err) {
        console.error(err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const fmt = (n?: number) => (n ?? 0).toLocaleString('en-IN')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Fraud Intelligence Overview</h1>
          <p className="text-sm text-text-secondary mt-1">
            Circular trading rings, shell-company networks, and ITC risk at a glance.
          </p>
        </div>
        <Link to="/worklist" className="btn-primary">View full worklist →</Link>
      </div>

      {loading ? (
        <div className="grid grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="panel p-4 h-28"><div className="skeleton h-full" /></div>)}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile label="Entities scanned" value={fmt(stats?.companies)} sub={`${fmt(stats?.directors)} directors linked`} accent="teal" />
          <StatTile label="Flagged entities" value={fmt(stats?.flagged_entities)} sub={`${fmt(stats?.cycles_detected)} circular loops detected`} accent="red" />
          <StatTile label="Est. ITC at risk" value={`₹${fmt(Math.round(stats?.estimated_itc_at_risk ?? 0))}`} sub="flagged capital base" accent="amber" />
          <StatTile label="Top risk state" value={stats?.top_risk_state || '—'} sub={`${fmt(stats?.open_cases)} open cases`} accent="green" />
        </div>
      )}

      <div className="grid grid-cols-3 gap-6">
        <div className="panel p-4 col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Highest-risk entities</h2>
            <Link to="/worklist" className="text-sm text-accent-ring hover:underline">See all →</Link>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-micro uppercase tracking-micro text-text-secondary border-b border-border">
                <th className="py-2 pr-4">Entity</th>
                <th className="py-2 pr-4">GSTIN / CIN</th>
                <th className="py-2 pr-4">State</th>
                <th className="py-2 pr-4">Loops</th>
                <th className="py-2 text-right">Risk</th>
              </tr>
            </thead>
            <tbody>
              {topRisks.map((item) => (
                <tr key={item.cin} className="border-b border-border last:border-0 hover:bg-raised/50">
                  <td className="py-2.5 pr-4">
                    <Link to={`/entity/${item.cin}/network`} className="font-medium hover:text-accent-ring">
                      {item.name}
                    </Link>
                  </td>
                  <td className="py-2.5 pr-4 mono-id text-[12px]">{item.gstin || item.cin}</td>
                  <td className="py-2.5 pr-4 text-text-secondary">{item.state || '—'}</td>
                  <td className="py-2.5 pr-4 text-text-secondary">{item.cycle_count || 0}</td>
                  <td className="py-2.5 text-right"><RiskBadge score={item.risk_score} /></td>
                </tr>
              ))}
              {topRisks.length === 0 && (
                <tr><td colSpan={5} className="py-8 text-center text-text-secondary text-sm">No entities scored yet — run analytics first.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="panel p-4">
          <h2 className="text-lg font-semibold mb-4">Quick search</h2>
          <form onSubmit={(e) => { e.preventDefault(); window.location.href = `/search?q=${encodeURIComponent(query)}` }} className="space-y-3">
            <input
              className="input w-full"
              placeholder="Enter GSTIN, CIN, or name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button className="btn-primary w-full" disabled={!query.trim()}>Search</button>
          </form>
          <div className="mt-6 pt-4 border-t border-border space-y-3 text-sm">
            <Link to="/loops" className="block text-accent-ring hover:underline">Detected loops →</Link>
            <Link to="/cases" className="block text-accent-ring hover:underline">Open case files →</Link>
            <Link to="/ingest" className="block text-accent-ring hover:underline">Ingest new data →</Link>
          </div>
        </div>
      </div>
    </div>
  )
}