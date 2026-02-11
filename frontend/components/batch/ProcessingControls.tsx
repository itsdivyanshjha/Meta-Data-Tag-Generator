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
    
    // Validate column mapping - only file_path is required
    const mapping = getColumnMapping()
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
      console.log('Starting path validation...')
      await validatePaths()
      console.log('Path validation completed')
    } catch (err) {
      console.error('Path validation error:', err)
      setError(err instanceof Error ? err.message : 'Validation failed. Please check your file paths and try again.')
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
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}
      
      {/* Validation Section */}
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-gray-800">Pre-flight Check</h4>
          <button
            onClick={handleValidatePaths}
            disabled={isValidating || isProcessing}
            className={`
              px-4 py-2 text-sm rounded-lg transition-colors font-medium
              ${isValidating 
                ? 'bg-blue-100 text-blue-700 cursor-wait border border-blue-300' 
                : isProcessing
                  ? 'bg-gray-200 text-gray-500 cursor-not-allowed border border-gray-300'
                  : 'bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 hover:border-gray-400'}
            `}
          >
            {isValidating ? '⏳ Validating...' : '🔍 Validate Paths'}
          </button>
        </div>
        
        {isValidating && (
          <div className="mb-3 p-2 bg-blue-50 border border-blue-200 rounded text-sm text-blue-700">
            <p className="font-medium">Validating {documents.length} file paths...</p>
            <p className="text-xs mt-1">This may take a moment depending on the number of files</p>
          </div>
        )}
        
        {hasValidated && !isValidating && (
          <div className="space-y-2">
            <div className="flex gap-4 text-sm font-medium">
              <span className="text-green-600 flex items-center gap-1">
                <span>✓</span> {validCount} valid
              </span>
              {invalidCount > 0 && (
                <span className="text-red-600 flex items-center gap-1">
                  <span>⚠️</span> {invalidCount} invalid
                </span>
              )}
            </div>
            {invalidCount > 0 && (
              <p className="text-xs text-red-600">
                Check invalid paths in the table below before starting processing
              </p>
            )}
            {invalidCount === 0 && validCount > 0 && (
              <p className="text-xs text-green-600">
                ✓ All paths are valid! You can proceed with processing.
              </p>
            )}
          </div>
        )}
        
        {!hasValidated && !isValidating && (
          <p className="text-sm text-gray-500">
            Validate file paths before processing to catch errors early. This checks if URLs are accessible and files exist.
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
            Start Processing ({documents.length} documents)
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
          <div className="p-3 bg-gray-50 rounded-lg text-center border border-gray-200">
            <p className="text-2xl font-bold text-gray-900">{documents.length}</p>
            <p className="text-xs text-gray-500">Total</p>
          </div>
          <div className="p-3 bg-green-50 rounded-lg text-center border border-green-200">
            <p className="text-2xl font-bold text-green-700">{successCount}</p>
            <p className="text-xs text-green-600">Success</p>
          </div>
          <div className="p-3 bg-red-50 rounded-lg text-center border border-red-200">
            <p className="text-2xl font-bold text-red-700">{failedCount}</p>
            <p className="text-xs text-red-600">Failed</p>
          </div>
        </div>
      )}
    </div>
  )
}
