'use client'

import { useCallback, useMemo, useRef, useState, useEffect } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { 
  ColDef, 
  CellValueChangedEvent,
  SelectionChangedEvent,
  GridReadyEvent,
  GridApi,
  ModuleRegistry,
  AllCommunityModule
} from 'ag-grid-community'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import { useBatchStore, DocumentStatus } from '@/lib/batchStore'

// Register AG Grid modules
ModuleRegistry.registerModules([AllCommunityModule])

// Status cell renderer with styled badges (no emojis)
const StatusCellRenderer = (props: any) => {
  const status: DocumentStatus = props.value

  const statusConfig = {
    pending: {
      label: 'Pending',
      color: 'text-gray-700',
      bg: 'bg-gray-100',
      border: 'border-gray-300',
      icon: (
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      )
    },
    processing: {
      label: 'Processing',
      color: 'text-blue-700',
      bg: 'bg-blue-100',
      border: 'border-blue-300',
      icon: (
        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
      )
    },
    success: {
      label: 'Success',
      color: 'text-green-700',
      bg: 'bg-green-100',
      border: 'border-green-300',
      icon: (
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )
    },
    failed: {
      label: 'Failed',
      color: 'text-red-700',
      bg: 'bg-red-100',
      border: 'border-red-300',
      icon: (
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      )
    }
  }

  const config = statusConfig[status] || statusConfig.pending

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${config.color} ${config.bg} ${config.border}`}>
      {config.icon}
      <span>{config.label}</span>
    </span>
  )
}

// Tag categorization helper
const getTagCategory = (tag: string): string => {
  const lower = tag.toLowerCase()

  if (/\d{4}|\d{2}-\d{2}|q\d|january|february|march|april|may|june|july|august|september|october|november|december|fy|financial year/i.test(lower)) {
    return 'tag-date'
  }

  if (/(scheme|yojana|program|initiative|mission|project|pmkvy|scholarship|subsidy|grant)/i.test(lower)) {
    return 'tag-program'
  }

  if (/(delhi|mumbai|bangalore|india|state|district|city|office|chennai|kolkata|hyderabad|pune)/i.test(lower)) {
    return 'tag-location'
  }

  if (/(report|newsletter|document|circular|notification|guidelines|policy|manual|form)/i.test(lower)) {
    return 'tag-document'
  }

  return 'tag-entity'
}

// Tags cell renderer with color coding and tooltip
const TagsCellRenderer = (props: any) => {
  const tags: string[] = props.value || []

  if (tags.length === 0) return <span className="text-gray-400 text-xs">—</span>

  const allTagsText = tags.join(', ')

  return (
    <div
      className="flex flex-wrap gap-1 py-1"
      title={allTagsText}
    >
      {tags.slice(0, 4).map((tag, idx) => {
        const category = getTagCategory(tag)
        return (
          <span
            key={idx}
            className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded ${category}`}
          >
            {tag}
          </span>
        )
      })}
      {tags.length > 4 && (
        <span
          className="text-xs text-gray-600 font-medium px-1 py-0.5"
          title={tags.slice(4).join(', ')}
        >
          +{tags.length - 4}
        </span>
      )}
    </div>
  )
}

// Path type cell editor
const PathTypeEditor = (props: any) => {
  const [value, setValue] = useState(props.value || 'url')
  
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setValue(e.target.value)
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      props.stopEditing()
    }
  }
  
  return (
    <select
      value={value}
      onChange={handleChange}
      onKeyDown={handleKeyDown}
      className="w-full h-full px-2 border-0 focus:ring-2 focus:ring-blue-500"
      autoFocus
    >
      <option value="url">URL</option>
      <option value="s3">S3</option>
      <option value="local">Local</option>
    </select>
  )
}

// Validation status cell renderer (not currently used but keeping for reference)
const ValidationCellRenderer = (props: any) => {
  const { validationResults } = useBatchStore()
  const path = props.value

  if (!path) return null

  const result = validationResults[path]

  if (!result) {
    return <span className="text-gray-400 text-xs">—</span>
  }

  if (result.valid) {
    return (
      <span className="inline-flex items-center gap-1 text-green-600 text-xs" title="Valid">
        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
        Valid
      </span>
    )
  }

  return (
    <span className="inline-flex items-center gap-1 text-red-600 text-xs" title={result.error || 'Invalid'}>
      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      {result.error || 'Invalid'}
    </span>
  )
}

