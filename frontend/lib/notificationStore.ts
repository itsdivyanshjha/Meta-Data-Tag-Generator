import { create } from 'zustand'
import { ErrorNotification } from '@/components/ErrorNotification'

interface NotificationStore {
  notifications: ErrorNotification[]
  addNotification: (notification: Omit<ErrorNotification, 'id'>) => void
  removeNotification: (id: string) => void
  addRateLimitError: (retryAfter: number, retryCount: number) => void
  addModelError: (modelName: string, errorDetail: string) => void
  addNetworkError: (details: string) => void
  clearAll: () => void
}

export const useNotificationStore = create<NotificationStore>((set) => ({
  notifications: [],

  addNotification: (notification) => {
    const id = `${Date.now()}-${Math.random()}`
    set((state) => ({
      notifications: [...state.notifications, { ...notification, id }],
    }))

    // Auto-remove after timeout if specified
    if (notification.autoClose && notification.autoClose > 0) {
      setTimeout(() => {
        set((state) => ({
          notifications: state.notifications.filter((n) => n.id !== id),
        }))
      }, notification.autoClose + 500) // Add buffer for animation
    }
  },

  removeNotification: (id: string) => {
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    }))
  },

  addRateLimitError: (retryAfter: number, retryCount: number) => {
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          id: `${Date.now()}-${Math.random()}`,
          type: 'rate-limit' as const,
          title: '⚡ Rate Limit Hit',
          message: `Too many requests to the AI provider (Attempt ${retryCount}). Retrying in ${Math.ceil(retryAfter / 1000)}s...`,
          autoClose: retryAfter + 1000,
        },
      ],
    }))
  },

  addModelError: (modelName: string, errorDetail: string) => {
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          id: `${Date.now()}-${Math.random()}`,
          type: 'model-error' as const,
          title: '🤖 Model Error',
          message: `Error with ${modelName}: ${errorDetail}`,
          autoClose: 8000,
        },
      ],
    }))
  },

  addNetworkError: (details: string) => {
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          id: `${Date.now()}-${Math.random()}`,
          type: 'network' as const,
          title: '🌐 Connection Issue',
          message: details,
          autoClose: 6000,
        },
      ],
    }))
  },

  clearAll: () => {
    set({ notifications: [] })
  },
}))
