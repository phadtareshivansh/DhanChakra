import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import api from '../utils/api'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Drawer from '../components/ui/Drawer'
import EmptyState from '../components/ui/EmptyState'
import Input from '../components/ui/Input'
import Modal from '../components/ui/Modal'
import Select from '../components/ui/Select'
import { useToast } from '../components/ui/Toast'
import RiskBadge from '../components/RiskBadge'
import InfoHint from '../components/InfoHint'
import GraphCanvas, {
  BenchmarkResult,
  GraphCanvasHandle,
  GraphEdgeModel,
  GraphNodeModel,
} from '../components/graph/GraphCanvas'
import { buildBenchmarkGraph } from '../utils/graphBenchmark'
import { cn } from '../utils/cn'
import { riskColorForScore } from '../utils/riskColors'
import {
  GraphPathsResponse,
  GraphTimelineResponse,
  NetworkEdge,
  NetworkNode,
  NetworkResponse,
  SearchResult,
} from '../types/api'
import { formatInr, formatInrCompact, titleCase, truncateMiddle } from '../utils/format'

const RENDER_CAP = 800
const CANVAS_THRESHOLD = 1500
const MAX_HOPS = 4

const TYPE_STYLES: Record<string, { color: string; label: string; shape: string }> = {
  Company: { color: '#1F8A8C', label: 'Company', shape: 'circle' },
  Director: { color: '#D6A94A', label: 'Director', shape: 'diamond' },
  Address: { color: '#8B99AB', label: 'Address', shape: 'square' },
  BankAccount: { color: '#7383A5', label: 'Bank account', shape: 'circle' },
  Transaction: { color: '#4FD1D4', label: 'Transaction', shape: 'dot' },
  GSTINFiling: { color: '#6FCF97', label: 'GST return', shape: 'circle' },
}

const ALL_TYPES = Object.keys(TYPE_STYLES)

function toGraphNode(raw: NetworkNode): GraphNodeModel {
  const rawRisk = raw.properties?.risk_score
  const risk = typeof rawRisk === 'number' ? rawRisk : Number(rawRisk)
  return {
    id: raw.id,
    label: raw.label,
    type: raw.type,
    properties: raw.properties || {},
    risk_score: Number.isFinite(risk) ? risk : undefined,
  }
}

function toGraphEdge(raw: NetworkEdge): GraphEdgeModel {
  return {
    source: raw.source,
    target: raw.target,
    type: raw.type,
    properties: raw.properties || {},
    flagged: raw.flagged,
    eway_mismatch: raw.eway_mismatch,
    date: raw.date,
  }
}

function edgeEndpoints(edge: GraphEdgeModel): [string, string] {
  const source = typeof edge.source === 'string' ? edge.source : edge.source.id
  const target = typeof edge.target === 'string' ? edge.target : edge.target.id
  return [source, target]
}

function edgeKey(edge: GraphEdgeModel): string {
  const [source, target] = edgeEndpoints(edge)
  return `${source}|${target}|${edge.type}`
}

function mergeGraph(
  previousNodes: GraphNodeModel[],
  previousEdges: GraphEdgeModel[],
  incoming: { nodes: NetworkNode[]; edges: NetworkEdge[] },
): { nodes: GraphNodeModel[]; edges: GraphEdgeModel[] } {
  const nodes = [...previousNodes]
  const known = new Set(nodes.map((node) => node.id))
  for (const raw of incoming.nodes) {
    if (!known.has(raw.id)) {
      known.add(raw.id)
      nodes.push(toGraphNode(raw))
    }
  }
  const edges = [...previousEdges]
  const seen = new Set(edges.map(edgeKey))
  for (const raw of incoming.edges) {
    const edge = toGraphEdge(raw)
    const key = edgeKey(edge)
    if (!seen.has(key)) {
      seen.add(key)
      edges.push(edge)
    }
  }
  return { nodes, edges }
}

function filterDates(nodes: GraphNodeModel[]): string[] {
  return nodes
    .filter((node) => node.type === 'Transaction' && (node.properties?.invoice_date || node.properties?.date))
    .map((node) => String(node.properties.invoice_date || node.properties.date).slice(0, 10))
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value))
    .sort()
}

