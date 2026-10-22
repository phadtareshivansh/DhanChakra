/** Shared display formatters for the analyst screens. */

export function formatInr(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  return `₹${Math.round(value).toLocaleString('en-IN')}`
}

/** Compact Indian notation: ₹1.2 Cr / ₹4.5 L / ₹8,200. */
export function formatInrCompact(value?: number | null): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '—'
  const abs = Math.abs(value)
  if (abs >= 1e7) return `₹${(value / 1e7).toFixed(abs >= 1e8 ? 0 : 2)} Cr`
  if (abs >= 1e5) return `₹${(value / 1e5).toFixed(abs >= 1e6 ? 0 : 1)} L`
  return formatInr(value)
}

export function formatDate(value?: string | null, withTime = false): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

export function relativeTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const seconds = (Date.now() - date.getTime()) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 86400 * 30) return `${Math.floor(seconds / 86400)}d ago`
  return formatDate(value)
}

export function initials(name?: string | null): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('')
}

export function titleCase(value?: string | null): string {
  if (!value) return '—'
  return value
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
}

export function truncateMiddle(value: string, max = 22): string {
  if (value.length <= max) return value
  const half = Math.floor((max - 1) / 2)
  return `${value.slice(0, half)}…${value.slice(-half)}`
}
