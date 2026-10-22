import { t } from '../i18n'
import { RISK_THRESHOLDS } from '../config/risk'

export function riskLevel(score?: number): { label: string; color: string } {
  if (score === undefined || score === null) {
    return { label: t('Insufficient data'), color: 'risk-neutral' }
  }
  if (score >= RISK_THRESHOLDS.critical) return { label: t('Critical'), color: 'risk-critical' }
  if (score >= RISK_THRESHOLDS.high) return { label: t('High'), color: 'risk-high' }
  if (score >= RISK_THRESHOLDS.medium) return { label: t('Medium'), color: 'risk-medium' }
  return { label: t('Low'), color: 'risk-low' }
}

export default function RiskBadge({ score, showScore = true }: { score?: number; showScore?: boolean }) {
  const { label, color } = riskLevel(score)
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-micro font-semibold`}
      style={{ backgroundColor: `var(--${color})`, color: 'var(--color-risk-badge-text)' }}
      title={t('Risk score: {score}', { score: score ?? 'n/a' })}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {showScore && score !== undefined && <span className="font-mono font-medium">{Math.round(score)}</span>}
      {label}
    </span>
  )
}