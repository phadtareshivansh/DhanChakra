import { ReactNode } from 'react'
import { cn } from '../utils/cn'
import Tooltip from './ui/Tooltip'

export interface InfoHintProps {
  /** Plain-language explanation shown on hover/focus. */
  content: ReactNode
  label?: string
  side?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}

/**
 * Small "?" affordance used next to domain jargon (ITC, GSTIN, cycle,
 * betweenness). Keeps the visible copy short while making the abbreviation
 * explainable on hover and keyboard focus.
 */
export default function InfoHint({
  content,
  label = 'What does this mean?',
  side = 'top',
  className,
}: InfoHintProps) {
  return (
    <Tooltip content={content} side={side}>
      <button
        type="button"
        aria-label={label}
        className={cn(
          'inline-flex h-4 w-4 items-center justify-center rounded-full border border-border text-[10px] font-semibold text-text-secondary',
          'transition-colors hover:border-accent-ring hover:text-accent-ring',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
          className,
        )}
      >
        ?
      </button>
    </Tooltip>
  )
}
