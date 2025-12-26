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
    importCSV
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
      {/* Header */}
      <div className="border-b border-gray-200 pb-3 px-6 pt-5 flex-shrink-0">
        <h2 className="text-lg font-bold text-gray-900">Batch CSV Upload</h2>
        <p className="text-sm text-gray-500 mt-1">Process multiple documents at once with real-time progress</p>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* File Upload Section */}
        {!hasData && (
          <div className="flex-1 overflow-y-auto px-6 py-6">
            <FileUploader />
          </div>
        )}

        {/* Spreadsheet Editor Section */}
        {hasData && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0 }}>
            {/* Column Mapping & Processing Controls - Fixed at top */}
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50" style={{ flexShrink: 0 }}>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <ColumnMappingPanel />
                <ProcessingControls />
              </div>
            </div>
            
            {/* Spreadsheet - Takes remaining space */}
            <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
              <div style={{ position: 'absolute', inset: 0 }}>
                <SpreadsheetEditor />
              </div>
            </div>
            
            {/* Export Section - Fixed at bottom */}
            {hasProcessedDocs && (
              <div className="px-6 py-4 border-t border-gray-200 flex-shrink-0 bg-gray-50">
                <ExportPanel />
              </div>
            )}
          </div>
        )}

        {/* Processing Progress Bar (if processing) */}
        {isProcessing && (
          <div className="px-6 py-3 bg-blue-50 border-t border-blue-200 flex-shrink-0">
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
    </div>
  )
}