function dateLabel(timestamp: number): string {
  if (!timestamp) return '—'
  return new Date(timestamp).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export default function GraphWorkspace() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const toast = useToast().push
  const graphRef = useRef<GraphCanvasHandle>(null)
  const requestedBench = Number(searchParams.get('bench') || 0)
  const benchmarkMode = Number.isFinite(requestedBench) && requestedBench > 0

  const [entity, setEntity] = useState<any>(null)
  const [rawNodes, setRawNodes] = useState<GraphNodeModel[]>([])
  const [rawEdges, setRawEdges] = useState<GraphEdgeModel[]>([])
  const [rootId, setRootId] = useState('')
  const [timeline, setTimeline] = useState<GraphTimelineResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [graphLoading, setGraphLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hops, setHops] = useState(2)

  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set(ALL_TYPES))
  const [riskMin, setRiskMin] = useState(0)
  const [flaggedOnly, setFlaggedOnly] = useState(false)
  const [focusRing, setFocusRing] = useState(false)
  const [search, setSearch] = useState('')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [pinned, setPinned] = useState<Set<string>>(new Set())
  const [timeRange, setTimeRange] = useState<[number, number]>([0, 0])
  const [layout, setLayout] = useState<'force' | 'hierarchical'>('force')
  const [renderAll, setRenderAll] = useState(false)
  const [mobileFilters, setMobileFilters] = useState(false)

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [pathSource, setPathSource] = useState('')
  const [pathTarget, setPathTarget] = useState('')
  const [pathBusy, setPathBusy] = useState(false)
  const [pathsResult, setPathsResult] = useState<GraphPathsResponse | null>(null)
  const [pathsOpen, setPathsOpen] = useState(false)
  const [pathError, setPathError] = useState<string | null>(null)
  const [pathNodeIds, setPathNodeIds] = useState<Set<string>>(new Set())
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResult | null>(null)

  const [landingQuery, setLandingQuery] = useState('')
  const [landingResults, setLandingResults] = useState<SearchResult[]>([])
  const [landingLoading, setLandingLoading] = useState(false)

  const resetFilters = useCallback(() => {
    setTypeFilter(new Set(ALL_TYPES))
    setRiskMin(0)
    setFlaggedOnly(false)
    setFocusRing(false)
    setSearch('')
    setHidden(new Set())
    setPinned(new Set())
    setPathNodeIds(new Set())
    setPathsResult(null)
    setPathError(null)
    setLayout('force')
    setRenderAll(false)
    setSelectedId(null)
    const dates = filterDates(rawNodes)
    if (dates.length) {
      setTimeRange([Date.parse(dates[0]), Date.parse(dates[dates.length - 1])])
    } else {
      setTimeRange([0, 0])
    }
  }, [rawNodes])

  // Synthetic benchmark graph (no API). Used by the P2.3 performance guard.
  useEffect(() => {
    if (!benchmarkMode) return
    const graph = buildBenchmarkGraph(requestedBench)
    setRawNodes(graph.nodes)
    setRawEdges(graph.edges)
    setRootId(graph.rootId)
    setEntity({
      name: `Synthetic neighbourhood benchmark`,
      cin: `BENCH-${requestedBench}`,
      risk_score: 72,
      state: 'Benchmark',
    })
    setHops(2)
    setRenderAll(true)
    setLoading(false)
    setGraphLoading(false)
    setError(null)
    setSelectedId(null)
    setHidden(new Set())
    setPinned(new Set())
    setTimeline(null)
    const dates = filterDates(graph.nodes)
    setTimeRange(dates.length ? [Date.parse(dates[0]), Date.parse(dates[dates.length - 1])] : [0, 0])
  }, [benchmarkMode, requestedBench])

  const applyNetwork = useCallback((data: NetworkResponse, entityId: string, depth: number) => {
    const nodes = data.nodes.map(toGraphNode)
    const edges = data.edges.map(toGraphEdge)
    setRawNodes(nodes)
    setRawEdges(edges)
    setRootId(entityId)
    setHops(depth)
    setSelectedId(null)
    setHidden(new Set())
    setPinned(new Set())
    setRenderAll(false)
    setPathNodeIds(new Set())
    setPathsResult(null)
    const dates = filterDates(nodes)
    setTimeRange(dates.length ? [Date.parse(dates[0]), Date.parse(dates[dates.length - 1])] : [0, 0])
  }, [])

  const loadTimeline = useCallback(async (entityId: string, depth: number) => {
    try {
      const response = await api.get<GraphTimelineResponse>(
        `/entities/${encodeURIComponent(entityId)}/network/timeline`,
        { params: { hops: depth, bucket: 'month' } },
      )
      setTimeline(response.data)
    } catch {
      setTimeline(null)
    }
  }, [])

  useEffect(() => {
    if (benchmarkMode) return
    if (!id) {
      setLoading(false)
      setEntity(null)
      setRawNodes([])
      setRawEdges([])
      setError(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      api.get(`/entities/${encodeURIComponent(id)}`),
      api.get<NetworkResponse>(`/entities/${encodeURIComponent(id)}/network`, { params: { hops: 2 } }),
    ])
      .then(([entityResponse, networkResponse]) => {
        if (cancelled) return
        setEntity(entityResponse.data)
        applyNetwork(networkResponse.data, entityResponse.data.id || id, 2)
        void loadTimeline(entityResponse.data.id || id, 2)
      })
      .catch((requestError) => {
        if (cancelled) return
        setError(requestError?.response?.data?.detail?.message || 'Could not load this neighbourhood.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, benchmarkMode, applyNetwork, loadTimeline])

  useEffect(() => {
    if (id || benchmarkMode) return
    let cancelled = false
    setLandingLoading(true)
    api
      .get('/entities/search', { params: { q: landingQuery, limit: 30 } })
      .then((response) => {
        if (cancelled) return
        const companies = (response.data.results as SearchResult[]).filter((item) => item.type === 'Company')
        setLandingResults(companies.slice(0, 10))
      })
      .catch(() => {
        if (!cancelled) setLandingResults([])
      })
      .finally(() => {
        if (!cancelled) setLandingLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [id, benchmarkMode, landingQuery])

  const dateBounds = useMemo(() => {
    const dates = filterDates(rawNodes)
    if (!dates.length) return null
    return [Date.parse(dates[0]), Date.parse(dates[dates.length - 1])] as [number, number]
  }, [rawNodes])

  const view = useMemo(() => {
    let nodes = rawNodes.filter((node) => !TYPE_STYLES[node.type] || typeFilter.has(node.type))
    if (riskMin > 0) {
      nodes = nodes.filter(
        (node) => node.type !== 'Company' || (node.risk_score ?? 0) >= riskMin || node.id === rootId,
      )
    }
    const allowed = new Set(nodes.map((node) => node.id))
    let edges = rawEdges.filter((edge) => {
      const [source, target] = edgeEndpoints(edge)
      return allowed.has(source) && allowed.has(target)
    })
    if (dateBounds && (timeRange[0] > dateBounds[0] || timeRange[1] < dateBounds[1])) {
      edges = edges.filter((edge) => {
        if (!edge.date) return true
        const stamp = Date.parse(edge.date)
        if (Number.isNaN(stamp)) return true
        return stamp >= timeRange[0] && stamp <= timeRange[1]
      })
    }
    if (flaggedOnly) edges = edges.filter((edge) => edge.flagged)
    edges = edges.filter((edge) => {
      const [source, target] = edgeEndpoints(edge)
      return !hidden.has(source) && !hidden.has(target)
    })
    const visibleIds = new Set<string>()
    for (const edge of edges) {
      const [source, target] = edgeEndpoints(edge)
      visibleIds.add(source)
      visibleIds.add(target)
    }
    if (!hidden.has(rootId)) visibleIds.add(rootId)
    let visibleNodes = nodes.filter((node) => visibleIds.has(node.id))
    if (!renderAll && visibleNodes.length > RENDER_CAP) {
      visibleNodes = [...visibleNodes]
        .sort((left, right) => {
          if (left.id === rootId) return -1
          if (right.id === rootId) return 1
          return (right.risk_score ?? -1) - (left.risk_score ?? -1)
        })
        .slice(0, RENDER_CAP)
    }
    const capped = new Set(visibleNodes.map((node) => node.id))
    const visibleEdges = edges.filter((edge) => {
      const [source, target] = edgeEndpoints(edge)
      return capped.has(source) && capped.has(target)
    })
    return {
      nodes: visibleNodes,
      edges: visibleEdges,
      total: visibleIds.size,
      totalEdges: rawEdges.length,
    }
  }, [
    rawNodes,
    rawEdges,
    typeFilter,
    riskMin,
    rootId,
    dateBounds,
    timeRange,
    flaggedOnly,
    hidden,
    renderAll,
  ])

  const mode: 'svg' | 'canvas' = renderAll && view.nodes.length > CANVAS_THRESHOLD ? 'canvas' : 'svg'

  const selectedNode = useMemo(
    () => rawNodes.find((node) => node.id === selectedId) || null,
    [rawNodes, selectedId],
  )

  const searchMatches = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return new Set<string>()
    return new Set(
      view.nodes
        .filter((node) => {
          const properties = node.properties || {}
          return (
            node.label.toLowerCase().includes(query) ||
            String(properties.cin || '').toLowerCase().includes(query) ||
            String(properties.gstin || '').toLowerCase().includes(query) ||
            String(properties.invoice_no || '').toLowerCase().includes(query)
          )
        })
        .map((node) => node.id),
    )
  }, [search, view.nodes])

  const flaggedNodeIds = useMemo(() => {
    const ids = new Set<string>()
    for (const edge of rawEdges) {
      if (!edge.flagged) continue
      const [source, target] = edgeEndpoints(edge)
      ids.add(source)
      ids.add(target)
    }
    return ids
  }, [rawEdges])

  const highlightIds = pathNodeIds.size > 0 ? pathNodeIds : searchMatches
  const focusMode: 'none' | 'search' | 'ring' | 'path' = pathNodeIds.size > 0
    ? 'path'
    : searchMatches.size > 0
      ? 'search'
      : focusRing
        ? 'ring'
        : 'none'

  const companyOptions = useMemo(
    () =>
      rawNodes
        .filter((node) => node.type === 'Company')
        .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0))
        .slice(0, 400)
        .map((node) => ({
          value: node.id,
          label: `${node.label}${node.properties?.cin ? ` · ${truncateMiddle(String(node.properties.cin), 18)}` : ''}`,
        })),
    [rawNodes],
  )

  useEffect(() => {
    if (!rootId) return
    setPathSource((current) => current || rootId)
    setPathTarget((current) => {
      if (current) return current
      const other = companyOptions.find((option) => option.value !== rootId)
      return other?.value || ''
    })
  }, [rootId, companyOptions])

  const handleSelect = useCallback((node: GraphNodeModel | null) => {
    setSelectedId(node?.id || null)
  }, [])

  const handleBenchmark = useCallback((result: BenchmarkResult) => {
    setBenchmarkResult(result)
    ;(window as any).__graphBenchmark = { ...result, at: new Date().toISOString() }
  }, [])

  const expandHop = useCallback(async () => {
    if (!id || benchmarkMode) {
      toast({ title: 'Benchmark mode', description: 'Synthetic graphs cannot expand from a server.', tone: 'info' })
      return
    }
    if (hops >= MAX_HOPS) {
      toast({ title: 'Maximum depth reached', description: `This workspace loads up to ${MAX_HOPS} hops.` })
      return
    }
    const next = hops + 1
    setGraphLoading(true)
    try {
      const response = await api.get<NetworkResponse>(`/entities/${encodeURIComponent(id)}/network`, {
        params: { hops: next },
      })
      applyNetwork(response.data, rootId || id, next)
      void loadTimeline(rootId || id, next)
      toast({ title: `Expanded to ${next} hops`, description: `${response.data.nodes.length} nodes loaded.` })
    } catch {
      toast({ title: 'Could not expand', description: 'The neighbourhood request failed.', tone: 'critical' })
    } finally {
      setGraphLoading(false)
    }
  }, [id, benchmarkMode, hops, rootId, applyNetwork, loadTimeline, toast])

  const focusRingNodes = useCallback(() => {
    if (!flaggedNodeIds.size) {
      toast({ title: 'No flagged ring edges', description: 'This neighbourhood has no detected cycle edges.' })
      return
    }
    setFocusRing(true)
    setFlaggedOnly(false)
    graphRef.current?.focusNodes([...flaggedNodeIds])
  }, [flaggedNodeIds, toast])

  const findPaths = useCallback(async () => {
    if (!pathSource || !pathTarget) {
      toast({ title: 'Pick two companies', description: 'Choose a source and target first.' })
      return
    }
    if (pathSource === pathTarget) {
      toast({ title: 'Pick two different companies' })
      return
    }
    setPathBusy(true)
    setPathError(null)
    try {
      const response = await api.get<GraphPathsResponse>('/graph/paths', {
        params: { source: pathSource, target: pathTarget, max_length: 6, limit: 8 },
      })
      setPathsResult(response.data)
      const merged = mergeGraph(rawNodes, rawEdges, response.data)
      setRawNodes(merged.nodes)
      setRawEdges(merged.edges)
      setPathsOpen(true)
      if (response.data.paths.length > 0) {
        const ids = new Set(response.data.paths[0].node_ids)
        setPathNodeIds(ids)
        window.setTimeout(() => graphRef.current?.focusNodes([...ids]), 80)
      }
    } catch (requestError: any) {
      const detail = requestError?.response?.data?.detail
      setPathError(detail?.message || 'No connecting path was found.')
      setPathsResult(null)
    } finally {
      setPathBusy(false)
    }
  }, [pathSource, pathTarget, rawNodes, rawEdges, toast])

  const focusPath = useCallback((index: number) => {
    const path = pathsResult?.paths[index]
    if (!path) return
    const ids = new Set(path.node_ids)
    setPathNodeIds(ids)
    setPathsOpen(false)
    window.setTimeout(() => graphRef.current?.focusNodes([...ids]), 60)
  }, [pathsResult])

  const expandSelected = useCallback(() => {
    if (!selectedId) return
    const adjacent = new Set<string>()
    for (const edge of rawEdges) {
      const [source, target] = edgeEndpoints(edge)
      if (source === selectedId) adjacent.add(target)
      if (target === selectedId) adjacent.add(source)
    }
    const hiddenNeighbours = [...adjacent].filter((nodeId) => hidden.has(nodeId))
    if (hiddenNeighbours.length === 0) {
      void expandHop()
      return
    }
    setHidden((current) => {
      const next = new Set(current)
      for (const nodeId of hiddenNeighbours) next.delete(nodeId)
      return next
    })
    toast({ title: 'Expanded neighbours', description: `${hiddenNeighbours.length} hidden node(s) shown.` })
  }, [selectedId, rawEdges, hidden, expandHop, toast])

  const collapseSelected = useCallback(() => {
    if (!selectedId) return
    const adjacent = new Set<string>()
    for (const edge of rawEdges) {
      const [source, target] = edgeEndpoints(edge)
      if (source === selectedId) adjacent.add(target)
      if (target === selectedId) adjacent.add(source)
    }
    setHidden((current) => {
      const next = new Set(current)
      for (const nodeId of adjacent) next.add(nodeId)
      return next
    })
    toast({ title: 'Collapsed neighbours', description: `${adjacent.size} node(s) hidden.` })
  }, [selectedId, rawEdges, toast])

  const hideSelected = useCallback(() => {
    if (!selectedId) return
    setHidden((current) => new Set(current).add(selectedId))
    setSelectedId(null)
  }, [selectedId])

  const togglePinSelected = useCallback(() => {
    if (!selectedId) return
    setPinned((current) => {
      const next = new Set(current)
      if (next.has(selectedId)) next.delete(selectedId)
      else next.add(selectedId)
      return next
    })
  }, [selectedId])

  const resetWorkspace = useCallback(() => {
    resetFilters()
    graphRef.current?.reset()
  }, [resetFilters])

  const exportPng = useCallback(async () => {
    try {
      await graphRef.current?.exportPng()
      toast({ title: 'PNG exported', description: 'The graph was saved to your downloads.' })
    } catch {
      toast({ title: 'Export failed', tone: 'critical' })
    }
  }, [toast])

  const exportSvg = useCallback(async () => {
    try {
      await graphRef.current?.exportSvg()
      toast({ title: 'SVG exported', description: 'The graph was saved to your downloads.' })
    } catch {
      toast({ title: 'Export failed', tone: 'critical' })
    }
  }, [toast])

  const toggleType = (type: string) => {
    setTypeFilter((current) => {
      const next = new Set(current)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  if (!id && !benchmarkMode) {
    return (
      <div className="-m-4 flex min-h-[calc(100vh-8rem)] flex-col bg-canvas sm:-m-6">
        <div className="border-b border-border px-6 py-5">
          <p className="micro-label">Graph workspace</p>
          <h1 className="mt-1 text-2xl font-semibold text-text-primary">Investigate a neighbourhood</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Search for a company to open a full-bleed network canvas with time, ring and path controls.
          </p>
        </div>
        <div className="mx-auto w-full max-w-3xl px-6 py-8">
          <Input
            label="Entity search"
            placeholder="Search by name, CIN, GSTIN or DIN"
            value={landingQuery}
            onChange={(event) => setLandingQuery(event.target.value)}
            autoFocus
          />
          <div className="mt-5 space-y-2">
            {landingLoading && <p className="text-xs text-text-secondary">Searching…</p>}
            {!landingLoading && landingResults.length === 0 && (
              <EmptyState
                compact
                title="No companies found"
                description="Try a shorter name, a CIN, or a GSTIN."
                action={
                  <Button variant="secondary" size="sm" onClick={() => setLandingQuery('')}>
                    Clear search
                  </Button>
                }
              />
            )}
            {landingResults.map((result) => (
              <button
                key={result.id}
                type="button"
                onClick={() => navigate(`/graph/${encodeURIComponent(result.identifier || result.id)}`)}
                className="flex w-full items-center justify-between gap-4 rounded-xl border border-border bg-surface px-4 py-3 text-left transition-colors hover:border-accent-ring/70 hover:bg-raised"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-text-primary">{result.name}</span>
                  <span className="block truncate font-mono text-[11px] text-text-secondary">
                    {result.identifier} · {result.state || 'State not recorded'}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {result.risk_score !== undefined && <RiskBadge score={result.risk_score} />}
                  <span className="text-xs text-accent-ring">Open graph →</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="-m-4 flex h-[calc(100vh-8rem)] items-center justify-center bg-canvas sm:-m-6">
        <div className="text-center">
          <div className="mx-auto h-9 w-9 animate-spin rounded-full border-2 border-border border-t-accent-ring" />
          <p className="mt-3 text-sm text-text-secondary">Loading neighbourhood…</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="-m-4 flex h-[calc(100vh-8rem)] items-center justify-center bg-canvas sm:-m-6">
        <EmptyState
          title="Could not open the graph workspace"
          description={error}
          action={
            <div className="flex gap-2">
              <Button onClick={() => window.location.reload()}>Retry</Button>
              <Button variant="secondary" onClick={() => navigate('/worklist')}>
                Back to worklist
              </Button>
            </div>
          }
        />
      </div>
    )
  }

  const riskScore = entity?.risk_score

  return (
    <div className="-m-4 flex h-[calc(100vh-8rem)] min-h-[560px] flex-col overflow-hidden bg-canvas sm:-m-6">
      <header className="flex h-14 shrink-0 flex-wrap items-center gap-2 border-b border-border bg-surface/80 px-3 backdrop-blur">
        <Button
          variant="ghost"
          size="sm"
          className="lg:hidden"
          onClick={() => setMobileFilters((current) => !current)}
          aria-pressed={mobileFilters}
        >
          Filters
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Link
              to={id ? `/entity/${encodeURIComponent(id)}/network` : '/worklist'}
              className="truncate text-sm font-semibold text-text-primary hover:text-accent-ring"
            >
              {entity?.name || 'Graph workspace'}
            </Link>
            {riskScore !== undefined && <RiskBadge score={riskScore} />}
            {benchmarkMode && <Badge tone="amber">Synthetic benchmark</Badge>}
          </div>
          <p className="truncate font-mono text-[10px] text-text-secondary">
            {entity?.cin || entity?.gstin || id || 'benchmark'} · {view.nodes.length.toLocaleString()} /{' '}
            {view.total.toLocaleString()} nodes · {view.edges.length.toLocaleString()} edges · {hops} hop
            {hops === 1 ? '' : 's'}
          </p>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          <div className="flex rounded-lg border border-border p-0.5" role="group" aria-label="Graph layout">
            <button
              type="button"
              onClick={() => setLayout('force')}
              className={cn(
                'rounded-md px-2 py-1 text-[11px] transition-colors',
                layout === 'force' ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary',
              )}
              aria-pressed={layout === 'force'}
            >
              Force
            </button>
            <button
              type="button"
              onClick={() => setLayout('hierarchical')}
              className={cn(
                'rounded-md px-2 py-1 text-[11px] transition-colors',
                layout === 'hierarchical' ? 'bg-accent text-white' : 'text-text-secondary hover:text-text-primary',
              )}
              aria-pressed={layout === 'hierarchical'}
            >
              Hierarchical
            </button>
          </div>
          <Button size="sm" variant="secondary" loading={graphLoading} onClick={() => void expandHop()}>
            +1 hop
          </Button>
          <Button size="sm" variant="ghost" onClick={focusRingNodes}>
            Focus ring
          </Button>
          <Button size="sm" variant="ghost" onClick={() => graphRef.current?.fit()}>
            Fit
          </Button>
          <Button size="sm" variant="ghost" onClick={resetWorkspace}>
            Reset
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void exportPng()}>
            PNG
          </Button>
          <Button size="sm" variant="ghost" onClick={() => void exportSvg()}>
            SVG
          </Button>
          <Badge tone={mode === 'canvas' ? 'accent' : 'neutral'}>{mode === 'canvas' ? 'Canvas' : 'SVG'}</Badge>
        </div>
      </header>

      <div className="relative flex min-h-0 flex-1">
        <aside
          className={cn(
            'absolute inset-y-0 left-0 z-20 w-[286px] shrink-0 space-y-4 overflow-y-auto border-r border-border bg-surface p-3.5 lg:static lg:z-auto lg:block',
            mobileFilters ? 'block shadow-2xl' : 'hidden',
          )}
          aria-label="Graph filters"
        >
          <div>
            <div className="flex items-center justify-between">
              <p className="micro-label">Search in graph</p>
              <button
                type="button"
                className="text-[11px] text-text-disabled hover:text-text-primary lg:hidden"
                onClick={() => setMobileFilters(false)}
              >
                Close
              </button>
            </div>
            <Input
              className="mt-1.5"
              placeholder="Name, CIN, GSTIN, invoice"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search within graph"
            />
            {search && (
              <p className="mt-1 text-[11px] text-text-secondary">
                {searchMatches.size} match{searchMatches.size === 1 ? '' : 'es'} highlighted.
              </p>
            )}
          </div>

          <section>
            <p className="micro-label">Node types</p>
            <div className="mt-2 space-y-1.5">
              {ALL_TYPES.map((type) => {
                const count = rawNodes.filter((node) => node.type === type).length
                if (count === 0) return null
                const style = TYPE_STYLES[type]
                return (
                  <label key={type} className="flex cursor-pointer items-center gap-2 text-xs text-text-secondary">
                    <input
                      type="checkbox"
                      checked={typeFilter.has(type)}
                      onChange={() => toggleType(type)}
                      className="h-3.5 w-3.5 rounded border-border bg-canvas accent-accent"
                    />
                    <span
                      className="h-2.5 w-2.5 shrink-0"
                      style={{
                        backgroundColor: style.color,
                        borderRadius: style.shape === 'circle' || style.shape === 'dot' ? '9999px' : '2px',
                        transform: style.shape === 'diamond' ? 'rotate(45deg)' : undefined,
                      }}
                    />
                    <span className="flex-1">{style.label}</span>
                    <span className="font-mono text-[10px] text-text-disabled">{count.toLocaleString()}</span>
                  </label>
                )
              })}
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between">
              <label htmlFor="risk-min" className="micro-label">
                Minimum risk
              </label>
              <span className="font-mono text-xs" style={{ color: riskColorForScore(riskMin) }}>
                {riskMin}
              </span>
            </div>
            <input
              id="risk-min"
              type="range"
              min={0}
              max={100}
              step={5}
              value={riskMin}
              onChange={(event) => setRiskMin(Number(event.target.value))}
              className="mt-2 w-full accent-accent"
            />
            <p className="text-[11px] text-text-secondary">Companies below the threshold are hidden; structural nodes remain for context.</p>
          </section>

          <section className="space-y-2">
            <label className="flex cursor-pointer items-start gap-2 text-xs text-text-secondary">
              <input
                type="checkbox"
                checked={flaggedOnly}
                onChange={(event) => setFlaggedOnly(event.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-border bg-canvas accent-accent"
              />
              <span>
                <span className="block font-medium text-text-primary">Only flagged cycle edges</span>
                <span className="text-[11px]">Drops structural context and shows detected rings.</span>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-2 text-xs text-text-secondary">
              <input
                type="checkbox"
                checked={focusRing}
                onChange={(event) => setFocusRing(event.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-border bg-canvas accent-accent"
              />
              <span>
                <span className="block font-medium text-text-primary">Emphasise ring edges</span>
                <span className="text-[11px]">Dims everything outside flagged cycles.</span>
              </span>
            </label>
          </section>

          <section>
            <div className="flex items-center justify-between">
              <p className="micro-label">Invoice window</p>
              <button
                type="button"
                className="text-[11px] text-text-disabled hover:text-text-primary"
                onClick={() => {
                  if (dateBounds) setTimeRange(dateBounds)
                }}
              >
                All dates
              </button>
            </div>
            {dateBounds ? (
              <>
                <div className="mt-2 flex h-8 items-end gap-[2px]" aria-hidden="true">
                  {(timeline?.buckets || []).slice(-24).map((bucket) => {
                    const max = Math.max(...(timeline?.buckets || []).map((item) => item.amount), 1)
                    return (
                      <span
                        key={bucket.period}
                        title={`${bucket.period}: ${formatInr(bucket.amount)} across ${bucket.count} invoice(s)`}
                        className="min-w-[3px] flex-1 rounded-t-sm bg-accent/60"
                        style={{ height: `${Math.max(8, (bucket.amount / max) * 100)}%` }}
                      />
                    )
                  })}
                </div>
                <label className="mt-2 block text-[11px] text-text-secondary" htmlFor="time-from">
                  From <span className="font-mono text-text-primary">{dateLabel(timeRange[0])}</span>
                </label>
                <input
                  id="time-from"
                  type="range"
                  min={dateBounds[0]}
                  max={dateBounds[1]}
                  step={86400000}
                  value={timeRange[0]}
                  onChange={(event) => {
                    const next = Number(event.target.value)
                    setTimeRange([Math.min(next, timeRange[1]), timeRange[1]])
                  }}
                  className="w-full accent-accent"
                />
                <label className="block text-[11px] text-text-secondary" htmlFor="time-to">
                  To <span className="font-mono text-text-primary">{dateLabel(timeRange[1])}</span>
                </label>
                <input
                  id="time-to"
                  type="range"
                  min={dateBounds[0]}
                  max={dateBounds[1]}
                  step={86400000}
                  value={timeRange[1]}
                  onChange={(event) => {
                    const next = Number(event.target.value)
                    setTimeRange([timeRange[0], Math.max(next, timeRange[0])])
                  }}
                  className="w-full accent-accent"
                />
              </>
            ) : (
              <p className="mt-2 text-[11px] text-text-secondary">
                No dated invoices in this neighbourhood. The time slider appears when invoice dates exist.
              </p>
            )}
          </section>

          <section className="rounded-lg border border-border bg-canvas p-3">
            <div className="flex items-center justify-between">
              <p className="micro-label">Path finder</p>
              <InfoHint content="Shortest connecting paths traverse invoices, shared directors and shared addresses. Up to eight paths are returned." />
            </div>
            {benchmarkMode ? (
              <p className="mt-2 text-[11px] text-text-secondary">Path finding is disabled for synthetic benchmarks.</p>
            ) : (
              <div className="mt-2 space-y-2">
                <Select
                  label="From"
                  selectSize="sm"
                  value={pathSource}
                  onChange={(event) => setPathSource(event.target.value)}
                  options={companyOptions}
                />
                <Select
                  label="To"
                  selectSize="sm"
                  value={pathTarget}
                  onChange={(event) => setPathTarget(event.target.value)}
                  options={companyOptions}
                />
                <Button size="sm" fullWidth loading={pathBusy} onClick={() => void findPaths()}>
                  Find paths
                </Button>
                {pathNodeIds.size > 0 && (
                  <Button size="sm" variant="ghost" fullWidth onClick={() => setPathNodeIds(new Set())}>
                    Clear path highlight
                  </Button>
                )}
                {pathError && <p className="text-[11px] text-risk-critical">{pathError}</p>}
              </div>
            )}
          </section>

          <section>
            <div className="flex items-center gap-1.5">
              <p className="micro-label">Legend</p>
              <InfoHint content="Risk is shown by the outer ring and the number inside company nodes. Cycle edges are red with arrowheads; dashed orange edges are high-value invoices with no matching e-Way Bill." />
            </div>
            <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5 text-[11px] text-text-secondary">
              {ALL_TYPES.filter((type) => rawNodes.some((node) => node.type === type)).map((type) => (
                <span key={type} className="flex items-center gap-1.5">
                  <span
                    className="h-2.5 w-2.5 shrink-0"
                    style={{
                      backgroundColor: TYPE_STYLES[type].color,
                      borderRadius: TYPE_STYLES[type].shape === 'circle' || TYPE_STYLES[type].shape === 'dot' ? '9999px' : '2px',
                      transform: TYPE_STYLES[type].shape === 'diamond' ? 'rotate(45deg)' : undefined,
                    }}
                  />
                  {TYPE_STYLES[type].label}
                </span>
              ))}
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 bg-risk-critical" /> Cycle edge
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 border-t border-dashed border-risk-high" /> e-Way gap
              </span>
            </div>
          </section>

          <Button variant="secondary" size="sm" fullWidth onClick={resetFilters}>
            Reset filters
          </Button>
        </aside>

        <section className="relative min-w-0 flex-1">
          {view.nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                title="Nothing matches these filters"
                description="Widen the risk threshold, re-enable node types, or reset filters."
                action={<Button size="sm" onClick={resetFilters}>Reset filters</Button>}
              />
            </div>
          ) : (
            <GraphCanvas
              ref={graphRef}
              nodes={view.nodes}
              edges={view.edges}
              rootId={rootId}
              mode={mode}
              layout={layout}
              highlightIds={highlightIds}
              focusMode={focusMode}
              selectedId={selectedId}
              pinnedIds={pinned}
              benchmark={benchmarkMode}
              onSelect={handleSelect}
              onBenchmark={handleBenchmark}
            />
          )}

          {view.total > view.nodes.length && (
            <div className="absolute left-1/2 top-3 z-10 flex max-w-[92%] -translate-x-1/2 items-center gap-3 rounded-lg border border-risk-high/40 bg-surface/95 px-3 py-2 text-xs shadow-lg backdrop-blur">
              <span className="text-text-secondary">
                Showing {view.nodes.length.toLocaleString()} of {view.total.toLocaleString()} nodes to keep
                rendering responsive.
              </span>
              <Button size="sm" onClick={() => setRenderAll(true)}>
                Render all
              </Button>
            </div>
          )}

          <div className="pointer-events-none absolute left-3 top-3 flex flex-col gap-1.5">
            {pathNodeIds.size > 0 && (
              <div className="pointer-events-auto flex items-center gap-2 rounded-lg border border-amber/40 bg-surface/95 px-3 py-1.5 text-[11px] shadow backdrop-blur">
                <span className="font-medium text-amber">Path highlighted</span>
                <button type="button" className="text-text-secondary hover:text-text-primary" onClick={() => setPathNodeIds(new Set())}>
                  Clear
                </button>
              </div>
            )}
            {flaggedOnly && (
              <div className="rounded-lg border border-risk-critical/40 bg-surface/95 px-3 py-1.5 text-[11px] text-risk-critical shadow backdrop-blur">
                Showing flagged cycle edges only
              </div>
            )}
            {benchmarkResult && (
              <div className="rounded-lg border border-accent-ring/40 bg-surface/95 px-3 py-1.5 text-[11px] shadow backdrop-blur">
                <span className="font-medium text-text-primary">Render benchmark</span>{' '}
                <span className="font-mono text-accent-ring">
                  {benchmarkResult.nodes.toLocaleString()} nodes · {benchmarkResult.fps.toFixed(1)} fps ·{' '}
                  {benchmarkResult.mode}
                </span>
              </div>
            )}
          </div>

          {graphLoading && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-canvas/50 backdrop-blur-[1px]">
              <div className="rounded-lg border border-border bg-surface px-4 py-3 text-xs text-text-secondary shadow-lg">
                Expanding neighbourhood…
              </div>
            </div>
          )}
        </section>
      </div>

      <Drawer
        open={Boolean(selectedNode)}
        onClose={() => setSelectedId(null)}
        title={selectedNode?.label || 'Node'}
        description={
          selectedNode
            ? `${titleCase(selectedNode.type)}${
                selectedNode.risk_score !== undefined ? ` · risk ${Math.round(selectedNode.risk_score)}` : ''
              }`
            : undefined
        }
        size="md"
        footer={
          selectedNode ? (
            <div className="flex w-full flex-wrap items-center gap-2">
              <Button size="sm" onClick={expandSelected}>
                Expand neighbours
              </Button>
              <Button size="sm" variant="secondary" onClick={collapseSelected}>
                Collapse
              </Button>
              <Button size="sm" variant="ghost" onClick={togglePinSelected}>
                {pinned.has(selectedNode.id) ? 'Unpin' : 'Pin'}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => graphRef.current?.focusNodes([selectedNode.id])}>
                Focus
              </Button>
              <Button size="sm" variant="ghost" onClick={hideSelected}>
                Hide
              </Button>
            </div>
          ) : undefined
        }
      >
        {selectedNode && (
          <div className="space-y-5">
            <div className="flex flex-wrap items-center gap-2">
              {selectedNode.risk_score !== undefined && <RiskBadge score={selectedNode.risk_score} />}
              <Badge tone="neutral">{titleCase(selectedNode.type)}</Badge>
              {pinned.has(selectedNode.id) && <Badge tone="amber">Pinned</Badge>}
            </div>

            <div className="grid gap-2 rounded-lg border border-border bg-canvas p-3 text-xs">
              <div className="flex items-center justify-between gap-3">
                <span className="text-text-secondary">Graph id</span>
                <span className="truncate font-mono text-[11px] text-text-primary">{selectedNode.id}</span>
              </div>
              {Object.entries(selectedNode.properties || {})
                .filter(([, value]) => value !== null && value !== undefined && value !== '')
                .slice(0, 18)
                .map(([key, value]) => (
                  <div key={key} className="flex items-start justify-between gap-3">
                    <span className="shrink-0 text-text-secondary">{titleCase(key)}</span>
                    <span className="break-all text-right font-mono text-[11px] text-text-primary">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
            </div>

            <div className="space-y-2">
              <p className="micro-label">Path finder</p>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="secondary" onClick={() => setPathSource(selectedNode.id)}>
                  Set as source
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setPathTarget(selectedNode.id)}>
                  Set as target
                </Button>
              </div>
            </div>

            {selectedNode.type === 'Company' && (
              <Button
                size="sm"
                variant="secondary"
                fullWidth
                onClick={() =>
                  navigate(
                    `/entity/${encodeURIComponent(
                      String(selectedNode.properties?.cin || selectedNode.id),
                    )}/network`,
                  )
                }
              >
                Open entity workspace
              </Button>
            )}

            {pathsResult && pathsResult.paths.length > 0 && (
              <div className="rounded-lg border border-border bg-canvas p-3">
                <p className="micro-label">Current path result</p>
                <p className="mt-1 text-xs text-text-secondary">
                  {pathsResult.paths.length} path(s), shortest {pathsResult.paths[0].length} edge(s).
                </p>
                <Button size="sm" variant="ghost" className="mt-2" onClick={() => setPathsOpen(true)}>
                  View paths
                </Button>
              </div>
            )}
          </div>
        )}
      </Drawer>

      <Modal
        open={pathsOpen}
        onClose={() => setPathsOpen(false)}
        title="Shortest connecting paths"
        description="Paths may traverse invoice transactions, shared directors and shared addresses."
        size="lg"
        footer={
          <Button variant="secondary" size="sm" onClick={() => setPathsOpen(false)}>
            Close
          </Button>
        }
      >
        {!pathsResult || pathsResult.paths.length === 0 ? (
          <EmptyState
            compact
            title="No connecting path"
            description={pathError || 'No path exists within six hops, or the two companies are disconnected.'}
          />
        ) : (
          <div className="space-y-2">
            {pathsResult.paths.map((path, index) => {
              const labels = path.node_ids.map(
                (nodeId) => rawNodes.find((node) => node.id === nodeId)?.label || nodeId,
              )
              return (
                <div key={`${index}-${path.node_ids.join('-')}`} className="rounded-lg border border-border bg-canvas p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge tone="accent">{path.length} edge{path.length === 1 ? '' : 's'}</Badge>
                      {path.total_amount !== undefined && (
                        <span className="font-mono text-[11px] text-amber">{formatInrCompact(path.total_amount)}</span>
                      )}
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => focusPath(index)}>
                      Show on canvas
                    </Button>
                  </div>
                  <p className="mt-2 break-words text-[11px] leading-relaxed text-text-secondary">
                    {labels.map((label, labelIndex) => (
                      <span key={`${label}-${labelIndex}`}>
                        <span className="text-text-primary">{label}</span>
                        {labelIndex < labels.length - 1 && <span className="mx-1 text-accent-ring">→</span>}
                      </span>
                    ))}
                  </p>
                </div>
              )
            })}
          </div>
        )}
      </Modal>
    </div>
  )
}
