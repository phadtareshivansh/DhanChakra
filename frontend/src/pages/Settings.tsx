import { t } from '../i18n'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../utils/api'
import { RISK_THRESHOLDS } from '../config/risk'

const THRESHOLDS_KEY = 'dhanchakra_thresholds'

export default function Settings() {
  const [thresholds, setThresholds] = useState({ ...RISK_THRESHOLDS })
  const [saved, setSaved] = useState(false)
  const [apiHealth, setApiHealth] = useState<string | null>(null)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(THRESHOLDS_KEY)
    if (stored) setThresholds(JSON.parse(stored))
    api.get('/health').then((r) => setApiHealth(r.data.status)).catch(() => setApiHealth('unreachable'))
    // The Users admin page is only meaningful for the Super Admin.
    try {
      const stored = localStorage.getItem('dhanchakra_user')
      if (stored) setIsAdmin(JSON.parse(stored).role === 'admin')
    } catch { /* ignore malformed stored user */ }
  }, [])

  const save = () => {
    localStorage.setItem(THRESHOLDS_KEY, JSON.stringify(thresholds))
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
    window.dispatchEvent(new Event('thresholds-updated'))
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h1 className="text-3xl font-bold">{t('Settings')}</h1>
        <p className="text-sm text-text-secondary mt-1">{t('Demo-scope configuration — risk thresholds from 03_UIUX_Design.md §2.3.')}</p>
      </div>

      <div className="panel p-5 space-y-4">
        <h2 className="text-lg font-semibold">{t('Risk score thresholds')}</h2>
        <div className="grid grid-cols-3 gap-4">
          {(['critical', 'high', 'medium'] as const).map((key) => (
            <div key={key}>
              <label htmlFor={`threshold-${key}`} className="micro-label block mb-1">
                {t(key === 'critical' ? 'Critical' : key === 'high' ? 'High' : 'Medium')} ≥
              </label>
              <input
                id={`threshold-${key}`}
                type="number"
                min={0}
                max={100}
                className="input w-full"
                value={thresholds[key]}
                onChange={(e) => setThresholds({ ...thresholds, [key]: Number(e.target.value) })}
              />
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between pt-2">
          <button className="btn-primary" onClick={save}>{saved ? t('✓ Saved') : t('Save thresholds')}</button>
          <button className="btn-secondary" onClick={() => setThresholds({ ...RISK_THRESHOLDS })}>{t('Reset defaults')}</button>
        </div>
      </div>

      {isAdmin && (
        <div className="panel p-5 space-y-2">
          <h2 className="text-lg font-semibold">{t('User management')}</h2>
          <p className="text-sm text-text-secondary">
            {t('Manage the two standard user slots. Visible to the Super Admin only.')}
          </p>
          <Link to="/admin/users" className="btn-secondary inline-block">{t('Manage users →')}</Link>
        </div>
      )}

      <div className="panel p-5 space-y-2">
        <h2 className="text-lg font-semibold">{t('System status')}</h2>
        <div className="flex items-center gap-2 text-sm">
          <span className={`w-2 h-2 rounded-full ${apiHealth === 'healthy' ? 'bg-success-500' : 'bg-risk-critical'}`} />
          {t('API:')} <span className="mono-id">{apiHealth || t('checking…')}</span>
        </div>
        <div className="text-sm text-text-secondary">
          {t('Graph engine: Neo4j 5.23 + GDS 2.x · Metadata: PostgreSQL 16 · Model: structural-v1 (heuristic, explainable)')}
        </div>
      </div>
    </div>
  )
}