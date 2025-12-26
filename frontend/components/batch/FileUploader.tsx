'use client'

import { useCallback, useState } from 'react'
import { useBatchStore } from '@/lib/batchStore'

export default function FileUploader() {
  const [isDragging, setIsDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  
  const { importCSV, documents } = useBatchStore()
  
  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setError('Please upload a CSV file')
      return
    }
    
    setIsLoading(true)
    setError(null)
    
    try {
      await importCSV(file)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to parse CSV')
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
          accept=".csv"
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          disabled={isLoading}
        />
        
        <div className="space-y-3">
          <div className="text-5xl">📊</div>
          <div>
            <p className="font-medium text-gray-700">
              {isLoading ? 'Loading CSV...' : 'Drop your CSV here or click to browse'}
            </p>
            <p className="text-sm text-gray-500 mt-1">
              CSV file with document metadata (title, file_path, file_source_type)
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
      
      {/* CSV format info */}
      <div className="p-4 bg-gray-50 border border-gray-200 rounded">
        <h3 className="font-semibold text-gray-800 mb-2">CSV Format Required</h3>
        <p className="text-sm text-gray-600 mb-3">
          Your CSV should have these columns:
        </p>
        <div className="bg-white rounded p-3 overflow-x-auto border border-gray-200">
          <code className="text-xs text-gray-700 whitespace-pre">
{`title,description,file_source_type,file_path
"Training Manual","Training document",url,https://example.com/doc1.pdf
"Annual Report","Financial report",url,https://example.com/doc2.pdf`}
          </code>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
            title (required)
          </span>
          <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
            file_path (required)
          </span>
          <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
            file_source_type: url | s3 | local
          </span>
          <span className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded">
            description (optional)
          </span>
        </div>
      </div>
    </div>
  )
}
