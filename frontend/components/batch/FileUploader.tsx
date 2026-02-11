'use client'

import { useCallback, useState } from 'react'
import { useBatchStore } from '@/lib/batchStore'

export default function FileUploader() {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  
  const { importCSV, documents } = useBatchStore()
  
  const handleFile = useCallback(async (file: File) => {
    const fileName = file.name.toLowerCase()
    const isCsv = fileName.endsWith('.csv')
    const isXlsx = fileName.endsWith('.xlsx') || fileName.endsWith('.xls')
    
    if (!isCsv && !isXlsx) {
      setError('Please upload a CSV or Excel file (.csv, .xlsx, .xls)')
      return
    }
    
    setIsLoading(true)
    setError(null)
    
    try {
      await importCSV(file)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to parse file')
    } finally {
      setIsLoading(false)
    }
  }, [importCSV])
  
  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    
    const file = e.dataTransfer.files[0]
    if (file) {
      handleFile(file)
    }
  }, [handleFile])
  
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFile(file)
    }
  }, [handleFile])
  
  // If documents are loaded, show summary instead
  if (documents.length > 0) {
    return (
      <div className="p-4 bg-green-50 border border-green-200 rounded">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-green-600 text-2xl">✓</span>
            <div>
              <p className="font-medium text-green-800">
                {documents.length} documents loaded
              </p>
              <p className="text-sm text-green-600">
                Ready for processing
              </p>
            </div>
          </div>
          <button
            onClick={() => useBatchStore.getState().reset()}
            className="text-sm text-green-700 hover:text-green-800 hover:underline"
          >
            Load Different File
          </button>
        </div>
      </div>
    )
  }
  
  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={(e) => { e.preventDefault(); setIsDragging(false) }}
        className={`
          relative border-2 border-dashed rounded-lg p-8 text-center transition-colors
          ${isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'}
          ${isLoading ? 'opacity-50 pointer-events-none' : ''}
        `}
      >
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isLoading}
        />
        
        <div className="space-y-3">
          <div className="text-5xl">📊</div>
          <div>
            <p className="font-medium text-gray-700">
              {isLoading ? 'Loading file...' : 'Drop your CSV or Excel file here or click to browse'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              CSV (.csv) or Excel (.xlsx, .xls) file with document metadata
            </p>
          </div>
        </div>
      </div>
      
      {/* Error message */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}
      
      {/* File Format Requirements - Simplified */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
        <h3 className="font-semibold text-gray-800 mb-3">What we need from your file</h3>
        
        {/* Simple Requirements Table */}
        <div className="space-y-2 mb-4">
          <div className="grid grid-cols-3 gap-3 text-sm">
            {/* Header */}
            <div className="font-medium text-gray-700">Field Name</div>
            <div className="font-medium text-gray-700">Required</div>
            <div className="font-medium text-gray-700">What to put here</div>
            
            {/* File Path Row */}
            <div className="text-gray-800">File Path / Link</div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 bg-red-500 rounded-full"></span>
              <span className="text-red-600 font-medium">Yes</span>
            </div>
            <div className="text-gray-600 text-xs">URL or file location</div>
            
            {/* Title Row */}
            <div className="text-gray-800">Title / Name</div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 bg-gray-300 rounded-full"></span>
              <span className="text-gray-600">No</span>
            </div>
            <div className="text-gray-600 text-xs">Document name</div>
            
            {/* File Type Row */}
            <div className="text-gray-800">File Type</div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 bg-gray-300 rounded-full"></span>
              <span className="text-gray-600">No</span>
            </div>
            <div className="text-gray-600 text-xs">url, s3, or local</div>
            
            {/* Description Row */}
            <div className="text-gray-800">Description</div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-2 h-2 bg-gray-300 rounded-full"></span>
              <span className="text-gray-600">No</span>
            </div>
            <div className="text-gray-600 text-xs">About the document</div>
          </div>
        </div>
        
        {/* Tip for Excel users */}
        <div className="p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
          <p className="font-medium mb-1">💡 Tip for Excel users:</p>
          <p>Paste links as plain text. Excel hyperlinks will not work as expected.</p>
        </div>
      </div>
    </div>
  )
}
