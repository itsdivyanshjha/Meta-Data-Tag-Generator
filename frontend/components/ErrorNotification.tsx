'use client'

import { useEffect, useState } from 'react'
import { X, AlertCircle, Zap, TrendingDown } from 'lucide-react'

export interface ErrorNotification {
  id: string
  type: 'rate-limit' | 'model-error' | 'network' | 'auth' | 'unknown'
  title: string
  message: string
  action?: {
    label: string
    href: string
  }
  autoClose?: number // ms, 0 for manual
}

interface ErrorNotificationProps {
  notification: ErrorNotification
  onClose: () => void
}

export function ErrorNotificationItem({ notification, onClose }: ErrorNotificationProps) {
  const [isVisible, setIsVisible] = useState(true)

  useEffect(() => {
    if (notification.autoClose && notification.autoClose > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false)
        onClose()
      }, notification.autoClose)
      return () => clearTimeout(timer)
    }
  }, [notification.autoClose, onClose])

  if (!isVisible) return null

  const getIcon = () => {
    switch (notification.type) {
      case 'rate-limit':
        return <Zap className="w-5 h-5 text-yellow-400" />
      case 'model-error':
        return <AlertCircle className="w-5 h-5 text-red-400" />
      case 'network':
        return <TrendingDown className="w-5 h-5 text-orange-400" />
      default:
        return <AlertCircle className="w-5 h-5 text-red-400" />
    }
  }

  const getColors = () => {
    switch (notification.type) {
      case 'rate-limit':
        return 'bg-yellow-950/50 border-yellow-700/50'
      case 'model-error':
        return 'bg-red-950/50 border-red-700/50'
      case 'network':
        return 'bg-orange-950/50 border-orange-700/50'
      default:
        return 'bg-red-950/50 border-red-700/50'
    }
  }

  const getTextColors = () => {
    switch (notification.type) {
      case 'rate-limit':
        return 'text-yellow-100'
      case 'model-error':
        return 'text-red-100'
      case 'network':
        return 'text-orange-100'
      default:
        return 'text-red-100'
    }
  }

  return (
    <div
      className={`
        rounded-lg border backdrop-blur-sm
        p-4 mb-3 flex items-start gap-3
        animate-in slide-in-from-top-2 fade-in duration-300
        ${getColors()}
      `}
    >
      <div className="flex-shrink-0 pt-0.5">{getIcon()}</div>

      <div className="flex-1 min-w-0">
        <h3 className={`font-semibold text-sm ${getTextColors()}`}>
          {notification.title}
        </h3>
        <p className={`text-xs mt-1 ${getTextColors()} opacity-90`}>
          {notification.message}
        </p>

        {notification.action && (
          <a
            href={notification.action.href}
            target="_blank"
            rel="noopener noreferrer"
            className={`inline-block mt-2 text-xs font-medium underline hover:opacity-75 transition-opacity ${
              notification.type === 'rate-limit'
                ? 'text-yellow-300'
                : 'text-red-300'
            }`}
          >
            {notification.action.label}
          </a>
        )}
      </div>

      <button
        onClick={() => {
          setIsVisible(false)
          onClose()
        }}
        className="flex-shrink-0 text-slate-400 hover:text-slate-300 transition-colors"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

interface ErrorNotificationContainerProps {
  notifications: ErrorNotification[]
  onRemove: (id: string) => void
}

export function ErrorNotificationContainer({
  notifications,
  onRemove,
}: ErrorNotificationContainerProps) {
  if (notifications.length === 0) return null

  return (
    <div className="fixed top-24 right-6 z-50 w-96 max-w-full">
      {notifications.map((notification) => (
        <ErrorNotificationItem
          key={notification.id}
          notification={notification}
          onClose={() => onRemove(notification.id)}
        />
      ))}
    </div>
  )
}
