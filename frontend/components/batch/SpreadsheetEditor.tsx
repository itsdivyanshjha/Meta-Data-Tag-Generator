'use client'

import { useCallback, useMemo, useRef, useState, useEffect } from 'react'
import { AgGridReact } from 'ag-grid-react'
import { 
  ColDef, 
  CellValueChangedEvent,
  SelectionChangedEvent,
  GridReadyEvent,
  GridApi
} from 'ag-grid-community'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import { useBatchStore, DocumentStatus } from '@/lib/batchStore'

// Status cell renderer
const StatusCellRenderer = (props: any) => {
  const status: DocumentStatus = props.value
  
  const statusConfig = {
    pending: { icon: '⏳', color: 'text-gray-500', bg: 'bg-gray-100' },
    processing: { icon: '🔄', color: 'text-blue-600', bg: 'bg-blue-100' },
    success: { icon: '✅', color: 'text-green-600', bg: 'bg-green-100' },
    failed: { icon: '❌', color: 'text-red-600', bg: 'bg-red-100' }
  }
  
  const config = statusConfig[status] || statusConfig.pending
  
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${config.color} ${config.bg}`}>
      <span className="mr-1">{config.icon}</span>
      {status}
    </span>
  )
}

// Tags cell renderer
const TagsCellRenderer = (props: any) => {
  const tags: string[] = props.value || []
  
  if (tags.length === 0) return <span className="text-gray-400 text-xs">—</span>
  
  return (
    <div className="flex flex-wrap gap-1 py-1">
      {tags.slice(0, 3).map((tag, idx) => (
        <span 
          key={idx} 
          className="inline-block px-1.5 py-0.5 text-xs bg-emerald-100 text-emerald-700 rounded"
        >
          {tag}
        </span>
      ))}
      {tags.length > 3 && (
        <span className="text-xs text-gray-500">+{tags.length - 3} more</span>
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

// Validation status cell renderer
const ValidationCellRenderer = (props: any) => {
  const { validationResults } = useBatchStore()
  const path = props.value
  
  if (!path) return null
  
  const result = validationResults[path]
  
  if (!result) {
    return <span className="text-gray-400">—</span>
  }
  
  if (result.valid) {
    return <span className="text-green-600" title="Valid">✓</span>
  }
  
  return (
    <span className="text-red-600" title={result.error || 'Invalid'}>
      ⚠️
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
  
  // Debug log
  useEffect(() => {
    console.log('========== SpreadsheetEditor Debug ==========')
    console.log('columns.length:', columns.length)
    console.log('documents.length:', documents.length)
    console.log('Columns:', columns)
    console.log('Documents sample:', documents.slice(0, 2))
    console.log('==========================================')
  }, [columns, documents])
  
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
        headerClass: col.systemColumn ? 'bg-blue-50' : '',
        cellClass: col.systemColumn ? 'bg-blue-50/30' : '',
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
                <span className={result.valid ? 'text-green-600' : 'text-red-600'}>
                  {result.valid ? '✓' : '⚠️'}
                </span>
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
    rowHeight: 42,
    headerHeight: 42,
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
  
  if (columns.length === 0 || documents.length === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center text-gray-500">
          <p className="text-lg mb-2">No data loaded</p>
          <p className="text-sm">Columns: {columns.length}, Documents: {documents.length}</p>
        </div>
      </div>
    )
  }
  
  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }} className="bg-white">
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
          className="px-3 py-1.5 text-sm bg-white border border-gray-300 hover:bg-gray-50 rounded transition-colors flex items-center gap-1.5 text-gray-700 shadow-sm"
        >
          <span>➕</span>
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
      
      {/* Status bar */}
      <div className="flex items-center gap-6 px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs text-gray-600 flex-shrink-0">
        <span className="font-medium">
          ✅ {documents.filter(d => d.status === 'success').length} processed
        </span>
        <span className="font-medium">
          ❌ {documents.filter(d => d.status === 'failed').length} failed
        </span>
        <span className="font-medium">
          ⏳ {documents.filter(d => d.status === 'pending').length} pending
        </span>
      </div>
    </div>
  )
}

