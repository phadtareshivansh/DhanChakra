import { t } from '../../i18n'
import { ReactNode, useId } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../utils/cn'
import { useOverlay } from './useOverlay'

export type DrawerSide = 'right' | 'left'
export type DrawerSize = 'sm' | 'md' | 'lg' | 'xl'

export interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  footer?: ReactNode
  side?: DrawerSide
  size?: DrawerSize
  className?: string
}

const sizeClasses: Record<DrawerSize, string> = {
  sm: 'w-80',
  md: 'w-[28rem]',
  lg: 'w-[36rem]',
  xl: 'w-[48rem]',
}

export default function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  side = 'right',
  size = 'md',
  className,
}: DrawerProps) {
  const containerRef = useOverlay(open, onClose)
  const titleId = useId()
  const descriptionId = useId()

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50">
      <div
        className="animate-fade-in absolute inset-0 bg-black/60 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          'absolute inset-y-0 flex max-w-full flex-col border-border bg-surface shadow-lg focus:outline-none',
          side === 'right' ? 'right-0 animate-slide-in-right border-l' : 'left-0 animate-slide-in-left border-r',
          sizeClasses[size],
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-md font-semibold text-text-primary">
              {title}
            </h2>
            {description && (
              <p id={descriptionId} className="mt-1 text-xs leading-relaxed text-text-secondary">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('Close panel')}
            className="-mr-1 -mt-1 rounded-md p-1.5 text-text-disabled transition-colors hover:bg-raised hover:text-text-primary"
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
