'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import ProtectedRoute from '@/components/ProtectedRoute'
import { getJobs, deleteJob, getJobDetail, JobSummary } from '@/lib/api'

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
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    partial: 'bg-orange-100 text-orange-800'
  }
  return statusColors[status] || 'bg-gray-100 text-gray-800'
}

interface JobDetailModalProps {
  jobId: string | null
  onClose: () => void
}

function DocumentPreviewModal({ doc, onClose }: { doc: any, onClose: () => void }) {
  const [copied, setCopied] = useState(false)

  const handleCopyTags = () => {
    if (doc.tags && doc.tags.length > 0) {
      copyToClipboard(doc.tags.join(', '))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  if (!doc) return null

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between bg-gradient-to-r from-blue-50 to-white">
          <h3 className="text-lg font-semibold text-gray-900">Document Preview: {doc.title}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-hidden flex">
          {/* Document Viewer - Left Side */}
          <div className="flex-1 bg-gray-900 flex items-center justify-center overflow-hidden">
            {doc.file_path && (doc.file_path.endsWith('.pdf') || doc.file_source_type === 'url') ? (
              <iframe
                src={doc.file_path}
                className="w-full h-full border-0"
                title={doc.title}
              />
            ) : doc.file_path?.startsWith('upload://') ? (
              <div className="text-center text-white p-8">
                <svg className="mx-auto h-16 w-16 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">Preview not available</p>
                <p className="text-sm text-gray-400 mt-2">Uploaded files cannot be previewed directly</p>
                <p className="text-xs text-gray-500 mt-1">{doc.file_path}</p>
              </div>
            ) : (
              <div className="text-center text-white p-8">
                <svg className="mx-auto h-16 w-16 text-gray-400 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">Preview not available</p>
                <p className="text-sm text-gray-400 mt-2">This file type cannot be previewed</p>
              </div>
            )}
          </div>

          {/* Document Details - Right Side */}
          <div className="w-96 bg-white border-l border-gray-200 overflow-y-auto">
            <div className="p-6 space-y-6">
            {/* Document Info */}
            <div>
              <h4 className="text-xl font-bold text-gray-900 mb-4">{doc.title}</h4>
              <div className="grid grid-cols-2 gap-4 bg-gray-50 p-4 rounded-lg">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">File Path</p>
                  <p className="text-sm font-medium text-gray-900 truncate mt-1">{doc.file_path}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Status</p>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium mt-1 ${getStatusBadge(doc.status)}`}>
                    {doc.status}
                  </span>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Source Type</p>
                  <p className="text-sm font-medium text-gray-900 mt-1">{doc.file_source_type}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Processed At</p>
                  <p className="text-sm font-medium text-gray-900 mt-1">{formatDate(doc.processed_at)}</p>
                </div>
              </div>
            </div>

            {/* Tags with Copy */}
            {doc.tags && doc.tags.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h5 className="font-semibold text-gray-900">Tags ({doc.tags.length})</h5>
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
                    <span key={i} className="px-3 py-1.5 bg-blue-100 text-blue-800 text-sm rounded-lg font-medium">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Extracted Text Preview */}
            {doc.extracted_text && (
              <div>
                <h5 className="font-semibold text-gray-900 mb-3">Extracted Text Preview</h5>
                <div className="bg-gray-50 p-4 rounded-lg max-h-64 overflow-y-auto">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">
                    {doc.extracted_text.substring(0, 1000)}
                    {doc.extracted_text.length > 1000 && '...'}
                  </p>
                </div>
              </div>
            )}

            {/* Error Message */}
            {doc.error_message && (
              <div className="bg-red-50 border border-red-200 p-4 rounded-lg">
                <p className="text-sm font-medium text-red-800">Error:</p>
                <p className="text-sm text-red-600 mt-1">{doc.error_message}</p>
              </div>
            )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function DocumentItem({ doc, onPreview }: { doc: any, onPreview: (doc: any) => void }) {
  const [docCopied, setDocCopied] = useState(false)

  const handleCopyDocTags = (docTags: string[]) => {
    copyToClipboard(docTags.join(', '))
    setDocCopied(true)
    setTimeout(() => setDocCopied(false), 2000)
  }

  return (
    <div className="p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900 truncate">{doc.title}</p>
          <p className="text-sm text-gray-500 truncate">{doc.file_path}</p>
        </div>
        <div className="flex items-center gap-2 ml-2">
          <button
            onClick={() => onPreview(doc)}
            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
          >
            Preview
          </button>
          <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(doc.status)}`}>
            {doc.status}
          </span>
        </div>
      </div>
      {doc.tags && doc.tags.length > 0 && (
        <div className="mt-2">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs text-gray-500">Tags:</span>
            <button
              onClick={() => handleCopyDocTags(doc.tags)}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
            >
              {docCopied ? (
                <>
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Copied
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Copy
                </>
              )}
            </button>
          </div>
          <div className="flex flex-wrap gap-1">
            {doc.tags.slice(0, 5).map((tag: string, i: number) => (
              <span key={i} className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded">
                {tag}
              </span>
            ))}
            {doc.tags.length > 5 && (
              <span className="text-xs text-gray-500">+{doc.tags.length - 5} more</span>
            )}
          </div>
        </div>
      )}
      {doc.error_message && (
        <p className="mt-2 text-sm text-red-600">{doc.error_message}</p>
      )}
    </div>
  )
}

