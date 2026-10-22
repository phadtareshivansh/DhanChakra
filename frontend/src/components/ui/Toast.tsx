import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react'
import { cn } from '../../utils/cn'

export type ToastTone = 'info' | 'success' | 'warning' | 'critical'

export interface ToastOptions {
  title: string
  description?: string
  tone?: ToastTone
  /** Milliseconds before auto-dismiss. Use 0 to require manual dismissal. */
  duration?: number
}

interface ToastRecord extends ToastOptions {
  id: number
}

interface ToastContextValue {
  push: (options: ToastOptions) => number
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

const toneStyles: Record<ToastTone, { border: string; icon: string; iconPath: string }> = {
  info: {
    border: 'border-l-accent',
    icon: 'text-accent-ring',
    iconPath: 'M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z',
  },
  success: {
    border: 'border-l-risk-low',
    icon: 'text-risk-low',
    iconPath: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  warning: {
    border: 'border-l-risk-medium',
    icon: 'text-risk-medium',
    iconPath: 'M12 9v2m0 4h.01M10.29 3.86l-8.2 14.2A1 1 0 003 19.5h18a1 1 0 00.91-1.44l-8.2-14.2a1 1 0 00-1.82 0z',
  },
  critical: {
    border: 'border-l-risk-critical',
    icon: 'text-risk-critical',
    iconPath: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
  },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([])
  const nextId = useRef(1)
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  const dismiss = useCallback((id: number) => {
    const timer = timers.current[id]
    if (timer) {
      clearTimeout(timer)
      delete timers.current[id]
    }
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const push = useCallback(
    (options: ToastOptions) => {
      const id = nextId.current
      nextId.current += 1
      setToasts((current) => [...current, { ...options, id }])
      const duration = options.duration ?? 5000
      if (duration > 0) {
        timers.current[id] = setTimeout(() => dismiss(id), duration)
      }
      return id
    },
    [dismiss],
  )

  const value = useMemo(() => ({ push, dismiss }), [push, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        aria-relevant="additions"
        className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-full max-w-sm flex-col gap-2"
      >
        {toasts.map((toast) => {
          const tone = toast.tone ?? 'info'
          const style = toneStyles[tone]
          return (
            <div
              key={toast.id}
              role="status"
              className={cn(
                'animate-toast-in pointer-events-auto flex items-start gap-3 rounded-lg border border-l-4 border-border bg-surface px-4 py-3 shadow-lg',
                style.border,
              )}
            >
              <svg
                className={cn('mt-0.5 h-5 w-5 shrink-0', style.icon)}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={style.iconPath} />
              </svg>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-text-primary">{toast.title}</p>
                {toast.description && (
                  <p className="mt-0.5 text-xs leading-relaxed text-text-secondary">{toast.description}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Dismiss notification"
                className="rounded p-1 text-text-disabled transition-colors hover:bg-raised hover:text-text-primary"
              >
                <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used inside <ToastProvider>')
  }
  return context
}
