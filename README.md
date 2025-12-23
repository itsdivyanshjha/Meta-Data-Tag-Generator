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
Processes a single PDF file and generates tags with optional exclusion list filtering.

**Request:**
- Content-Type: `multipart/form-data`
- Fields:
  - `pdf_file`: PDF file (File, optional - required if `pdf_url` not provided)
  - `pdf_url`: URL to PDF file (String, optional - required if `pdf_file` not provided)
    - Supports any publicly accessible HTTP/HTTPS URL
    - Examples: CloudFront URLs, S3 URLs, direct file links
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
  "extraction_method": "pypdf2" | "tesseract_ocr",
  "ocr_confidence": 0.0,
  "raw_ai_response": "string",
  "error": null
}
```

### POST `/api/batch/process`
Processes a CSV file containing multiple documents with optional exclusion list filtering.

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
    - Contains words/phrases to exclude from generated tags
    - Format: One term per line or comma-separated
    - Comments: Lines starting with `#` are ignored

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
- **OCR**: Tesseract OCR with `pytesseract`, `pdf2image`, `Pillow`
- **AI Client**: OpenAI Python SDK (configured for OpenRouter)
- **Exclusion Parsing**: Custom parser supporting `.txt` and `.pdf` formats
