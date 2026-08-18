export default function StatTile({ label, value, sub, accent }: {
  label: string
  value: string
  sub?: string
  accent?: 'teal' | 'amber' | 'red' | 'green'
}) {
  const color = accent === 'amber' ? '#D6A94A' : accent === 'red' ? '#E5484D' : accent === 'green' ? '#6FCF97' : '#1F8A8C'
  return (
    <div className="panel p-4">
      <div className="micro-label">{label}</div>
      <div className="mt-2 font-mono text-3xl font-medium" style={{ color }}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-text-secondary">{sub}</div>}
    </div>
  )
}