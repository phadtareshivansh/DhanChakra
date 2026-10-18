// Risk band thresholds. Single source of truth for the UI; override via env.

function num(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export const RISK_THRESHOLDS = {
  critical: num(import.meta.env.VITE_RISK_CRITICAL_THRESHOLD, 85),
  high: num(import.meta.env.VITE_RISK_HIGH_THRESHOLD, 65),
  medium: num(import.meta.env.VITE_RISK_MEDIUM_THRESHOLD, 40),
}

export type RiskBand = 'critical' | 'high' | 'medium' | 'low'

export function riskBand(score?: number | null): RiskBand | null {
  if (score === undefined || score === null) return null
  if (score >= RISK_THRESHOLDS.critical) return 'critical'
  if (score >= RISK_THRESHOLDS.high) return 'high'
  if (score >= RISK_THRESHOLDS.medium) return 'medium'
  return 'low'
}
