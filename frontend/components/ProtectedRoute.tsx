'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/authStore'

interface ProtectedRouteProps {
  children: React.ReactNode
  fallback?: React.ReactNode
}

export default function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuthStore()
  const [isHydrated, setIsHydrated] = useState(false)

  // Handle hydration - Zustand persisted state loads after initial render
  useEffect(() => {
    setIsHydrated(true)
  }, [])

  useEffect(() => {
    // Only redirect after hydration is complete
    if (isHydrated && !isLoading && !isAuthenticated) {
      router.push('/login')
    }
  }, [isHydrated, isAuthenticated, isLoading, router])

  // Show loading state while hydrating or checking auth
  if (!isHydrated || isLoading) {
    return fallback || <LoadingSpinner />
  }

  // If not authenticated, show nothing (redirect will happen)
  if (!isAuthenticated) {
    return fallback || <LoadingSpinner />
  }

  return <>{children}</>
}

function LoadingSpinner() {
  return (
    <div className="min-h-[60vh] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <svg className="animate-spin h-10 w-10 text-blue-600" viewBox="0 0 24 24">
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
            fill="none"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
        <p className="text-gray-500">Loading...</p>
      </div>
    </div>
  )
}