function JobDetailModal({ jobId, onClose }: JobDetailModalProps) {
  const [job, setJob] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [previewDoc, setPreviewDoc] = useState<any>(null)

  const loadJobDetail = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const data = await getJobDetail(jobId!)
      setJob(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load job details')
    } finally {
      setIsLoading(false)
    }
  }, [jobId])

  useEffect(() => {
    if (jobId) {
      loadJobDetail()
    }
  }, [jobId, loadJobDetail])

  if (!jobId) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-3xl w-full max-h-[80vh] overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-gray-900">Job Details</h3>
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
          ) : job ? (
            <div className="space-y-6">
              {/* Job Info */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-gray-500">Type</p>
                  <p className="font-medium capitalize">{job.job_type}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Status</p>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(job.status)}`}>
                    {job.status}
                  </span>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Created</p>
                  <p className="font-medium">{formatDate(job.created_at)}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Completed</p>
                  <p className="font-medium">{formatDate(job.completed_at)}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Processed</p>
                  <p className="font-medium">{job.processed_count} / {job.total_documents}</p>
                </div>
                <div>
                  <p className="text-sm text-gray-500">Failed</p>
                  <p className="font-medium text-red-600">{job.failed_count}</p>
                </div>
              </div>

              {/* Documents */}
              {job.documents && job.documents.length > 0 && (
                <div>
                  <h4 className="font-medium text-gray-900 mb-3">Documents ({job.documents.length})</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {job.documents.map((doc: any) => (
                      <DocumentItem key={doc.id} doc={doc} onPreview={setPreviewDoc} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {/* Document Preview Modal */}
      {previewDoc && <DocumentPreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />}
    </div>
  )
}

function HistoryContent() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [filteredJobs, setFilteredJobs] = useState<JobSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')

  const applyFilters = useCallback(() => {
    let result = [...jobs]

    if (statusFilter !== 'all') {
      result = result.filter(j => j.status === statusFilter)
    }

    if (typeFilter !== 'all') {
      result = result.filter(j => j.job_type === typeFilter)
    }

    result.sort((a, b) => {
      const dateA = new Date(a.created_at).getTime()
      const dateB = new Date(b.created_at).getTime()
      return sortOrder === 'newest' ? dateB - dateA : dateA - dateB
    })

    setFilteredJobs(result)
  }, [jobs, statusFilter, typeFilter, sortOrder])

  useEffect(() => {
    loadJobs()
  }, [])

  useEffect(() => {
    applyFilters()
  }, [applyFilters])

  async function loadJobs() {
    try {
      setIsLoading(true)
      setError(null)
      const response = await getJobs(100, 0)
      setJobs(response.jobs)
    } catch (err: any) {
      setError(err.message || 'Failed to load history')
    } finally {
      setIsLoading(false)
    }
  }

  async function handleDelete(jobId: string) {
    if (!confirm('Are you sure you want to delete this job?')) return

    try {
      setDeletingId(jobId)
      await deleteJob(jobId)
      setJobs(jobs.filter(j => j.id !== jobId))
    } catch (err: any) {
      alert(err.message || 'Failed to delete job')
    } finally {
      setDeletingId(null)
    }
  }

  // Get unique statuses and types for filters
  const statuses = [...new Set(jobs.map(j => j.status))]
  const types = [...new Set(jobs.map(j => j.job_type))]

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

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 px-6 py-4 rounded-lg">
        <p className="font-medium">Error loading history</p>
        <p className="text-sm mt-1">{error}</p>
        <button onClick={loadJobs} className="mt-3 text-sm text-red-600 hover:text-red-800 underline">
          Try again
        </button>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-20">
        <svg className="mx-auto h-16 w-16 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <h3 className="mt-4 text-lg font-medium text-gray-900">No processing history</h3>
        <p className="mt-2 text-gray-500">Your processed documents will appear here.</p>
        <Link
          href="/"
          className="mt-6 inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Process Documents
        </Link>
      </div>
    )
  }

  return (
    <>
      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Status:</label>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="all">All</option>
            {statuses.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Type:</label>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="all">All</option>
            {types.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700">Sort:</label>
          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value as 'newest' | 'oldest')}
            className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </div>

        <div className="ml-auto text-sm text-gray-500">
          Showing {filteredJobs.length} of {jobs.length} jobs
        </div>
      </div>

      {/* Jobs Table */}
      <div className="overflow-hidden bg-white rounded-xl border border-gray-200 shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Documents
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Completed
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {filteredJobs.map((job) => (
              <tr key={job.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className="text-sm font-medium text-gray-900 capitalize">
                    {job.job_type}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap">
                  <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusBadge(job.status)}`}>
                    {job.status}
                  </span>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  <span className="text-green-600">{job.processed_count}</span>
                  {job.failed_count > 0 && (
                    <> / <span className="text-red-600">{job.failed_count} failed</span></>
                  )}
                  {' '}of {job.total_documents}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatDate(job.created_at)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                  {formatDate(job.completed_at)}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm space-x-3">
                  <button
                    onClick={() => setSelectedJobId(job.id)}
                    className="text-blue-600 hover:text-blue-800"
                  >
                    View
                  </button>
                  <button
                    onClick={() => handleDelete(job.id)}
                    disabled={deletingId === job.id}
                    className="text-red-600 hover:text-red-800 disabled:opacity-50"
                  >
                    {deletingId === job.id ? 'Deleting...' : 'Delete'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Job Detail Modal */}
      <JobDetailModal jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
    </>
  )
}

export default function HistoryPage() {
  return (
    <ProtectedRoute>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Processing History</h1>
            <p className="text-gray-500 mt-1">View and manage your document processing jobs</p>
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

        <HistoryContent />
      </div>
    </ProtectedRoute>
  )
}
