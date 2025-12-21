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
- **Purpose**: Text extraction from scanned PDF images
- **Languages**: Hindi (`hin`) and English (`eng`)
- **Usage**: Converts PDF pages to images, performs OCR, returns Unicode text

### AWS S3 (Optional)
- **Library**: `boto3`
- **Purpose**: Download PDF files from S3 buckets (batch processing only)
- **Authentication**: AWS access key ID and secret access key (optional, required only for S3 sources)

### HTTP Requests
- **Library**: `requests`
- **Purpose**: Download PDF files from HTTP/HTTPS URLs (batch processing only)

## Backend API Endpoints

Base URL: `http://localhost:8000` (development)

### GET `/`
Returns API information.
**Response:**
```json
{
  "message": "Document Meta-Tagging API",
  "version": "1.0.0"
}
```

### POST `/api/single/process`
Processes a single PDF file and generates tags.

**Request:**
- Content-Type: `multipart/form-data`
- Fields:
  - `pdf_file`: PDF file (File)
  - `config`: JSON string with `TaggingConfig`
    ```json
    {
      "api_key": "string",
      "model_name": "string",
      "num_pages": 3,
      "num_tags": 8
    }
    ```

**Response:**
```json
{
  "success": true,
  "document_title": "string",
  "tags": ["tag1", "tag2", ...],
  "extracted_text_preview": "string",
  "processing_time": 0.0,
  "is_scanned": false,
  "extraction_method": "pypdf2" | "tesseract_ocr",
  "ocr_confidence": 0.0,
  "raw_ai_response": "string",
  "error": null
}
```

### POST `/api/batch/process`
Processes a CSV file containing multiple documents.

**Request:**
- Content-Type: `multipart/form-data`
- Fields:
  - `csv_file`: CSV file (File)
  - `config`: JSON string with `TaggingConfig`

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
  "summary": {
    "documents": [...],
    "errors": [...]
  }
}
```

### GET `/api/batch/template`
Returns CSV template and column descriptions.

**Response:**
```json
{
  "template": "CSV string",
  "columns": [
    {
      "name": "title",
      "required": true,
      "description": "Document title"
    },
    ...
  ]
}
```

### GET `/api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "message": "Document Meta-Tagging API is running"
}
```

### GET `/api/status`
Simple status check.

**Response:**
```json
{
  "status": "ok",
  "service": "document-meta-tagging-api"
}
```

## Technical Stack

- **Backend Framework**: FastAPI (Python 3.8+)
- **Frontend Framework**: Next.js (TypeScript)
- **PDF Text Extraction**: PyPDF2 (text-based PDFs)
- **OCR**: Tesseract OCR with `pytesseract`, `pdf2image`, `Pillow`
- **AI Client**: OpenAI Python SDK (configured for OpenRouter)
