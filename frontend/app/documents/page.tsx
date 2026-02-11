'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import ProtectedRoute from '@/components/ProtectedRoute'
import { getDocuments, searchDocuments, getDocumentDetail, DocumentSummary } from '@/lib/api'

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString()
}

function getStatusBadge(status: string) {
  const statusColors: Record<string, string> = {
    pending: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-blue-100 text-blue-800',
    success: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800'
  }
  return statusColors[status] || 'bg-gray-100 text-gray-800'
}

interface DocumentDetailModalProps {
  docId: string | null
  onClose: () => void
}

function DocumentDetailModal({ docId, onClose }: DocumentDetailModalProps) {
  const [doc, setDoc] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const loadDocDetail = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await getDocumentDetail(docId!)
      setDoc(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load document details')
    } finally {
      setIsLoading(false)
    }
  }, [docId])

  useEffect(() => {
    if (docId) {
      loadDocDetail()
    }
  }, [docId, loadDocDetail])

  const handleCopyTags = () => {
    if (doc?.tags && doc.tags.length > 0) {
      copyToClipboard(doc.tags.join(', '))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (!docId) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Document Details</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(80vh-80px)]">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <svg className="animate-spin h-8 w-8 text-blue-600" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
            </div>
          ) : error ? (
            <div className="text-red-600 text-center py-8">{error}</div>
          ) : doc ? (
            <div className="space-y-6">
              {/* Document Info */}
              <div>
                <h4 className="font-medium text-gray-900 text-lg">{doc.title}</h4>
                <p className="text-sm text-gray-500 mt-1">{doc.file_path}</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Status</p>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(doc.status)}`}>
                    {doc.status}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Source Type</p>
                  <p className="font-medium capitalize">{doc.file_source_type}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Size</p>
                  <p className="font-medium">{doc.file_size ? `${(doc.file_size / 1024).toFixed(1)} KB` : '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Processed</p>
                  <p className="font-medium">{formatDate(doc.processed_at)}</p>
                </div>
              </div>

              {/* Tags */}
              {doc.tags && doc.tags.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-sm text-gray-500">Tags ({doc.tags.length})</p>
                    <button
                      onClick={handleCopyTags}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
                    >
                      {copied ? (
                        <>
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                          Copied!
                        </>
                      ) : (
                        <>
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                          </svg>
                        Copy Tags
                        </>
                      )}
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {doc.tags.map((tag: string, i: number) => (
                      <span key={i} className="px-3 py-1 bg-blue-100 text-blue-800 text-sm rounded-lg">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Error Message */}
              {doc.error_message && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <p className="text-sm font-medium text-red-800">Error</p>
                  <p className="text-sm text-red-700 mt-1">{doc.error_message}</p>
                </div>
              )}

              {/* Extracted Text Preview */}
              {doc.extracted_text && (
                <div>
                  <p className="text-sm text-gray-500 mb-2">Extracted Text Preview</p>
                  <div className="bg-gray-50 rounded-lg p-4 max-h-48 overflow-y-auto">
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">
                      {doc.extracted_text.slice(0, 1000)}
                      {doc.extracted_text.length > 1000 && '...'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function DocumentsContent() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)

  useEffect(() => {
    loadDocuments()
  }, [])

  async function loadDocuments() {
    try {
      setIsLoading(true)
      setError(null)
      setHasSearched(false)
      const response = await getDocuments(50)
      setDocuments(response.documents)
    } catch (err: any) {
      setError(err.message || 'Failed to load documents')
    } finally {
      setIsLoading(false)
    }
  }

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) {
      loadDocuments()
      return
    }

    try {
      setIsSearching(true)
      setError(null)
      setHasSearched(true)
      const response = await searchDocuments(searchQuery.trim(), 50)
      setDocuments(response.documents)
    } catch (err: any) {
      setError(err.message || 'Search failed')
    } finally {
      setIsSearching(false)
    }
  }, [searchQuery])

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch()
    }
  }

  const clearSearch = () => {
    setSearchQuery('')
    loadDocuments()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <svg className="animate-spin h-8 w-8 text-blue-600" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      </div>
    )
  }

  return (
    <>
      {/* Search Bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Search by document title or tags..."
              className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            />
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <button
            onClick={handleSearch}
            disabled={isSearching}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-blue-400 transition-colors"
          >
            {isSearching ? 'Searching...' : 'Search'}
          </button>
          {hasSearched && (
            <button
              onClick={clearSearch}
              className="px-4 py-2.5 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Clear
            </button>
          )}
        </div>
        {hasSearched && (
          <p className="mt-3 text-sm text-gray-500">
            Found {documents.length} document{documents.length !== 1 ? 's' : ''} matching &quot;{searchQuery}&quot;
          </p>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-6 py-4 rounded-lg mb-6">
          <p className="font-medium">Error</p>
          <p className="text-sm mt-1">{error}</p>
        </div>
      )}

      {documents.length === 0 ? (
        <div className="text-center py-20">
          <svg className="mx-auto h-16 w-16 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900">
            {hasSearched ? 'No documents found' : 'No documents yet'}
          </h3>
          <p className="mt-2 text-gray-500">
            {hasSearched ? 'Try a different search term.' : 'Process some documents to see them here.'}
          </p>
          {!hasSearched && (
            <Link
              href="/"
              className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Process Documents
            </Link>
          )}
        </div>
      ) : (
        <div className="grid gap-4">
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer"
              onClick={() => setSelectedDocId(doc.id)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-gray-900 truncate">{doc.title}</h3>
                  <p className="text-sm text-gray-500 truncate mt-1">{doc.file_path}</p>
                </div>
                <span className={`ml-4 inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(doc.status)}`}>
                  {doc.status}
                </span>
              </div>

              {doc.tags && doc.tags.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {doc.tags.slice(0, 6).map((tag, i) => (
                    <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded">
                      {tag}
                    </span>
                  ))}
                  {doc.tags.length > 6 && (
                    <span className="px-2 py-0.5 text-gray-500 text-xs">
                      +{doc.tags.length - 6} more
                    </span>
                  )}
                </div>
              )}

              <div className="mt-3 flex items-center gap-4 text-xs text-gray-500">
                <span className="capitalize">{doc.file_source_type}</span>
                <span>{formatDate(doc.processed_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      <DocumentDetailModal docId={selectedDocId} onClose={() => setSelectedDocId(null)} />
    </>
  )
}

export default function DocumentsPage() {
  return (
    <ProtectedRoute>
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
            <p className="text-gray-500 mt-1">Search and view your processed documents</p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Dashboard
            </Link>
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              New Job
            </Link>
          </div>
        </div>

        <DocumentsContent />
      </div>
    </ProtectedRoute>
  )
}
