'use client'

import { useState, useCallback } from 'react'
import { processSinglePDF, APIError } from '@/lib/api'
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
          // Set preview URL directly for valid URLs
          setPreviewUrl(url)
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

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
  }

  return (
    <div className="space-y-6">
      <div className="card p-6 space-y-4">
        <div className="border-b border-gray-200 pb-3">
          <h2 className="text-lg font-bold text-gray-900">Single PDF Upload</h2>
          <p className="text-sm text-gray-500">Upload a PDF to generate tags</p>
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

      {/* PDF Preview - Increased height */}
      {previewUrl && (
        <div className="card p-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">PDF Preview</h3>
          <div className="border border-gray-300 rounded overflow-hidden" style={{ height: '600px' }}>
            <iframe 
              src={previewUrl} 
              className="w-full h-full"
              title="PDF Preview"
            />
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="card p-6 space-y-6">
          {/* Success Banner */}
          <div className="p-4 bg-green-50 border border-green-200 rounded">
            <p className="font-semibold text-green-800">✓ Tags Generated Successfully</p>
            <p className="text-sm text-green-600">
              Processed in {result.processing_time}s
            </p>
          </div>

          {/* Document Title */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-medium text-gray-500">Document Title</h3>
              {/* OCR Status Badge */}
              {result.is_scanned !== undefined && (
                <span className={`text-xs px-2 py-1 rounded ${
                  result.is_scanned 
                    ? 'bg-purple-100 text-purple-700 border border-purple-300' 
                    : 'bg-blue-100 text-blue-700 border border-blue-300'
                }`}>
                  {result.is_scanned ? (
                    <>📷 Scanned PDF{result.ocr_confidence ? ` (${result.ocr_confidence}% confidence)` : ''}</>
                  ) : (
                    <>📄 Text PDF</>
                  )}
                </span>
              )}
            </div>
            <p className="text-lg font-semibold text-gray-900">{result.document_title}</p>
            {/* Extraction Method Info */}
            {result.extraction_method && (
              <p className="text-xs text-gray-500 mt-1">
                Extracted using: {result.extraction_method === 'pypdf2' ? 'PyPDF2' : result.extraction_method === 'tesseract_ocr' ? 'Tesseract OCR (Hindi + English)' : result.extraction_method}
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
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-500">Generated Tags</h3>
              {result.tags && result.tags.length > 0 && (
                <button
                  onClick={copyTags}
                  className="text-sm text-blue-600 hover:underline"
                >
                  Copy all
                </button>
              )}
            </div>
            {result.tags && result.tags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {result.tags.map((tag, index) => (
                  <span key={index} className="tag-pill">
                    {tag}
                  </span>
                ))}
              </div>
            ) : (
              <div className="p-4 bg-red-50 border border-red-200 rounded">
                <p className="text-sm text-red-700 font-semibold mb-2">⚠️ No tags were parsed from the AI response</p>
                <p className="text-xs text-red-600">Check the "Raw AI Response" above to see what the model returned. The parsing logic may need adjustment.</p>
              </div>
            )}
          </div>

          {/* Text Preview */}
          <div>
            <h3 className="text-sm font-medium text-gray-500 mb-2">Extracted Text Preview</h3>
            <div className="p-4 bg-gray-50 rounded max-h-60 overflow-y-auto border border-gray-200">
              <p className="text-sm text-gray-700 leading-relaxed">
                {result.extracted_text_preview}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
