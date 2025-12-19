'use client'

import { useState, useCallback } from 'react'
import { processBatchCSV, downloadCSV, APIError } from '@/lib/api'
import { TaggingConfig, BatchProcessResponse } from '@/lib/types'

interface BatchUploadProps {
  config: TaggingConfig
}

export default function BatchUpload({ config }: BatchUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<BatchProcessResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      if (selectedFile.name.endsWith('.csv')) {
        setFile(selectedFile)
        setResult(null)
        setError(null)
      } else {
        setError('Please select a CSV file')
      }
    }
  }

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && droppedFile.name.endsWith('.csv')) {
      setFile(droppedFile)
      setResult(null)
      setError(null)
    } else {
      setError('Please drop a CSV file')
    }
  }, [])

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }, [])

  const handleSubmit = async () => {
    if (!file) {
      setError('Please select a CSV file')
      return
    }

    if (!config.api_key) {
      setError('Please enter your OpenRouter API key in the configuration panel')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const response = await processBatchCSV(file, config)
      setResult(response)
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError(err instanceof Error ? err.message : 'An unexpected error occurred')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (result?.output_csv_url) {
      downloadCSV(result.output_csv_url, 'tagged_documents.csv')
    }
  }

  return (
    <div className="card p-6 space-y-6">
      <div className="border-b border-gray-200 pb-4">
        <h2 className="text-lg font-bold text-gray-900">Batch CSV Upload</h2>
        <p className="text-sm text-gray-500">Process multiple documents at once</p>
      </div>

      {/* CSV Format Info */}
      <div className="p-4 bg-blue-50 border border-blue-200 rounded">
        <h3 className="font-semibold text-blue-800 mb-2">
          CSV Format Required
        </h3>
        <p className="text-sm text-blue-700 mb-3">
          Your CSV should have these columns:
        </p>
        <div className="bg-white rounded p-3 overflow-x-auto">
          <code className="text-xs text-gray-700">
            title, description, file_source_type, file_path, publishing_date, file_size
          </code>
        </div>
        <div className="mt-3">
          <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">
            file_source_type: &quot;url&quot;, &quot;s3&quot;, or &quot;local&quot;
          </span>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          isDragging
            ? 'border-blue-500 bg-blue-50'
            : file
            ? 'border-green-500 bg-green-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <input
          type="file"
          accept=".csv"
          onChange={handleFileChange}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        
        {file ? (
          <div className="space-y-3">
            <div className="text-green-600 text-4xl">✓</div>
            <div>
              <p className="font-semibold text-gray-900 truncate max-w-xs mx-auto">
                {file.name}
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                setFile(null)
                setResult(null)
              }}
              className="text-sm text-gray-500 hover:text-red-600 transition-colors"
            >
              Remove file
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-gray-400 text-4xl">📊</div>
            <div>
              <p className="font-semibold text-gray-700">
                Drop your CSV here or click to browse
              </p>
              <p className="text-sm text-gray-500">
                CSV file with document metadata
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Submit Button */}
      <button
        onClick={handleSubmit}
        disabled={loading || !file || !config.api_key}
        className="btn-primary w-full"
      >
        {loading ? (
          <span>Processing batch...</span>
        ) : (
          <span>Process Batch CSV</span>
        )}
      </button>

      {/* Loading Progress */}
      {loading && (
        <div className="p-4 bg-gray-50 rounded">
          <p className="text-sm text-gray-700 mb-3">
            Processing documents... This may take a few minutes depending on the number of documents.
          </p>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div className="h-full bg-blue-600 rounded-full animate-pulse" style={{width: '60%'}} />
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6 pt-4 border-t border-gray-200">
          {/* Success Banner */}
          <div className="p-4 bg-green-50 border border-green-200 rounded">
            <p className="font-semibold text-green-800">✓ Batch Processing Complete</p>
            <p className="text-sm text-green-600">
              Processed in {result.processing_time}s
            </p>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 bg-gray-50 rounded text-center">
              <p className="text-sm text-gray-500">Total</p>
              <p className="text-3xl font-bold text-gray-900">{result.total_documents}</p>
            </div>
            <div className="p-4 bg-green-50 rounded text-center">
              <p className="text-sm text-green-600">Processed</p>
              <p className="text-3xl font-bold text-green-700">{result.processed_count}</p>
            </div>
            <div className="p-4 bg-red-50 rounded text-center">
              <p className="text-sm text-red-600">Failed</p>
              <p className="text-3xl font-bold text-red-700">{result.failed_count}</p>
            </div>
          </div>

          {/* Download Button */}
          <button
            onClick={handleDownload}
            className="w-full bg-green-600 hover:bg-green-700 text-white font-medium py-3 px-6 rounded"
          >
            Download Enhanced CSV with Tags
          </button>

          {/* Document Results */}
          {result.summary_report?.documents && result.summary_report.documents.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-gray-500 mb-3">Document Results</h3>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {result.summary_report.documents.map((doc, index) => (
                  <div 
                    key={index}
                    className={`p-3 rounded border ${
                      doc.success 
                        ? 'bg-green-50 border-green-200' 
                        : 'bg-red-50 border-red-200'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-700 truncate flex-1 mr-2">
                        {doc.title}
                      </span>
                      {doc.success ? (
                        <span className="text-green-600">✓</span>
                      ) : (
                        <span className="text-red-600">✗</span>
                      )}
                    </div>
                    {doc.success && doc.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {doc.tags.slice(0, 5).map((tag, tagIndex) => (
                          <span key={tagIndex} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-700 rounded">
                            {tag}
                          </span>
                        ))}
                        {doc.tags.length > 5 && (
                          <span className="text-xs text-gray-500">+{doc.tags.length - 5} more</span>
                        )}
                      </div>
                    )}
                    {!doc.success && doc.error && (
                      <p className="text-xs text-red-600 mt-1">{doc.error}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
