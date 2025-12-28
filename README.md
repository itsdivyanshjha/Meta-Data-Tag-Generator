# Meta-Data-Tag-Generator

Document metadata tagging system using AI and OCR.

## External APIs Used

### OpenRouter API
- **Endpoint**: `https://openrouter.ai/api/v1/chat/completions`
- **Method**: POST
- **Purpose**: AI tag generation from extracted document text
- **Request**: Chat completions format with document content
- **Response**: Generated tags in text format
- **Authentication**: OpenRouter API key (required, user-provided)
- **Model**: Configurable via request (e.g., `google/gemini-flash-1.5`, `openai/gpt-4o-mini`)

### Tesseract OCR
- **Type**: Local OCR engine (CLI tool)
- **Purpose**: Text extraction from scanned PDF images (fast path)
- **Languages**: Hindi (`hin`) and English (`eng`)
- **Usage**: Converts PDF pages to images, performs OCR, returns Unicode text
- **Strengths**: Fast, lightweight, good for Hindi/English documents

### EasyOCR
- **Type**: Deep learning OCR engine (Python library)
- **Purpose**: Advanced text extraction for complex Indian languages (high accuracy)
- **Languages**: 80+ languages including Hindi, Tamil, Telugu, Bengali, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and more
- **Model**: CNN + LSTM neural networks
- **Usage**: Automatic fallback when Tesseract confidence is low (<60%)
- **Strengths**: Superior accuracy for complex scripts, handles ligatures, better on low-quality scans

### AWS S3 (Optional)
- **Library**: `boto3`
- **Purpose**: Download PDF files from S3 buckets (batch processing only)
- **Authentication**: AWS access key ID and secret access key (optional, required only for S3 sources)

### HTTP Requests
- **Library**: `requests`
- **Purpose**: Download PDF files from HTTP/HTTPS URLs (batch processing only)

## Backend API Endpoints

Base URL: `http://localhost:8000` (development)  
All endpoints are prefixed with `/api` except the root endpoint.

---

### 1. GET `/`
**Purpose:** Root endpoint to verify API availability and version.

**Where it's used:** Not directly used by frontend, but useful for API testing and health checks.

**Response:**
```json
{
  "message": "Document Meta-Tagging API",
  "version": "1.0.0"
}
```

---

### 2. POST `/api/single/process`
**Purpose:** Processes a single PDF file and generates AI-powered metadata tags. Supports both file uploads and URL-based document retrieval.

**Where it's used:** 
- Frontend Component: `frontend/components/SingleUpload.tsx`
- Frontend API Client: `frontend/lib/api.ts` → `processSinglePDF()`
- Use Case: Single document processing on the main page (`/`)

**Request:**
- Content-Type: `multipart/form-data`
- Fields:
  - `pdf_file`: PDF file (File, optional - required if `pdf_url` not provided)
  - `pdf_url`: URL to PDF file (String, optional - required if `pdf_file` not provided)
    - Supports any publicly accessible HTTP/HTTPS URL
    - Examples: CloudFront URLs, S3 URLs, direct file links, government portals
  - `config`: JSON string with `TaggingConfig` (required)
    ```json
    {
      "api_key": "string",
      "model_name": "string",
      "num_pages": 3,
      "num_tags": 8,
      "exclusion_words": ["word1", "word2"]  // Optional
    }
    ```
  - `exclusion_file`: Exclusion list file (File, optional)
    - Supported formats: `.txt`, `.pdf`
    - Contains words/phrases to exclude from generated tags
    - Format: One term per line or comma-separated
    - Comments: Lines starting with `#` are ignored

**Note:** Provide either `pdf_file` OR `pdf_url`, not both.

**Response:**
```json
{
  "success": true,
  "document_title": "string",
  "tags": ["tag1", "tag2", ...],
  "extracted_text_preview": "string",
  "processing_time": 0.0,
  "is_scanned": false,
  "extraction_method": "pypdf2" | "tesseract_ocr" | "easyocr",
  "ocr_confidence": 0.0,
  "raw_ai_response": "string",
  "error": null
}
```

