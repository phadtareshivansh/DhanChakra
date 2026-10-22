import { t } from '../../i18n'
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from 'react'
import * as d3 from 'd3'
import { formatInr } from '../../utils/format'

export interface GraphNodeModel extends d3.SimulationNodeDatum {
  id: string
  label: string
  type: string
  properties: Record<string, any>
  risk_score?: number
}

export interface GraphEdgeModel extends d3.SimulationLinkDatum<GraphNodeModel> {
  source: string | GraphNodeModel
  target: string | GraphNodeModel
  type: string
  properties: Record<string, any>
  flagged?: boolean
  eway_mismatch?: boolean
  date?: string | null
}

export interface BenchmarkResult {
  nodes: number
  edges: number
  mode: 'svg' | 'canvas'
  fps: number
  frames: number
  seconds: number
}

export interface GraphCanvasHandle {
  fit: () => void
  reset: () => void
  focusNodes: (ids: string[]) => void
  exportPng: () => Promise<void>
  exportSvg: () => Promise<void>
}

interface GraphCanvasProps {
  nodes: GraphNodeModel[]
  edges: GraphEdgeModel[]
  rootId: string
  mode: 'svg' | 'canvas'
  layout: 'force' | 'hierarchical'
  highlightIds?: Set<string>
  focusMode?: 'none' | 'search' | 'ring' | 'path'
  selectedId?: string | null
  pinnedIds?: Set<string>
  benchmark?: boolean
  onSelect: (node: GraphNodeModel | null) => void
  onBenchmark?: (result: BenchmarkResult) => void
}

const TYPE_COLORS: Record<string, string> = {
  Company: '#1F8A8C',
  Director: '#D6A94A',
  Address: '#8B99AB',
  BankAccount: '#7383A5',
  Transaction: '#4FD1D4',
  GSTINFiling: '#6FCF97',
}

const RISK_COLORS = {
  critical: '#E5484D',
  high: '#F97316',
  medium: '#EAB308',
  low: '#22C55E',
}

function riskColor(score?: number): string {
  if (score === undefined || score === null) return '#26303E'
  if (score >= 85) return RISK_COLORS.critical
  if (score >= 65) return RISK_COLORS.high
  if (score >= 40) return RISK_COLORS.medium
  return RISK_COLORS.low
}

function nodeRadius(node: GraphNodeModel): number {
  if (node.type === 'Company') return 16 + Math.min(8, (node.risk_score || 0) / 20)
  if (node.type === 'Transaction') return 5
  if (node.type === 'Director') return 11
  return 10
}

function endpointId(endpoint: string | GraphNodeModel): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

