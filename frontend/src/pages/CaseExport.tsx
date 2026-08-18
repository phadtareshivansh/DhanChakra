import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../utils/api'
import { riskLevel } from '../components/RiskBadge'

export default function CaseExport() {
  const { id } = useParams<{ id: string }>()
  const [payload, setPayload] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    api.get(`/cases/${id}/export/preview`)
      .then((res) => setPayload(res.data.payload))
      .catch((err) => setError(err.response?.data?.detail?.message || 'Failed to load'))
      .finally(() => setLoading(false))
  }, [id])

  const download = async () => {
    try {
      const res = await api.post(`/cases/${id}/export?include_network=true`)
      const blob = new Blob([JSON.stringify(res.data.payload, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dhan-chakra-case-${id!.slice(0, 8)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert('Export failed')
    }
  }

  if (loading) {
    return <div className="panel p-6"><div className="skeleton h-40" /></div>
  }
  if (error) {
    return <div className="panel p-10 text-center text-risk-critical">{error}</div>
  }

  const caseData = payload?.case
  const entity = payload?.entity
  const evidence = payload?.evidence
  const { label } = riskLevel(entity?.risk_score)

  return (
    <div>
      {/* Light-mode print-ready preview per 03_UIUX_Design.md §2.4 */}
      <div className="bg-[#F7F9FB] text-[#141B24] rounded-xl p-8 shadow-lg print-area">
        <div className="flex items-start justify-between border-b-2 border-[#141B24] pb-4 mb-6">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D]">Dhan-Chakra · Case Evidence Bundle</div>
            <h1 className="text-2xl font-bold mt-1">{caseData?.title}</h1>
            <div className="font-mono text-xs mt-1 text-[#5B6B7D]">Case {caseData?.id}</div>
          </div>
          <div className="text-right">
            <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D]">Status</div>
            <div className="font-medium">{caseData?.status}</div>
            <div className="text-xs text-[#5B6B7D] mt-1">
              Opened {caseData?.created_at ? new Date(caseData.created_at).toLocaleDateString() : '—'}
            </div>
          </div>
        </div>

        {entity && (
          <div className="mb-6">
            <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D] mb-2">Subject entity</div>
            <div className="flex items-center gap-4">
              <div>
                <div className="text-lg font-semibold">{entity.name}</div>
                <div className="font-mono text-sm">CIN {entity.cin} · GSTIN {entity.gstin}</div>
              </div>
              <div className="ml-auto text-right">
                <div className="text-3xl font-bold font-mono">{entity.risk_score ?? '—'}</div>
                <div className="text-xs font-semibold uppercase">{label}</div>
              </div>
            </div>
          </div>
        )}

        {evidence && (
          <div className="mb-6">
            <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D] mb-2">Rationale</div>
            <ul className="space-y-1.5 text-sm">
              {evidence.reasons?.map((r: string, i: number) => (
                <li key={i} className="flex gap-2"><span className="text-[#C0392B] font-bold">▸</span>{r}</li>
              ))}
            </ul>

            {evidence.evidence?.cycles?.length > 0 && (
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D] mb-2">Detected loops</div>
                {evidence.evidence.cycles.map((c: any, i: number) => (
                  <div key={i} className="border border-[#E1E7ED] rounded p-3 mb-2 bg-white">
                    <div className="text-sm font-semibold text-[#C0392B]">{c.hop_count}-hop cycle · ₹{Number(c.total_amount || 0).toLocaleString('en-IN')}</div>
                    <div className="font-mono text-xs mt-1 text-[#5B6B7D]">{c.members?.map((m: any) => m.name).join(' → ')}</div>
                  </div>
                ))}
              </div>
            )}

            {evidence.evidence?.shared_directors?.length > 0 && (
              <div className="mt-4">
                <div className="text-xs font-semibold uppercase tracking-wide text-[#5B6B7D] mb-2">Shared directors</div>
                {evidence.evidence.shared_directors.map((sd: any, i: number) => (
                  <div key={i} className="text-sm mb-1">
                    <span className="font-semibold">{sd.director}</span> — {sd.companies?.join(', ')}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="text-xs text-[#5B6B7D] border-t border-[#E1E7ED] pt-3">
          Exported {payload?.exported_at ? new Date(payload.exported_at).toLocaleString() : '—'} · Dhan-Chakra graph-AI engine ·
          scores are audit-prioritization aids, not legal verdicts
        </div>
      </div>

      <div className="flex gap-3 mt-4 print:hidden">
        <button className="btn-primary" onClick={download}>⬇ Download JSON bundle</button>
        <button className="btn-secondary" onClick={() => window.print()}>🖨 Print / save as PDF</button>
        <Link to={`/cases?highlight=${id}`} className="btn-secondary">Back to cases</Link>
      </div>
    </div>
  )
}