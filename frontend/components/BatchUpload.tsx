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
    <div className="card h-full flex flex-col">
      {/* Header - Fixed at top */}
      <div className="border-b border-gray-200 pb-3 px-6 pt-5 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Batch CSV Upload</h2>
            <p className="text-sm text-gray-500 mt-1">Process multiple documents at once with real-time progress</p>
          </div>
          <button
            onClick={reset}
            disabled={documents.length === 0}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
            Refresh
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
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <ColumnMappingPanel />
                <ProcessingControls />
              </div>
            </div>
            
            {/* Spreadsheet - Fixed height to show ~10 rows */}
            <div className="px-6 py-4 border-b border-gray-200" style={{ height: '600px', minHeight: '500px' }}>
              <SpreadsheetEditor />
            </div>
            
            {/* Export Section - Always visible when scrolled to */}
            {hasProcessedDocs && (
              <div className="px-6 py-6 bg-gray-50">
                <ExportPanel />
              </div>
            )}
            
            {/* Processing Progress Bar (if processing) */}
            {isProcessing && (
              <div className="px-6 py-4 bg-blue-50 border-b border-blue-200">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-blue-800">Processing documents...</p>
                  <p className="text-sm text-blue-600">{Math.round(progress * 100)}%</p>
                </div>
                <div className="w-full bg-blue-200 rounded-full h-2">
                  <div 
                    className="h-full bg-blue-600 rounded-full transition-all duration-300"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
