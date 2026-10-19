import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Case } from '../types/api'
import api from '../utils/api'
import RiskBadge from '../components/RiskBadge'

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-accent/15 text-accent-ring',
  in_progress: 'bg-amber/20 text-amber',
  closed: 'bg-text-disabled/20 text-text-secondary',
}

export default function CasesView() {
  const [params] = useSearchParams()
  const [cases, setCases] = useState<Case[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newCase, setNewCase] = useState({ title: '', description: '', company_cin: '', priority: 0 })
  const [statusFilter, setStatusFilter] = useState('')
  const [highlight] = useState(params.get('highlight') || null)
  const [exporting, setExporting] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const fetchCases = async () => {
    setLoading(true)
    try {
      const res = await api.get(`/cases${statusFilter ? `?status=${statusFilter}` : ''}`)
      setCases(res.data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCases() }, [statusFilter])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const response = await api.post('/cases', { ...newCase, priority: Number(newCase.priority) })
      setCases([response.data, ...cases])
      setShowCreate(false)
      setNewCase({ title: '', description: '', company_cin: '', priority: 0 })
    } catch (err) {
      console.error(err)
      alert('Failed to create case')
    }
  }

  const setStatus = async (c: Case, status: string) => {
    try {
      const res = await api.patch(`/cases/${c.id}`, { status })
      setCases(cases.map((x) => (x.id === c.id ? res.data : x)))
    } catch (err) {
      console.error(err)
    }
  }

  const exportCase = async (c: Case) => {
    setExporting(c.id)
    try {
      const res = await api.post(`/cases/${c.id}/export?include_network=true`)
      const bundle = JSON.stringify(res.data.payload, null, 2)
      const blob = new Blob([bundle], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dhan-chakra-case-${c.id.slice(0, 8)}.json`
      a.click()
      URL.revokeObjectURL(url)
      setDone(c.id)
      setTimeout(() => setDone(null), 3000)
    } catch (err) {
      console.error(err)
      alert('Export failed')
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Case Files</h1>
          <p className="text-sm text-text-secondary mt-1">Fraud investigations opened against flagged entities and rings.</p>
        </div>
        <button className="btn-primary" onClick={() => setShowCreate(true)}>+ New case</button>
      </div>

      <div className="flex gap-2">
        {['', 'open', 'in_progress', 'closed'].map((s) => (
          <button
            key={s}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-colors ${
              statusFilter === s ? 'bg-accent text-white' : 'bg-raised text-text-secondary hover:text-text-primary'
            }`}
            onClick={() => setStatusFilter(s)}
          >
            {s === '' ? 'All' : s.replace('_', ' ')}
          </button>
        ))}
      </div>

      {showCreate && (
        <form onSubmit={handleCreate} className="panel p-5 space-y-4">
          <h3 className="text-lg font-semibold">Create new case</h3>
          <div>
            <label className="micro-label block mb-1">Title</label>
            <input className="input w-full" value={newCase.title} onChange={(e) => setNewCase({ ...newCase, title: e.target.value })} required />
          </div>
          <div>
            <label className="micro-label block mb-1">Description</label>
            <textarea className="input w-full h-20 pt-2" rows={3} value={newCase.description} onChange={(e) => setNewCase({ ...newCase, description: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="micro-label block mb-1">Company CIN</label>
              <input className="input w-full font-mono" placeholder="L12345MH2020PLC123456" value={newCase.company_cin} onChange={(e) => setNewCase({ ...newCase, company_cin: e.target.value })} />
            </div>
            <div>
              <label className="micro-label block mb-1">Priority</label>
              <select className="input w-full" value={newCase.priority} onChange={(e) => setNewCase({ ...newCase, priority: Number(e.target.value) })}>
                <option value={0}>0 — Standard</option>
                <option value={1}>1 — Priority</option>
                <option value={2}>2 — Critical</option>
              </select>
            </div>
          </div>
          <div className="flex gap-3 pt-2">
            <button type="submit" className="btn-primary">Create</button>
            <button type="button" className="btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </form>
      )}

      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-raised">
            <tr className="text-left text-micro uppercase tracking-micro text-text-secondary">
              <th className="py-2.5 px-4">Case</th>
              <th className="py-2.5 px-4">Status</th>
              <th className="py-2.5 px-4">Priority</th>
              <th className="py-2.5 px-4">Company CIN</th>
              <th className="py-2.5 px-4">Updated</th>
              <th className="py-2.5 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>{[0, 1, 2, 3, 4, 5].map((i) => <td key={i} className="px-4 py-4"><div className="skeleton h-5" /></td>)}</tr>
            )}
            {!loading && cases.map((c) => (
              <tr key={c.id} className={`border-t border-border hover:bg-raised/40 ${highlight === c.id ? 'bg-accent/10' : ''}`}>
                <td className="px-4 py-3">
                  <div className="font-medium">{c.title}</div>
                  {c.company_cin && (
                    <Link to={`/entity/${c.company_cin}/network`} className="text-[11px] mono-id text-accent-ring hover:underline">
                      {c.company_cin}
                    </Link>
                  )}
                </td>
                <td className="px-4 py-3">
                  <select
                    className={`px-2 py-1 rounded-full text-micro font-semibold border-none ${STATUS_COLORS[c.status] || ''}`}
                    value={c.status}
                    onChange={(e) => setStatus(c, e.target.value)}
                  >
                    <option value="open">open</option>
                    <option value="in_progress">in_progress</option>
                    <option value="closed">closed</option>
                  </select>
                  <div className="mt-1"><RiskBadge score={c.risk_score} showScore={false} /></div>
                </td>
                <td className="px-4 py-3 font-mono text-data">{c.priority}</td>
                <td className="px-4 py-3 mono-id text-[12px]">{c.company_cin || '—'}</td>
                <td className="px-4 py-3 text-text-secondary">{new Date(c.updated_at).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <Link to={`/case/${c.id}/export`} className="btn-secondary btn-compact">Preview</Link>
                    <button className="btn-secondary btn-compact" onClick={() => exportCase(c)} disabled={exporting === c.id}>
                      {done === c.id ? '✓ Exported' : exporting === c.id ? 'Exporting…' : 'Export JSON'}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {!loading && cases.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-text-secondary">
                  No cases yet — open one from the worklist or entity page.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}