**Backend Implementation:** `backend/app/routers/single.py`

---

### 3. GET `/api/single/preview`
**Purpose:** Proxy endpoint to fetch and serve PDF files from URLs, bypassing CORS restrictions for frontend preview functionality.

**Where it's used:**
- Frontend Component: `frontend/components/SingleUpload.tsx` (PDF preview iframe)
- Frontend API Client: `frontend/lib/api.ts` → `getPdfPreviewUrl()`
- Use Case: Enables PDF preview in browser when processing documents via URL

**Request:**
- Query Parameters:
  - `url`: URL of the PDF to preview (required, must be HTTP/HTTPS)

**Response:**
- Content-Type: `application/pdf`
- Returns: PDF file bytes with appropriate headers for iframe embedding

**Backend Implementation:** `backend/app/routers/single.py`

---

### 4. POST `/api/batch/process`
**Purpose:** Legacy synchronous batch processing endpoint. Processes a CSV file containing multiple documents and returns results after completion. **Note:** This is the legacy endpoint. For real-time progress updates, use the WebSocket endpoint instead.

**Where it's used:**
- Frontend API Client: `frontend/lib/api.ts` → `processBatchCSV()`
- Use Case: Simple batch processing without real-time updates (currently not actively used in favor of WebSocket endpoint)

**Request:**
- Content-Type: `multipart/form-data`
- Fields:
  - `csv_file`: CSV file (File, required)
  - `config`: JSON string with `TaggingConfig` (required)
    ```json
    {
      "api_key": "string",
      "model_name": "string",
      "num_pages": 3,
      "num_tags": 8,
      "exclusion_words": ["word1", "word2"]  // Optional
    }
    ```
  - `exclusion_file`: Exclusion list file (File, optional)
    - Supported formats: `.txt`, `.pdf`

**CSV Format:**
- Required columns: `title`, `file_source_type`, `file_path`
- Optional columns: `description`, `publishing_date`, `file_size`
- `file_source_type`: `"url"` | `"s3"` | `"local"`

**Response:**
```json
{
  "success": true,
  "total_documents": 0,
  "processed_count": 0,
  "failed_count": 0,
  "output_csv_url": "string",
  "summary_report": {
    "documents": [...],
    "errors": [...]
  },
  "processing_time": 0.0
}
```

**Backend Implementation:** `backend/app/routers/batch.py`

---

### 5. WebSocket `/api/batch/ws/{job_id}`
**Purpose:** Real-time batch processing via WebSocket connection. Provides live progress updates as documents are processed, enabling interactive UI feedback.

**Where it's used:**
- Frontend Store: `frontend/lib/batchStore.ts` → `startProcessing()`
- Frontend Component: `frontend/components/batch/ProcessingControls.tsx`
- Use Case: Batch processing page (`/batch`) with real-time progress tracking

**Connection Flow:**
1. Client connects to WebSocket with a unique `job_id` in the URL
2. Client sends batch start request:
```json
{
  "documents": [
    {
      "title": "Document 1",
      "file_path": "https://example.com/doc.pdf",
      "file_source_type": "url",
      "description": "...",
      ...
    }
  ],
  "config": {
    "api_key": "...",
    "model_name": "...",
    "num_pages": 3,
    "num_tags": 8,
    "exclusion_words": [...]
  },
  "column_mapping": {
    "title": "column_1",
    "file_path": "column_2",
    ...
  }
}
```
3. Server sends progress updates for each document:
```json
{
  "job_id": "...",
  "row_id": "uuid",
  "row_number": 1,
  "title": "Document 1",
  "status": "processing" | "success" | "failed",
  "progress": 0.5,
  "tags": ["tag1", "tag2"],
  "error": null,
  "metadata": {
    "extraction_method": "pypdf2",
    "is_scanned": false,
    ...
  }
}
```
4. Server sends completion message:
```json
{
  "type": "completed",
  "job_id": "...",
  "total_documents": 10,
  "processed_count": 9,
  "failed_count": 1,
  "processing_time": 45.2,
  "message": "Completed: 9 succeeded, 1 failed"
}
```

