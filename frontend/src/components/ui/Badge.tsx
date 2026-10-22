import { ReactNode } from 'react'
import { cn } from '../../utils/cn'

export type BadgeTone = 'neutral' | 'accent' | 'amber' | 'critical' | 'high' | 'medium' | 'low' | 'outline'

const toneClasses: Record<BadgeTone, string> = {
  neutral: 'bg-raised text-text-secondary border border-border',
  accent: 'bg-accent/15 text-accent-ring border border-accent/30',
  amber: 'bg-amber/15 text-amber border border-amber/30',
  critical: 'bg-risk-critical/15 text-risk-critical border border-risk-critical/30',
  high: 'bg-risk-high/15 text-risk-high border border-risk-high/30',
  medium: 'bg-risk-medium/15 text-risk-medium border border-risk-medium/30',
  low: 'bg-risk-low/15 text-risk-low border border-risk-low/30',
  outline: 'bg-transparent text-text-secondary border border-border',
}

export interface BadgeProps {
  children: ReactNode
  tone?: BadgeTone
  /** Render a leading status dot in the current text colour. */
  dot?: boolean
  className?: string
}

export default function Badge({ children, tone = 'neutral', dot = false, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-micro font-semibold whitespace-nowrap',
        toneClasses[tone],
        className,
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  )
}
