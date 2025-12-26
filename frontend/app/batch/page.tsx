'use client'

import { useState } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import FileUploader from '@/components/batch/FileUploader'
import ProcessingControls from '@/components/batch/ProcessingControls'
import ExportPanel from '@/components/batch/ExportPanel'
import { useBatchStore } from '@/lib/batchStore'

// Dynamically import SpreadsheetEditor to avoid SSR issues with AG Grid
const SpreadsheetEditor = dynamic(
  () => import('@/components/batch/SpreadsheetEditor'),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-96 bg-gray-50 rounded-lg">
        <div className="text-gray-500">Loading spreadsheet editor...</div>
      </div>
    )
  }
)

export default function BatchProcessingPage() {
  const [activePanel, setActivePanel] = useState<'upload' | 'settings' | 'export'>('upload')
  const { documents, columns, isProcessing, progress } = useBatchStore()
  
  const hasData = documents.length > 0
  const hasProcessedDocs = documents.some(d => d.status === 'success' || d.status === 'failed')
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-[1920px] mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link 
                href="/"
                className="text-slate-400 hover:text-white transition-colors"
              >
                ← Back
              </Link>
              <div className="h-6 w-px bg-slate-700" />
              <div>
                <h1 className="text-xl font-semibold text-white flex items-center gap-2">
                  <span className="text-2xl">📊</span>
                  Batch Processing
                </h1>
                <p className="text-sm text-slate-400">
                  Process multiple documents with real-time progress
                </p>
              </div>
            </div>
            
            {/* Progress indicator */}
            {isProcessing && (
              <div className="flex items-center gap-3">
                <div className="w-48 h-2 bg-slate-700 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 transition-all duration-300"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
                <span className="text-sm text-slate-400">
                  {Math.round(progress * 100)}%
                </span>
              </div>
            )}
          </div>
        </div>
      </header>
      
      {/* Main content */}
      <main className="max-w-[1920px] mx-auto p-6">
        <div className="flex gap-6 h-[calc(100vh-120px)]">
          {/* Left sidebar - Controls */}
          <aside className="w-96 flex-shrink-0 space-y-4 overflow-y-auto">
            {/* Panel tabs */}
            <div className="flex rounded-lg bg-slate-800/50 p-1">
              <button
                onClick={() => setActivePanel('upload')}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  activePanel === 'upload'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                📁 Upload
              </button>
              <button
                onClick={() => setActivePanel('settings')}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  activePanel === 'settings'
                    ? 'bg-slate-700 text-white'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                ⚙️ Process
              </button>
              <button
                onClick={() => setActivePanel('export')}
                disabled={!hasProcessedDocs}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
                  activePanel === 'export'
                    ? 'bg-slate-700 text-white'
                    : hasProcessedDocs
                      ? 'text-slate-400 hover:text-white'
                      : 'text-slate-600 cursor-not-allowed'
                }`}
              >
                📥 Export
              </button>
            </div>
            
            {/* Panel content */}
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-xl border border-slate-700/50 p-6">
              {activePanel === 'upload' && <FileUploader />}
              {activePanel === 'settings' && <ProcessingControls />}
              {activePanel === 'export' && <ExportPanel />}
            </div>
            
            {/* Quick stats */}
            {hasData && (
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-slate-800/50 rounded-lg p-3 text-center border border-slate-700/50">
                  <p className="text-2xl font-bold text-white">{documents.length}</p>
                  <p className="text-xs text-slate-400">Total</p>
                </div>
                <div className="bg-emerald-900/30 rounded-lg p-3 text-center border border-emerald-700/50">
                  <p className="text-2xl font-bold text-emerald-400">
                    {documents.filter(d => d.status === 'success').length}
                  </p>
                  <p className="text-xs text-emerald-400/70">Success</p>
                </div>
                <div className="bg-red-900/30 rounded-lg p-3 text-center border border-red-700/50">
                  <p className="text-2xl font-bold text-red-400">
                    {documents.filter(d => d.status === 'failed').length}
                  </p>
                  <p className="text-xs text-red-400/70">Failed</p>
                </div>
              </div>
            )}
          </aside>
          
          {/* Main area - Spreadsheet */}
          <div className="flex-1 bg-white rounded-xl overflow-hidden shadow-2xl">
            {hasData ? (
              <SpreadsheetEditor />
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-500">
                <div className="text-6xl mb-4">📋</div>
                <h2 className="text-xl font-medium text-gray-700 mb-2">
                  No Data Loaded
                </h2>
                <p className="text-gray-500 mb-6">
                  Upload a CSV file to get started
                </p>
                <button
                  onClick={() => setActivePanel('upload')}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Go to Upload
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
      
      {/* Processing overlay */}
      {isProcessing && (
        <div className="fixed bottom-6 right-6 bg-slate-800 rounded-xl shadow-2xl border border-slate-700 p-4 z-50">
          <div className="flex items-center gap-4">
            <div className="relative">
              <div className="w-12 h-12 rounded-full border-4 border-slate-700 border-t-blue-500 animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xs font-bold text-white">
                  {Math.round(progress * 100)}%
                </span>
              </div>
            </div>
            <div>
              <p className="font-medium text-white">Processing documents...</p>
              <p className="text-sm text-slate-400">
                {documents.filter(d => d.status === 'success').length} / {documents.length} completed
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