**Message Types:**
- `started`: Job initialization confirmation
- `progress`: Individual document processing update
- `completed`: Batch processing finished
- `error`: Error occurred during processing

**Backend Implementation:** `backend/app/routers/batch.py` → `batch_progress_websocket()`

---

### 6. POST `/api/batch/validate-paths`
**Purpose:** Pre-flight validation endpoint that checks file paths before batch processing. Validates accessibility of URLs, S3 objects, and local files to catch errors early.

**Where it's used:**
- Frontend Store: `frontend/lib/batchStore.ts` → `validatePaths()`
- Frontend Component: `frontend/components/batch/ProcessingControls.tsx` (Pre-flight Check section)
- Use Case: Batch processing page - validates all file paths before starting processing

**Request:**
- Content-Type: `application/json`
- Body:
```json
{
  "paths": [
    {
      "path": "https://example.com/doc.pdf",
      "type": "url"
    },
    {
      "path": "s3://bucket/key.pdf",
      "type": "s3"
    },
    {
      "path": "/path/to/file.pdf",
      "type": "local"
    }
  ]
}
```

**Response:**
```json
{
  "results": [
    {
      "path": "https://example.com/doc.pdf",
      "valid": true,
      "error": null,
      "content_type": "application/pdf",
      "size": 1024000
    },
    {
      "path": "s3://bucket/missing.pdf",
      "valid": false,
      "error": "Object not found",
      "content_type": null,
      "size": null
    }
  ],
  "total": 2,
  "valid_count": 1,
  "invalid_count": 1
}
```

**Validation Methods:**
- **URL**: HTTP HEAD request (falls back to GET if HEAD not allowed)
- **S3**: AWS SDK `head_object()` check (if S3 configured)
- **Local**: File system existence check

**Backend Implementation:** `backend/app/routers/batch.py` → `validate_paths()`

---

### 7. GET `/api/batch/template`
**Purpose:** Returns a CSV template with sample data and column descriptions for batch processing. Helps users understand the required CSV format.

**Where it's used:**
- Frontend API Client: `frontend/lib/api.ts` → `getCSVTemplate()`
- Frontend Component: `frontend/components/batch/FileUploader.tsx` (template download feature)
- Use Case: Batch processing page - provides downloadable CSV template

**Response:**
```json
{
  "template": "title,description,file_source_type,file_path,publishing_date,file_size\n\"Training Manual\",\"PMSPECIAL training document\",url,https://example.com/doc1.pdf,2025-01-15,1.2MB\n...",
  "columns": [
    {
      "name": "title",
      "required": true,
      "description": "Document title"
    },
    {
      "name": "description",
      "required": false,
      "description": "Document description"
    },
    {
      "name": "file_source_type",
      "required": true,
      "description": "Source type: url, s3, or local"
    },
    {
      "name": "file_path",
      "required": true,
      "description": "Path or URL to the file"
    },
    {
      "name": "publishing_date",
      "required": false,
      "description": "Publication date"
    },
    {
      "name": "file_size",
      "required": false,
      "description": "File size"
    }
  ],
  "note": "For real-time processing with progress updates, use the WebSocket endpoint at /api/batch/ws/{job_id}"
}
```

**Backend Implementation:** `backend/app/routers/batch.py`

---

### 8. GET `/api/health`
**Purpose:** Comprehensive health check endpoint for monitoring and deployment verification.

