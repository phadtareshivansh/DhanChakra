import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../utils/api'
import { AuditLogEntry, LoopsResponse, StatsOverview } from '../types/api'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Skeleton, { SkeletonText } from '../components/ui/Skeleton'
import InfoHint from '../components/InfoHint'
import { formatInr, formatInrCompact, relativeTime, titleCase } from '../utils/format'
import { riskLevel } from '../components/RiskBadge'

const BAND_META = [
  { key: 'critical', label: 'Critical', color: 'var(--color-risk-critical)' },
  { key: 'high', label: 'High', color: 'var(--color-risk-high)' },
  { key: 'medium', label: 'Medium', color: 'var(--color-risk-medium)' },
  { key: 'low', label: 'Low', color: 'var(--color-risk-low)' },
] as const

function StatCard({
  label,
  value,
  sub,
  hint,
  tone = 'accent',
}: {
  label: string
  value: string
  sub?: string
  hint?: string
  tone?: 'accent' | 'amber' | 'critical' | 'neutral' | 'low'
}) {
  const color =
    tone === 'critical'
      ? 'var(--color-risk-critical)'
      : tone === 'amber'
        ? 'var(--color-amber)'
        : tone === 'low'
          ? 'var(--color-risk-low)'
          : tone === 'neutral'
            ? 'var(--color-text-primary)'
            : 'var(--color-accent-ring)'
  return (
    <div className="panel relative overflow-hidden p-4">
      <span className="absolute inset-x-0 top-0 h-0.5" style={{ backgroundColor: color }} aria-hidden="true" />
      <div className="flex items-start justify-between gap-2">
        <span className="micro-label">{label}</span>
        {hint && <InfoHint content={hint} />}
      </div>
      <div className="mt-2 font-mono text-2xl font-medium" style={{ color }}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-text-secondary">{sub}</div>}
    </div>
  )
}

function TrendChart({ points }: { points: { period: string; amount: number; invoices: number }[] }) {
  if (points.length === 0) {
    return (
      <EmptyState
        compact
        title="No dated invoices yet"
        description="The trend appears once invoices carrying a return period (or invoice date) are ingested."
        action={
          <Link to="/ingest">
            <Button variant="secondary" size="sm">Import GST invoices</Button>
          </Link>
        }
      />
    )
  }

  const width = 640
  const height = 190
  const padX = 34
  const padY = 20
  const max = Math.max(...points.map((point) => point.amount), 1)
  const stepX = points.length > 1 ? (width - padX * 2) / (points.length - 1) : 0
  const coords = points.map((point, index) => ({
    x: padX + stepX * index,
    y: height - padY - (point.amount / max) * (height - padY * 2),
    point,
  }))
  const line = coords.map(({ x, y }) => `${x},${y}`).join(' ')
  const area = `M ${coords[0].x} ${height - padY} L ${coords.map(({ x, y }) => `${x} ${y}`).join(' L ')} L ${coords[coords.length - 1].x} ${height - padY} Z`
  const tickIndexes = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]))

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-48 w-full" role="img" aria-label="Flagged invoice value by return period">
        <defs>
          <linearGradient id="trend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity="0.35" />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={padX}
            x2={width - padX}
            y1={height - padY - fraction * (height - padY * 2)}
            y2={height - padY - fraction * (height - padY * 2)}
            stroke="var(--color-border)"
            strokeDasharray="3 4"
          />
        ))}
        <path d={area} fill="url(#trend-fill)" />
        <polyline points={line} fill="none" stroke="var(--color-accent)" strokeWidth={2.5} strokeLinejoin="round" />
        {coords.map(({ x, y, point }) => (
          <circle key={`${point.period}-${x}`} cx={x} cy={y} r={4} fill="var(--color-accent)" stroke="var(--color-surface)" strokeWidth={2}>
            <title>{`${point.period}: ${formatInr(point.amount)} across ${point.invoices} invoice(s)`}</title>
          </circle>
        ))}
        {tickIndexes.map((index) => (
          <text
            key={index}
            x={coords[index].x}
            y={height - 4}
            textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'}
            fontSize={10}
            fill="var(--color-text-secondary)"
            fontFamily="IBM Plex Mono, monospace"
          >
            {points[index].period}
          </text>
        ))}
      </svg>
      <div className="mt-1 flex items-center justify-between text-xs text-text-secondary">
        <span>Peak period: {formatInrCompact(max)}</span>
        <span>{points.reduce((sum, point) => sum + point.invoices, 0)} flagged invoices</span>
      </div>
    </div>
  )
}

