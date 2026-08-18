export function riskLevel(score?: number): { label: string; color: string } {
  if (score === undefined || score === null) {
    return { label: 'Insufficient data', color: 'risk-neutral' }
  }
  if (score >= 85) return { label: 'Critical', color: 'risk-critical' }
  if (score >= 65) return { label: 'High', color: 'risk-high' }
  if (score >= 40) return { label: 'Medium', color: 'risk-medium' }
  return { label: 'Low', color: 'risk-low' }
}

export default function RiskBadge({ score, showScore = true }: { score?: number; showScore?: boolean }) {
  const { label, color } = riskLevel(score)
  const textColor = color === 'risk-medium' ? '#141B24' : '#0B0F14'
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-micro font-semibold`}
      style={{ backgroundColor: `var(--${color})`, color: textColor === '#0B0F14' && color === 'risk-neutral' ? '#E7EDF3' : textColor }}
      title={`Risk score: ${score ?? 'n/a'}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {showScore && score !== undefined && <span className="font-mono font-medium">{Math.round(score)}</span>}
      {label}
    </span>
  )
}