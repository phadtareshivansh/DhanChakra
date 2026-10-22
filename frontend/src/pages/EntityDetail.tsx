import { t } from '../i18n'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import * as d3 from 'd3'
import api from '../utils/api'
import {
  Case,
  EntityHistoryEvent,
  EntityHistoryResponse,
  EntityNote,
  ExplainResponse,
  NetworkResponse,
  TimelineInvoice,
  TimelineResponse,
} from '../types/api'
import { riskLevel } from '../components/RiskBadge'
import ExplainDrawer from '../components/ExplainDrawer'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import EmptyState from '../components/ui/EmptyState'
import Skeleton, { SkeletonText } from '../components/ui/Skeleton'
import Tabs from '../components/ui/Tabs'
import { useToast } from '../components/ui/Toast'
import InfoHint from '../components/InfoHint'
import { riskColorForScore } from '../utils/riskColors'
import { RISK_THRESHOLDS } from '../config/risk'
import { formatDate, formatInr, formatInrCompact, relativeTime, titleCase, truncateMiddle } from '../utils/format'

interface GraphNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: string
  properties: Record<string, any>
}

interface GraphEdge extends d3.SimulationLinkDatum<GraphNode> {
  source: string | GraphNode
  target: string | GraphNode
  type: string
  properties: Record<string, any>
  flagged?: boolean
  /** True when the edge carries an invoice with no matching e-Way Bill
   *  movement record (TASK B1). */
  eway_mismatch?: boolean
}

const TYPE_COLORS: Record<string, string> = {
  Company: '#1F8A8C',
  Director: '#D6A94A',
  Address: '#8B99AB',
  BankAccount: '#7383A5',
  Transaction: '#4FD1D4',
  GSTINFiling: '#6FCF97',
}

const DRIVER_LABELS: Record<string, string> = {
  cycle: 'Invoice cycle membership',
  shared_director: 'Shared director',
  shared_address: 'Shared registered address',
  eway_mismatch: 'e-Way Bill mismatch',
  burst: 'Invoice burst',
  degree: 'Network degree',
  pagerank: 'PageRank influence',
  betweenness: 'Betweenness bridge',
}

const HISTORY_TONE: Record<string, string> = {
  feedback: 'var(--color-amber)',
  case: 'var(--color-accent)',
  note: 'var(--color-text-secondary)',
  invoice: 'var(--color-risk-low)',
}

function edgeEndpointId(endpoint: string | GraphNode): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

