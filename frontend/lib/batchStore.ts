/**
 * Zustand Store for Batch Processing
 * 
 * Manages the state for the interactive spreadsheet-based batch processing system.
 */

import { create } from 'zustand'
import { v4 as uuidv4 } from 'uuid'
import Papa from 'papaparse'
import * as XLSX from 'xlsx'
import { useAuthStore } from './authStore'
import { useNotificationStore } from './notificationStore'

// ===== TYPES =====

export type DocumentStatus = 'pending' | 'processing' | 'success' | 'failed'
export type PathType = 'url' | 's3' | 'local'
export type ExportFormat = 'csv' | 'excel' | 'json'

export interface ColumnDefinition {
  id: string              // UUID (stable)
  name: string            // User-editable display name
  originalName: string    // Original name from CSV
  systemColumn: boolean   // Is this a required system column?
  visible: boolean        // Show/hide in editor
  position: number        // Column order
  width?: number          // Column width
}

export interface DocumentRow {
  id: string              // Row unique ID
  rowNumber: number       // Original row number from CSV (1-indexed)
  data: Record<string, any>  // Column ID → value
  status: DocumentStatus
  tags?: string[]
  error?: string
  metadata?: {
    is_scanned?: boolean
    extraction_method?: string
    ocr_confidence?: number
    processing_time?: number
  }
}

export interface ExportPreset {
  id: string
  name: string
  selectedColumns: string[]           // Column IDs to export
  columnRenames: Record<string, string>  // Column ID → export name
  format: ExportFormat
}

export interface ValidationResult {
  path: string
  valid: boolean
  error?: string
}

export interface ProcessingSettings {
  numTags: number
  modelName: string
  numPages: number
  apiKey: string
  exclusionWords?: string[]
}

interface BatchState {
  // Data
  columns: ColumnDefinition[]
  documents: DocumentRow[]
  
  // Column mapping (system field -> column ID)
  columnMapping: Record<string, string | undefined>
  setColumnMapping: (mapping: Record<string, string | undefined>) => void
  
  // Export config
  exportPresets: ExportPreset[]
  selectedExportColumns: string[]  // Column IDs to include in export
  setSelectedExportColumns: (columnIds: string[]) => void
  
  // Processing
  jobId: string | null
  isProcessing: boolean
  progress: number
  processingSettings: ProcessingSettings
  
  // WebSocket
  websocket: WebSocket | null
  
  // Validation
  validationResults: Record<string, ValidationResult>
  isValidating: boolean
  
  // Column actions
  addColumn: (name: string, afterColumnId?: string) => void
  removeColumn: (columnId: string) => void
  renameColumn: (columnId: string, newName: string) => void
  reorderColumns: (columnIds: string[]) => void
  toggleColumnVisibility: (columnId: string) => void
  updateColumnWidth: (columnId: string, width: number) => void
  
  // Row actions
  updateRow: (rowId: string, updates: Partial<DocumentRow>) => void
  updateRowData: (rowId: string, columnId: string, value: any) => void
  bulkUpdateRows: (rowIds: string[], field: string, value: any) => void
  deleteRows: (rowIds: string[]) => void
  addRow: () => void
  
  // Import
  importCSV: (file: File) => Promise<void>
  
  // Column mapping
  getColumnMapping: () => Record<string, string>
  
  // Processing
  setProcessingSettings: (settings: Partial<ProcessingSettings>) => void
  startProcessing: () => Promise<void>
  stopProcessing: () => void
  updateProgress: (update: any) => void
  
  // Validation
  validatePaths: () => Promise<void>
  
  // Export
  saveExportPreset: (preset: Omit<ExportPreset, 'id'>) => void
  deleteExportPreset: (presetId: string) => void
  exportData: (preset: ExportPreset) => void
  exportAsCSV: (selectedColumnIds?: string[], filteredDocuments?: any[]) => string
  
  // Reset
  reset: () => void
}

// System column names that map to backend fields
const SYSTEM_COLUMN_NAMES = ['title', 'file_path', 'file_source_type', 'description']
const REQUIRED_COLUMNS = ['title', 'file_path', 'file_source_type']