const ACTION_TONE: Record<string, string> = {
  login_succeeded: 'var(--color-risk-low)',
  login_failed: 'var(--color-risk-critical)',
  login_locked_out: 'var(--color-risk-critical)',
  created_case: 'var(--color-accent)',
  entity_feedback: 'var(--color-amber)',
  exported_case: 'var(--color-accent)',
}

export default function Dashboard() {
  const [stats, setStats] = useState<StatsOverview | null>(null)
  const [loops, setLoops] = useState<LoopsResponse | null>(null)
  const [activity, setActivity] = useState<AuditLogEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [statsRes, loopsRes, auditRes] = await Promise.allSettled([
        api.get<StatsOverview>('/stats/overview'),
        api.get<LoopsResponse>('/analytics/loops?max_length=6'),
        api.get<AuditLogEntry[]>('/audit?limit=8'),
      ])
      if (statsRes.status === 'rejected') {
        throw statsRes.reason
      }
      setStats(statsRes.value.data)
      setLoops(loopsRes.status === 'fulfilled' ? loopsRes.value.data : null)
      setActivity(auditRes.status === 'fulfilled' ? auditRes.value.data : [])
      setLastUpdated(new Date())
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || 'Could not load the intelligence overview.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const distribution = stats?.risk_distribution
  const bandTotal = useMemo(
    () => (distribution ? BAND_META.reduce((sum, band) => sum + (distribution[band.key] || 0), 0) : 0),
    [distribution],
  )
  const topRings = useMemo(
    () => [...(loops?.loops || [])].sort((a, b) => (b.total_amount || 0) - (a.total_amount || 0)).slice(0, 5),
    [loops],
  )
  const flaggedPct =
    stats && stats.companies > 0 ? Math.round((stats.flagged_entities / stats.companies) * 100) : 0

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="micro-label text-accent-ring">Command centre</p>
          <h1 className="mt-1 text-display font-semibold tracking-tight">Fraud intelligence</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-secondary">
            A ranked view of network risk across registered entities, fraud rings and open investigations.
            {lastUpdated && <span className="ml-1 text-text-disabled">Updated {relativeTime(lastUpdated.toISOString())}.</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to="/ingest"><Button variant="secondary">Import data</Button></Link>
          <Link to="/worklist"><Button>Open worklist</Button></Link>
        </div>
      </div>

      {error && (
        <div className="panel flex flex-wrap items-center justify-between gap-3 border-risk-critical/40 p-4" role="alert">
          <div>
            <p className="text-sm font-medium text-risk-critical">{error}</p>
            <p className="mt-0.5 text-xs text-text-secondary">The API may be warming up or a data source may be unavailable.</p>
          </div>
          <Button variant="secondary" onClick={load} loading={loading}>Retry</Button>
        </div>
      )}

      {loading && !stats ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="panel p-4">
                <Skeleton className="h-3 w-20" />
                <Skeleton className="mt-3 h-8 w-24" />
                <Skeleton className="mt-2 h-3 w-28" />
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="panel p-5 lg:col-span-2"><SkeletonText lines={7} /></div>
            <div className="panel p-5"><SkeletonText lines={7} /></div>
          </div>
        </>
      ) : stats ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Entities monitored"
              value={stats.companies.toLocaleString('en-IN')}
              sub={`${stats.directors.toLocaleString('en-IN')} directors in the graph`}
              tone="neutral"
            />
            <StatCard
              label="Flagged entities"
              value={stats.flagged_entities.toLocaleString('en-IN')}
              sub={`${flaggedPct}% of the monitored base`}
              tone="critical"
              hint="Entities at or above the risk flag threshold. Flagging opens them to analyst review, not an automatic finding."
            />
            <StatCard
              label="Rings detected"
              value={stats.cycles_detected.toLocaleString('en-IN')}
              sub="Closed invoice loops"
              tone="amber"
              hint="A ring (cycle) is a closed chain of invoices that returns to the starting entity, a common circular-trading pattern."
            />
            <StatCard
              label="Estimated ITC at risk"
              value={formatInrCompact(stats.estimated_itc_at_risk)}
              sub="Based on flagged-entity exposure"
              tone="accent"
              hint="ITC = Input Tax Credit. This is an exposure estimate derived from the flagged entities' capital base, not a tax assessment."
            />
            <StatCard
              label="Open cases"
              value={stats.open_cases.toLocaleString('en-IN')}
              sub={stats.top_risk_state ? `Highest-risk state: ${stats.top_risk_state}` : 'No state concentration yet'}
              tone="low"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="panel p-5 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold">Risk distribution</h2>
                  <p className="mt-0.5 text-xs text-text-secondary">Entity count by current risk band.</p>
                </div>
                <Badge tone="outline">{bandTotal.toLocaleString('en-IN')} scored</Badge>
              </div>

              {bandTotal === 0 ? (
                <EmptyState compact title="No scored entities" description="Risk scores appear after the scoring job has run on an ingested graph." />
              ) : (
                <>
                  <div className="mt-4 flex h-3 w-full overflow-hidden rounded-full bg-raised" role="img" aria-label="Risk band distribution">
                    {BAND_META.map((band) => {
                      const count = distribution?.[band.key] || 0
                      const width = bandTotal ? (count / bandTotal) * 100 : 0
                      return width > 0 ? (
                        <span
                          key={band.key}
                          className="h-full transition-[width] duration-500"
                          style={{ width: `${width}%`, backgroundColor: band.color }}
                          title={`${band.label}: ${count}`}
                        />
                      ) : null
                    })}
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                    {BAND_META.map((band) => {
                      const count = distribution?.[band.key] || 0
                      const pct = bandTotal ? Math.round((count / bandTotal) * 100) : 0
                      return (
                        <div key={band.key} className="rounded-lg border border-border bg-raised/40 px-3 py-2">
                          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
                            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: band.color }} aria-hidden="true" />
                            {band.label}
                          </div>
                          <div className="mt-1 font-mono text-lg">{count.toLocaleString('en-IN')}</div>
                          <div className="text-micro text-text-disabled">{pct}% of scored</div>
                        </div>
                      )
                    })}
                  </div>
                </>
              )}

              <div className="mt-5 border-t border-border pt-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h2 className="flex items-center gap-1.5 text-sm font-semibold">
                      ITC-at-risk trend
                      <InfoHint
                        side="bottom"
                        content="Proxy: total invoice value from flagged sellers grouped by GST return period (or invoice month when no period is present). Tax-rate data is not stored, so this is exposure, not a computed credit claim."
                      />
                    </h2>
                    <p className="mt-0.5 text-xs text-text-secondary">Flagged-seller invoice value by return period.</p>
                  </div>
                </div>
                <div className="mt-2">
                  <TrendChart points={stats.exposure_trend || []} />
                </div>
              </div>
            </div>

            <div className="panel flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="flex items-center gap-1.5 text-sm font-semibold">
                    Top rings
                    <InfoHint side="bottom" content="Rings are closed invoice cycles found in the transaction graph. Larger amounts and more members usually indicate higher exposure." />
                  </h2>
                  <p className="mt-0.5 text-xs text-text-secondary">By invoice value in the ring.</p>
                </div>
                <Link to="/loops" className="text-xs text-accent-ring hover:underline">View all</Link>
              </div>

              {topRings.length === 0 ? (
                <EmptyState compact title="No rings detected" description="Run the risk job after importing invoice data to detect circular trading." />
              ) : (
                <ol className="mt-3 divide-y divide-border">
                  {topRings.map((ring, index) => {
                    const members = ring.companies || []
                    return (
                      <li key={`${ring.path[0]}-${index}`} className="py-3">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex min-w-0 items-center gap-2">
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-raised font-mono text-[11px] text-text-secondary">
                              {index + 1}
                            </span>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">
                                {members[0]?.name || `Ring ${index + 1}`}
                                {members.length > 1 && <span className="text-text-secondary"> +{members.length - 1}</span>}
                              </p>
                              <p className="text-data text-text-disabled">
                                {members.length} members · {ring.length} invoice edges
                              </p>
                            </div>
                          </div>
                          <span className="shrink-0 font-mono text-data text-amber">{formatInrCompact(ring.total_amount)}</span>
                        </div>
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {members.slice(0, 3).map((member) => (
                            <Link
                              key={member.cin || member.name}
                              to={`/entity/${member.cin || member.name}/network`}
                              className="max-w-[12rem] truncate rounded border border-border px-1.5 py-0.5 text-[11px] text-text-secondary hover:text-accent-ring"
                            >
                              {member.name || member.cin}
                            </Link>
                          ))}
                        </div>
                      </li>
                    )
                  })}
                </ol>
              )}
              <div className="mt-auto pt-3">
                <Link to="/cases">
                  <Button variant="secondary" fullWidth>Open case board</Button>
                </Link>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="panel p-5 lg:col-span-2">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold">Recent activity</h2>
                  <p className="mt-0.5 text-xs text-text-secondary">Latest audit events across ingestion, scoring and investigations.</p>
                </div>
                <Badge tone="neutral">{activity.length} events</Badge>
              </div>
              {activity.length === 0 ? (
                <EmptyState compact title="No activity yet" description="Imports, score runs, logins and case actions are logged here as they happen." />
              ) : (
                <ul className="mt-3 space-y-0 divide-y divide-border">
                  {activity.map((entry) => (
                    <li key={entry.id} className="flex items-start gap-3 py-2.5">
                      <span
                        className="mt-1.5 h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: ACTION_TONE[entry.action] || 'var(--color-text-disabled)' }}
                        aria-hidden="true"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{titleCase(entry.action)}</p>
                        <p className="truncate text-xs text-text-secondary">
                          {entry.entity_type ? `${entry.entity_type}` : 'System'}
                          {entry.entity_id ? ` · ${entry.entity_id}` : ''}
                          {entry.details?.title ? ` · ${entry.details.title}` : ''}
                        </p>
                      </div>
                      <time className="shrink-0 text-xs text-text-disabled" dateTime={entry.timestamp}>
                        {relativeTime(entry.timestamp)}
                      </time>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="panel p-5">
              <h2 className="text-sm font-semibold">Risk band reference</h2>
              <p className="mt-0.5 text-xs text-text-secondary">Bands used by badges, filters and exports.</p>
              <dl className="mt-3 space-y-2">
                {BAND_META.map((band) => {
                  const level = riskLevel(
                    band.key === 'critical' ? 85 : band.key === 'high' ? 65 : band.key === 'medium' ? 40 : 0,
                  )
                  return (
                    <div key={band.key} className="flex items-center justify-between gap-2 rounded-lg border border-border bg-raised/40 px-3 py-2">
                      <dt className="flex items-center gap-2 text-sm">
                        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: band.color }} aria-hidden="true" />
                        {level.label}
                      </dt>
                      <dd className="font-mono text-data text-text-secondary">
                        {band.key === 'critical' ? '85–100' : band.key === 'high' ? '65–84' : band.key === 'medium' ? '40–64' : '0–39'}
                      </dd>
                    </div>
                  )
                })}
              </dl>
              <p className="mt-3 text-xs leading-relaxed text-text-disabled">
                Scores are model-assisted prioritisation, not a legal finding. An analyst confirms every case.
              </p>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
