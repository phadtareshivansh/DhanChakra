import { t } from '../../i18n'
import { formatDate, formatInr, titleCase } from '../../utils/format'
import type { GraphEdgeModel, GraphNodeModel } from './GraphCanvas'

function endpointId(endpoint: string | GraphNodeModel): string {
  return typeof endpoint === 'string' ? endpoint : endpoint.id
}

function edgeName(type: string): string {
  return t(titleCase(type.replace(/_/g, ' ').toLowerCase()))
}

interface GraphTableProps {
  nodes: GraphNodeModel[]
  edges: GraphEdgeModel[]
  onInspect?: (node: GraphNodeModel) => void
}

/**
 * Read-only, keyboard-accessible alternative to the canvas. It is the graph
 * view on phones and is available from the toolbar at every breakpoint.
 */
export default function GraphTable({ nodes, edges, onInspect }: GraphTableProps) {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const shownNodes = nodes.slice(0, 500)
  const shownEdges = edges.slice(0, 1000)

  return (
    <div className="h-full overflow-y-auto p-4" role="region" aria-label={t('Graph table view')}>
      <p className="mb-4 max-w-3xl text-xs leading-relaxed text-text-secondary">
        {t(
          'Read-only table alternative. The interactive canvas is available on tablet and desktop; every visible entity and relationship is listed here for screen readers and small screens.',
        )}
      </p>

      {(nodes.length > shownNodes.length || edges.length > shownEdges.length) && (
        <p className="mb-4 rounded-lg border border-risk-high/40 bg-surface px-3 py-2 text-xs text-text-secondary">
          {t('Showing the first {nodes} entities and {edges} relationships. Narrow the filters to see more.', {
            nodes: shownNodes.length,
            edges: shownEdges.length,
          })}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full min-w-[46rem] border-collapse text-left text-xs">
          <caption className="border-b border-border px-3 py-2 text-left text-sm font-semibold text-text-primary">
            {t('Entities ({count})', { count: nodes.length })}
          </caption>
          <thead className="bg-canvas text-text-secondary">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">{t('Name')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Type')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Identifier')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Risk')}</th>
              {onInspect && <th scope="col" className="px-3 py-2 font-medium">{t('Actions')}</th>}
            </tr>
          </thead>
          <tbody>
            {shownNodes.map((node) => {
              const identifier =
                node.properties?.cin || node.properties?.gstin || node.properties?.din || node.id
              return (
                <tr key={node.id} className="border-t border-border/70">
                  <th scope="row" className="max-w-[18rem] truncate px-3 py-2 font-medium text-text-primary">
                    {node.label}
                  </th>
                  <td className="whitespace-nowrap px-3 py-2 text-text-secondary">{t(titleCase(node.type))}</td>
                  <td className="px-3 py-2 font-mono text-[11px] text-text-secondary">{String(identifier)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-text-secondary">
                    {node.risk_score === undefined ? '—' : Math.round(node.risk_score)}
                  </td>
                  {onInspect && (
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() => onInspect(node)}
                        className="rounded-md border border-border px-2 py-1 text-[11px] text-text-primary hover:bg-raised"
                        aria-label={t('Inspect {name}', { name: node.label })}
                      >
                        {t('Inspect')}
                      </button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-5 overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full min-w-[46rem] border-collapse text-left text-xs">
          <caption className="border-b border-border px-3 py-2 text-left text-sm font-semibold text-text-primary">
            {t('Relationships ({count})', { count: edges.length })}
          </caption>
          <thead className="bg-canvas text-text-secondary">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">{t('From')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Relationship')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('To')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Date')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Value')}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t('Signals')}</th>
            </tr>
          </thead>
          <tbody>
            {shownEdges.map((edge) => {
              const sourceId = endpointId(edge.source)
              const targetId = endpointId(edge.target)
              const amount =
                nodeById.get(sourceId)?.properties?.amount ??
                nodeById.get(targetId)?.properties?.amount
              return (
                <tr key={`${sourceId}-${targetId}-${edge.type}`} className="border-t border-border/70">
                  <td className="max-w-[14rem] truncate px-3 py-2 text-text-primary">
                    {nodeById.get(sourceId)?.label || sourceId}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-text-secondary">{edgeName(edge.type)}</td>
                  <td className="max-w-[14rem] truncate px-3 py-2 text-text-primary">
                    {nodeById.get(targetId)?.label || targetId}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-text-secondary">
                    {edge.date ? formatDate(edge.date) : '—'}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-text-secondary">
                    {amount === undefined || amount === null ? '—' : formatInr(Number(amount))}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-text-secondary">
                    {edge.flagged ? t('Flagged cycle') : edge.eway_mismatch ? t('e-Way mismatch') : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
