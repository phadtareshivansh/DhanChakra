import { RISK_THRESHOLDS } from '../config/risk'

export function riskColorForScore(score: number): string {
  if (score >= RISK_THRESHOLDS.critical) return '#E5484D'
  if (score >= RISK_THRESHOLDS.high) return '#F2994A'
  if (score >= RISK_THRESHOLDS.medium) return '#F2C94C'
  return '#6FCF97'
}
