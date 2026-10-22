import { cn } from '../../utils/cn'

export interface FilterChipOption {
  id: string
  label: string
  count?: number
}

export interface FilterChipsProps {
  options: FilterChipOption[]
  selected: string[]
  onToggle: (id: string) => void
  onClear?: () => void
  className?: string
  ariaLabel?: string
}

export default function FilterChips({
  options,
  selected,
  onToggle,
  onClear,
  className,
  ariaLabel = 'Filters',
}: FilterChipsProps) {
  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)} role="group" aria-label={ariaLabel}>
      {options.map((option) => {
        const active = selected.includes(option.id)
        return (
          <button
            key={option.id}
            type="button"
            aria-pressed={active}
            onClick={() => onToggle(option.id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring',
              active
                ? 'border-accent bg-accent/15 text-accent-ring'
                : 'border-border text-text-secondary hover:bg-raised hover:text-text-primary',
            )}
          >
            {option.label}
            {typeof option.count === 'number' && (
              <span
                className={cn(
                  'rounded-full px-1.5 font-mono text-[10px]',
                  active ? 'bg-accent/20' : 'bg-raised',
                )}
              >
                {option.count}
              </span>
            )}
          </button>
        )
      })}
      {onClear && selected.length > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-text-secondary underline-offset-2 hover:text-text-primary hover:underline"
        >
          Clear all
        </button>
      )}
    </div>
  )
}
