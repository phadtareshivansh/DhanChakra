import { Link, useLocation, useNavigate, Outlet } from 'react-router-dom'
import { useState, useEffect, useRef } from 'react'
import api from '../utils/api'
import { SearchResult } from '../types/api'
import RiskBadge from './RiskBadge'
import { RISK_THRESHOLDS } from '../config/risk'

export default function Layout() {
  const location = useLocation()
  const navigate = useNavigate()
  const [user, setUser] = useState<any>(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [showResults, setShowResults] = useState(false)
  const [showLegend, setShowLegend] = useState(true)
  const [notifs, setNotifs] = useState<any[]>([])
  const [showNotifs, setShowNotifs] = useState(false)
  const searchRef = useRef<HTMLDivElement>(null)
  const notifRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get('/notifications?unread_only=false').then(r => setNotifs(r.data || [])).catch(() => {})
  }, [])

  useEffect(() => {
    const stored = localStorage.getItem('dhanchakra_user')
    if (stored) setUser(JSON.parse(stored))
  }, [])

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false)
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifs(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    const timeout = setTimeout(async () => {
      try {
        const res = await api.get(`/entities/search?q=${encodeURIComponent(query)}&limit=8`)
        setResults(res.data.results)
        setShowResults(true)
      } catch {
        setResults([])
      }
    }, 250)
    return () => clearTimeout(timeout)
  }, [query])

  const navItems = [
    { path: '/', label: 'Dashboard', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' },
    { path: '/worklist', label: 'Worklist', icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4' },
    { path: '/loops', label: 'Loops', icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
    { path: '/cases', label: 'Cases', icon: 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' },
    { path: '/ingest', label: 'Ingest', icon: 'M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12' },
    { path: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ]

  const crumbs = location.pathname.split('/').filter(Boolean).map((seg, i, arr) => ({
    label: seg.charAt(0).toUpperCase() + seg.slice(1),
    path: '/' + arr.slice(0, i + 1).join('/'),
  }))

  const logout = () => {
    localStorage.removeItem('dhanchakra_token')
    localStorage.removeItem('dhanchakra_user')
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-canvas text-text-primary">
      <aside className="fixed inset-y-0 left-0 z-40 w-60 bg-surface border-r border-border">
        <div className="flex h-16 items-center px-5 border-b border-border">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/favicon.svg" alt="Dhan-Chakra" className="w-8 h-8 rounded-lg border border-border object-cover bg-surface" />
            <div>
              <div className="text-lg font-bold leading-tight">Dhan-Chakra</div>
              <div className="text-[10px] uppercase tracking-micro text-text-secondary">Graph-AI Fraud Engine</div>
            </div>
          </Link>
        </div>

        <nav className="p-3 space-y-1">
          {navItems.map((item) => {
            const active = item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  active ? 'bg-accent/15 text-accent-ring' : 'text-text-secondary hover:bg-raised hover:text-text-primary'
                }`}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={item.icon} />
                </svg>
                {item.label}
              </Link>
            )
          })}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-sm font-semibold">
              {(user?.display_name || user?.email || 'U')[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium truncate">{user?.display_name || user?.email || 'Analyst'}</div>
              <div className="text-[10px] uppercase tracking-micro text-text-secondary">{user?.role || 'guest'}</div>
            </div>
            {user && (
              <button onClick={logout} className="text-text-secondary hover:text-risk-critical text-xs" title="Log out">⏻</button>
            )}
          </div>
        </div>
      </aside>

      <div className="ml-60 min-h-screen">
        <header className="sticky top-0 z-30 bg-canvas/90 backdrop-blur border-b border-border">
          <div className="px-6 py-3 flex items-center gap-6">
            {crumbs.length > 0 ? (
              <nav className="text-xs text-text-secondary">
                <Link to="/" className="hover:text-accent-ring">Home</Link>
                {crumbs.map((c, i) => (
                  <span key={c.path}>
                    <span className="mx-1.5 text-text-disabled">›</span>
                    <Link to={c.path} className={i === crumbs.length - 1 ? 'text-text-primary' : 'hover:text-accent-ring'}>
                      {c.label}
                    </Link>
                  </span>
                ))}
              </nav>
            ) : <div />}
            <div ref={searchRef} className="relative ml-auto w-80">
              <input
                className="input w-full pl-9"
                placeholder="Search GSTIN / CIN / company name…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => query.trim().length >= 2 && setShowResults(true)}
              />
              <svg className="w-4 h-4 absolute left-3 top-3 text-text-disabled" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              {showResults && results.length > 0 && (
                <div className="absolute top-11 right-0 w-full panel-raised rounded-lg shadow-xl overflow-hidden">
                  {results.map((r) => (
                    <button
                      key={r.id}
                      className="w-full text-left px-4 py-2.5 hover:bg-raised border-b border-border last:border-0"
                      onClick={() => { setShowResults(false); setQuery(''); navigate(`/entity/${r.id}/network`) }}
                    >
                      <div className="text-sm font-medium">{r.name}</div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="mono-id text-[11px]">{r.identifier}</span>
                        <span className="text-[10px] uppercase tracking-micro text-text-secondary">{r.type}</span>
                        {r.risk_score !== undefined && <RiskBadge score={r.risk_score} showScore={false} />}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div ref={notifRef} className="relative ml-2">
              <button className="btn-ghost btn-compact relative" onClick={() => setShowNotifs(!showNotifs)}>
                <span>🔔</span>
                {notifs.some((n: any) => !n.read) && <span className="absolute -top-1 -right-1 w-2 h-2 bg-red-500 rounded-full" />}
              </button>
              {showNotifs && (
                <div className="absolute top-9 right-0 w-80 panel-raised rounded-lg shadow-xl overflow-hidden">
                  <div className="px-3 py-2 text-xs font-medium border-b border-border">Notifications</div>
                  {notifs.length === 0 && <div className="px-3 py-2 text-xs text-text-secondary">No notifications</div>}
                  {notifs.slice(0, 10).map((n: any) => (
                    <button key={n.id} className="w-full text-left px-3 py-2 text-xs border-b border-border hover:bg-raised" onClick={async()=>{try{await api.post(`/notifications/${n.id}/read`); setNotifs(notifs.map(x=>x.id===n.id?{...x,read:true}:x));}catch{}}}>
                      <div className={n.read ? 'text-text-secondary' : 'text-text-primary'}>{n.message}</div>
                      <div className="text-[10px] text-text-disabled mt-0.5">{n.created_at?.slice(0,16)}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </header>

        {showLegend && (
          <div className="px-6 pt-4">
            <div className="panel px-4 py-2 flex items-center gap-5 text-[11px] text-text-secondary">
              <span className="micro-label">Risk legend</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-risk-critical mr-1" />Critical ≥{RISK_THRESHOLDS.critical}</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-risk-high mr-1" />High {RISK_THRESHOLDS.high}–{RISK_THRESHOLDS.critical - 1}</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-risk-medium mr-1" />Medium {RISK_THRESHOLDS.medium}–{RISK_THRESHOLDS.high - 1}</span>
              <span><span className="inline-block w-2 h-2 rounded-full bg-risk-low mr-1" />Low &lt;{RISK_THRESHOLDS.medium}</span>
              <button onClick={() => setShowLegend(false)} className="ml-auto text-text-disabled hover:text-text-primary">✕</button>
            </div>
          </div>
        )}

        <main className="p-6"><Outlet /></main>
      </div>
    </div>
  )
}