export default function SpreadsheetEditor() {
  const gridRef = useRef<AgGridReact>(null)
  const [gridApi, setGridApi] = useState<GridApi | null>(null)
  const [selectedRowIds, setSelectedRowIds] = useState<string[]>([])
  
  const { 
    columns, 
    documents, 
    updateRowData, 
    renameColumn,
    removeColumn,
    addColumn,
    validationResults,
    getColumnMapping
  } = useBatchStore()
  
  
  // Build AG Grid column definitions
  const columnDefs = useMemo((): ColDef[] => {
    const defs: ColDef[] = [
      {
        field: 'select',
        headerName: '',
        checkboxSelection: true,
        headerCheckboxSelection: true,
        width: 50,
        pinned: 'left',
        lockPosition: true,
        suppressMovable: true
      },
      {
        field: 'rowNumber',
        headerName: '#',
        width: 60,
        pinned: 'left',
        lockPosition: true,
        editable: false,
        cellClass: 'text-gray-500 text-center'
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 100,
        pinned: 'left',
        editable: false,
        cellRenderer: StatusCellRenderer
      }
    ]
    
    // Get column mapping to identify system columns
    const columnMapping = getColumnMapping()
    
    // Add user columns
    for (const col of columns.sort((a, b) => a.position - b.position)) {
      if (!col.visible) continue
      
      const systemField = Object.entries(columnMapping).find(([id]) => id === col.id)?.[1]
      const isPathTypeColumn = systemField === 'file_source_type'
      const isPathColumn = systemField === 'file_path'
      
      const colDef: ColDef = {
        field: col.id,
        headerName: col.name,
        editable: true,
        width: col.width || 150,
        minWidth: 80,
        resizable: true,
        sortable: true,
        filter: true,
        headerClass: col.systemColumn ? 'font-semibold' : '',
        cellClass: col.systemColumn ? 'border-l-2 border-l-blue-500 bg-blue-50/40 font-medium' : '',
        headerTooltip: col.systemColumn ? 'Required system column' : undefined,
      }
      
      // Special handling for path type column
      if (isPathTypeColumn) {
        colDef.cellEditor = PathTypeEditor
        colDef.cellEditorPopup = false
      }
      
      // Add validation indicator for path column
      if (isPathColumn) {
        colDef.cellRenderer = (params: any) => {
          const path = params.value
          const result = validationResults[path]

          return (
            <div className="flex items-center gap-2">
              <span className="flex-1 truncate">{path}</span>
              {result && (
                result.valid ? (
                  <svg className="w-4 h-4 text-green-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4 text-red-600 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                )
              )}
            </div>
          )
        }
      }
      
      defs.push(colDef)
    }
    
    // Add tags column
    defs.push({
      field: 'tags',
      headerName: 'Generated Tags',
      width: 250,
      editable: false,
      cellRenderer: TagsCellRenderer,
      cellClass: 'bg-emerald-50/30'
    })
    
    // Add error column
    defs.push({
      field: 'error',
      headerName: 'Error',
      width: 200,
      editable: false,
      cellClass: 'text-red-600 text-xs',
      hide: true // Hidden by default, shown when there are errors
    })
    
    return defs
  }, [columns, validationResults, getColumnMapping])
  
  // Build row data for AG Grid
  const rowData = useMemo(() => {
    return documents.map(doc => ({
      id: doc.id,
      rowNumber: doc.rowNumber,
      status: doc.status,
      tags: doc.tags,
      error: doc.error,
      ...doc.data
    }))
  }, [documents])
  
  // Handle cell value change
  const onCellValueChanged = useCallback((event: CellValueChangedEvent) => {
    const rowId = event.data.id
    const columnId = event.colDef.field as string
    
    // Don't update system fields (rowNumber, status, tags, error, select)
    if (['id', 'rowNumber', 'status', 'tags', 'error', 'select'].includes(columnId)) {
      return
    }
    
    updateRowData(rowId, columnId, event.newValue)
  }, [updateRowData])
  
  // Handle selection change
  const onSelectionChanged = useCallback((event: SelectionChangedEvent) => {
    const selectedNodes = event.api.getSelectedNodes()
    const ids = selectedNodes.map(node => node.data.id)
    setSelectedRowIds(ids)
  }, [])
  
  // Handle grid ready
  const onGridReady = useCallback((event: GridReadyEvent) => {
    setGridApi(event.api)
  }, [])
  
  // Default column definition
  const defaultColDef = useMemo((): ColDef => ({
    resizable: true,
    sortable: true,
    editable: true,
    cellClass: 'align-middle'
  }), [])
  
  // Grid options
  const gridOptions = useMemo(() => ({
    rowSelection: 'multiple' as const,
    suppressRowClickSelection: false,
    enableRangeSelection: true,
    undoRedoCellEditing: true,
    enableCellChangeFlash: true,
    animateRows: true,
    getRowId: (params: any) => params.data.id,
    rowHeight: 48,
    headerHeight: 44,
    suppressCellFocus: false,
    enableCellTextSelection: true,
    suppressClipboardPaste: false,
    clipboardDelimiter: ',',
    rowClassRules: {
      'row-processing': (params: any) => params.data.status === 'processing',
      'row-success': (params: any) => params.data.status === 'success',
      'row-failed': (params: any) => params.data.status === 'failed',
    }
  }), [])

  // Calculate stats - must be before any early returns
  const stats = useMemo(() => {
    const total = documents.length
    const processed = documents.filter(d => d.status === 'success').length
    const failed = documents.filter(d => d.status === 'failed').length
    const pending = documents.filter(d => d.status === 'pending').length
    const processing = documents.filter(d => d.status === 'processing').length

    return { total, processed, failed, pending, processing }
  }, [documents])

  if (columns.length === 0 || documents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-gradient-to-br from-gray-50 to-gray-100 rounded-lg border-2 border-dashed border-gray-300">
        <div className="text-center px-6 py-8">
          <div className="w-16 h-16 mx-auto mb-4 bg-gray-200 rounded-full flex items-center justify-center">
            <svg className="w-8 h-8 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <p className="text-lg font-semibold text-gray-700 mb-2">No Data Loaded</p>
          <p className="text-sm text-gray-500">Upload a CSV file to get started</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }} className="bg-white">
      {/* Stats Cards */}
      <div className="grid grid-cols-5 gap-3 px-4 py-3 bg-gray-50 border-b border-gray-200" style={{ flexShrink: 0 }}>
        <div className="bg-white border border-gray-200 rounded-lg px-3 py-2">
          <div className="text-xs text-gray-500 font-medium mb-0.5">Total</div>
          <div className="text-xl font-bold text-gray-900">{stats.total}</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2">
          <div className="text-xs text-green-700 font-medium mb-0.5">Processed</div>
          <div className="text-xl font-bold text-green-700">{stats.processed}</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <div className="text-xs text-red-700 font-medium mb-0.5">Failed</div>
          <div className="text-xl font-bold text-red-700">{stats.failed}</div>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
          <div className="text-xs text-blue-700 font-medium mb-0.5">Processing</div>
          <div className="text-xl font-bold text-blue-700">{stats.processing}</div>
        </div>
        <div className="bg-gray-50 border border-gray-300 rounded-lg px-3 py-2">
          <div className="text-xs text-gray-600 font-medium mb-0.5">Pending</div>
          <div className="text-xl font-bold text-gray-700">{stats.pending}</div>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-4 px-4 py-2.5 bg-white border-b border-gray-200" style={{ flexShrink: 0 }}>
        <span className="text-sm text-gray-700 font-medium">
          {documents.length} documents
        </span>

        {selectedRowIds.length > 0 && (
          <>
            <span className="text-gray-300">|</span>
            <span className="text-sm text-blue-600 font-medium">
              {selectedRowIds.length} selected
            </span>
          </>
        )}

        <div style={{ flex: 1 }} />

        <button
          onClick={() => addColumn('New Column')}
          className="px-3 py-1.5 text-sm bg-white border border-gray-300 hover:bg-gray-50 rounded-lg transition-colors flex items-center gap-1.5 text-gray-700 shadow-sm"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add Column</span>
        </button>
      </div>
      
      {/* Grid - Takes all available space */}
      <div style={{ flex: 1, width: '100%', overflow: 'hidden' }}>
        <div className="ag-theme-alpine" style={{ width: '100%', height: '100%' }}>
          <AgGridReact
            ref={gridRef}
            columnDefs={columnDefs}
            rowData={rowData}
            defaultColDef={defaultColDef}
            onCellValueChanged={onCellValueChanged}
            onSelectionChanged={onSelectionChanged}
            onGridReady={onGridReady}
            {...gridOptions}
          />
        </div>
      </div>
      
      {/* Status bar - removed since stats are now at top */}
    </div>
  )
}

