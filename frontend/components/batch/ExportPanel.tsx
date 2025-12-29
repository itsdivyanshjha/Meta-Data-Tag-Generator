'use client'

import { useState, useEffect } from 'react'
import { useBatchStore } from '@/lib/batchStore'

export default function ExportPanel() {
  const [isOpen, setIsOpen] = useState(false)
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])
  const [columnRenames, setColumnRenames] = useState<Record<string, string>>({})
  const [includeOnlySuccess, setIncludeOnlySuccess] = useState(false)
  
  const { columns, documents, exportAsCSV } = useBatchStore()
  
  // Initialize selectedColumns with all column IDs when columns load
  useEffect(() => {
    if (columns.length > 0 && selectedColumns.length === 0) {
      setSelectedColumns(columns.map(col => col.id))
    }
  }, [columns])
  
  // Calculate stats
  const successCount = documents.filter(d => d.status === 'success').length
  const hasProcessedDocs = documents.some(d => d.status === 'success' || d.status === 'failed')
  
  const handleExport = () => {
    const csv = exportAsCSV()
    
    // Filter rows if needed
    let csvData = csv
    if (includeOnlySuccess) {
      // Re-export with only successful rows
      const lines = csv.split('\n')
      const header = lines[0]
      const dataLines = lines.slice(1).filter(line => {
        // Check if status column contains 'success'
        return line.includes(',success,') || line.includes('"success"')
      })
      csvData = [header, ...dataLines].join('\n')
    }
    
    // Download
    const blob = new Blob([csvData], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `tagged_documents_${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    
    setIsOpen(false)
  }
  
  const handleQuickExport = () => {
    const csv = exportAsCSV()
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `tagged_documents_${new Date().toISOString().split('T')[0]}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
  
  if (documents.length === 0 || !hasProcessedDocs) {
    return null
  }
  
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-700">Export Results</h3>
      
      {/* Quick export button */}
      <button
        onClick={handleQuickExport}
        className="w-full py-3 px-6 rounded-lg font-medium transition-colors bg-green-600 hover:bg-green-700 text-white flex items-center justify-center gap-2"
      >
        <span>📥</span>
        Download CSV with Tags
      </button>
      
      {/* Stats */}
      <div className="text-sm text-gray-600 text-center">
        {successCount} documents with generated tags
      </div>
      
      {/* Advanced export options toggle */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="text-sm text-blue-600 hover:underline w-full text-left"
      >
        {isOpen ? '▲ Hide advanced options' : '▼ Show advanced options'}
      </button>
      
      {/* Advanced export options */}
      {isOpen && (
        <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-4">
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeOnlySuccess}
                onChange={(e) => setIncludeOnlySuccess(e.target.checked)}
                className="rounded text-blue-600"
              />
              <span className="text-sm">Export only successfully processed documents</span>
            </label>
          </div>
          
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700">Columns to Export</h4>
            <div className="max-h-48 overflow-y-auto space-y-1 border border-gray-200 rounded-lg p-3 bg-white">
              {columns.map(col => (
                <label key={col.id} className="flex items-center gap-2 text-sm hover:bg-gray-50 p-1.5 rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedColumns.includes(col.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedColumns(prev => [...prev, col.id])
                      } else {
                        setSelectedColumns(prev => prev.filter(id => id !== col.id))
                      }
                    }}
                    className="rounded text-blue-600 cursor-pointer"
                  />
                  <span>{col.name}</span>
                  {col.systemColumn && (
                    <span className="text-xs text-blue-600">(required)</span>
                  )}
                </label>
              ))}
              <label className="flex items-center gap-2 text-sm bg-green-50 p-1.5 rounded">
                <input
                  type="checkbox"
                  checked={true}
                  disabled
                  className="rounded text-blue-600 opacity-50 cursor-not-allowed"
                />
                <span className="font-medium">Generated Tags</span>
                <span className="text-xs text-green-600">(always included)</span>
              </label>
            </div>
          </div>
          
          <button
            onClick={handleExport}
            className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            Export with Options
          </button>
        </div>
      )}
    </div>
  )
}
