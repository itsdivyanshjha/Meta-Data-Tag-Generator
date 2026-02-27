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
      <body className={`min-h-screen bg-stone-50 flex flex-col ${ibmPlexSans.className}`}>
        <Header />

        <main className="flex-1 w-full px-8 py-8">
          {children}
        </main>
      </body>
    </html>
  )
}
