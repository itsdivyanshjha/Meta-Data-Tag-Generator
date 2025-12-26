import './globals.css'
import type { Metadata } from 'next'
import { IBM_Plex_Sans } from 'next/font/google'

const ibmPlexSans = IBM_Plex_Sans({ 
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
})

export const metadata: Metadata = {
  title: 'Document Tagger',
  description: 'AI-powered document tagging',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`min-h-screen bg-gray-50 ${ibmPlexSans.className}`}>
        <header className="bg-white border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 py-4">
            <h1 className="text-xl font-bold text-gray-900">
              Document Metadata-Tagging
            </h1>
          </div>
        </header>

        <main className="w-full px-6 py-6 mb-12">
          {children}
        </main>

        <footer className="border-t border-gray-200 mt-auto">
          <div className="max-w-7xl mx-auto px-4 py-3">
            <p className="text-center text-xs text-gray-400">
              Document Meta-Tagging System
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
