import { useEffect, useRef, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import * as d3 from 'd3'
import api from '../utils/api'
import { NetworkResponse, ExplainResponse } from '../types/api'
import RiskBadge from '../components/RiskBadge'
import ExplainDrawer from '../components/ExplainDrawer'
import { riskColorForScore } from '../utils/riskColors'
import { RISK_THRESHOLDS } from '../config/risk'

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
}

const TYPE_COLORS: Record<string, string> = {
  Company: '#1F8A8C',
  Director: '#D6A94A',
  Address: '#8B99AB',
  BankAccount: '#7383A5',
  Transaction: '#4FD1D4',
  GSTINFiling: '#6FCF97',
}

export default function EntityDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const svgRef = useRef<SVGSVGElement>(null)
  const [tab, setTab] = useState<'network' | 'overview' | 'evidence'>('network')
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

  const load = async (depth: number) => {
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
      setError(err.response?.data?.detail?.message || 'Failed to load entity')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (id) load(2) }, [id])

  useEffect(() => {
    if (!id) return
    api.get(`/entities/${id}/explain`)
      .then((res) => setExplanation(res.data))
      .catch(() => setExplanation(null))
  }, [id])

  // Flagged-cycle edges are marked by the API (see graph_service.get_network),
  // so the highlight is deterministic and can't be lost to client-side races.
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
      .attr('stroke', (d: any) => d.flagged ? '#E5484D' : '#26303E')
      .attr('stroke-width', (d: any) => d.flagged ? 3 : 1.5)
      .attr('stroke-opacity', 0.85)
      .attr('marker-end', 'url(#arrow)')

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
    const svg = d3.select(svgRef.current)
    const width = svgRef.current!.clientWidth
    const height = svgRef.current!.clientHeight || 600
    const xVals = nodes.map((n) => (n as any).x ?? width / 2)
    const yVals = nodes.map((n) => (n as any).y ?? height / 2)
    const minX = Math.min(...xVals), maxX = Math.max(...xVals)
    const minY = Math.min(...yVals), maxY = Math.max(...yVals)
    const dx = maxX - minX || width, dy = maxY - minY || height
    const scale = Math.min(width / dx, height / dy) * 0.8
    const tx = width / 2 - (minX + dx / 2) * scale
    const ty = height / 2 - (minY + dy / 2) * scale
    svg.transition().duration(500).call(
      d3.zoom<SVGSVGElement, unknown>().transform as any,
      d3.zoomIdentity.translate(tx, ty).scale(scale)
    )
  }

  const createCase = async () => {
    if (!entity) return
    setCreatingCase(true)
    try {
      const res = await api.post('/cases', {
        title: `Investigation: ${entity.name || entity.cin}`,
        description: `Case opened from entity ${entity.cin || entity.id} with risk score ${entity.risk_score ?? 'n/a'}`,
        company_cin: entity.cin,
        priority: entity.risk_score && entity.risk_score >= RISK_THRESHOLDS.high ? 2 : entity.risk_score && entity.risk_score >= RISK_THRESHOLDS.medium ? 1 : 0,
      })
      navigate(`/cases?highlight=${res.data.id}`)
    } catch (err) {
      console.error(err)
      alert('Failed to open case')
    } finally {
      setCreatingCase(false)
    }
  }

  if (error && !entity) {
    return (
      <div className="panel p-10 text-center">
        <div className="text-risk-critical font-medium">{error}</div>
        <Link to="/worklist" className="btn-secondary mt-4">Back to worklist</Link>
      </div>
    )
  }

  const tabs = [
    { key: 'network' as const, label: 'Network' },
    { key: 'overview' as const, label: 'Overview' },
    { key: 'evidence' as const, label: 'Evidence' },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{entity?.name || 'Entity'}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="mono-id">{entity?.cin || entity?.id}</span>
            {entity?.gstin && <span className="mono-id text-text-secondary">{entity?.gstin}</span>}
            <RiskBadge score={entity?.risk_score} />
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-secondary" onClick={() => { setShowExplain(true) }} disabled={!explanation}>
            ⚠ Why flagged?
          </button>
          <button className="btn-primary" onClick={createCase} disabled={creatingCase}>
            {creatingCase ? 'Opening…' : 'Open case'}
          </button>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === t.key ? 'border-accent-ring text-accent-ring' : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="panel p-6 h-[560px]"><div className="skeleton h-full" /></div>
      ) : tab === 'network' ? (
        <div className="panel h-[560px] relative overflow-hidden">
          <svg ref={svgRef} className="w-full h-full" />
          <div className="absolute bottom-4 right-4 flex gap-2">
            <button className="btn-secondary btn-compact" onClick={fitView}>Fit to view</button>
            <button className="btn-secondary btn-compact" onClick={() => load(1)} disabled={hops === 1}>1-hop</button>
            <button className="btn-secondary btn-compact" onClick={() => load(2)} disabled={hops === 2}>2-hop</button>
            <button className="btn-secondary btn-compact" onClick={() => load(3)} disabled={hops === 3}>3-hop</button>
          </div>
          <div className="absolute top-3 left-3 flex flex-wrap gap-3 text-[11px] text-text-secondary pointer-events-none">
            <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-accent mr-1" />Company</span>
            <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-amber mr-1" />Director</span>
            <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-text-secondary mr-1" />Address</span>
            <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-secondary-400 mr-1" />Bank account</span>
            <span className="ml-2 text-risk-critical">red edges = flagged cycle</span>
          </div>

          {selectedNode && (
            <div className="absolute bottom-4 left-4 panel-raised p-4 rounded-lg max-w-xs">
              <h3 className="font-semibold text-sm">{selectedNode.label}</h3>
              <p className="text-xs text-text-secondary mt-0.5">{selectedNode.type}</p>
              <div className="mt-2 space-y-1 text-xs text-text-secondary max-h-40 overflow-y-auto">
                {Object.entries(selectedNode.properties).slice(0, 12).map(([k, v]) => (
                  <div key={k}><span className="text-text-primary font-medium">{k}:</span> <span className="font-mono">{String(v)}</span></div>
                ))}
              </div>
              {selectedNode.type === 'Company' && (
                <Link
                  to={`/entity/${selectedNode.properties.cin || selectedNode.id}/network`}
                  className="mt-3 text-xs text-accent-ring hover:underline"
                >
                  View network →
                </Link>
              )}
              <button onClick={() => setSelectedNode(null)} className="mt-2 text-xs text-text-secondary hover:text-text-primary">Close</button>
            </div>
          )}
        </div>
      ) : tab === 'overview' ? (
        <div className="grid grid-cols-2 gap-4">
          <div className="panel p-5">
            <div className="micro-label mb-3">Company details</div>
            <dl className="space-y-2 text-sm">
              {[
                ['CIN', entity?.cin], ['GSTIN', entity?.gstin], ['Name', entity?.name],
                ['Status', entity?.status], ['ROC', entity?.roc], ['NIC code', entity?.nic_code],
                ['Incorporated', entity?.incorporation_date], ['Authorized capital', entity?.authorized_capital ? `₹${entity.authorized_capital.toLocaleString('en-IN')}` : '—'],
                ['Paid-up capital', entity?.paid_up_capital ? `₹${entity.paid_up_capital.toLocaleString('en-IN')}` : '—'],
              ].map(([k, v]) => (
                <div key={k as string} className="flex justify-between border-b border-border pb-1.5">
                  <dt className="text-text-secondary">{k}</dt>
                  <dd className="font-mono text-[12px] text-right">{String(v ?? '—')}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="space-y-4">
            <div className="panel p-5">
              <div className="micro-label mb-3">Risk features</div>
              <dl className="space-y-2 text-sm">
                {[
                  ['Risk score', entity?.risk_score !== undefined ? `${Math.round(entity.risk_score)} / 100` : '—'],
                  ['Community ID', entity?.community_id || '—'],
                  ['PageRank', entity?.pagerank?.toFixed(4) || '—'],
                  ['Betweenness', entity?.betweenness?.toFixed(4) || '—'],
                ].map(([k, v]) => (
                  <div key={k as string} className="flex justify-between border-b border-border pb-1.5">
                    <dt className="text-text-secondary">{k}</dt>
                    <dd className="font-mono text-[12px]">{String(v)}</dd>
                  </div>
                ))}
              </dl>
              <div className="mt-4">
                <div className="micro-label mb-2">Risk level</div>
                <RiskBadge score={entity?.risk_score} />
              </div>
            </div>
            <div className="panel p-5">
              <div className="micro-label mb-3">Quick actions</div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary btn-compact" onClick={() => { setShowExplain(true) }} disabled={!explanation}>Explain flag</button>
                <button className="btn-secondary btn-compact" onClick={createCase} disabled={creatingCase}>Open case</button>
                <Link to="/worklist" className="btn-secondary btn-compact">Back to worklist</Link>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="panel p-5 space-y-4">
          <div className="micro-label">Why flagged?</div>
          {explanation ? (
            <>
              <ul className="space-y-2">
                {explanation.reasons.map((reason, i) => (
                  <li key={i} className="flex gap-2 text-sm"><span className="text-accent-ring">▸</span>{reason}</li>
                ))}
              </ul>
              {explanation.evidence.cycles.length > 0 && (
                <div>
                  <div className="micro-label mb-2">Detected loops</div>
                  {explanation.evidence.cycles.map((cycle, i) => (
                    <div key={i} className="panel p-3 mb-2">
                      <div className="text-xs text-risk-critical font-semibold mb-1">
                        {cycle.hop_count}-hop cycle · ₹{Number(cycle.total_amount || 0).toLocaleString('en-IN')}
                      </div>
                      <div className="font-mono text-[11px] text-text-secondary">
                        {cycle.members?.map((m: any) => m.name).join(' → ')}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {explanation.evidence.shared_directors.length > 0 && (
                <div>
                  <div className="micro-label mb-2">Shared directors</div>
                  {explanation.evidence.shared_directors.map((sd, i) => (
                    <div key={i} className="text-sm mb-1">{sd.director} — {sd.companies?.join(', ')}</div>
                  ))}
                </div>
              )}
              {explanation.evidence.shared_addresses.length > 0 && (
                <div>
                  <div className="micro-label mb-2">Shared registered addresses</div>
                  {explanation.evidence.shared_addresses.map((sa, i) => (
                    <div key={i} className="text-sm mb-1 font-mono text-[12px]">{sa.address} ({sa.state}) — {sa.companies?.join(', ')}</div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-text-secondary">No explanation available.</p>
          )}
        </div>
      )}

      {showExplain && explanation && (
        <ExplainDrawer data={explanation} entityId={id!} onClose={() => setShowExplain(false)} />
      )}
    </div>
  )
}