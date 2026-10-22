import type { GraphEdgeModel, GraphNodeModel } from '../components/graph/GraphCanvas'

/**
 * Build a deterministic synthetic "neighbourhood" for render benchmarks.
 *
 * Real deployments do not ship a 10,000-node demo graph, so the P2.3
 * performance guard is exercised with a synthetic graph of the requested
 * size. The shape mirrors a GST network: mostly companies, plus directors,
 * addresses and invoice/transaction nodes linked by invoice and structural
 * edges. This measures the renderer, not the Neo4j query.
 */
export function buildBenchmarkGraph(count: number): {
  nodes: GraphNodeModel[]
  edges: GraphEdgeModel[]
  rootId: string
} {
  let seed = 20260722
  const random = () => {
    seed = (seed * 1664525 + 1013904223) % 4294967296
    return seed / 4294967296
  }

  const safeCount = Math.max(20, Math.floor(count))
  const nodes: GraphNodeModel[] = []
  const companies: GraphNodeModel[] = []
  const directors: GraphNodeModel[] = []
  const addresses: GraphNodeModel[] = []

  for (let index = 0; index < safeCount; index += 1) {
    const roll = random()
    let type = 'Company'
    if (roll > 0.82) type = 'Transaction'
    else if (roll > 0.66) type = 'Director'
    else if (roll > 0.54) type = 'Address'

    const suffix = String(index).padStart(6, '0')
    const node: GraphNodeModel = {
      id: `bench-${suffix}`,
      label:
        type === 'Company'
          ? `Benchmark Traders ${suffix}`
          : type === 'Director'
            ? `Director ${suffix}`
            : type === 'Address'
              ? `Address ${suffix}`
              : `INV-${suffix}`,
      type,
      properties:
        type === 'Company'
          ? {
              cin: `U${suffix}MH2020PTC${suffix}`,
              gstin: `27ABCDE${suffix.slice(-4)}F1Z${index % 10}`,
              state: index % 3 === 0 ? 'Maharashtra' : index % 3 === 1 ? 'Gujarat' : 'Delhi',
            }
          : type === 'Transaction'
            ? {
                invoice_no: `INV-${suffix}`,
                amount: Math.round(5000 + random() * 900000),
                invoice_date: `2025-${String(1 + (index % 12)).padStart(2, '0')}-${String(1 + (index % 27)).padStart(2, '0')}`,
              }
            : { identifier: `ID-${suffix}` },
      risk_score: type === 'Company' ? Math.round(random() * 100) : undefined,
    }
    nodes.push(node)
    if (type === 'Company') companies.push(node)
    else if (type === 'Director') directors.push(node)
    else if (type === 'Address') addresses.push(node)
  }

  const edges: GraphEdgeModel[] = []
  const seen = new Set<string>()
  const addEdge = (source: GraphNodeModel, target: GraphNodeModel, type: string, flagged = false, date: string | null = null) => {
    const key = `${source.id}|${target.id}|${type}`
    const reverse = `${target.id}|${source.id}|${type}`
    if (seen.has(key) || seen.has(reverse)) return
    seen.add(key)
    edges.push({
      source: source.id,
      target: target.id,
      type,
      properties: {},
      flagged,
      date,
    })
  }

  // A long invoice chain forms several deliberately flagged rings.
  const companyCount = companies.length
  for (let index = 0; index < companyCount; index += 1) {
    const source = companies[index]
    const target = companies[(index + 1) % companyCount]
    addEdge(source, target, 'BILLED_TO', index % 37 === 0)
    if (index % 2 === 0) {
      const target2 = companies[(index + 3) % companyCount]
      addEdge(source, target2, 'BILLED_TO', index % 41 === 0)
    }
  }

  // Structural links ensure the graph is not one giant ring.
  directors.forEach((director, index) => {
    const company = companies[index % Math.max(1, companyCount)]
    if (company) addEdge(director, company, 'DIRECTOR_OF')
    if (index % 3 === 0) {
      const other = companies[(index * 7 + 11) % Math.max(1, companyCount)]
      if (other) addEdge(director, other, 'DIRECTOR_OF')
    }
  })
  addresses.forEach((address, index) => {
    const company = companies[(index * 5) % Math.max(1, companyCount)]
    if (company) addEdge(address, company, 'REGISTERED_AT')
  })

  // Invoice/txn nodes are attached to two companies so the renderer sees the
  // same Company -> Transaction -> Company shape as the live graph.
  const transactions = nodes.filter((node) => node.type === 'Transaction')
  transactions.forEach((transaction, index) => {
    const seller = companies[(index * 13) % Math.max(1, companyCount)]
    const buyer = companies[(index * 17 + 5) % Math.max(1, companyCount)]
    const date = String(transaction.properties?.invoice_date || '2025-06-15')
    if (seller) addEdge(seller, transaction, 'BILLED', index % 53 === 0, date)
    if (buyer) addEdge(transaction, buyer, 'BILLED_TO', index % 59 === 0, date)
  })

  return { nodes, edges, rootId: companies[0]?.id || nodes[0].id }
}