function edgeKey(edge: GraphEdgeModel): string {
  return `${endpointId(edge.source)}|${endpointId(edge.target)}|${edge.type}`
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

const GraphCanvas = forwardRef<GraphCanvasHandle, GraphCanvasProps>(function GraphCanvas(
  props,
  ref,
) {
  const {
    nodes,
    edges,
    rootId,
    mode,
    layout,
    highlightIds,
    focusMode = 'none',
    selectedId,
    pinnedIds,
    benchmark,
    onSelect,
    onBenchmark,
  } = props

  const containerRef = useRef<HTMLDivElement>(null)
  const svgRef = useRef<SVGSVGElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const minimapRef = useRef<HTMLCanvasElement>(null)
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const transformRef = useRef(d3.zoomIdentity)
  const simulationRef = useRef<d3.Simulation<GraphNodeModel, undefined> | null>(null)
  const nodeSelRef = useRef<d3.Selection<SVGGElement, GraphNodeModel, SVGGElement, unknown> | null>(null)
  const edgeSelRef = useRef<d3.Selection<SVGLineElement, GraphEdgeModel, SVGGElement, unknown> | null>(null)
  const drawRef = useRef<(() => void) | null>(null)
  const minimapDrawRef = useRef<(() => void) | null>(null)
  const applyTransformRef = useRef<((transform: d3.ZoomTransform) => void) | null>(null)
  const sizeRef = useRef({ width: 800, height: 600 })
  const [size, setSize] = useState({ width: 800, height: 600 })
  const [hover, setHover] = useState<{ node: GraphNodeModel; x: number; y: number } | null>(null)
  const stateRef = useRef({ highlightIds, focusMode, selectedId, nodes, edges, rootId })
  stateRef.current = { highlightIds, focusMode, selectedId, nodes, edges, rootId }

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const update = () => {
      const width = Math.max(320, element.clientWidth)
      const height = Math.max(320, element.clientHeight)
      sizeRef.current = { width, height }
      setSize({ width, height })
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const drawMinimap = useCallback(() => {
    const canvas = minimapRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const width = 150
    const height = 96
    const dpr = window.devicePixelRatio || 1
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = 'rgba(11,15,20,0.85)'
    ctx.fillRect(0, 0, width, height)
    const { nodes: currentNodes } = stateRef.current
    if (currentNodes.length === 0) return

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const node of currentNodes) {
      if (node.x === undefined || node.y === undefined || Number.isNaN(node.x) || Number.isNaN(node.y)) continue
      minX = Math.min(minX, node.x)
      maxX = Math.max(maxX, node.x)
      minY = Math.min(minY, node.y)
      maxY = Math.max(maxY, node.y)
    }
    if (!Number.isFinite(minX)) return
    const spanX = Math.max(1, maxX - minX)
    const spanY = Math.max(1, maxY - minY)
    const scale = Math.min((width - 10) / spanX, (height - 10) / spanY)
    const offsetX = (width - spanX * scale) / 2
    const offsetY = (height - spanY * scale) / 2

    ctx.fillStyle = 'rgba(79,209,212,0.55)'
    for (const node of currentNodes) {
      if (node.x === undefined || node.y === undefined) continue
      const x = offsetX + (node.x - minX) * scale
      const y = offsetY + (node.y - minY) * scale
      ctx.fillRect(x, y, 1.4, 1.4)
    }

    const transform = transformRef.current
    const { width: viewWidth, height: viewHeight } = sizeRef.current
    const vx = offsetX + (-transform.x / transform.k - minX) * scale
    const vy = offsetY + (-transform.y / transform.k - minY) * scale
    const vw = (viewWidth / transform.k) * scale
    const vh = (viewHeight / transform.k) * scale
    ctx.strokeStyle = '#4FD1D4'
    ctx.lineWidth = 1
    ctx.strokeRect(
      Math.max(1, vx),
      Math.max(1, vy),
      Math.min(width - 2, Math.max(4, vw)),
      Math.min(height - 2, Math.max(4, vh)),
    )
  }, [])
  minimapDrawRef.current = drawMinimap

  const buildSceneSvg = useCallback((): string => {
    const { nodes: currentNodes, edges: currentEdges } = stateRef.current
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const node of currentNodes) {
      if (node.x === undefined || node.y === undefined) continue
      minX = Math.min(minX, node.x)
      maxX = Math.max(maxX, node.x)
      minY = Math.min(minY, node.y)
      maxY = Math.max(maxY, node.y)
    }
    if (!Number.isFinite(minX)) {
      minX = 0; maxX = 800; minY = 0; maxY = 600
    }
    const pad = 60
    minX -= pad; maxX += pad; minY -= pad; maxY += pad
    const width = Math.max(320, maxX - minX)
    const height = Math.max(240, maxY - minY)
    const nodeById = new Map(currentNodes.map((node) => [node.id, node]))
    const parts: string[] = [
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="${minX} ${minY} ${width} ${height}">`,
      '<rect x="' + minX + '" y="' + minY + '" width="' + width + '" height="' + height + '" fill="#0B0F14"/>',
      '<defs><marker id="arrow" viewBox="0 -5 10 10" refX="22" refY="0" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,-5L10,0L0,5" fill="#E5484D"/></marker></defs>',
    ]
    for (const edge of currentEdges) {
      const source = nodeById.get(endpointId(edge.source))
      const target = nodeById.get(endpointId(edge.target))
      if (!source || !target || source.x === undefined || target.x === undefined) continue
      const color = edge.flagged ? '#E5484D' : edge.eway_mismatch ? '#F97316' : '#26303E'
      parts.push(
        `<line x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}" stroke="${color}" stroke-width="${edge.flagged ? 2.5 : 1}" ${edge.flagged ? 'marker-end="url(#arrow)"' : ''}/>`,
      )
    }
    for (const node of currentNodes) {
      if (node.x === undefined || node.y === undefined) continue
      const radius = nodeRadius(node)
      const fill = TYPE_COLORS[node.type] || '#64748b'
      const stroke = node.type === 'Company' ? riskColor(node.risk_score) : '#26303E'
      if (node.type === 'Director') {
        parts.push(`<rect x="${node.x - radius}" y="${node.y - radius}" width="${radius * 2}" height="${radius * 2}" fill="${fill}" stroke="${stroke}" stroke-width="2" transform="rotate(45 ${node.x} ${node.y})"/>`)
      } else if (node.type === 'Address') {
        parts.push(`<rect x="${node.x - radius}" y="${node.y - radius}" width="${radius * 2}" height="${radius * 2}" rx="2" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`)
      } else {
        parts.push(`<circle cx="${node.x}" cy="${node.y}" r="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`)
      }
      if (node.type === 'Company' && node.risk_score !== undefined) {
        parts.push(`<text x="${node.x}" y="${node.y + 3}" text-anchor="middle" font-family="monospace" font-size="9" fill="#E7EDF3">${Math.round(node.risk_score)}</text>`)
      }
      parts.push(`<text x="${node.x}" y="${node.y + radius + 12}" text-anchor="middle" font-family="monospace" font-size="10" fill="#E7EDF3">${escapeXml(node.label.slice(0, 24))}</text>`)
    }
    parts.push('</svg>')
    return parts.join('')
  }, [])

  useImperativeHandle(ref, () => ({
    fit: () => {
      const { nodes: currentNodes } = stateRef.current
      if (!currentNodes.length) return
      applyFit(currentNodes.map((node) => node.id))
    },
    reset: () => {
      applyTransformRef.current?.(d3.zoomIdentity)
    },
    focusNodes: (ids: string[]) => applyFit(ids),
    exportPng: async () => {
      const svg = buildSceneSvg()
      const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      try {
        await new Promise<void>((resolve, reject) => {
          const image = new Image()
          image.onload = () => {
            const width = Math.min(2400, image.width)
            const height = Math.max(400, (image.height / image.width) * width)
            const canvas = document.createElement('canvas')
            canvas.width = width
            canvas.height = height
            const ctx = canvas.getContext('2d')
            if (!ctx) { reject(new Error('Canvas unavailable')); return }
            ctx.fillStyle = '#0B0F14'
            ctx.fillRect(0, 0, width, height)
            ctx.drawImage(image, 0, 0, width, height)
            canvas.toBlob((png) => {
              if (!png) { reject(new Error('PNG encode failed')); return }
              downloadBlob(png, 'dhan-chakra-graph.png')
              resolve()
            }, 'image/png')
          }
          image.onerror = () => reject(new Error('Could not render SVG'))
          image.src = url
        })
      } finally {
        URL.revokeObjectURL(url)
      }
    },
    exportSvg: async () => {
      downloadBlob(new Blob([buildSceneSvg()], { type: 'image/svg+xml;charset=utf-8' }), 'dhan-chakra-graph.svg')
    },
  }))

  function applyFit(ids: string[]) {
    const { nodes: currentNodes } = stateRef.current
    const wanted = ids.length ? new Set(ids) : null
    const subset = currentNodes.filter((node) => !wanted || wanted.has(node.id))
    if (subset.length === 0) return
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const node of subset) {
      if (node.x === undefined || node.y === undefined) continue
      minX = Math.min(minX, node.x)
      maxX = Math.max(maxX, node.x)
      minY = Math.min(minY, node.y)
      maxY = Math.max(maxY, node.y)
    }
    if (!Number.isFinite(minX)) return
    const { width, height } = sizeRef.current
    const spanX = Math.max(80, maxX - minX)
    const spanY = Math.max(80, maxY - minY)
    const k = Math.max(0.08, Math.min(3, Math.min((width - 120) / spanX, (height - 120) / spanY)))
    const tx = width / 2 - ((minX + maxX) / 2) * k
    const ty = height / 2 - ((minY + maxY) / 2) * k
    applyTransformRef.current?.(d3.zoomIdentity.translate(tx, ty).scale(k))
  }

  // ==== SVG renderer ====
  useEffect(() => {
    if (mode !== 'svg' || !svgRef.current) return
    const width = size.width
    const height = size.height
    const svg = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('viewBox', `0 0 ${width} ${height}`)
    const root = svg.append('g').attr('class', 'zoom-layer')
    nodeSelRef.current = null
    edgeSelRef.current = null

    const defs = svg.append('defs')
    defs.append('marker')
      .attr('id', 'gc-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#E5484D')
    defs.append('marker')
      .attr('id', 'gc-arrow-normal')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 22)
      .attr('refY', 0)
      .attr('markerWidth', 5)
      .attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#4B5563')

    const link = root.append('g')
      .attr('class', 'graph-edges')
      .selectAll<SVGLineElement, GraphEdgeModel>('line')
      .data(edges, edgeKey)
      .join('line')
      .attr('stroke', (edge) => edge.flagged ? RISK_COLORS.critical : edge.eway_mismatch ? RISK_COLORS.high : '#26303E')
      .attr('stroke-width', (edge) => edge.flagged ? 2.5 : 1)
      .attr('stroke-dasharray', (edge) => edge.eway_mismatch && !edge.flagged ? '4 3' : null)
      .attr('marker-end', (edge) => edge.flagged ? 'url(#gc-arrow)' : null)
    edgeSelRef.current = link

    const node = root.append('g')
      .attr('class', 'graph-nodes')
      .selectAll<SVGGElement, GraphNodeModel>('g')
      .data(nodes, (node) => node.id)
      .join('g')
      .attr('class', 'graph-node')
      .style('cursor', 'pointer')
    nodeSelRef.current = node

    node.each(function (datum) {
      const group = d3.select(this)
      const radius = nodeRadius(datum)
      const fill = TYPE_COLORS[datum.type] || '#64748b'
      const stroke = datum.type === 'Company' ? riskColor(datum.risk_score) : '#26303E'
      if (datum.type === 'Director' || datum.type === 'Address') {
        group.append('rect')
          .attr('x', -radius)
          .attr('y', -radius)
          .attr('width', radius * 2)
          .attr('height', radius * 2)
          .attr('rx', datum.type === 'Address' ? 2 : 0)
          .attr('fill', fill)
          .attr('stroke', stroke)
          .attr('stroke-width', datum.type === 'Director' ? 2 : 1.5)
          .attr('transform', datum.type === 'Director' ? `rotate(45)` : null)
      } else {
        group.append('circle')
          .attr('r', radius)
          .attr('fill', fill)
          .attr('stroke', stroke)
          .attr('stroke-width', datum.type === 'Company' ? 2.5 : 1.5)
      }
      group.append('circle')
        .attr('class', 'node-halo')
        .attr('r', radius + 6)
        .attr('fill', 'none')
        .attr('stroke', '#4FD1D4')
        .attr('stroke-width', 2)
        .attr('opacity', 0)
        .style('pointer-events', 'none')
      if (datum.type === 'Company' && datum.risk_score !== undefined) {
        group.append('text')
          .attr('text-anchor', 'middle')
          .attr('dy', 3)
          .attr('fill', '#0B0F14')
          .attr('font-family', 'IBM Plex Mono, monospace')
          .attr('font-size', 9)
          .attr('font-weight', 600)
          .text(Math.round(datum.risk_score))
      }
      group.append('text')
        .attr('class', 'node-label')
        .attr('text-anchor', 'middle')
        .attr('dy', radius + 13)
        .attr('fill', '#E7EDF3')
        .attr('font-family', 'IBM Plex Mono, monospace')
        .attr('font-size', 10)
        .text(datum.label.length > 24 ? `${datum.label.slice(0, 24)}…` : datum.label)
    })

    node
      .on('click', (event, datum) => {
        event.stopPropagation()
        onSelect(datum)
      })
      .on('mouseenter', (event, datum) => {
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) setHover({ node: datum, x: event.clientX - rect.left, y: event.clientY - rect.top })
      })
      .on('mousemove', (event, datum) => {
        const rect = containerRef.current?.getBoundingClientRect()
        if (rect) setHover({ node: datum, x: event.clientX - rect.left, y: event.clientY - rect.top })
      })
      .on('mouseleave', () => setHover(null))

    const updatePositions = () => {
      link
        .attr('x1', (edge: any) => edge.source?.x ?? 0)
        .attr('y1', (edge: any) => edge.source?.y ?? 0)
        .attr('x2', (edge: any) => edge.target?.x ?? 0)
        .attr('y2', (edge: any) => edge.target?.y ?? 0)
      node.attr('transform', (datum: any) => `translate(${datum.x ?? 0},${datum.y ?? 0})`)
    }

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.05, 6])
      .on('zoom', (event) => {
        transformRef.current = event.transform
        root.attr('transform', event.transform.toString())
        minimapDrawRef.current?.()
      })
    zoomRef.current = zoom
    svg.call(zoom)
    svg.on('dblclick.zoom', null)
    applyTransformRef.current = (transform) => {
      svg.call(zoom.transform as any, transform)
    }

    if (layout === 'hierarchical') {
      layoutHierarchical(nodes, edges, rootId)
      updatePositions()
      minimapDrawRef.current?.()
      window.setTimeout(() => applyFit(nodes.map((item) => item.id)), 30)
      return () => { simulationRef.current?.stop() }
    }

    const simulation = d3.forceSimulation<GraphNodeModel>(nodes)
      .force('link', d3.forceLink<GraphNodeModel, GraphEdgeModel>(edges)
        .id((item) => item.id)
        .distance(nodes.length > 2000 ? 54 : 110)
        .strength(nodes.length > 2000 ? 0.25 : 0.5))
      .force('charge', d3.forceManyBody().strength(nodes.length > 2000 ? -60 : -320).theta(0.9))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .alphaDecay(nodes.length > 2000 ? 0.08 : 0.05)
    if (nodes.length <= 2000 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      simulation.force('collision', d3.forceCollide().radius(26))
    }
    simulationRef.current = simulation
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      // Settle the layout immediately instead of animating it.
      simulation.stop()
      simulation.tick(160)
      updatePositions()
      minimapDrawRef.current?.()
      const reducedTimer = window.setTimeout(() => applyFit(nodes.map((item) => item.id)), 30)
      return () => {
        window.clearTimeout(reducedTimer)
        simulation.stop()
        simulationRef.current = null
        svg.on('.zoom', null)
      }
    }
    let tickCount = 0
    simulation.on('tick', () => {
      updatePositions()
      tickCount += 1
      if (tickCount % 12 === 0) minimapDrawRef.current?.()
    })
    simulation.on('end', () => {
      updatePositions()
      minimapDrawRef.current?.()
      applyFit(nodes.map((item) => item.id))
    })
    const timer = window.setTimeout(() => {
      if (tickCount < 3) return
      applyFit(nodes.map((item) => item.id))
    }, 850)

    return () => {
      window.clearTimeout(timer)
      simulation.stop()
      simulationRef.current = null
      svg.on('.zoom', null)
    }
  }, [mode, layout, nodes, edges, rootId, size.width, size.height, onSelect])

  // ==== Canvas renderer ====
  useEffect(() => {
    if (mode !== 'canvas' || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const width = size.width
    const height = size.height
    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
    canvas.style.width = `${width}px`
    canvas.style.height = `${height}px`
    const nodeById = new Map(nodes.map((node) => [node.id, node]))

    const draw = () => {
      const view = stateRef.current
      const transform = transformRef.current
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)
      ctx.save()
      ctx.translate(transform.x, transform.y)
      ctx.scale(transform.k, transform.k)

      const highlighted = view.highlightIds && view.highlightIds.size > 0 ? view.highlightIds : null
      const ringFocus = view.focusMode === 'ring'
      const pathFocus = view.focusMode === 'path'
      const selected = view.selectedId
      const flaggedNodeIds = new Set<string>()
      if (ringFocus) {
        for (const edge of edges) {
          if (edge.flagged) {
            flaggedNodeIds.add(endpointId(edge.source))
            flaggedNodeIds.add(endpointId(edge.target))
          }
        }
      }

      for (const edge of edges) {
        const source = nodeById.get(endpointId(edge.source))
        const target = nodeById.get(endpointId(edge.target))
        if (!source || !target || source.x === undefined || target.x === undefined) continue
        const bothHighlighted = highlighted
          ? highlighted.has(source.id) && highlighted.has(target.id)
          : false
        let color = '#26303E'
        let edgeWidth = 1
        let alpha = 1
        if (edge.flagged) {
          color = RISK_COLORS.critical
          edgeWidth = 2.5
        } else if (edge.eway_mismatch) {
          color = RISK_COLORS.high
          edgeWidth = 1.6
        }
        if (ringFocus) {
          alpha = edge.flagged ? 1 : 0.07
        } else if (highlighted) {
          if (bothHighlighted) {
            color = pathFocus ? RISK_COLORS.medium : '#4FD1D4'
            edgeWidth = 2.5
          } else {
            alpha = 0.07
          }
        }
        ctx.globalAlpha = alpha
        ctx.strokeStyle = color
        ctx.lineWidth = edgeWidth
        if (edge.eway_mismatch && !edge.flagged) ctx.setLineDash([4, 3])
        else ctx.setLineDash([])
        ctx.beginPath()
        ctx.moveTo(source.x, source.y!)
        ctx.lineTo(target.x!, target.y!)
        ctx.stroke()
        if ((edge.flagged || bothHighlighted) && target.x !== undefined) {
          const angle = Math.atan2((target.y || 0) - (source.y || 0), (target.x || 0) - (source.x || 0))
          const arrowX = target.x - Math.cos(angle) * (nodeRadius(target) + 3)
          const arrowY = (target.y || 0) - Math.sin(angle) * (nodeRadius(target) + 3)
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.moveTo(arrowX, arrowY)
          ctx.lineTo(arrowX - Math.cos(angle - 0.4) * 8, arrowY - Math.sin(angle - 0.4) * 8)
          ctx.lineTo(arrowX - Math.cos(angle + 0.4) * 8, arrowY - Math.sin(angle + 0.4) * 8)
          ctx.closePath()
          ctx.fill()
        }
      }
      ctx.setLineDash([])

      for (const node of nodes) {
        if (node.x === undefined || node.y === undefined) continue
        const nodeHighlighted = highlighted?.has(node.id) ?? false
        let alpha = 1
        if (ringFocus) alpha = flaggedNodeIds.has(node.id) ? 1 : 0.12
        else if (highlighted) alpha = nodeHighlighted ? 1 : 0.12
        ctx.globalAlpha = alpha
        const radius = nodeRadius(node)
        const fill = TYPE_COLORS[node.type] || '#64748b'
        const stroke = node.type === 'Company' ? riskColor(node.risk_score) : '#26303E'
        ctx.fillStyle = fill
        ctx.strokeStyle = stroke
        ctx.lineWidth = node.type === 'Company' ? 2.5 : 1.5
        if (node.type === 'Director') {
          ctx.save()
          ctx.translate(node.x, node.y)
          ctx.rotate(Math.PI / 4)
          ctx.fillRect(-radius, -radius, radius * 2, radius * 2)
          ctx.strokeRect(-radius, -radius, radius * 2, radius * 2)
          ctx.restore()
        } else if (node.type === 'Address') {
          ctx.fillRect(node.x - radius, node.y - radius, radius * 2, radius * 2)
          ctx.strokeRect(node.x - radius, node.y - radius, radius * 2, radius * 2)
        } else {
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius, 0, Math.PI * 2)
          ctx.fill()
          ctx.stroke()
        }
        if (node.id === selected || (highlighted ? nodeHighlighted : false)) {
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius + 6, 0, Math.PI * 2)
          ctx.strokeStyle = '#4FD1D4'
          ctx.lineWidth = 2
          ctx.stroke()
        }
        if (node.type === 'Company' && node.risk_score !== undefined) {
          ctx.fillStyle = '#0B0F14'
          ctx.font = '600 9px "IBM Plex Mono", monospace'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(String(Math.round(node.risk_score)), node.x, node.y)
        }
        const showLabel = nodes.length <= 900 || node.id === selected || nodeHighlighted || node.id === rootId || transform.k > 1.4
        if (showLabel) {
          ctx.fillStyle = '#E7EDF3'
          ctx.font = '10px "IBM Plex Mono", monospace'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          const label = node.label.length > 24 ? `${node.label.slice(0, 24)}…` : node.label
          ctx.fillText(label, node.x, node.y + radius + 6)
        }
      }
      ctx.globalAlpha = 1
      ctx.restore()
    }
    drawRef.current = draw

    const hitTest = (clientX: number, clientY: number): GraphNodeModel | null => {
      const rect = canvas.getBoundingClientRect()
      const transform = transformRef.current
      const graphX = (clientX - rect.left - transform.x) / transform.k
      const graphY = (clientY - rect.top - transform.y) / transform.k
      let best: GraphNodeModel | null = null
      let bestDistance = Infinity
      const threshold = 16 / transform.k
      for (const node of nodes) {
        if (node.x === undefined || node.y === undefined) continue
        const distance = Math.hypot(node.x - graphX, node.y - graphY)
        if (distance < nodeRadius(node) + threshold && distance < bestDistance) {
          best = node
          bestDistance = distance
        }
      }
      return best
    }

    let dragging = false
    let moved = false
    let lastX = 0
    let lastY = 0
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      const rect = canvas.getBoundingClientRect()
      const mouseX = event.clientX - rect.left
      const mouseY = event.clientY - rect.top
      const transform = transformRef.current
      const factor = event.deltaY < 0 ? 1.15 : 1 / 1.15
      const nextK = Math.max(0.05, Math.min(6, transform.k * factor))
      const ratio = nextK / transform.k
      transformRef.current = d3.zoomIdentity
        .translate(mouseX - (mouseX - transform.x) * ratio, mouseY - (mouseY - transform.y) * ratio)
        .scale(nextK)
      draw()
      minimapDrawRef.current?.()
    }
    const onPointerDown = (event: PointerEvent) => {
      dragging = true
      moved = false
      lastX = event.clientX
      lastY = event.clientY
      canvas.setPointerCapture(event.pointerId)
    }
    const onPointerMove = (event: PointerEvent) => {
      if (dragging) {
        const dx = event.clientX - lastX
        const dy = event.clientY - lastY
        if (Math.abs(dx) + Math.abs(dy) > 2) moved = true
        lastX = event.clientX
        lastY = event.clientY
        const transform = transformRef.current
        transformRef.current = d3.zoomIdentity.translate(transform.x + dx, transform.y + dy).scale(transform.k)
        draw()
        minimapDrawRef.current?.()
        return
      }
      const hit = hitTest(event.clientX, event.clientY)
      const rect = containerRef.current?.getBoundingClientRect()
      if (rect) {
        setHover(hit ? { node: hit, x: event.clientX - rect.left, y: event.clientY - rect.top } : null)
      }
    }
    const onPointerUp = (event: PointerEvent) => {
      const wasDragging = dragging
      dragging = false
      if (!wasDragging) return
      if (!moved) {
        onSelect(hitTest(event.clientX, event.clientY))
      }
    }
    const onPointerLeave = () => setHover(null)
    canvas.addEventListener('wheel', onWheel, { passive: false })
    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('pointerleave', onPointerLeave)

    applyTransformRef.current = (transform) => {
      transformRef.current = transform
      draw()
    }

    if (layout === 'hierarchical') {
      layoutHierarchical(nodes, edges, rootId)
      draw()
      minimapDrawRef.current?.()
      window.setTimeout(() => applyFit(nodes.map((item) => item.id)), 30)
      return () => {
        canvas.removeEventListener('wheel', onWheel)
        canvas.removeEventListener('pointerdown', onPointerDown)
        canvas.removeEventListener('pointermove', onPointerMove)
        canvas.removeEventListener('pointerup', onPointerUp)
        canvas.removeEventListener('pointerleave', onPointerLeave)
      }
    }

    const simulation = d3.forceSimulation<GraphNodeModel>(nodes)
      .force('link', d3.forceLink<GraphNodeModel, GraphEdgeModel>(edges)
        .id((item) => item.id)
        .distance(nodes.length > 2000 ? 54 : 110)
        .strength(nodes.length > 2000 ? 0.25 : 0.5))
      .force('charge', d3.forceManyBody().strength(nodes.length > 2000 ? -60 : -320).theta(0.9))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .alphaDecay(nodes.length > 2000 ? 0.08 : 0.05)
    if (nodes.length <= 2000 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      simulation.force('collision', d3.forceCollide().radius(26))
    }
    simulationRef.current = simulation
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      // Settle the layout immediately instead of animating it.
      simulation.stop()
      simulation.tick(160)
      draw()
      minimapDrawRef.current?.()
      const reducedTimer = window.setTimeout(() => applyFit(nodes.map((item) => item.id)), 30)
      return () => {
        window.clearTimeout(reducedTimer)
        simulation.stop()
        simulationRef.current = null
        canvas.removeEventListener('wheel', onWheel)
        canvas.removeEventListener('pointerdown', onPointerDown)
        canvas.removeEventListener('pointermove', onPointerMove)
        canvas.removeEventListener('pointerup', onPointerUp)
        canvas.removeEventListener('pointerleave', onPointerLeave)
        drawRef.current = null
      }
    }
    let tickCount = 0
    simulation.on('tick', () => {
      draw()
      tickCount += 1
      if (tickCount % 10 === 0) minimapDrawRef.current?.()
    })
    simulation.on('end', () => {
      draw()
      minimapDrawRef.current?.()
      applyFit(nodes.map((item) => item.id))
    })
    const timer = window.setTimeout(() => applyFit(nodes.map((item) => item.id)), 900)
    draw()
    minimapDrawRef.current?.()

    return () => {
      window.clearTimeout(timer)
      simulation.stop()
      simulationRef.current = null
      canvas.removeEventListener('wheel', onWheel)
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('pointerleave', onPointerLeave)
      drawRef.current = null
    }
  }, [mode, layout, nodes, edges, rootId, size.width, size.height, onSelect])

  // ==== Highlight / focus ====
  useEffect(() => {
    if (mode !== 'svg') return
    const nodeGroups = nodeSelRef.current
    const lines = edgeSelRef.current
    if (!nodeGroups || !lines) return
    const active = (highlightIds && highlightIds.size > 0) || focusMode === 'ring' || !!selectedId
    if (!active) {
      nodeGroups.attr('opacity', 1)
      nodeGroups.select<SVGCircleElement>('.node-halo').attr('opacity', 0)
      nodeGroups.select<SVGTextElement>('.node-label').attr('display', null)
      lines
        .attr('opacity', 1)
        .attr('stroke', (edge) => edge.flagged ? RISK_COLORS.critical : edge.eway_mismatch ? RISK_COLORS.high : '#26303E')
        .attr('stroke-width', (edge) => edge.flagged ? 2.5 : 1)
      return
    }
    const flaggedNodeIds = new Set<string>()
    for (const edge of edges) {
      if (edge.flagged) {
        flaggedNodeIds.add(endpointId(edge.source))
        flaggedNodeIds.add(endpointId(edge.target))
      }
    }
    const highlighted = highlightIds && highlightIds.size > 0 ? highlightIds : null
    nodeGroups
      .attr('opacity', (node) => {
        if (node.id === selectedId) return 1
        if (focusMode === 'ring') return flaggedNodeIds.has(node.id) ? 1 : 0.12
        if (highlighted) return highlighted.has(node.id) ? 1 : 0.12
        return 1
      })
      .each(function (node) {
        const group = d3.select(this)
        const showHalo = node.id === selectedId
        group.select<SVGCircleElement>('.node-halo').attr('opacity', showHalo ? 0.9 : 0)
        const showLabel = nodes.length <= 220 || node.id === selectedId || (highlighted?.has(node.id) ?? false) || node.id === rootId
        group.select<SVGTextElement>('.node-label').attr('display', showLabel ? null : 'none')
      })
    lines
      .attr('opacity', (edge) => {
        if (focusMode === 'ring') return edge.flagged ? 1 : 0.06
        if (highlighted) {
          const source = endpointId(edge.source)
          const target = endpointId(edge.target)
          return highlighted.has(source) && highlighted.has(target) ? 1 : 0.06
        }
        return 1
      })
      .attr('stroke', (edge) => {
        if (highlighted && focusMode === 'path') {
          const source = endpointId(edge.source)
          const target = endpointId(edge.target)
          if (highlighted.has(source) && highlighted.has(target)) return RISK_COLORS.medium
        }
        return edge.flagged ? RISK_COLORS.critical : edge.eway_mismatch ? RISK_COLORS.high : '#26303E'
      })
      .attr('stroke-width', (edge) => {
        if (highlighted && focusMode === 'path') {
          const source = endpointId(edge.source)
          const target = endpointId(edge.target)
          if (highlighted.has(source) && highlighted.has(target)) return 2.5
        }
        return edge.flagged ? 2.5 : 1
      })
  }, [mode, highlightIds, focusMode, selectedId, nodes.length, edges, rootId])

  // Apply pin state without rebuilding the graph.
  useEffect(() => {
    for (const node of nodes) {
      if (pinnedIds?.has(node.id)) {
        if (node.x !== undefined) node.fx = node.x
        if (node.y !== undefined) node.fy = node.y
      } else {
        node.fx = null
        node.fy = null
      }
    }
    if (simulationRef.current && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      simulationRef.current.alpha(0.35).restart()
    } else if (mode === 'canvas') {
      drawRef.current?.()
    }
  }, [pinnedIds, nodes, mode])

  // Redraw canvas when selection/highlight changes.
  useEffect(() => {
    if (mode === 'canvas') drawRef.current?.()
  }, [mode, highlightIds, focusMode, selectedId])

  useEffect(() => {
    if (!benchmark) return
    let frames = 0
    let animation = 0
    const start = performance.now()
    const loop = () => {
      frames += 1
      const elapsed = performance.now() - start
      if (elapsed < 4000) {
        animation = requestAnimationFrame(loop)
      } else {
        onBenchmark?.({
          nodes: nodes.length,
          edges: edges.length,
          mode,
          fps: frames / (elapsed / 1000),
          frames,
          seconds: elapsed / 1000,
        })
      }
    }
    animation = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animation)
  }, [benchmark, nodes.length, edges.length, mode, onBenchmark])

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-canvas">
      {mode === 'svg' ? (
        <svg ref={svgRef} className="h-full w-full" role="img" aria-label={t('Investigation network graph')} />
      ) : (
        <canvas ref={canvasRef} className="h-full w-full touch-none" aria-label={t('Investigation network graph')} role="img" />
      )}
      <canvas
        ref={minimapRef}
        className="pointer-events-none absolute bottom-3 right-3 rounded-md border border-border shadow-lg"
        aria-hidden="true"
      />
      {hover && (
        <div
          className="pointer-events-none absolute z-20 max-w-xs rounded-lg border border-border bg-surface/95 p-2 text-xs shadow-xl backdrop-blur"
          style={{ left: Math.min(hover.x + 12, sizeRef.current.width - 240), top: Math.max(8, hover.y - 12) }}
        >
          <div className="font-medium text-text-primary">{hover.node.label}</div>
          <div className="text-[11px] text-text-secondary">
            {hover.node.type}
            {hover.node.risk_score !== undefined ? ` · risk ${Math.round(hover.node.risk_score)}` : ''}
          </div>
          {hover.node.properties?.gstin && (
            <div className="font-mono text-[10px] text-text-disabled">{hover.node.properties.gstin}</div>
          )}
          {hover.node.properties?.amount !== undefined && (
            <div className="font-mono text-[10px] text-amber">{formatInr(Number(hover.node.properties.amount))}</div>
          )}
        </div>
      )}
    </div>
  )
})

