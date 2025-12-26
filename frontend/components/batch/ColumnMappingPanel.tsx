'use client'

import { useBatchStore } from '@/lib/batchStore'

export default function ColumnMappingPanel() {
  const { columns, columnMapping, setColumnMapping } = useBatchStore()
  
  // System fields that can be mapped
  const systemFields = [
    { key: 'file_path', label: 'PDF File Path/URL', required: true, description: 'Column containing PDF links or paths' },
    { key: 'title', label: 'Document Title', required: false, description: 'Optional: Document title/name' },
    { key: 'description', label: 'Description', required: false, description: 'Optional: Document description' },
  ]
  
  const handleMappingChange = (systemField: string, columnId: string) => {
    setColumnMapping({
      ...columnMapping,
      [systemField]: columnId === '' ? undefined : columnId
    })
  }
  
  const hasFilePath = columnMapping['file_path']
  
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-5">
      <div className="mb-4">
        <h3 className="text-base font-semibold text-gray-900">Column Mapping</h3>
        <p className="text-xs text-gray-500 mt-1">
          Map your CSV columns to system fields
        </p>
      </div>
      
      {!hasFilePath && (
        <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-md">
          <p className="text-xs text-amber-800">
            <span className="font-medium">⚠️ Required:</span> Select the column containing PDF file paths/URLs
          </p>
        </div>
      )}
      
      <div className="space-y-4">
        {systemFields.map(field => (
          <div key={field.key}>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">
              {field.label}
              {field.required && <span className="text-red-500 ml-1">*</span>}
            </label>
            <select
              value={columnMapping[field.key] || ''}
              onChange={(e) => handleMappingChange(field.key, e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              <option value="">-- Select column --</option>
              {columns.map(col => (
                <option key={col.id} value={col.id}>
                  {col.name}
                </option>
              ))}
            </select>
            {field.description && (
              <p className="text-xs text-gray-500 mt-1">{field.description}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

