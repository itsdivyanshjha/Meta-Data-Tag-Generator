'use client'

import { useState } from 'react'
import { useBatchStore } from '@/lib/batchStore'

export default function ProcessingControls() {
  const [error, setError] = useState<string | null>(null)
  
  const {
    documents,
    isProcessing,
    progress,
    processingSettings,
    startProcessing,
    stopProcessing,
    validatePaths,
    isValidating,
    validationResults,
    getColumnMapping
  } = useBatchStore()
  
  const handleStartProcessing = async () => {
    setError(null)
    
    // Validate API key
    if (!processingSettings.apiKey) {
      setError('Please enter your OpenRouter API key in the configuration panel')
      return
    }
    
    // Validate column mapping
    const mapping = getColumnMapping()
    if (!mapping || !Object.values(mapping).includes('title')) {
      setError('Could not find a "title" column. Please ensure your CSV has a title column.')
      return
    }
    if (!Object.values(mapping).includes('file_path')) {
      setError('Could not find a "file_path" column. Please ensure your CSV has a file path column.')
      return
    }
    
    try {
      await startProcessing()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start processing')
    }
  }
  
  const handleValidatePaths = async () => {
    setError(null)
    try {
      await validatePaths()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed')
    }
  }
  
  // Calculate validation stats
  const validCount = Object.values(validationResults).filter(r => r.valid).length
  const invalidCount = Object.values(validationResults).filter(r => !r.valid).length
  const hasValidated = Object.keys(validationResults).length > 0
  
  // Calculate processing stats
  const successCount = documents.filter(d => d.status === 'success').length
  const failedCount = documents.filter(d => d.status === 'failed').length
  
  if (documents.length === 0) {
    return null
  }
  
  return (
    <div className="space-y-4">
      {/* Error message */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}
      
      {/* Validation Section */}
      <div className="p-4 bg-gray-50 border border-gray-200 rounded">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-gray-800">Pre-flight Check</h4>
          <button
            onClick={handleValidatePaths}
            disabled={isValidating || isProcessing}
            className={`
              px-4 py-2 text-sm rounded-md transition-colors
              ${isValidating 
                ? 'bg-gray-200 text-gray-500 cursor-wait' 
                : 'bg-white border border-gray-300 hover:bg-gray-50 text-gray-700'}
            `}
          >
            {isValidating ? 'Validating...' : 'Validate Paths'}
          </button>
        </div>
        
        {hasValidated && (
          <div className="flex gap-4 text-sm">
            <span className="text-green-600">✓ {validCount} valid</span>
            {invalidCount > 0 && (
              <span className="text-red-600">⚠️ {invalidCount} invalid</span>
            )}
          </div>
        )}
        
        {!hasValidated && (
          <p className="text-sm text-gray-500">
            Validate file paths before processing to catch errors early
          </p>
        )}
      </div>
      
      {/* Action Buttons */}
      <div className="flex gap-3">
        {!isProcessing ? (
          <button
            onClick={handleStartProcessing}
            disabled={documents.length === 0 || !processingSettings.apiKey}
            className={`
              flex-1 py-3 px-6 rounded-lg font-medium text-white transition-colors
              ${documents.length === 0 || !processingSettings.apiKey
                ? 'bg-gray-300 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700'
              }
            `}
          >
            🚀 Start Processing ({documents.length} documents)
          </button>
        ) : (
          <button
            onClick={stopProcessing}
            className="flex-1 py-3 px-6 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors"
          >
            ⏹ Stop Processing
          </button>
        )}
      </div>
      
      {/* Processing Stats */}
      {(isProcessing || successCount > 0 || failedCount > 0) && (
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 bg-gray-50 rounded text-center border border-gray-200">
            <p className="text-2xl font-bold text-gray-900">{documents.length}</p>
            <p className="text-xs text-gray-500">Total</p>
          </div>
          <div className="p-3 bg-green-50 rounded text-center border border-green-200">
            <p className="text-2xl font-bold text-green-700">{successCount}</p>
            <p className="text-xs text-green-600">Success</p>
          </div>
          <div className="p-3 bg-red-50 rounded text-center border border-red-200">
            <p className="text-2xl font-bold text-red-700">{failedCount}</p>
            <p className="text-xs text-red-600">Failed</p>
          </div>
        </div>
      )}
    </div>
  )
}
