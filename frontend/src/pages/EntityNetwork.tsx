import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as d3 from 'd3'
import api from '../utils/api'

interface NetworkNode extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: string
  properties: Record<string, any>
}

interface NetworkEdge extends d3.SimulationLinkDatum<NetworkNode> {
  source: string | NetworkNode
  target: string | NetworkNode
  type: string
  properties: Record<string, any>
  flagged?: boolean
}

function pairKey(a: any, b: any) {
  const sa = a?.cin || a?.name || a
  const sb = b?.cin || b?.name || b
  return [String(sa), String(sb)].sort().join('::')
}

export default function EntityNetwork() {
  const { id } = useParams<{ id: string }>()
  const svgRef = useRef<SVGSVGElement>(null)
  const [nodes, setNodes] = useState<NetworkNode[]>([])
  const [edges, setEdges] = useState<NetworkEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null)
  const [timeline, setTimeline] = useState<any[]>([])
  const [timeRange, setTimeRange] = useState<[number, number]>([0, 0])
  const [burstPairs, setBurstPairs] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!id) return
    
    const fetchNetwork = async () => {
      setLoading(true)
      try {
        const response = await api.get(`/entities/${id}/network?hops=2`)
        setNodes(response.data.nodes || [])
        setEdges(response.data.edges || [])
        try {
          const t = await api.get(`/entities/${id}/timeline`)
          const tl = t.data?.timeline || []
          setTimeline(tl)
          if (tl.length) setTimeRange([0, tl.length - 1])
        } catch {
          setTimeline([])
        }
      } catch (err) {
        setError('Failed to load network')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    fetchNetwork()
  }, [id])

  useEffect(() => {
    const byPair: Record<string, any[]> = {}
    for (const t of timeline) {
      const k = pairKey(t.counterparty, { cin: id })
      if (!byPair[k]) byPair[k] = []
      byPair[k].push(t)
    }
    const bursts = new Set<string>()
    for (const [k, items] of Object.entries(byPair)) {
      if (items.length < 3) continue
      const sorted = [...items].sort((a: any, b: any) => String(a.date).localeCompare(String(b.date)))
      const first = new Date(sorted[0].date)
      const last = new Date(sorted[sorted.length - 1].date)
      const span = (last.getTime() - first.getTime()) / (1000 * 3600 * 24)
      if (span <= 14) bursts.add(k)
    }
    setBurstPairs(bursts)
  }, [timeline, id])

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return

    const svg = d3.select(svgRef.current)
    const width = svgRef.current.clientWidth
    const height = svgRef.current.clientHeight || 500

    svg.selectAll('*').remove()

    const simulation = d3.forceSimulation<NetworkNode>(nodes)
      .force('link', d3.forceLink<NetworkNode, NetworkEdge>(edges).id((d) => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40))

    const visibleEdges = timeline.length && timeRange[1] >= timeRange[0]
      ? edges.filter(() => true)
      : edges

    const isBurstEdge = (d: any) => {
      const s = typeof d.source === 'object' ? d.source : nodes.find(n => n.id === d.source)
      const t = typeof d.target === 'object' ? d.target : nodes.find(n => n.id === d.target)
      const k = pairKey(s, t)
      return burstPairs.has(k)
    }

    const link = svg.append('g')
      .attr('stroke-opacity', 0.6)
      .selectAll('line')
      .data(visibleEdges)
      .join('line')
      .attr('stroke', (d: any) => (d.flagged || isBurstEdge(d) ? '#e5484d' : (d.eway_mismatch ? '#f97316' : '#94a3b8')))
      .attr('stroke-width', (d: any) => (d.flagged || isBurstEdge(d) ? 3.5 : 2))
      .attr('stroke-dasharray', (d: any) => (isBurstEdge(d) && !d.flagged ? '6,4' : null))

    // e-Way Bill mismatch badge (TASK B1): an invoice whose high value has no
    // matching movement record. It is drawn as its own marker rather than
    // only a stroke colour, so an edge that is BOTH a flagged cycle edge and
    // an e-Way mismatch still shows both signals.
    const ewayBadge = svg.append('g')
      .selectAll('circle')
      .data(visibleEdges.filter((d: any) => d.eway_mismatch))
      .join('circle')
      .attr('r', 6)
      .attr('fill', '#f97316')
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
    ewayBadge.append('title')
      .text('e-Way Bill mismatch — high-value invoice with no matching movement record')

    const node = svg.append('g')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', 25)
      .attr('fill', (d) => {
        switch (d.type) {
          case 'Company': return '#0ea5e9'
          case 'Director': return '#22c55e'
          case 'Address': return '#f59e0b'
          case 'BankAccount': return '#8b5cf6'
          default: return '#64748b'
        }
      })
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .call(drag(simulation) as any)
      .on('click', (event, d) => {
        setSelectedNode(d)
        event.stopPropagation()
      })

    const label = svg.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .attr('font-size', 11)
      .attr('font-weight', 500)
      .attr('fill', '#1e293b')
      .attr('text-anchor', 'middle')
      .attr('dy', 35)
      .text((d) => d.label.length > 18 ? d.label.slice(0, 18) + '...' : d.label)

    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y)

      node
        .attr('cx', (d) => d.x ?? 0)
        .attr('cy', (d) => d.y ?? 0)

      label
        .attr('x', (d) => d.x ?? 0)
        .attr('y', (d) => d.y ?? 0)

      ewayBadge
        .attr('cx', (d: any) => (((d.source as any)?.x ?? 0) + ((d.target as any)?.x ?? 0)) / 2)
        .attr('cy', (d: any) => (((d.source as any)?.y ?? 0) + ((d.target as any)?.y ?? 0)) / 2)
    })

    function drag(simulation: d3.Simulation<NetworkNode, NetworkEdge>) {
      function dragstarted(event: d3.D3DragEvent<SVGCircleElement, NetworkNode, NetworkNode>) {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        event.subject.fx = event.subject.x
        event.subject.fy = event.subject.y
      }
      function dragged(event: d3.D3DragEvent<SVGCircleElement, NetworkNode, NetworkNode>) {
        event.subject.fx = event.x
        event.subject.fy = event.y
      }
      function dragended(event: d3.D3DragEvent<SVGCircleElement, NetworkNode, NetworkNode>) {
        if (!event.active) simulation.alphaTarget(0)
        event.subject.fx = null
        event.subject.fy = null
      }
      return d3.drag<SVGCircleElement, NetworkNode>().on('start', dragstarted).on('drag', dragged).on('end', dragended)
    }

    return () => {
      simulation.stop()
    }
  }, [nodes, edges])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[500px]">
        <div className="animate-spin rounded-full h-10 w-10 border-3 border-primary-600 border-t-transparent"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-[500px] text-red-600">
        {error}
      </div>
    )
  }

  return (
    <div className="h-[600px] bg-white rounded-lg border border-gray-200 relative">
      <svg ref={svgRef} className="w-full h-full" />
      <div className="absolute top-3 left-3 flex flex-wrap gap-3 text-[11px] text-gray-500 pointer-events-none">
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-sky-500 mr-1" />Company</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-green-500 mr-1" />Director</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500 mr-1" />Address</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-violet-500 mr-1" />Bank</span>
        <span className="text-red-600">red solid = flagged cycle</span>
        <span className="text-red-600">red dashed = burst (high-volume window)</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-full bg-orange-500 mr-1" />e-Way Bill mismatch (no movement record)</span>
      </div>
      {timeline.length > 0 && (
        <div className="absolute bottom-3 left-3 right-3 bg-white/90 p-2 rounded border border-gray-200">
          <div className="flex items-center gap-2 text-[11px] text-gray-600">
            <span>Timeline</span>
            <input type="range" min={0} max={timeline.length - 1} value={timeRange[1]} onChange={(e) => setTimeRange([0, parseInt(e.target.value)])} className="flex-1" />
            <span>{timeline[timeRange[1]]?.date}</span>
          </div>
        </div>
      )}
      {selectedNode && (
        <div className="absolute bottom-4 right-4 bg-white p-4 rounded-lg shadow-lg border border-gray-200 max-w-xs">
          <h3 className="font-semibold text-gray-900">{selectedNode.label}</h3>
          <p className="text-sm text-gray-500">{selectedNode.type}</p>
          <div className="mt-2 text-xs text-gray-600">
            {Object.entries(selectedNode.properties).map(([k, v]) => (
              <div key={k}><span className="font-medium">{k}:</span> {String(v)}</div>
            ))}
          </div>
          <button
            onClick={() => setSelectedNode(null)}
            className="mt-2 text-primary-600 hover:underline text-sm"
          >
            Close
          </button>
        </div>
      )}
    </div>
  )
}