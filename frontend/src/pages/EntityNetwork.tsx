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

export default function EntityNetwork() {
  const { id } = useParams<{ id: string }>()
  const svgRef = useRef<SVGSVGElement>(null)
  const [nodes, setNodes] = useState<NetworkNode[]>([])
  const [edges, setEdges] = useState<NetworkEdge[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<NetworkNode | null>(null)

  useEffect(() => {
    if (!id) return
    
    const fetchNetwork = async () => {
      setLoading(true)
      try {
        const response = await api.get(`/entities/${id}/network?hops=2`)
        setNodes(response.data.nodes)
        setEdges(response.data.edges)
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

    const link = svg.append('g')
      .attr('stroke-opacity', 0.6)
      .selectAll('line')
      .data(edges)
      .join('line')
      .attr('stroke', (d) => (d.flagged ? '#e5484d' : '#94a3b8'))
      .attr('stroke-width', (d) => (d.flagged ? 3 : 2))

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
        <span className="text-red-600">red edges = flagged cycle</span>
      </div>
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