'use client'

import { useState, useEffect } from 'react'
import dynamic from 'next/dynamic'
import { TaggingConfig } from '@/lib/types'
import { useBatchStore } from '@/lib/batchStore'
import FileUploader from '@/components/batch/FileUploader'
import ProcessingControls from '@/components/batch/ProcessingControls'
import ExportPanel from '@/components/batch/ExportPanel'
import ColumnMappingPanel from '@/components/batch/ColumnMappingPanel'

// Dynamically import SpreadsheetEditor to avoid SSR issues with AG Grid
const SpreadsheetEditor = dynamic(
  () => import('@/components/batch/SpreadsheetEditor'),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-full bg-gray-50 rounded">
        <div className="text-gray-500">Loading spreadsheet editor...</div>
      </div>
    )
  }
)

interface BatchUploadProps {
  config: TaggingConfig
  exclusionFile?: File | null
}

export default function BatchUpload({ config, exclusionFile }: BatchUploadProps) {
  const { 
    documents, 
    setProcessingSettings,
    processingSettings,
    importCSV,
    reset
  } = useBatchStore()
  
  // Sync config with store
  useEffect(() => {
    setProcessingSettings({
      apiKey: config.api_key || '',
      modelName: config.model_name || 'openai/gpt-4o-mini',
      numPages: config.num_pages || 3,
      numTags: config.num_tags || 8,
      exclusionWords: config.exclusion_words || []
    })
  }, [config, setProcessingSettings])
  
  const hasData = documents.length > 0
  const hasProcessedDocs = documents.some(d => d.status === 'success' || d.status === 'failed')
  const isProcessing = useBatchStore(state => state.isProcessing)
  const progress = useBatchStore(state => state.progress)
  
  
  return (
    <div className="card h-full flex flex-col overflow-hidden">
      {/* Header - Fixed at top */}
      <div className="border-b border-gray-200 pb-4 px-6 pt-6 flex-shrink-0 bg-gradient-to-b from-white to-gray-50">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Batch Processing</h2>
            <p className="text-sm text-gray-500 mt-1">Process multiple documents with real-time progress tracking</p>
          </div>
          <button
            onClick={reset}
            disabled={documents.length === 0}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white hover:bg-gray-100 border border-gray-300 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            title="Reset batch upload (keeps configuration)"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Reset
          </button>
        </div>
      </div>

      {/* Scrollable Content Area - Contains ALL sections */}
      <div className="flex-1 overflow-y-auto">
        {/* File Upload Section */}
        {!hasData && (
          <div className="px-6 py-6">
            <FileUploader />
          </div>
        )}

        {/* All Batch Processing Sections - Scrollable */}
        {hasData && (
          <div className="flex flex-col">
            {/* Column Mapping & Processing Controls */}
            <div className="px-6 py-5 border-b border-gray-200 bg-gradient-to-b from-gray-50 to-white">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <ColumnMappingPanel />
                <ProcessingControls />
              </div>
            </div>

            {/* Spreadsheet - Fixed height for visibility */}
            <div className="px-6 py-4 border-b border-gray-200" style={{ height: '600px', minHeight: '500px' }}>
              <SpreadsheetEditor />
            </div>
            
            {/* Processing Progress Bar (if processing) - Sticky at bottom */}
            {isProcessing && (
              <div className="px-6 py-4 bg-gradient-to-r from-blue-50 to-indigo-50 border-t-2 border-blue-300 flex-shrink-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <p className="text-sm font-semibold text-blue-800">Processing documents...</p>
                  </div>
                  <p className="text-sm font-bold text-blue-700">{Math.round(progress * 100)}%</p>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-2.5 shadow-inner">
                  <div
                    className="h-full bg-gradient-to-r from-blue-600 to-blue-700 rounded-full transition-all duration-300 shadow-sm"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              </div>
            )}

            {/* Export Section - Sticky at bottom when processed */}
            {hasProcessedDocs && !isProcessing && (
              <div className="px-6 py-5 bg-gradient-to-b from-gray-50 to-white border-t border-gray-200 flex-shrink-0">
                <ExportPanel />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