**Where it's used:**
- Frontend API Client: `frontend/lib/api.ts` → `checkHealth()`
- Use Case: Health monitoring, deployment checks, API status verification

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "message": "Document Meta-Tagging API is running"
}
```

**Backend Implementation:** `backend/app/routers/status.py`

---

### 9. GET `/api/status`
**Purpose:** Simple status check endpoint for quick API availability verification.

**Where it's used:** Not directly used by frontend, but useful for basic health checks.

**Response:**
```json
{
  "status": "ok",
  "service": "document-meta-tagging-api"
}
```

**Backend Implementation:** `backend/app/routers/status.py`

---

## API Usage Summary by Frontend Page

### Main Page (`/`) - Single Document Processing
- **POST `/api/single/process`**: Process single PDF (file upload or URL)
- **GET `/api/single/preview`**: Preview PDF from URL

### Batch Processing Page (`/batch`) - Multiple Document Processing
- **WebSocket `/api/batch/ws/{job_id}`**: Real-time batch processing with live updates
- **POST `/api/batch/validate-paths`**: Pre-flight path validation
- **GET `/api/batch/template`**: Download CSV template
- **POST `/api/batch/process`**: Legacy synchronous batch processing (fallback)

### Global
- **GET `/api/health`**: Health check for monitoring

## Features

### URL-Based Document Processing
The system supports processing PDFs from URLs in addition to file uploads. This is useful for:
- Processing documents from public websites
- Handling CloudFront/S3 URLs
- Batch processing without downloading files first
- Integration with external document management systems

**Supported URL types:**
- Direct PDF URLs: `https://example.com/document.pdf`
- CloudFront URLs: `https://d1581jr3fp95xu.cloudfront.net/path/to/file.pdf`
- S3 public URLs: `https://bucket.s3.region.amazonaws.com/file.pdf`
- Government/institutional sites: `https://socialjustice.gov.in/writereaddata/UploadFile/66991763713697.pdf`

**How it works:**
- User provides a URL instead of uploading a file
- Backend downloads the PDF (60-second timeout, 50MB limit)
- PDF is processed the same way as uploaded files
- Preview works directly with the URL (if CORS allows)

### Exclusion List Filtering
The system supports exclusion lists to filter out common/generic terms that appear repeatedly across documents. This improves ElasticSearch searchability by ensuring tags are specific and unique to each document.

**How it works:**
- Upload a `.txt` or `.pdf` file containing exclusion terms
- Terms can be listed one per line or comma-separated
- Comments (lines starting with `#`) are ignored
- The system uses a two-layer approach:
  1. **Pre-generation**: AI is instructed to avoid excluded terms
  2. **Post-processing**: Any excluded terms that slip through are filtered out
- **Guaranteed tag count**: If you request 5 tags and 2 get filtered, you still get 5 tags (system requests extra tags from AI to compensate)

**Example exclusion list (`exclusion-list.txt`):**
```
# Common government organizations
government-india
ministry-of-social-justice
social-justice

# Generic document types
annual-report
newsletter
policy-document

# Overly generic terms
empowerment
constitutional-provisions
```

## Technical Stack

- **Backend Framework**: FastAPI (Python 3.8+)
- **Frontend Framework**: Next.js (TypeScript)
- **PDF Text Extraction**: PyPDF2 (text-based PDFs)
- **OCR Primary**: Tesseract OCR with `pytesseract`, `pdf2image`, `Pillow` (fast, Hindi+English)
- **OCR Enhanced**: EasyOCR with PyTorch (accurate, 80+ languages including all Indian languages)
- **AI Client**: OpenAI Python SDK (configured for OpenRouter)
- **Exclusion Parsing**: Custom parser supporting `.txt` and `.pdf` formats

### Hybrid OCR Approach

The system uses a smart 3-tier extraction strategy:

1. **PyPDF2** (fastest): Tries text-based extraction first
2. **Tesseract OCR** (fast): Fallback for scanned documents, good for Hindi/English
3. **EasyOCR** (most accurate): Automatic fallback if:
   - Tesseract confidence < 60%
   - Complex Indian scripts detected
   - Better extraction quality needed

This ensures optimal speed and accuracy for all document types.
