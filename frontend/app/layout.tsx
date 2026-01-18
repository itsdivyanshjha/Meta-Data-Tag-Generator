import './globals.css'
import type { Metadata } from 'next'
import { IBM_Plex_Sans } from 'next/font/google'
import Header from '@/components/Header'

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
})

export const metadata: Metadata = {
  title: 'MetaDataTagger',
  description: 'AI-powered document metadata tagging solution',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`min-h-screen bg-stone-50 ${ibmPlexSans.className}`}>
        <Header />

        <main className="w-full px-8 py-8">
          {children}
        </main>

        <footer className="border-t border-gray-200 mt-auto bg-white">
          <div className="px-8 py-4">
            <p className="text-center text-sm text-gray-500">
              Multi-lingual Document Processing System
            </p>
          </div>
        </footer>
      </body>
    </html>
  )
}