// Helper function to detect error type from error message
function detectErrorType(errorMessage: string): 'rate-limit' | 'model-error' | 'network' | 'unknown' {
  const msg = errorMessage.toLowerCase()
  if (msg.includes('429') || msg.includes('too many requests') || msg.includes('rate')) {
    return 'rate-limit'
  } else if (msg.includes('400') || msg.includes('bad request') || msg.includes('developer instruction')) {
    return 'model-error'
  } else if (msg.includes('connection') || msg.includes('network') || msg.includes('timeout')) {
    return 'network'
  }
  return 'unknown'
}

// Initial processing settings
const initialProcessingSettings: ProcessingSettings = {
  numTags: 8,
  modelName: 'openai/gpt-4o-mini',
  numPages: 3,
  apiKey: '',
  exclusionWords: []
}

export const useBatchStore = create<BatchState>((set, get) => ({
  // Initial state
  columns: [],
  documents: [],
  columnMapping: {},
  exportPresets: [],
  selectedExportColumns: [],
  jobId: null,
  isProcessing: false,
  progress: 0,
  processingSettings: initialProcessingSettings,
  websocket: null,
  validationResults: {},
  isValidating: false,
  
  // Column mapping actions
  setColumnMapping: (mapping) => set({ columnMapping: mapping }),
  
  setSelectedExportColumns: (columnIds) => set({ selectedExportColumns: columnIds }),
  
  // ===== COLUMN ACTIONS =====
  
  addColumn: (name, afterColumnId) => {
    set((state) => {
      const newColumn: ColumnDefinition = {
        id: uuidv4(),
        name,
        originalName: name,
        systemColumn: false,
        visible: true,
        position: state.columns.length,
        width: 150
      }
      
      let newColumns: ColumnDefinition[]
      
      if (afterColumnId) {
        const afterIndex = state.columns.findIndex(c => c.id === afterColumnId)
        if (afterIndex >= 0) {
          newColumns = [
            ...state.columns.slice(0, afterIndex + 1),
            newColumn,
            ...state.columns.slice(afterIndex + 1)
          ]
        } else {
          newColumns = [...state.columns, newColumn]
        }
      } else {
        newColumns = [...state.columns, newColumn]
      }
      
      // Update positions
      newColumns = newColumns.map((col, idx) => ({ ...col, position: idx }))
      
      // Add empty value for this column in all documents
      const newDocuments = state.documents.map(doc => ({
        ...doc,
        data: { ...doc.data, [newColumn.id]: '' }
      }))
      
      return { columns: newColumns, documents: newDocuments }
    })
  },
  
  removeColumn: (columnId) => {
    const column = get().columns.find(c => c.id === columnId)
    
    if (column?.systemColumn) {
      console.warn('Cannot delete system columns')
      return
    }
    
    set((state) => {
      const newColumns = state.columns
        .filter(c => c.id !== columnId)
        .map((col, idx) => ({ ...col, position: idx }))
      
      const newDocuments = state.documents.map(doc => {
        const { [columnId]: _, ...restData } = doc.data
        return { ...doc, data: restData }
      })
      
      return { columns: newColumns, documents: newDocuments }
    })
  },
  
  renameColumn: (columnId, newName) => {
    set((state) => ({
      columns: state.columns.map(col =>
        col.id === columnId ? { ...col, name: newName } : col
      )
    }))
  },
  
  reorderColumns: (columnIds) => {
    set((state) => ({
      columns: columnIds.map((id, idx) => {
        const col = state.columns.find(c => c.id === id)
        return col ? { ...col, position: idx } : col
      }).filter(Boolean) as ColumnDefinition[]
    }))
  },
  
  toggleColumnVisibility: (columnId) => {
    set((state) => ({
      columns: state.columns.map(col =>
        col.id === columnId ? { ...col, visible: !col.visible } : col
      )
    }))
  },
  
  updateColumnWidth: (columnId, width) => {
    set((state) => ({
      columns: state.columns.map(col =>
        col.id === columnId ? { ...col, width } : col
      )
    }))
  },
  
  // ===== ROW ACTIONS =====
  
  updateRow: (rowId, updates) => {
    set((state) => ({
      documents: state.documents.map(doc =>
        doc.id === rowId ? { ...doc, ...updates } : doc
      )
    }))
  },
  
  updateRowData: (rowId, columnId, value) => {
    set((state) => ({
      documents: state.documents.map(doc =>
        doc.id === rowId
          ? { ...doc, data: { ...doc.data, [columnId]: value } }
          : doc
      )
    }))
  },
  
  bulkUpdateRows: (rowIds, field, value) => {
    set((state) => ({
      documents: state.documents.map(doc => {
        if (!rowIds.includes(doc.id)) return doc
        
        if (field === 'data') {
          return { ...doc, data: { ...doc.data, ...value } }
        }
        return { ...doc, [field]: value }
      })
    }))
  },
  
  deleteRows: (rowIds) => {
    set((state) => ({
      documents: state.documents
        .filter(doc => !rowIds.includes(doc.id))
        .map((doc, idx) => ({ ...doc, rowNumber: idx + 1 }))
    }))
  },
  
  addRow: () => {
    set((state) => {
      const newRow: DocumentRow = {
        id: uuidv4(),
        rowNumber: state.documents.length + 1,
        data: Object.fromEntries(state.columns.map(col => [col.id, ''])),
        status: 'pending'
      }
      
      return { documents: [...state.documents, newRow] }
    })
  },
  
  // ===== IMPORT =====
  
  importCSV: async (file) => {
    return new Promise((resolve, reject) => {
      const fileName = file.name.toLowerCase()
      const isExcel = fileName.endsWith('.xlsx') || fileName.endsWith('.xls')
      
      if (isExcel) {
        // Handle Excel files
        const reader = new FileReader()
        reader.onload = (e) => {
          try {
            const data = new Uint8Array(e.target?.result as ArrayBuffer)
            const workbook = XLSX.read(data, { type: 'array' })
            
            // Get first sheet
            const sheetName = workbook.SheetNames[0]
            if (!sheetName) {
              reject(new Error('No sheets found in Excel file'))
              return
            }
            
            const worksheet = workbook.Sheets[sheetName]
            const rows = XLSX.utils.sheet_to_json(worksheet, { 
              defval: '',  // Use empty string for empty cells
              blankrows: false 
            }) as Record<string, string>[]
            
            if (rows.length === 0) {
              reject(new Error('No data found in Excel sheet'))
              return
            }
            
            // Get headers from first row keys
            const headers = Object.keys(rows[0])
            
            if (headers.length === 0) {
              reject(new Error('No columns found in Excel file'))
              return
            }
            
            processData(headers, rows, 'Excel')
          } catch (err) {
            reject(err)
          }
        }
        reader.onerror = () => reject(new Error('Failed to read Excel file'))
        reader.readAsArrayBuffer(file)
      } else {
        // Handle CSV files with PapaParse
        Papa.parse(file, {
          header: true,
          skipEmptyLines: true,
          complete: (results) => {
            const headers = results.meta.fields || []
            
            if (headers.length === 0) {
              reject(new Error('No columns found in CSV'))
              return
            }
            
            processData(headers, results.data as Record<string, string>[], 'CSV')
          },
          error: (error) => {
            reject(new Error(`CSV parsing error: ${error.message}`))
          }
        })
      }
      
      // Common data processing for both CSV and Excel
      function processData(headers: string[], rows: Record<string, string>[], source: string) {
        try {
          // Create column definitions
          const columns: ColumnDefinition[] = headers.map((header, idx) => {
            const lowerHeader = header.toLowerCase().trim()
            const isSystemColumn = SYSTEM_COLUMN_NAMES.includes(lowerHeader)
            
            return {
              id: uuidv4(),
              name: header,
              originalName: header,
              systemColumn: isSystemColumn,
              visible: true,
              position: idx,
              width: isSystemColumn ? 200 : 150
            }
          })
          
          // Create document rows
          const documents: DocumentRow[] = rows.map((row, idx) => ({
            id: uuidv4(),
            rowNumber: idx + 1,
            data: Object.fromEntries(
              columns.map(col => [col.id, String(row[col.originalName] || '')])
            ),
            status: 'pending' as DocumentStatus
          }))
          
          // Auto-detect column mapping
          const autoMapping: Record<string, string> = {}
          for (const col of columns) {
            const lowerName = col.name.toLowerCase().trim()
            
            if (lowerName === 'title' || lowerName === 'document_title' || lowerName === 'doc_title' || lowerName === 'name') {
              autoMapping['title'] = col.id
            } else if (lowerName === 'file_path' || lowerName === 'filepath' || lowerName === 'path' || lowerName === 'url' || lowerName === 'pdf_link' || lowerName === 'link' || lowerName === 'pdf_url' || lowerName === 'document_url') {
              autoMapping['file_path'] = col.id
            } else if (lowerName === 'description' || lowerName === 'desc' || lowerName === 'summary') {
              autoMapping['description'] = col.id
            }
          }
          
          // Initialize selectedExportColumns with all column IDs
          const selectedExportColumns = columns.map(c => c.id)
          
          set({
            columns,
            documents,
            columnMapping: autoMapping,
            selectedExportColumns,
            progress: 0,
            isProcessing: false,
            validationResults: {}
          })
          
          console.log(`✅ Loaded ${documents.length} documents from ${source} file`)
          resolve()
        } catch (err) {
          reject(err)
        }
      }
    })
  },
  
  // ===== COLUMN MAPPING =====
  
  getColumnMapping: () => {
    const { columnMapping } = get()
    // Return the user-configured mapping (system field -> column ID)
    // We need to invert it for processing (column ID -> system field)
    const inverted: Record<string, string> = {}
    for (const [systemField, columnId] of Object.entries(columnMapping)) {
      if (columnId) {
        inverted[columnId] = systemField
      }
    }
    return inverted
  },
  
  // ===== PROCESSING =====
  
  setProcessingSettings: (settings) => {
    set((state) => ({
      processingSettings: { ...state.processingSettings, ...settings }
    }))
  },
  
  startProcessing: async () => {
    const { documents, columns, processingSettings, columnMapping: userColumnMapping } = get()
    
    if (!processingSettings.apiKey) {
      throw new Error('API key is required')
    }
    
    if (documents.length === 0) {
      throw new Error('No documents to process')
    }
    
    // Validate that file_path is mapped
    if (!userColumnMapping['file_path']) {
      throw new Error('Please map the "PDF File Path/URL" column before processing')
    }
    
    const jobId = uuidv4()
    set({ jobId, isProcessing: true, progress: 0 })
    
    // Reset document statuses
    set((state) => ({
      documents: state.documents.map(doc => ({
        ...doc,
        status: 'pending' as DocumentStatus,
        tags: undefined,
        error: undefined
      }))
    }))
    
    // Prepare documents data using the column mapping
    const documentsData = documents.map(doc => {
      const rowData: Record<string, any> = {
        id: doc.id,
        row_number: doc.rowNumber
      }
      
      // Map user columns to system fields
      for (const [systemField, columnId] of Object.entries(userColumnMapping)) {
        if (columnId && doc.data[columnId] !== undefined) {
          rowData[systemField] = doc.data[columnId]
        }
      }
      
      // If no file_source_type is mapped, try to auto-detect from file_path
      if (!rowData['file_source_type'] && rowData['file_path']) {
        const path = rowData['file_path'].toLowerCase()
        if (path.startsWith('http://') || path.startsWith('https://')) {
          rowData['file_source_type'] = 'url'
        } else if (path.startsWith('s3://')) {
          rowData['file_source_type'] = 's3'
        } else {
          rowData['file_source_type'] = 'local'
        }
      }
      
      return rowData
    })
    
    // Determine WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = process.env.NEXT_PUBLIC_API_URL 
      ? new URL(process.env.NEXT_PUBLIC_API_URL).host 
      : 'localhost:8000'
    
    // Get authentication token if available
    const authStore = useAuthStore.getState()
    const token = authStore.getAccessToken()
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
    const wsUrl = `${wsProtocol}//${wsHost}/api/batch/ws/${jobId}${tokenParam}`
    
    try {
      const ws = new WebSocket(wsUrl)
      set({ websocket: ws })
      
      ws.onopen = () => {
        console.log('WebSocket connected, sending documents...')
        
        // Send the batch start request
        ws.send(JSON.stringify({
          documents: documentsData,
          config: {
            api_key: processingSettings.apiKey,
            model_name: processingSettings.modelName,
            num_pages: processingSettings.numPages,
            num_tags: processingSettings.numTags,
            exclusion_words: processingSettings.exclusionWords
          }
        }))
      }
      
      ws.onmessage = (event) => {
        const update = JSON.parse(event.data)
        get().updateProgress(update)
      }
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        set({ isProcessing: false })
      }
      
      ws.onclose = () => {
        console.log('WebSocket closed')
        set({ websocket: null, isProcessing: false })
      }
      
    } catch (error) {
      console.error('Failed to connect WebSocket:', error)
      set({ isProcessing: false })
      throw error
    }
  },
  
  stopProcessing: () => {
    const { websocket, jobId } = get()
    
    console.log('Stopping processing...', { websocket: !!websocket, jobId })
    
    if (websocket) {
      // Close WebSocket with explicit close code to signal cancellation
      try {
        websocket.close(1000, 'User requested cancellation')
      } catch (e) {
        console.error('Error closing WebSocket:', e)
      }
    }
    
    // Immediately update state to reflect stopping
    set({ isProcessing: false, websocket: null })
    
    // Also try to cancel on backend via API if jobId exists
    if (jobId) {
      console.log('Job ID exists, attempting backend cancellation for', jobId)
      // Note: The WebSocket close should be enough, but we log for debugging
    }
  },
  
  updateProgress: (update) => {
    // Handle different message types
    if (update.type === 'started') {
      console.log('Batch processing started:', update.message)
      return
    }
    
    if (update.type === 'completed') {
      console.log('Batch processing completed:', update.message)
      set({ isProcessing: false, progress: 1 })
      return
    }
    
    if (update.error && !update.row_id && update.row_id !== 0) {
      console.error('Batch error:', update.error)
      
      // Use error_type if available, otherwise detect from error message
      const errorType = update.error_type || detectErrorType(update.error)
      
      // Emit appropriate notification based on error type
      switch (errorType) {
        case 'rate-limit':
          useNotificationStore.getState().addRateLimitError(
            update.retry_after_ms || 2000,
            update.retry_count || 1
          )
          break
        case 'model-error':
          useNotificationStore.getState().addModelError(
            update.model_name || 'Unknown',
            update.error
          )
          break
        case 'network':
          useNotificationStore.getState().addNetworkError(update.error)
          break
        default:
          useNotificationStore.getState().addNotification({
            type: 'unknown',
            title: '❌ Processing Error',
            message: update.error,
            autoClose: 0 // Manual close for critical errors
          })
      }
      
      set({ isProcessing: false })
      return
    }
    
    // Handle progress update
    const rowNumber = update.row_number || update.row_id + 1
    
    set((state) => ({
      progress: update.progress || 0,
      documents: state.documents.map(doc => {
        if (doc.rowNumber === rowNumber) {
          return {
            ...doc,
            status: update.status as DocumentStatus,
            tags: update.tags,
            error: update.error,
            metadata: update.metadata
          }
        }
        return doc
      })
    }))
  },
  
  // ===== VALIDATION =====
  
  validatePaths: async () => {
    const { documents, columns, getColumnMapping } = get()
    
    set({ isValidating: true })
    
    try {
      const columnMapping = getColumnMapping()
      
      // Find file_path and file_source_type column IDs
      const pathColumnId = Object.entries(columnMapping).find(([_, v]) => v === 'file_path')?.[0]
      const typeColumnId = Object.entries(columnMapping).find(([_, v]) => v === 'file_source_type')?.[0]
      
      if (!pathColumnId) {
        console.warn('No file_path column found')
        set({ isValidating: false })
        throw new Error('No file_path column mapped. Please map your file path column first.')
      }
      
      // Prepare paths for validation
      const paths = documents.map(doc => ({
        path: doc.data[pathColumnId] || '',
        type: typeColumnId ? (doc.data[typeColumnId] || 'url').toLowerCase() : 'url'
      }))
      
      if (paths.length === 0) {
        set({ isValidating: false })
        throw new Error('No paths to validate. Please load documents first.')
      }
      
      console.log(`Validating ${paths.length} paths via /api/batch/validate-paths`)
      
      // Get auth token
      const token = useAuthStore.getState().getAccessToken()
      if (!token) {
        set({ isValidating: false })
        throw new Error('Please log in to validate paths')
      }
      
      // Call validation API with timeout
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 120000) // 2 minute timeout
      
      try {
        const response = await fetch(`${apiUrl}/api/batch/validate-paths`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ paths }),
          signal: controller.signal
        })
        
        clearTimeout(timeoutId)
        
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || errorData.message || `Validation failed: ${response.statusText}`)
        }
        
        const data = await response.json()
        console.log(`Validation complete: ${data.valid_count} valid, ${data.invalid_count} invalid`)
        
        // Store results indexed by path
        const validationResults: Record<string, ValidationResult> = {}
        for (const result of data.results) {
          validationResults[result.path] = result
        }
        
        set({ validationResults, isValidating: false })
      } catch (fetchError: any) {
        clearTimeout(timeoutId)
        if (fetchError.name === 'AbortError') {
          throw new Error('Validation timeout. Too many paths to validate. Try validating a smaller batch or check your network connection.')
        }
        throw fetchError
      }
      
    } catch (error) {
      console.error('Validation error:', error)
      set({ isValidating: false })
      throw error // Re-throw so the UI can show the error
    }
  },
  
  // ===== EXPORT =====
  
  saveExportPreset: (preset) => {
    set((state) => ({
      exportPresets: [
        ...state.exportPresets,
        { ...preset, id: uuidv4() }
      ]
    }))
  },
  
  deleteExportPreset: (presetId) => {
    set((state) => ({
      exportPresets: state.exportPresets.filter(p => p.id !== presetId)
    }))
  },
  
  exportData: (preset) => {
    const { columns, documents } = get()
    
    // Get selected columns in order
    const selectedColumns = preset.selectedColumns
      .map(id => columns.find(c => c.id === id))
      .filter(Boolean) as ColumnDefinition[]
    
    // Build export data
    const exportRows = documents.map(doc => {
      const row: Record<string, any> = {}
      
      for (const col of selectedColumns) {
        const exportName = preset.columnRenames[col.id] || col.name
        row[exportName] = doc.data[col.id] || ''
      }
      
      // Add tags if present
      if (doc.tags && doc.tags.length > 0) {
        const tagsExportName = preset.columnRenames['_tags'] || 'Generated Tags'
        row[tagsExportName] = doc.tags.join(', ')
      }
      
      return row
    })
    
    // Generate CSV
    const csv = Papa.unparse(exportRows)
    
    // Download
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `export_${new Date().toISOString().split('T')[0]}.csv`
    link.click()
  },
  
  exportAsCSV: (selectedColumnIds?: string[], filteredDocuments?: any[]) => {
    const { columns, documents } = get()
    
    // Use filtered documents if provided, otherwise use all
    const docsToExport = filteredDocuments || documents
    
    // Determine which columns to export
    const columnsToExport = selectedColumnIds && selectedColumnIds.length > 0
      ? columns.filter(col => selectedColumnIds.includes(col.id))
      : columns  // Export all if none specified
    
    // Build export data with selected columns + tags
    const exportRows = docsToExport.map(doc => {
      const row: Record<string, any> = {}
      
      // Add selected columns
      for (const col of columnsToExport) {
        row[col.name] = doc.data[col.id] || ''
      }
      
      // Always add tags and status
      row['Generated Tags'] = doc.tags?.join(', ') || ''
      row['Processing Status'] = doc.status
      row['Error'] = doc.error || ''
      
      return row
    })
    
    return Papa.unparse(exportRows)
  },
  
  // ===== RESET =====
  
  reset: () => {
    const { websocket } = get()
    if (websocket) {
      websocket.close()
    }
    
    set({
      columns: [],
      documents: [],
      jobId: null,
      isProcessing: false,
      progress: 0,
      websocket: null,
      validationResults: {}
    })
  }
}))

