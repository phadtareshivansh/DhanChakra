import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../utils/api'
import { WorklistResponse } from '../types/api'
import RiskBadge from '../components/RiskBadge'

type SortKey = 'risk_score' | 'name' | 'paid_up_capital'
type Direction = 'desc' | 'asc'

export default function Worklist() {
  const [data, setData] = useState<WorklistResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<SortKey>('risk_score')
  const [direction, setDirection] = useState<Direction>('desc')
  const [state, setState] = useState('')
  const [sector, setSector] = useState('')
  const [minScore, setMinScore] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ sort, direction, page: String(page), page_size: String(pageSize) })
      if (state) params.set('state', state)
      if (sector) params.set('sector', sector)
      if (minScore) params.set('min_score', minScore)
      const res = await api.get(`/worklist?${params}`)
      setData(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [sort, direction, state, sector, minScore, page])

  const toggleSort = (key: SortKey) => {
    if (sort === key) {
      setDirection(direction === 'desc' ? 'asc' : 'desc')
    } else {
      setSort(key)
      setDirection('desc')
    }
  }

  const SortIcon = ({ col }: { col: SortKey }) => (
    sort === col ? <span className="ml-1 text-accent-ring">{direction === 'desc' ? '↓' : '↑'}</span> : null
  )

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Risk Worklist</h1>
        <p className="text-sm text-text-secondary mt-1">
          {data ? `${data.total} entities ranked` : 'Loading…'} — sorted by risk score by default.
        </p>
      </div>

      <div className="panel p-4 flex flex-wrap items-end gap-3">
        <div>
          <label className="micro-label block mb-1">State</label>
          <input className="input" placeholder="e.g. Maharashtra" value={state} onChange={(e) => { setPage(1); setState(e.target.value) }} />
        </div>
        <div>
          <label className="micro-label block mb-1">Sector (NIC code)</label>
          <input className="input" placeholder="e.g. 62099" value={sector} onChange={(e) => { setPage(1); setSector(e.target.value) }} />
        </div>
        <div>
          <label className="micro-label block mb-1">Min risk score</label>
          <input className="input w-28" type="number" min={0} max={100} value={minScore} onChange={(e) => { setPage(1); setMinScore(e.target.value) }} />
        </div>
        <button
          className="btn-secondary"
          onClick={() => { setState(''); setSector(''); setMinScore(''); setPage(1) }}
        >
          Clear filters
        </button>
      </div>

      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-raised">
            <tr className="text-left text-micro uppercase tracking-micro text-text-secondary">
              <th className="py-2.5 px-4 cursor-pointer hover:text-text-primary" onClick={() => toggleSort('risk_score')}>Risk Score <SortIcon col="risk_score" /></th>
              <th className="py-2.5 px-4 cursor-pointer hover:text-text-primary" onClick={() => toggleSort('name')}>Entity Name <SortIcon col="name" /></th>
              <th className="py-2.5 px-4">GSTIN / CIN</th>
              <th className="py-2.5 px-4">State</th>
              <th className="py-2.5 px-4">Sector</th>
              <th className="py-2.5 px-4 cursor-pointer hover:text-text-primary" onClick={() => toggleSort('paid_up_capital')}>Paid-up Capital <SortIcon col="paid_up_capital" /></th>
              <th className="py-2.5 px-4">Loops</th>
              <th className="py-2.5 px-4">Community</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                {[0, 1, 2, 3, 4, 5, 6, 7].map((i) => (
                  <td key={i} className="px-4 py-4"><div className="skeleton h-5" /></td>
                ))}
              </tr>
            )}
            {!loading && data?.items.map((item) => (
              <tr key={item.cin} className="border-t border-border hover:bg-raised/40">
                <td className="px-4 py-3"><RiskBadge score={item.risk_score} /></td>
                <td className="px-4 py-3">
                  <Link to={`/entity/${item.cin}/network`} className="font-medium hover:text-accent-ring">{item.name}</Link>
                  <div className="text-[11px] text-text-secondary mt-0.5">{item.status || ''}</div>
                </td>
                <td className="px-4 py-3 mono-id text-[12px]">{item.gstin || item.cin}</td>
                <td className="px-4 py-3 text-text-secondary">{item.state || '—'}</td>
                <td className="px-4 py-3 mono-id text-[12px] text-text-secondary">{item.nic_code || '—'}</td>
                <td className="px-4 py-3 font-mono text-[12px]">₹{(item.paid_up_capital ?? 0).toLocaleString('en-IN')}</td>
                <td className="px-4 py-3 text-text-secondary">{item.cycle_count || 0}</td>
                <td className="px-4 py-3 mono-id text-[12px] text-text-secondary">{item.community_id || '—'}</td>
              </tr>
            ))}
            {!loading && data?.items.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-text-secondary">
                  No entities match these filters — try widening the risk range.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        <div className="px-4 py-3 border-t border-border flex items-center justify-between text-sm">
          <span className="text-text-secondary">{data?.total || 0} entities · page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button className="btn-secondary btn-compact" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <button className="btn-secondary btn-compact" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </div>
  )
}