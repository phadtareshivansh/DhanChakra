export function riskColorForScore(score: number): string {
  if (score >= 85) return '#E5484D'
  if (score >= 65) return '#F2994A'
  if (score >= 40) return '#F2C94C'
  return '#6FCF97'
}