function layoutHierarchical(nodes: GraphNodeModel[], edges: GraphEdgeModel[], rootId: string) {
  const adjacency = new Map<string, Set<string>>()
  for (const node of nodes) adjacency.set(node.id, new Set())
  for (const edge of edges) {
    const source = endpointId(edge.source)
    const target = endpointId(edge.target)
    adjacency.get(source)?.add(target)
    adjacency.get(target)?.add(source)
  }
  const depth = new Map<string, number>()
  const queue: string[] = []
  if (adjacency.has(rootId)) {
    depth.set(rootId, 0)
    queue.push(rootId)
  }
  while (queue.length > 0) {
    const current = queue.shift() as string
    const currentDepth = depth.get(current) || 0
    for (const next of adjacency.get(current) || []) {
      if (!depth.has(next)) {
        depth.set(next, currentDepth + 1)
        queue.push(next)
      }
    }
  }
  let maxDepth = 0
  for (const value of depth.values()) maxDepth = Math.max(maxDepth, value)
  for (const node of nodes) {
    if (!depth.has(node.id)) depth.set(node.id, maxDepth + 1)
  }
  const layers = new Map<number, GraphNodeModel[]>()
  for (const node of nodes) {
    const layer = depth.get(node.id) || 0
    if (!layers.has(layer)) layers.set(layer, [])
    layers.get(layer)!.push(node)
  }
  const width = Math.max(600, Math.max(...nodes.map((node) => node.x || 0)) || 600)
  for (const [layer, members] of layers) {
    const spacing = Math.min(160, Math.max(80, width / Math.max(1, members.length)))
    const startX = width / 2 - ((members.length - 1) * spacing) / 2
    members.forEach((node, index) => {
      node.x = startX + index * spacing
      node.y = 60 + layer * 110
      node.fx = node.x
      node.fy = node.y
    })
  }
}

export default GraphCanvas
