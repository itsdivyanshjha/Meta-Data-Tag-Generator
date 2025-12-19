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
    <div className="glass-card p-6 space-y-6">
      <div className="flex items-center gap-3 pb-4 border-b border-slate-200 dark:border-slate-700">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
          <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-800 dark:text-white">Batch CSV Upload</h2>
          <p className="text-sm text-slate-500 dark:text-slate-400">Process multiple documents at once</p>
        </div>
      </div>

      {/* CSV Format Info */}
      <div className="p-4 bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-xl">
        <h3 className="font-semibold text-indigo-800 dark:text-indigo-200 mb-2 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          CSV Format Required
        </h3>
        <p className="text-sm text-indigo-700 dark:text-indigo-300 mb-3">
          Your CSV should have these columns:
        </p>
        <div className="bg-white dark:bg-slate-800 rounded-lg p-3 overflow-x-auto">
          <code className="text-xs text-slate-700 dark:text-slate-300 whitespace-nowrap">
            title, description, file_source_type, file_path, publishing_date, file_size
          </code>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="px-2 py-1 bg-indigo-100 dark:bg-indigo-800/50 text-indigo-700 dark:text-indigo-300 rounded-md">
            file_source_type: &quot;url&quot;, &quot;s3&quot;, or &quot;local&quot;
          </span>
        </div>
      </div>

      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`relative border-2 border-dashed rounded-2xl p-8 text-center transition-all duration-300 ${
          isDragging
            ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
            : file
            ? 'border-emerald-300 bg-emerald-50/50 dark:bg-emerald-900/10 dark:border-emerald-700'
            : 'border-slate-300 dark:border-slate-600 hover:border-indigo-400 hover:bg-slate-50 dark:hover:bg-slate-800/50'
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
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-600 flex items-center justify-center">
              <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-slate-800 dark:text-white truncate max-w-xs mx-auto">
                {file.name}
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation()
                setFile(null)
                setResult(null)
              }}
              className="text-sm text-slate-500 hover:text-red-500 transition-colors"
            >
              Remove file
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-slate-200 to-slate-300 dark:from-slate-700 dark:to-slate-600 flex items-center justify-center">
              <svg className="w-8 h-8 text-slate-500 dark:text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-slate-700 dark:text-slate-200">
                Drop your CSV here or click to browse
              </p>
              <p className="text-sm text-slate-500 dark:text-slate-400">
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
        className="btn-primary w-full flex items-center justify-center gap-2"
      >
        {loading ? (
          <>
            <svg className="animate-spin w-5 h-5" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="loading-dots">Processing batch</span>
          </>
        ) : (
          <>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            Process Batch CSV
          </>
        )}
      </button>

      {/* Loading Progress */}
      {loading && (
        <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
          <p className="text-sm text-slate-700 dark:text-slate-300 mb-3">
            Processing documents... This may take a few minutes depending on the number of documents.
          </p>
          <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2 overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-sky-500 to-indigo-500 rounded-full animate-pulse" 
              style={{width: '60%'}}
            />
          </div>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="flex items-start gap-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl">
          <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="space-y-6 pt-4 border-t border-slate-200 dark:border-slate-700">
          {/* Success Banner */}
          <div className="flex items-center gap-3 p-4 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-xl">
            <div className="w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center flex-shrink-0">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-emerald-800 dark:text-emerald-200">Batch Processing Complete</p>
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                Processed in {result.processing_time}s
              </p>
            </div>
          </div>

          {/* Stats Grid */}
          <div className="grid grid-cols-3 gap-4">
            <div className="p-4 bg-slate-50 dark:bg-slate-800/50 rounded-xl text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">Total</p>
              <p className="text-3xl font-bold text-slate-800 dark:text-white">{result.total_documents}</p>
            </div>
            <div className="p-4 bg-emerald-50 dark:bg-emerald-900/20 rounded-xl text-center">
              <p className="text-sm text-emerald-600 dark:text-emerald-400">Processed</p>
              <p className="text-3xl font-bold text-emerald-700 dark:text-emerald-300">{result.processed_count}</p>
            </div>
            <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-xl text-center">
              <p className="text-sm text-red-600 dark:text-red-400">Failed</p>
              <p className="text-3xl font-bold text-red-700 dark:text-red-300">{result.failed_count}</p>
            </div>
          </div>

          {/* Download Button */}
          <button
            onClick={handleDownload}
            className="w-full flex items-center justify-center gap-2 bg-gradient-to-r from-emerald-500 to-emerald-600 hover:from-emerald-600 hover:to-emerald-700 text-white font-semibold py-3 px-6 rounded-xl transition-all duration-300 transform hover:scale-[1.02] hover:shadow-lg hover:shadow-emerald-500/25"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Enhanced CSV with Tags
          </button>

          {/* Document Results */}
          {result.summary_report?.documents && result.summary_report.documents.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-slate-500 dark:text-slate-400 mb-3">Document Results</h3>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {result.summary_report.documents.map((doc, index) => (
                  <div 
                    key={index}
                    className={`p-3 rounded-lg border ${
                      doc.success 
                        ? 'bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200 dark:border-emerald-800' 
                        : 'bg-red-50/50 dark:bg-red-900/10 border-red-200 dark:border-red-800'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-slate-700 dark:text-slate-200 truncate flex-1 mr-2">
                        {doc.title}
                      </span>
                      {doc.success ? (
                        <svg className="w-5 h-5 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5 text-red-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      )}
                    </div>
                    {doc.success && doc.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {doc.tags.slice(0, 5).map((tag, tagIndex) => (
                          <span key={tagIndex} className="text-xs px-2 py-0.5 bg-sky-100 dark:bg-sky-900/50 text-sky-700 dark:text-sky-300 rounded">
                            {tag}
                          </span>
                        ))}
                        {doc.tags.length > 5 && (
                          <span className="text-xs text-slate-500">+{doc.tags.length - 5} more</span>
                        )}
                      </div>
                    )}
                    {!doc.success && doc.error && (
                      <p className="text-xs text-red-600 dark:text-red-400 mt-1">{doc.error}</p>
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