export default function EntityDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const toast = useToast()
  const svgRef = useRef<SVGSVGElement>(null)
  type TabId = 'network' | 'transactions' | 'people' | 'evidence' | 'history' | 'notes'
  const [tab, setTab] = useState<TabId>('network')
  const [entity, setEntity] = useState<any>(null)
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null)
  const [showExplain, setShowExplain] = useState(false)
  const [hops, setHops] = useState(2)
  const [creatingCase, setCreatingCase] = useState(false)
  const [timeline, setTimeline] = useState<TimelineInvoice[] | null>(null)
  const [history, setHistory] = useState<EntityHistoryEvent[] | null>(null)
  const [notes, setNotes] = useState<EntityNote[] | null>(null)
  const [tabError, setTabError] = useState<string | null>(null)
  const [noteDraft, setNoteDraft] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState<string | null>(null)

  const load = useCallback(async (depth: number) => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [entityRes, netRes] = await Promise.all([
        api.get(`/entities/${id}`),
        api.get(`/entities/${id}/network?hops=${depth}`),
      ])
      setEntity(entityRes.data)
      const net: NetworkResponse = netRes.data
      setNodes(net.nodes)
      setEdges(net.edges)
      setHops(depth)
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || t('Failed to load entity'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { if (id) load(2) }, [id, load])

  useEffect(() => {
    if (!id) return
    api.get(`/entities/${id}/explain`)
      .then((res) => setExplanation(res.data))
      .catch(() => setExplanation(null))
  }, [id])

  useEffect(() => {
    if (!id) return
    setTabError(null)
    if (tab === 'transactions' && timeline === null) {
      api.get<TimelineResponse>(`/entities/${id}/timeline`)
        .then((res) => setTimeline(res.data.timeline || []))
        .catch((err) => setTabError(err?.response?.data?.detail?.message || 'Could not load transactions.'))
    }
    if (tab === 'history' && history === null) {
      api.get<EntityHistoryResponse>(`/entities/${id}/history`)
        .then((res) => setHistory(res.data.events || []))
        .catch((err) => setTabError(err?.response?.data?.detail?.message || 'Could not load entity history.'))
    }
    if (tab === 'notes' && notes === null) {
      api.get<EntityNote[]>(`/entities/${id}/notes`)
        .then((res) => setNotes(res.data))
        .catch((err) => setTabError(err?.response?.data?.detail?.message || 'Could not load notes.'))
    }
  }, [id, tab, timeline, history, notes])

  // Flagged-cycle edges are marked by the API, so the highlight is deterministic.
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0 || tab !== 'network') return

    const svg = d3.select(svgRef.current)
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight || 600
    svg.selectAll('*').remove()

    const container = svg.append('g')
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => container.attr('transform', event.transform))
    svg.call(zoom as any)

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force('link', d3.forceLink<GraphNode, GraphEdge>(edges).id((d) => d.id).distance(110))
      .force('charge', d3.forceManyBody().strength(-350))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(45))

    const link = container.append('g')
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', (d: any) => d.flagged ? '#E5484D' : (d.eway_mismatch ? '#F97316' : '#26303E'))
      .attr('stroke-width', (d: any) => d.flagged ? 3 : 1.5)
      .attr('stroke-opacity', 0.85)
      .attr('marker-end', 'url(#arrow)')

    const ewayBadge = container.append('g')
      .selectAll('circle')
      .data(edges.filter((d: any) => d.eway_mismatch))
      .join('circle')
      .attr('r', 6)
      .attr('fill', '#F97316')
      .attr('stroke', '#0B1220')
      .attr('stroke-width', 1.5)
    ewayBadge.append('title')
      .text('e-Way Bill mismatch — high-value invoice with no matching movement record')

    svg.append('defs').append('marker')
      .attr('id', 'arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 28)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#26303E')

    const node = container.append('g')
      .selectAll('g')
      .data(nodes)
      .join('g')
      .call(drag(simulation) as any)
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedNode(d)
      })

    node.append('circle')
      .attr('r', (d: any) => (d.type === 'Company' ? 22 : 15))
      .attr('fill', (d: any) => TYPE_COLORS[d.type] || '#64748b')
      .attr('stroke', (d: any) => {
        if (d.properties?.risk_score !== undefined) {
          return riskColorForScore(Number(d.properties.risk_score))
        }
        return '#E7EDF3'
      })
      .attr('stroke-width', (d: any) => d.properties?.risk_score !== undefined ? 4 : 1.5)

    node.append('text')
      .attr('dy', (d: any) => (d.type === 'Company' ? 36 : 29))
      .attr('text-anchor', 'middle')
      .attr('fill', '#E7EDF3')
      .attr('font-size', 10)
      .attr('font-family', 'IBM Plex Mono, monospace')
      .text((d: any) => (d.label.length > 20 ? d.label.slice(0, 20) + '…' : d.label))

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)
      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
      ewayBadge
        .attr('cx', (d: any) => (((d.source as any)?.x ?? 0) + ((d.target as any)?.x ?? 0)) / 2)
        .attr('cy', (d: any) => (((d.source as any)?.y ?? 0) + ((d.target as any)?.y ?? 0)) / 2)
    })

    function drag(simulation: d3.Simulation<GraphNode, undefined>) {
      function dragstarted(event: any, d: any) {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      }
      function dragged(event: any, d: any) {
        d.fx = event.x
        d.fy = event.y
      }
      function dragended(event: any, d: any) {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      }
      return d3.drag<any, any>().on('start', dragstarted).on('drag', dragged).on('end', dragended)
    }

    return () => {
      simulation.stop()
    }
  }, [nodes, edges, tab])

  const fitView = () => {
    if (!svgRef.current) return
    const svg = d3.select(svgRef.current)
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight || 600
    const xVals = nodes.map((node) => (node as any).x ?? width / 2)
    const yVals = nodes.map((node) => (node as any).y ?? height / 2)
    const minX = Math.min(...xVals), maxX = Math.max(...xVals)
    const minY = Math.min(...yVals), maxY = Math.max(...yVals)
    const dx = maxX - minX || width, dy = maxY - minY || height
    const scale = Math.min(width / dx, height / dy) * 0.8
    const tx = width / 2 - (minX + dx / 2) * scale
    const ty = height / 2 - (minY + dy / 2) * scale
    svg.transition().duration(500).call(
      d3.zoom<SVGSVGElement, unknown>().transform as any,
      d3.zoomIdentity.translate(tx, ty).scale(scale),
    )
  }

  const createCase = async () => {
    if (!entity) return
    setCreatingCase(true)
    try {
      const res = await api.post<Case>('/cases', {
        title: `Investigation: ${entity.name || entity.cin}`,
        description: `Case opened from entity ${entity.cin || entity.id} with risk score ${entity.risk_score ?? 'n/a'}`,
        company_cin: entity.cin,
        priority: entity.risk_score && entity.risk_score >= RISK_THRESHOLDS.high ? 2 : entity.risk_score && entity.risk_score >= RISK_THRESHOLDS.medium ? 1 : 0,
      })
      toast.push({ title: t('Case opened'), description: res.data.title, tone: 'success' })
      navigate(`/cases?highlight=${res.data.id}`)
    } catch (err: any) {
      toast.push({ title: t('Failed to open case'), description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setCreatingCase(false)
    }
  }

  const submitFeedback = async (label: 'confirm_fraud' | 'false_positive' | 'needs_review') => {
    if (!id) return
    setFeedbackBusy(label)
    try {
      await api.post(`/entities/${id}/feedback`, { label })
      toast.push({ title: t('Label recorded'), description: titleCase(label), tone: 'success' })
      setHistory(null)
    } catch (err: any) {
      toast.push({ title: t('Could not record label'), description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setFeedbackBusy(null)
    }
  }

  const addToWatchlist = async () => {
    try {
      await api.post('/watchlist', { entity_id: id, entity_cin: entity?.cin })
      toast.push({ title: t('Added to watchlist'), tone: 'success' })
    } catch (err: any) {
      toast.push({ title: t('Could not update watchlist'), description: err?.response?.data?.detail?.message, tone: 'critical' })
    }
  }

  const submitNote = async () => {
    if (!id || !noteDraft.trim()) return
    setSavingNote(true)
    try {
      const res = await api.post<EntityNote>(`/entities/${id}/notes`, { body: noteDraft.trim() })
      setNotes((current) => [res.data, ...(current || [])])
      setNoteDraft('')
      setHistory(null)
      toast.push({ title: t('Note added'), tone: 'success' })
    } catch (err: any) {
      toast.push({ title: t('Could not save note'), description: err?.response?.data?.detail?.message, tone: 'critical' })
    } finally {
      setSavingNote(false)
    }
  }

  const ewayMismatches = explanation?.evidence?.eway_mismatches || []
  const ewayCount = ewayMismatches.length
  const ewayTotal = ewayMismatches.reduce((sum, mismatch) => sum + Number(mismatch.amount || 0), 0)
  const directors = useMemo(() => nodes.filter((node) => node.type === 'Director'), [nodes])
  const addresses = useMemo(() => nodes.filter((node) => node.type === 'Address'), [nodes])
  const riskDecomposition = explanation?.evidence?.risk_decomposition || null
  const driverEntries = useMemo(() => {
    if (!riskDecomposition) return []
    return Object.entries(DRIVER_LABELS)
      .map(([key, label]) => ({ key, label, value: Number(riskDecomposition[key] || 0) }))
      .filter((driver) => driver.value > 0)
      .sort((a, b) => b.value - a.value)
  }, [riskDecomposition])
  const maxDriver = Math.max(...driverEntries.map((driver) => driver.value), 1)
  const totalTransactions = (timeline || []).reduce((sum, invoice) => sum + Number(invoice.amount || 0), 0)
  const entityState = addresses[0]?.properties?.state || '—'

  const connectedCompanies = (nodeId: string) => {
    const companyIds = new Set<string>()
    edges.forEach((edge) => {
      const source = edgeEndpointId(edge.source)
      const target = edgeEndpointId(edge.target)
      if (source === nodeId) companyIds.add(target)
      if (target === nodeId) companyIds.add(source)
    })
    return nodes
      .filter((node) => companyIds.has(node.id) && node.type === 'Company' && node.id !== nodeId)
      .map((node) => node.label)
  }

  const tabItems = [
    { id: 'network', label: t('Network'), count: nodes.length },
    { id: 'transactions', label: t('Transactions'), count: timeline?.length },
    { id: 'people', label: t('Directors & addresses'), count: directors.length + addresses.length },
    { id: 'evidence', label: t('Evidence'), count: explanation?.reasons.length },
    { id: 'history', label: t('History'), count: history?.length },
    { id: 'notes', label: t('Notes'), count: notes?.length },
  ]

  if (error && !entity) {
    return (
      <div className="panel p-10 text-center" role="alert">
        <p className="text-sm font-medium text-risk-critical">{error}</p>
        <div className="mt-4 flex justify-center gap-2">
          <Button variant="secondary" onClick={() => load(2)}>{t('Retry')}</Button>
          <Link to="/worklist"><Button variant="ghost">{t('Back to worklist')}</Button></Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link to="/worklist" className="text-xs text-text-secondary hover:text-accent-ring">{t('← Risk worklist')}</Link>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{entity?.name || t('Entity')}</h1>
            {entity?.status && <Badge tone="neutral" dot>{titleCase(entity.status)}</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-text-secondary">
            <span className="mono-id">{entity?.cin || entity?.id}</span>
            {entity?.gstin && (
              <span className="inline-flex items-center gap-1">
                <span className="mono-id">{entity.gstin}</span>
                <InfoHint content={t('GSTIN is the 15-character GST registration number for this entity.')} />
              </span>
            )}
            <span>{entityState}</span>
            {entity?.roc && <span>{t('ROC')} {entity.roc}</span>}
            {entity?.incorporation_date && <span>{t('Incorporated')} {formatDate(entity.incorporation_date)}</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => navigate(`/graph/${encodeURIComponent(entity?.id || id || '')}`)}>{t('Graph workspace')}</Button>
          <Button variant="secondary" onClick={addToWatchlist}>{t('Watchlist')}</Button>
          <Button variant="secondary" onClick={() => setShowExplain(true)} disabled={!explanation}>{t('Why flagged?')}</Button>
          <Button variant="secondary" onClick={() => setTab('notes')}>{t('Add note')}</Button>
          <Button onClick={createCase} loading={creatingCase}>{t('Open case')}</Button>
        </div>
      </div>

      {loading && !entity ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="panel p-4"><Skeleton className="h-3 w-24" /><Skeleton className="mt-3 h-7 w-20" /></div>
            ))}
          </div>
          <div className="panel p-6"><SkeletonText lines={8} /></div>
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="panel relative overflow-hidden p-4">
              <span
                className="absolute inset-x-0 top-0 h-0.5"
                style={{ backgroundColor: riskColorForScore(entity?.risk_score ?? 0) }}
                aria-hidden="true"
              />
              <div className="flex items-center justify-between">
                <span className="micro-label">{t('Risk score')}</span>
                <InfoHint content={t('Model-assisted priority score from 0–100. It combines network evidence such as rings, shared directors, addresses and transaction behaviour.')} />
              </div>
              <div className="mt-2 flex items-end gap-2">
                <span className="font-mono text-3xl font-medium" style={{ color: riskColorForScore(entity?.risk_score ?? 0) }}>
                  {entity?.risk_score !== undefined ? Math.round(entity.risk_score) : '—'}
                </span>
                <span className="pb-1 text-xs text-text-secondary">/ 100 · {riskLevel(entity?.risk_score).label}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-raised">
                <div
                  className="h-full rounded-full transition-[width] duration-500"
                  style={{ width: `${Math.min(100, Math.max(0, entity?.risk_score ?? 0))}%`, backgroundColor: riskColorForScore(entity?.risk_score ?? 0) }}
                />
              </div>
              <p className="mt-2 text-xs text-text-secondary">{t('Source:')} {entity?.risk_source || 'heuristic'}</p>
            </div>

            <div className="panel p-4">
              <span className="micro-label">{t('Paid-up capital')}</span>
              <div className="mt-2 font-mono text-2xl">{formatInrCompact(entity?.paid_up_capital)}</div>
              <p className="mt-2 text-xs text-text-secondary">{t('Authorised')} {formatInrCompact(entity?.authorized_capital)}</p>
            </div>

            <div className="panel p-4">
              <div className="flex items-center justify-between">
                <span className="micro-label">{t('Ring membership')}</span>
                <InfoHint content={t('Number of closed invoice cycles (rings) this entity appears in. Rings are a strong circular-trading signal.')} />
              </div>
              <div className="mt-2 font-mono text-2xl text-amber">{explanation?.evidence.cycles.length ?? 0}</div>
              <p className="mt-2 text-xs text-text-secondary">
                {explanation?.evidence.cycles.length ? 'Detected invoice cycle(s)' : 'No closed cycle detected'}
              </p>
            </div>

            <div className={`panel p-4 ${ewayCount > 0 ? 'border-risk-high/50' : ''}`}>
              <div className="flex items-center justify-between">
                <span className="micro-label">{t('e-Way mismatches')}</span>
                <InfoHint content={t('High-value invoices with no matching e-Way Bill movement record. A mismatch is a signal, not proof of evasion.')} />
              </div>
              <div className={`mt-2 font-mono text-2xl ${ewayCount > 0 ? 'text-risk-high' : ''}`}>{ewayCount}</div>
              <p className="mt-2 text-xs text-text-secondary">
                {ewayCount > 0 ? `${formatInr(ewayTotal)} across mismatched invoices` : 'All matched or none applicable'}
              </p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="panel p-5 lg:col-span-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="flex items-center gap-1.5 text-sm font-semibold">
                    {t('Risk drivers')}
                    <InfoHint side="bottom" content={t('How the score decomposes into evidence. Contributions are points added by each signal; they may be capped before the total.')} />
                  </h2>
                  <p className="mt-0.5 text-xs text-text-secondary">{t('Evidence contribution to the current score.')}</p>
                </div>
                <Badge tone={entity?.risk_source === 'gnn_v1' ? 'accent' : 'neutral'}>
                  {entity?.risk_source === 'gnn_v1' ? 'GNN-assisted' : 'Structural'}
                </Badge>
              </div>

              {driverEntries.length === 0 ? (
                <EmptyState
                  compact
                  title={t('No driver breakdown')}
                  description={explanation ? 'This entity was scored before component attribution was recorded.' : 'The explanation API is unavailable; the score still stands.'}
                />
              ) : (
                <div className="mt-4 space-y-2.5">
                  {driverEntries.map((driver) => (
                    <div key={driver.key}>
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="text-text-secondary">{driver.label}</span>
                        <span className="font-mono text-text-primary">+{driver.value.toFixed(1)}</span>
                      </div>
                      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-raised">
                        <div
                          className="h-full rounded-full bg-accent transition-[width] duration-500"
                          style={{ width: `${Math.max(3, (driver.value / maxDriver) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {explanation && explanation.reasons.length > 0 && (
                <ul className="mt-4 space-y-1.5 border-t border-border pt-3">
                  {explanation.reasons.slice(0, 3).map((reason, index) => (
                    <li key={index} className="flex gap-2 text-xs text-text-secondary">
                      <span className="text-accent-ring">▸</span>{reason}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="panel p-5">
              <h2 className="text-sm font-semibold">{t('Entity profile')}</h2>
              <dl className="mt-3 space-y-2 text-sm">
                {[
                  ['CIN', entity?.cin],
                  ['GSTIN', entity?.gstin],
                  ['NIC sector', entity?.nic_code],
                  ['ROC', entity?.roc],
                  ['Community', entity?.community_id],
                  ['PageRank', entity?.pagerank !== undefined ? Number(entity.pagerank).toFixed(4) : null],
                  ['Betweenness', entity?.betweenness !== undefined ? Number(entity.betweenness).toFixed(4) : null],
                ].map(([label, value]) => (
                  <div key={label as string} className="flex items-start justify-between gap-3 border-b border-border pb-1.5 last:border-0">
                    <dt className="flex items-center gap-1 text-xs text-text-secondary">
                      {label}
                      {label === 'Betweenness' && (
                        <InfoHint content={t('A graph-centrality measure: how often this entity sits on the shortest path between others. High betweenness can indicate a bridge between otherwise separate clusters.')} />
                      )}
                    </dt>
                    <dd className="text-right font-mono text-[12px]">{String(value ?? '—')}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4 grid grid-cols-3 gap-2">
                <Button size="sm" variant="secondary" onClick={() => submitFeedback('confirm_fraud')} loading={feedbackBusy === 'confirm_fraud'}>{t('Confirm')}</Button>
                <Button size="sm" variant="secondary" onClick={() => submitFeedback('needs_review')} loading={feedbackBusy === 'needs_review'}>{t('Review')}</Button>
                <Button size="sm" variant="secondary" onClick={() => submitFeedback('false_positive')} loading={feedbackBusy === 'false_positive'}>{t('False +')}</Button>
              </div>
              <p className="mt-2 text-[11px] text-text-disabled">{t('Labels feed model feedback; they do not close the entity.')}</p>
            </div>
          </div>

          <Tabs items={tabItems} value={tab} onChange={(next) => { setTab(next as TabId); setTabError(null) }} />
          {tabError && (
            <div className="panel border-risk-critical/40 p-4 text-sm text-risk-critical" role="alert">{tabError}</div>
          )}

          {tab === 'network' && (
            <div className="panel relative h-[560px] overflow-hidden">
              {nodes.length === 0 ? (
                <EmptyState
                  title={t('No network found')}
                  description={t('This entity has no relationships in the graph yet. Ingest MCA/GST data to build its neighbourhood.')}
                  action={<Link to="/ingest"><Button variant="secondary">{t('Import data')}</Button></Link>}
                />
              ) : (
                <>
                  <svg ref={svgRef} className="h-full w-full" aria-label={t('Entity network graph')} />
                  <div className="absolute bottom-4 right-4 flex gap-2">
                    <Button size="sm" variant="secondary" onClick={fitView}>{t('Fit to view')}</Button>
                    {[1, 2, 3].map((depth) => (
                      <Button key={depth} size="sm" variant="secondary" onClick={() => load(depth)} disabled={hops === depth}>
                        {depth}{t('-hop')}
                      </Button>
                    ))}
                  </div>
                  <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-3 text-[11px] text-text-secondary">
                    <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-accent" />{t('Company')}</span>
                    <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber" />{t('Director')}</span>
                    <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-text-secondary" />{t('Address')}</span>
                    <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-secondary-400" />{t('Bank account')}</span>
                    <span className="text-risk-critical">{t('red edges = flagged cycle')}</span>
                    <span className="text-risk-high">{t('orange dot = e-Way mismatch')}</span>
                  </div>
                  {selectedNode && (
                    <div className="panel-raised absolute bottom-4 left-4 max-w-xs rounded-lg p-4">
                      <h3 className="text-sm font-semibold">{selectedNode.label}</h3>
                      <p className="mt-0.5 text-xs text-text-secondary">{selectedNode.type}</p>
                      <div className="mt-2 max-h-40 space-y-1 overflow-y-auto text-xs text-text-secondary">
                        {Object.entries(selectedNode.properties).slice(0, 12).map(([key, value]) => (
                          <div key={key}><span className="font-medium text-text-primary">{key}:</span> <span className="font-mono">{String(value)}</span></div>
                        ))}
                      </div>
                      {selectedNode.type === 'Company' && (
                        <Link
                          to={`/entity/${selectedNode.properties.cin || selectedNode.id}/network`}
                          className="mt-3 text-xs text-accent-ring hover:underline"
                        >
                          {t('View network →')}
                        </Link>
                      )}
                      <button type="button" onClick={() => setSelectedNode(null)} className="mt-2 text-xs text-text-secondary hover:text-text-primary">{t('Close')}</button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {tab === 'transactions' && (
            <div className="panel overflow-hidden">
              {timeline === null ? (
                <div className="p-5"><SkeletonText lines={8} /></div>
              ) : timeline.length === 0 ? (
                <EmptyState
                  title={t('No billed invoices')}
                  description={t('No outgoing invoices are attached to this entity in the graph. Invoices appear after GST ingestion.')}
                />
              ) : (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
                    <div>
                      <h2 className="text-sm font-semibold">{t('Outgoing invoices')}</h2>
                      <p className="text-xs text-text-secondary">{t('Sorted by invoice date, oldest first.')}</p>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-sm">{formatInr(totalTransactions)}</div>
                      <div className="text-[11px] text-text-secondary">{timeline.length} {t('invoices')}</div>
                    </div>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[720px] text-sm">
                      <thead className="bg-raised/60 text-left text-micro uppercase tracking-micro text-text-secondary">
                        <tr>
                          <th className="px-4 py-2.5">{t('Date')}</th>
                          <th className="px-4 py-2.5">{t('Counterparty')}</th>
                          <th className="px-4 py-2.5">{t('Seller GSTIN')}</th>
                          <th className="px-4 py-2.5">{t('Buyer GSTIN')}</th>
                          <th className="px-4 py-2.5">{t('Return period')}</th>
                          <th className="px-4 py-2.5 text-right">{t('Amount')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {timeline.map((invoice, index) => (
                          <tr key={`${invoice.date}-${index}`} className="border-t border-border hover:bg-raised/40">
                            <td className="px-4 py-2.5 text-xs text-text-secondary">{formatDate(invoice.date)}</td>
                            <td className="px-4 py-2.5">
                              {invoice.counterparty?.cin ? (
                                <Link
                                  to={`/entity/${invoice.counterparty.cin}/network`}
                                  className="font-medium hover:text-accent-ring"
                                >
                                  {invoice.counterparty.name || invoice.counterparty.cin}
                                </Link>
                              ) : (
                                <span className="font-medium">{invoice.counterparty?.name || '—'}</span>
                              )}
                            </td>
                            <td className="px-4 py-2.5 font-mono text-data text-text-secondary">{invoice.seller_gstin || '—'}</td>
                            <td className="px-4 py-2.5 font-mono text-data text-text-secondary">{invoice.buyer_gstin || '—'}</td>
                            <td className="px-4 py-2.5 font-mono text-data text-text-secondary">{invoice.return_period || '—'}</td>
                            <td className="px-4 py-2.5 text-right font-mono text-data">{formatInr(invoice.amount)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}

          {tab === 'people' && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="panel p-5">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">{t('Directors')}</h2>
                  <Badge tone="neutral">{directors.length}</Badge>
                </div>
                {directors.length === 0 ? (
                  <EmptyState compact title={t('No directors in this neighbourhood')} description={t('Try a wider hop depth on the Network tab, or ingest MCA director records.')} />
                ) : (
                  <ul className="mt-3 divide-y divide-border">
                    {directors.map((director) => {
                      const companies = connectedCompanies(director.id)
                      return (
                        <li key={director.id} className="py-3">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-medium">{director.label}</p>
                              <p className="font-mono text-[11px] text-text-secondary">{t('DIN')} {director.properties.din || '—'}</p>
                            </div>
                            <Badge tone={companies.length > 1 ? 'amber' : 'neutral'}>{companies.length} {t('link')}{companies.length === 1 ? '' : 's'}</Badge>
                          </div>
                          {companies.length > 0 && (
                            <p className="mt-1 text-xs text-text-secondary">
                              {t('Connected to')} {companies.slice(0, 3).join(', ')}{companies.length > 3 ? ` +${companies.length - 3}` : ''}
                            </p>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
              <div className="panel p-5">
                <div className="flex items-center justify-between">
                  <h2 className="flex items-center gap-1.5 text-sm font-semibold">
                    {t('Registered addresses')}
                    <InfoHint content={t('Shared addresses across unrelated companies can indicate shell entities using the same premises.')} />
                  </h2>
                  <Badge tone="neutral">{addresses.length}</Badge>
                </div>
                {addresses.length === 0 ? (
                  <EmptyState compact title={t('No addresses in this neighbourhood')} description={t('Addresses appear when MCA records link companies to registered premises.')} />
                ) : (
                  <ul className="mt-3 divide-y divide-border">
                    {addresses.map((address) => {
                      const companies = connectedCompanies(address.id)
                      return (
                        <li key={address.id} className="py-3">
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="text-sm">{address.properties.normalized_address || address.label || 'Registered address'}</p>
                              <p className="text-xs text-text-secondary">
                                {[address.properties.state, address.properties.pincode].filter(Boolean).join(' · ') || 'State not recorded'}
                              </p>
                            </div>
                            <Badge tone={companies.length > 1 ? 'amber' : 'neutral'}>{companies.length} {t('compan')}{companies.length === 1 ? 'y' : 'ies'}</Badge>
                          </div>
                          {companies.length > 0 && (
                            <p className="mt-1 truncate text-xs text-text-secondary">{companies.slice(0, 3).join(', ')}</p>
                          )}
                        </li>
                      )
                    })}
                  </ul>
                )}
              </div>
            </div>
          )}

          {tab === 'evidence' && (
            <div className="space-y-4">
              {!explanation ? (
                <div className="panel p-5"><SkeletonText lines={5} /></div>
              ) : (
                <>
                  <div className="panel p-5">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-semibold">{t('Why this entity is flagged')}</h2>
                      <Badge tone="accent">{explanation.reasons.length} {t('signals')}</Badge>
                    </div>
                    {explanation.reasons.length === 0 ? (
                      <EmptyState compact title={t('No positive evidence')} description={t('The score may come from model priors rather than structural evidence.')} />
                    ) : (
                      <ul className="mt-3 space-y-2">
                        {explanation.reasons.map((reason, index) => (
                          <li key={index} className="flex gap-2 text-sm"><span className="text-accent-ring">▸</span>{reason}</li>
                        ))}
                      </ul>
                    )}
                  </div>

                  {explanation.evidence.cycles.length > 0 && (
                    <div className="panel p-5">
                      <h2 className="text-sm font-semibold">{t('Detected invoice cycles')}</h2>
                      <div className="mt-3 space-y-3">
                        {explanation.evidence.cycles.map((cycle, index) => (
                          <div key={index} className="rounded-lg border border-risk-critical/30 bg-risk-critical/5 p-3">
                            <div className="text-xs font-semibold text-risk-critical">
                              {cycle.hop_count}{t('-hop cycle across')} {cycle.company_count} {t('companies ·')} {formatInr(cycle.total_invoice_amount)}
                            </div>
                            <div className="mt-1 font-mono text-[11px] text-text-secondary">
                              {cycle.companies?.map((member) => member.name).join(' → ')}
                            </div>
                            {cycle.invoices?.length > 0 && (
                              <div className="mt-2 space-y-1 border-t border-risk-critical/20 pt-2 text-[11px] text-text-secondary">
                                {cycle.invoices.slice(0, 4).map((invoice, invoiceIndex) => (
                                  <div key={invoiceIndex} className="flex justify-between gap-2">
                                    <span className="truncate">{invoice.invoice_no || 'Invoice'} · {invoice.seller_name || invoice.seller_cin} → {invoice.buyer_name || invoice.buyer_cin}</span>
                                    <span className="shrink-0 font-mono">{formatInr(invoice.amount)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="grid gap-4 lg:grid-cols-2">
                    <div className="panel p-5">
                      <h2 className="text-sm font-semibold">{t('Shared directors')}</h2>
                      {explanation.evidence.shared_directors.length === 0 ? (
                        <p className="mt-2 text-xs text-text-secondary">{t('No shared-director links in the evidence set.')}</p>
                      ) : (
                        <ul className="mt-3 space-y-2">
                          {explanation.evidence.shared_directors.map((director, index) => (
                            <li key={index} className="rounded-lg border border-border bg-raised/40 p-2.5 text-xs">
                              <p className="font-medium text-text-primary">{director.director}</p>
                              <p className="mt-0.5 text-text-secondary">{director.companies?.join(', ')}</p>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="panel p-5">
                      <h2 className="text-sm font-semibold">{t('Shared registered addresses')}</h2>
                      {explanation.evidence.shared_addresses.length === 0 ? (
                        <p className="mt-2 text-xs text-text-secondary">{t('No shared-address links in the evidence set.')}</p>
                      ) : (
                        <ul className="mt-3 space-y-2">
                          {explanation.evidence.shared_addresses.map((address, index) => (
                            <li key={index} className="rounded-lg border border-border bg-raised/40 p-2.5 text-xs">
                              <p className="font-mono text-[11px] text-text-primary">{address.address}</p>
                              <p className="mt-0.5 text-text-secondary">{address.state} · {address.companies?.join(', ')}</p>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>

                  <div className="panel p-5">
                    <div className="flex items-center justify-between">
                      <h2 className="flex items-center gap-1.5 text-sm font-semibold">
                        {t('e-Way Bill mismatches')}
                        <InfoHint content={t('Invoices above the configured high-value threshold whose declared e-Way Bill reference has no matching movement record, or whose amount differs materially.')} />
                      </h2>
                      <Badge tone={ewayCount > 0 ? 'high' : 'neutral'}>{ewayCount}</Badge>
                    </div>
                    {ewayCount === 0 ? (
                      <p className="mt-2 text-xs text-text-secondary">{t('No e-Way mismatches recorded for this entity.')}</p>
                    ) : (
                      <div className="mt-3 space-y-2">
                        {ewayMismatches.map((mismatch, index) => (
                          <div key={index} className="rounded-lg border border-risk-high/30 bg-risk-high/5 p-3">
                            <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold">
                              <span>{mismatch.invoice_no || 'Invoice'} · {formatInr(mismatch.amount)}</span>
                              {mismatch.date && <span className="font-normal text-text-secondary">{formatDate(mismatch.date)}</span>}
                            </div>
                            <p className="mt-1 text-[11px] text-text-primary">{mismatch.reason_label || mismatch.reason}</p>
                            {mismatch.claimed_ref && (
                              <p className="font-mono text-[11px] text-text-secondary">
                                {t('Cites')} {mismatch.claimed_ref}{mismatch.movement_ref ? '' : ' — no movement record exists'}
                              </p>
                            )}
                            {mismatch.movement_ref && (
                              <p className="font-mono text-[11px] text-text-secondary">
                                {mismatch.movement_ref}: {formatInr(mismatch.movement_amount)}
                                {mismatch.movement_date ? ` on ${mismatch.movement_date}` : ''}
                                {mismatch.from_state && mismatch.to_state ? `, ${mismatch.from_state} → ${mismatch.to_state}` : ''}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {tab === 'history' && (
            <div className="panel p-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold">{t('Entity history')}</h2>
                  <p className="text-xs text-text-secondary">{t('Analyst labels, case activity, notes and invoices, newest first.')}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setHistory(null)}>{t('Refresh')}</Button>
              </div>
              {history === null ? (
                <div className="mt-4"><SkeletonText lines={6} /></div>
              ) : history.length === 0 ? (
                <EmptyState compact title={t('No history yet')} description={t('Labels, case events, notes and invoices will appear here as they are recorded.')} />
              ) : (
                <ol className="mt-4 space-y-0">
                  {history.map((event, index) => (
                    <li key={`${event.kind}-${index}`} className="relative flex gap-3 pb-4 last:pb-0">
                      <span className="relative flex flex-col items-center">
                        <span className="mt-1.5 h-2.5 w-2.5 rounded-full" style={{ backgroundColor: HISTORY_TONE[event.kind] || 'var(--color-text-disabled)' }} aria-hidden="true" />
                        {index < history.length - 1 && <span className="mt-1 w-px flex-1 bg-border" aria-hidden="true" />}
                      </span>
                      <div className="min-w-0 flex-1 border-b border-border pb-3 last:border-0">
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                          <p className="text-sm font-medium">{event.title}</p>
                          <time className="text-xs text-text-disabled" dateTime={event.at}>{relativeTime(event.at)}</time>
                        </div>
                        <p className="text-xs text-text-secondary">
                          {titleCase(event.kind)}
                          {event.actor ? ` · ${event.actor}` : ''}
                          {event.amount !== undefined && event.amount !== null ? ` · ${formatInr(event.amount)}` : ''}
                        </p>
                        {event.detail && <p className="mt-1 text-xs text-text-secondary">{event.detail}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}

          {tab === 'notes' && (
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="panel p-5 lg:col-span-1">
                <h2 className="text-sm font-semibold">{t('Add an analyst note')}</h2>
                <p className="mt-0.5 text-xs text-text-secondary">{t('Notes are visible to everyone working this entity and appear in its history.')}</p>
                <textarea
                  className="mt-3 min-h-32 w-full rounded-lg border border-border bg-canvas p-3 text-sm text-text-primary placeholder:text-text-disabled focus:border-accent-ring focus:outline-none focus:ring-2 focus:ring-accent-ring"
                  placeholder={t('What did you verify? Include source references where possible.')}
                  value={noteDraft}
                  onChange={(event) => setNoteDraft(event.target.value)}
                  maxLength={5000}
                />
                <div className="mt-2 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-text-disabled">{noteDraft.length}/5000</span>
                  <Button size="sm" onClick={submitNote} loading={savingNote} disabled={!noteDraft.trim()}>{t('Save note')}</Button>
                </div>
              </div>
              <div className="panel p-5 lg:col-span-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold">{t('Notes')}</h2>
                  <Badge tone="neutral">{notes?.length ?? 0}</Badge>
                </div>
                {notes === null ? (
                  <div className="mt-4"><SkeletonText lines={5} /></div>
                ) : notes.length === 0 ? (
                  <EmptyState compact title={t('No notes yet')} description={t('Record verification steps, source documents or handover context for the next analyst.')} />
                ) : (
                  <ul className="mt-3 divide-y divide-border">
                    {notes.map((note) => (
                      <li key={note.id} className="py-3">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-xs font-medium">{note.author_name || 'Analyst'}</span>
                          <time className="text-[11px] text-text-disabled" dateTime={note.created_at}>{relativeTime(note.created_at)}</time>
                        </div>
                        <p className="mt-1 whitespace-pre-wrap text-sm text-text-secondary">{note.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <p className="text-xs text-text-disabled">
        {t('Entity reference')} {truncateMiddle(entity?.cin || id || '', 28)} {t('· scores are prioritisation aids; verify evidence before enforcement.')}
      </p>

      {showExplain && explanation && (
        <ExplainDrawer data={explanation} entityId={id!} onClose={() => setShowExplain(false)} />
      )}
    </div>
  )
}
