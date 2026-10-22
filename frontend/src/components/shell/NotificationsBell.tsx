import { useEffect, useRef, useState } from 'react'
import api from '../../utils/api'
import { cn } from '../../utils/cn'

interface Notification {
  id: number | string
  message: string
  read: boolean
  created_at?: string
}

export default function NotificationsBell() {
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)
  const [error, setError] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .get('/notifications?unread_only=false')
      .then((response) => setNotifications((response.data ?? []) as Notification[]))
      .catch(() => setError(true))
  }, [])

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  const unread = notifications.filter((notification) => !notification.read)

  const markRead = async (notification: Notification) => {
    if (notification.read) return
    setNotifications((current) =>
      current.map((item) => (item.id === notification.id ? { ...item, read: true } : item)),
    )
    try {
      await api.post(`/notifications/${notification.id}/read`)
    } catch {
      setNotifications((current) =>
        current.map((item) => (item.id === notification.id ? { ...item, read: false } : item)),
      )
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label={unread.length > 0 ? `Notifications, ${unread.length} unread` : 'Notifications'}
        aria-expanded={open}
        className="relative flex h-9 w-9 items-center justify-center rounded-lg text-text-secondary transition-colors hover:bg-raised hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-ring"
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.6}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 11-6 0"
          />
        </svg>
        {unread.length > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-risk-critical px-1 text-[9px] font-bold text-white">
            {unread.length > 9 ? '9+' : unread.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-80 overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-semibold text-text-primary">Notifications</span>
            <span className="text-[10px] text-text-secondary">{unread.length} unread</span>
          </div>
          {error && (
            <div className="px-3 py-3 text-xs text-risk-critical">Could not load notifications.</div>
          )}
          {!error && notifications.length === 0 && (
            <div className="px-3 py-4 text-xs text-text-secondary">No notifications yet.</div>
          )}
          <div className="max-h-80 overflow-y-auto">
            {notifications.slice(0, 10).map((notification) => (
              <button
                key={notification.id}
                type="button"
                onClick={() => markRead(notification)}
                className="block w-full border-b border-border px-3 py-2 text-left last:border-0 hover:bg-raised"
              >
                <div className="flex items-start gap-2">
                  {!notification.read && (
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-ring" />
                  )}
                  <div className={cn('min-w-0', notification.read && 'pl-3.5')}>
                    <div
                      className={cn(
                        'text-xs leading-relaxed',
                        notification.read ? 'text-text-secondary' : 'text-text-primary',
                      )}
                    >
                      {notification.message}
                    </div>
                    {notification.created_at && (
                      <div className="mt-0.5 text-[10px] text-text-disabled">
                        {notification.created_at.slice(0, 16)}
                      </div>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
