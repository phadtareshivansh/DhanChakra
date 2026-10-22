import { t } from '../i18n'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { SearchResult } from '../types/api'
import api from '../utils/api'
import RiskBadge from '../components/RiskBadge'

export default function EntitySearch() {
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('q') || '')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setLoading(true)
    setError(null)
    try {
      const response = await api.get(`/entities/search?q=${encodeURIComponent(query)}`)
      setResults(response.data.results)
      setSearched(true)
    } catch (err) {
      setError(t('Failed to search entities'))
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">{t('Entity Search')}</h1>
        <p className="text-sm text-text-secondary mt-1">{t('Search by GSTIN, CIN, company name, DIN, or IFSC.')}</p>
      </div>

      <form onSubmit={handleSearch} className="flex gap-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('e.g. 27AAAAA0000A1Z5 or Alpha Corp…')}
          className="input flex-1"
        />
        <button type="submit" disabled={loading || !query.trim()} className="btn-primary">
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm">
          {error}
        </div>
      )}

      {loading && (
        <div className="panel p-4 space-y-3">
          {[0, 1, 2].map((i) => <div key={i} className="skeleton h-12" />)}
        </div>
      )}

      {!loading && searched && results.length > 0 && (
        <div className="panel overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-raised">
              <tr className="text-left text-micro uppercase tracking-micro text-text-secondary">
                <th className="py-2.5 px-4">{t('Type')}</th>
                <th className="py-2.5 px-4">{t('Name')}</th>
                <th className="py-2.5 px-4">{t('Identifier')}</th>
                <th className="py-2.5 px-4">{t('State')}</th>
                <th className="py-2.5 px-4">{t('Risk')}</th>
                <th className="py-2.5 px-4 text-right">{t('Actions')}</th>
              </tr>
            </thead>
            <tbody>
              {results.map((result) => (
                <tr key={result.id} className="border-t border-border hover:bg-raised/40">
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded-full text-micro font-semibold bg-accent/15 text-accent-ring">
                      {result.type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium">{result.name}</td>
                  <td className="px-4 py-3 mono-id text-[12px]">{result.identifier}</td>
                  <td className="px-4 py-3 text-text-secondary">{result.state || '—'}</td>
                  <td className="px-4 py-3"><RiskBadge score={result.risk_score} /></td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/entity/${result.id}/network`} className="text-accent-ring hover:underline text-sm">
                      {t('View Network →')}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && searched && results.length === 0 && (
        <div className="panel p-12 text-center text-text-secondary">
          <div className="text-3xl mb-2">⌕</div>
          {t('No entities match "')}{query}{t('" — try a broader name or a partial CIN/GSTIN.')}
        </div>
      )}
    </div>
  )
}