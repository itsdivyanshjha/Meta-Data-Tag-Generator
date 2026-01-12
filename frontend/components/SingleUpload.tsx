'use client'

import { useState, useCallback } from 'react'
import { processSinglePDF, APIError, getPdfPreviewUrl } from '@/lib/api'
import { TaggingConfig, SinglePDFResponse } from '@/lib/types'

interface SingleUploadProps {
  config: TaggingConfig
  exclusionFile?: File | null
}

export default function SingleUpload({ config, exclusionFile }: SingleUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<SinglePDFResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  // URL input state
  const [pdfUrl, setPdfUrl] = useState<string>('')
  const [urlError, setUrlError] = useState<string | null>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0]
      if (selectedFile.type === 'application/pdf') {
        setFile(selectedFile)
        setPdfUrl('') // Clear URL if file selected
        setResult(null)
        setError(null)
        setUrlError(null)
        // Create preview URL
        const url = URL.createObjectURL(selectedFile)
        setPreviewUrl(url)
      } else {
        setError('Please select a PDF file')
      }
    }
  }

  const handleUrlChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const url = e.target.value
    setPdfUrl(url)
    setUrlError(null)
    
    if (url) {
      setFile(null) // Clear file if URL entered
      setResult(null)
      setError(null)
      
      // Validate URL format
      try {
        if (url && !url.startsWith('http://') && !url.startsWith('https://')) {
          setUrlError('URL must start with http:// or https://')
        } else if (url) {
          // Use proxy endpoint to bypass CORS restrictions
          setPreviewUrl(getPdfPreviewUrl(url))
        }
      } catch (err) {
        setUrlError('Invalid URL format')
      }
    } else {
      setPreviewUrl(null)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile && droppedFile.type === 'application/pdf') {
      setFile(droppedFile)
      setPdfUrl('') // Clear URL if file dropped
      setResult(null)
      setError(null)
      setUrlError(null)
      const url = URL.createObjectURL(droppedFile)
      setPreviewUrl(url)
    } else {
      setError('Please drop a PDF file')
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

  // Fullscreen modal handlers
  const openFullscreen = () => setIsFullscreen(true)
  const closeFullscreen = () => setIsFullscreen(false)

  // ESC key to close fullscreen
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape' && isFullscreen) {
      closeFullscreen()
    }
  }, [isFullscreen])

  // Add ESC key listener
  useState(() => {
    if (typeof window !== 'undefined') {
      window.addEventListener('keydown', handleKeyDown)
      return () => window.removeEventListener('keydown', handleKeyDown)
    }
  })

  const handleSubmit = async () => {
    // Validate input
    if (!file && !pdfUrl) {
      setError('Please select a PDF file or enter a PDF URL')
      return
    }

    if (file && pdfUrl) {
      setError('Please provide either a file or a URL, not both')
      return
    }

    if (pdfUrl && !pdfUrl.startsWith('http://') && !pdfUrl.startsWith('https://')) {
      setError('URL must start with http:// or https://')
      return
    }

    if (!config.api_key) {
      setError('Please enter your OpenRouter API key in the configuration panel')
      return
    }

    if (!config.model_name) {
      setError('Please enter a model name in the configuration panel')
      return
    }

    setLoading(true)
    setError(null)
    setUrlError(null)

    try {
      const response = await processSinglePDF(file, config, exclusionFile, pdfUrl || undefined)
      console.log('API Response:', response) // Debug log
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

  const copyTags = () => {
    if (result?.tags && result.tags.length > 0) {
      navigator.clipboard.writeText(result.tags.join(', '))
    }
  }

  const resetUpload = () => {
    // Clear all PDF-related state
    setFile(null)
    setPdfUrl('')
    setResult(null)
    setError(null)
    setUrlError(null)
    setPreviewUrl(null)
    setIsDragging(false)
    
    // Reset file input if it exists
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    if (fileInput) {
      fileInput.value = ''
    }
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
  }

  // Categorize tags for color-coding
  const getTagCategory = (tag: string): string => {
    const lower = tag.toLowerCase()

    // Date patterns (years, months, quarters)
    if (/\d{4}|\d{2}-\d{2}|q\d|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec/i.test(lower)) {
      return 'tag-date'
    }

    // Program/Scheme patterns
    if (/(scheme|yojana|program|initiative|mission|project|pmkvy|scholarship)/i.test(lower)) {
      return 'tag-program'
    }

    // Location patterns
    if (/(delhi|mumbai|bangalore|india|state|district|city|office)/i.test(lower)) {
      return 'tag-location'
    }

    // Document type patterns
    if (/(report|newsletter|document|circular|notification|guidelines|manual|policy|budget)/i.test(lower)) {
      return 'tag-document'
    }

    // Entity/Organization (default)
    return 'tag-entity'
  }

  return (
    <div className="space-y-8">
      <div className="card p-8 space-y-5">
        <div className="border-b border-gray-200 pb-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-gray-900">Single PDF Upload</h2>
              <p className="text-sm text-gray-500">Upload a PDF to generate tags</p>
            </div>
            <button
              onClick={resetUpload}
              disabled={!file && !pdfUrl && !result}
              className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Reset PDF upload (keeps configuration)"
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

        {/* Drop Zone - Reduced height */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`relative border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
            isDragging
              ? 'border-blue-500 bg-blue-50'
              : file
              ? 'border-green-500 bg-green-50'
              : 'border-gray-300 hover:border-gray-400'
          }`}
        >
          <input
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          />
          
          {file ? (
            <div className="space-y-2">
              <div className="text-green-600 text-3xl">✓</div>
              <div>
                <p className="font-semibold text-gray-900 truncate max-w-xs mx-auto">
                  {file.name}
                </p>
                <p className="text-sm text-gray-500">
                  {formatFileSize(file.size)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  setFile(null)
                  setResult(null)
                  setPreviewUrl(null)
                  setError(null)
                }}
                className="text-sm text-gray-500 hover:text-red-600 transition-colors"
              >
                Remove file
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="text-gray-400 text-3xl">📄</div>
              <div>
                <p className="font-semibold text-gray-700">
                  Drop your PDF here or click to browse
                </p>
                <p className="text-sm text-gray-500">
                  Supports PDF files up to 50MB
                </p>
              </div>
            </div>
          )}
        </div>

        {/* OR Separator */}
        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-gray-300"></div>
          </div>
          <div className="relative flex justify-center text-sm">
            <span className="px-2 bg-white text-gray-500">OR</span>
          </div>
        </div>

        {/* URL Input */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">
            Enter PDF URL
          </label>
          <input
            type="url"
            value={pdfUrl}
            onChange={handleUrlChange}
            placeholder="https://example.com/document.pdf"
            disabled={!!file || loading}
            className={`input-field ${file ? 'opacity-50 cursor-not-allowed' : ''}`}
          />
          <p className="text-xs text-gray-500">
            Paste a direct link to any publicly accessible PDF file
          </p>
          {urlError && (
            <p className="text-xs text-red-600">
              {urlError}
            </p>
          )}
          {pdfUrl && !urlError && (
            <div className="p-2 bg-green-50 border border-green-200 rounded text-xs text-green-700">
              ✓ URL ready: {pdfUrl.length > 60 ? pdfUrl.substring(0, 60) + '...' : pdfUrl}
            </div>
          )}
        </div>

        {/* Submit Button */}
        <button
          onClick={handleSubmit}
          disabled={loading || (!file && !pdfUrl) || !config.api_key || !config.model_name || !!urlError}
          className="btn-primary w-full"
        >
          {loading ? (
            <span>Processing...</span>
          ) : (
            <span>Generate Tags</span>
          )}
        </button>

        {/* Error Message */}
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
            {error}
          </div>
        )}
      </div>

      {/* PDF Preview with Fullscreen */}
      {previewUrl && (
        <div className="card p-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-base font-semibold text-gray-900">PDF Preview</h3>
            <button
              onClick={openFullscreen}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
              title="Open fullscreen"
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
                  d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
                />
              </svg>
              Fullscreen
            </button>
          </div>
          <div className="border border-gray-200 rounded-lg overflow-hidden shadow-sm" style={{ height: '800px' }}>
            <iframe
              src={previewUrl}
              className="w-full h-full"
              title="PDF Preview"
            />
          </div>
        </div>
      )}

      {/* Enhanced Fullscreen PDF Modal */}
      {isFullscreen && previewUrl && (
        <div
          className="fixed inset-0 z-50 bg-black bg-opacity-95 flex flex-col animate-fadeIn"
          onClick={closeFullscreen}
        >
          {/* Modal Header */}
          <div className="flex items-center justify-between px-6 py-4 bg-gradient-to-r from-gray-900 to-gray-800 border-b border-gray-700 shadow-lg">
            <div className="flex items-center gap-3">
              <svg className="w-6 h-6 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <h3 className="text-lg font-semibold text-white">Document Preview</h3>
            </div>

            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-gray-800 rounded-lg border border-gray-600">
                <kbd className="px-2 py-0.5 text-xs font-semibold text-gray-300 bg-gray-700 border border-gray-600 rounded">ESC</kbd>
                <span className="text-xs text-gray-400">to close</span>
              </div>

              <button
                onClick={closeFullscreen}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg"
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
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
                Close
              </button>
            </div>
          </div>

          {/* Modal Content */}
          <div
            className="flex-1 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full h-full bg-white rounded-xl shadow-2xl overflow-hidden">
              <iframe
                src={previewUrl}
                className="w-full h-full"
                title="PDF Preview Fullscreen"
              />
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="card p-8 space-y-6">
          {/* Success Banner */}
          <div className="p-5 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <div className="flex-1">
                <p className="font-semibold text-green-900">Tags Generated Successfully</p>
                <p className="text-sm text-green-700 mt-1">
                  Processed in {result.processing_time}s
                </p>
              </div>
            </div>
          </div>

          {/* Document Title */}
          <div className="border-b border-gray-100 pb-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Document Title</h3>
              {/* OCR Status Badge */}
              {result.is_scanned !== undefined && (
                <span className={`text-xs px-3 py-1.5 rounded-full font-medium ${
                  result.is_scanned
                    ? 'bg-purple-100 text-purple-700 border border-purple-200'
                    : 'bg-blue-100 text-blue-700 border border-blue-200'
                }`}>
                  {result.is_scanned ? (
                    <>Scanned PDF{result.ocr_confidence ? ` · ${result.ocr_confidence}% confidence` : ''}</>
                  ) : (
                    <>Text PDF</>
                  )}
                </span>
              )}
            </div>
            <p className="text-xl font-bold text-gray-900">{result.document_title}</p>
            {/* Extraction Method Info */}
            {result.extraction_method && (
              <p className="text-sm text-gray-500 mt-2">
                Extracted using {result.extraction_method === 'pypdf2' ? 'PyPDF2' : result.extraction_method === 'tesseract_ocr' ? 'Tesseract OCR' : result.extraction_method}
              </p>
            )}
          </div>

          {/* RAW AI RESPONSE - DEBUG */}
          {result.raw_ai_response && (
            <div className="p-4 bg-yellow-50 border border-yellow-300 rounded">
              <h3 className="text-sm font-semibold text-yellow-800 mb-2">🔍 Debug: Raw AI Response</h3>
              <code className="text-xs text-yellow-900 break-words whitespace-pre-wrap">
                {result.raw_ai_response}
              </code>
            </div>
          )}

          {/* Generated Tags */}
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">Generated Tags</h3>
                {result.tags && result.tags.length > 0 && (
                  <p className="text-sm text-gray-600 mt-1">{result.tags.length} tags generated</p>
                )}
              </div>
              {result.tags && result.tags.length > 0 && (
                <button
                  onClick={copyTags}
                  className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors border border-blue-200"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Copy all
                </button>
              )}
            </div>
            {result.tags && result.tags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {result.tags.map((tag, index) => (
                  <span key={index} className={`tag-pill ${getTagCategory(tag)}`}>
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700 font-semibold mb-2">No tags were parsed from the AI response</p>
                <p className="text-xs text-red-600">Check the &quot;Raw AI Response&quot; above to see what the model returned. The parsing logic may need adjustment.</p>
              </div>
            )}
          </div>

          {/* Text Preview */}
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">Extracted Text Preview</h3>
            <div className="p-5 bg-gradient-to-br from-gray-50 to-slate-50 rounded-xl max-h-60 overflow-y-auto border border-gray-200">
              <p className="text-sm text-gray-700 leading-relaxed font-mono">
                {result.extracted_text_preview}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
