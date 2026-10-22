import { t } from '../../i18n'
import { ReactNode, useId, useRef } from 'react'
import { cn } from '../../utils/cn'

export interface TabItem {
  id: string
  label: ReactNode
  count?: number
  disabled?: boolean
}

export interface TabsProps {
  items: TabItem[]
  value: string
  onChange: (id: string) => void
  className?: string
  /** Stretch tabs to fill the available width. */
  fullWidth?: boolean
}

export default function Tabs({ items, value, onChange, className, fullWidth = false }: TabsProps) {
  const baseId = useId()
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const move = (direction: 1 | -1, currentId: string) => {
    const enabled = items.filter((item) => !item.disabled)
    const index = enabled.findIndex((item) => item.id === currentId)
    if (index === -1) return
    const next = enabled[(index + direction + enabled.length) % enabled.length]
    onChange(next.id)
    refs.current[next.id]?.focus()
  }

  return (
    <div
      role="tablist"
      aria-label={t('Sections')}
      className={cn('flex items-center gap-1 border-b border-border', className)}
    >
      {items.map((item) => {
        const selected = item.id === value
        return (
          <button
            key={item.id}
            ref={(element) => {
              refs.current[item.id] = element
            }}
            role="tab"
            id={`${baseId}-tab-${item.id}`}
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            disabled={item.disabled}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowRight') {
                event.preventDefault()
                move(1, item.id)
              }
              if (event.key === 'ArrowLeft') {
                event.preventDefault()
                move(-1, item.id)
              }
            }}
            className={cn(
              'relative -mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
              fullWidth && 'flex-1 justify-center',
              selected
                ? 'border-accent text-text-primary'
                : 'border-transparent text-text-secondary hover:text-text-primary',
              item.disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            {item.label}
            {typeof item.count === 'number' && (
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[10px] font-mono',
                  selected ? 'bg-accent/15 text-accent-ring' : 'bg-raised text-text-secondary',
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export function TabPanel({
  id,
  value,
  children,
  className,
}: {
  id: string
  value: string
  children: ReactNode
  className?: string
}) {
  if (id !== value) return null
  return (
    <div role="tabpanel" className={cn('pt-4', className)}>
      {children}
    </div>
  )
}
