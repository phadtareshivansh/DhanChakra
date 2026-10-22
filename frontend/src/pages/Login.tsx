import { t } from '../i18n'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../utils/api'
import { TokenResponse } from '../types/api'

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const demoHint = import.meta.env.VITE_DEMO_HINT as string | undefined

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await api.post<TokenResponse>('/auth/login', { email, password })
      localStorage.setItem('dhanchakra_token', res.data.access_token)
      // The access token is deliberately short-lived; the refresh token is
      // what keeps the session alive (TASK C1).
      if (res.data.refresh_token) {
        localStorage.setItem('dhanchakra_refresh_token', res.data.refresh_token)
      }
      localStorage.setItem('dhanchakra_user', JSON.stringify(res.data.user))
      navigate('/')
    } catch (err: any) {
      setError(err.response?.data?.detail?.message || t('Login failed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-canvas flex items-center justify-center px-4">
      <div className="panel-raised rounded-xl p-8 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-8">
          <img src="/favicon.svg" alt={t('Dhan-Chakra')} className="w-14 h-14 rounded-xl border border-border object-cover bg-surface" />
          <div>
            <h1 className="text-2xl font-bold">{t('Dhan-Chakra')}</h1>
            <p className="text-xs text-text-secondary mt-0.5">{t('Graph-AI Engine for Shell Company Loops & GST Fraud Detection')}</p>
          </div>
        </div>

        {error && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-risk-critical/10 border border-risk-critical/30 text-risk-critical text-sm">
            {error}
          </div>
        )}

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="micro-label block mb-1.5">{t('Email')}</label>
            <input
              className="input w-full"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t('you@example.gov.in')}
            />
          </div>
          <div>
            <label className="micro-label block mb-1.5">{t('Password')}</label>
            <input
              className="input w-full"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? t('Signing in…') : t('Sign in')}
          </button>
        </form>

        {demoHint && (
          <div className="mt-6 pt-4 border-t border-border text-xs text-text-secondary space-y-1">
            {demoHint.split('|').map((line, i) => (
              <p key={i}><span className="mono-id">{line.trim()}</span></p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}