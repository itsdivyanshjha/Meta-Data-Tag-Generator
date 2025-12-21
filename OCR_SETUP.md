# OCR Support Setup Guide

## Overview
Your document tagging system now has **automatic OCR support** for scanned government PDFs. The system intelligently detects if a PDF is scanned and automatically uses Tesseract OCR with Hindi + English language support.

## Features Implemented

### Backend (FastAPI)
✅ **Hybrid PDF Extraction**
- Primary: PyPDF2 for text-based PDFs (fast)
- Fallback: Tesseract OCR for scanned PDFs (accurate)
- Auto-detection: Determines if PDF is scanned based on text extraction results

✅ **OCR Metadata**
- `is_scanned`: Boolean indicating if document is scanned
- `extraction_method`: "pypdf2", "tesseract_ocr", or "ocr_failed"
- `ocr_confidence`: Percentage confidence score (0-100) for OCR results

✅ **Multi-language Support**
- Default: English + Hindi (eng+hin)
- Extensible to other languages

### Frontend (Next.js)
✅ **OCR Status Badge**
- 📄 Text PDF (blue badge)
- 📷 Scanned PDF with confidence score (purple badge)

✅ **Extraction Method Display**
- Shows which method was used to extract text

## Installation

### 1. Install Python OCR Dependencies

```bash
cd /Users/divyanshjha/Developer/Meta-Data-Tag-Generator/backend

# Activate virtual environment
source venv/bin/activate

# Install new dependencies
pip install pytesseract pdf2image Pillow
```

### 2. Install Tesseract OCR Engine

**On macOS:**
```bash
brew install tesseract tesseract-lang
```

**On Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-hin tesseract-ocr-eng
sudo apt-get install poppler-utils  # For pdf2image
```

**On Windows:**
1. Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install to: `C:\Program Files\Tesseract-OCR`
3. Add to PATH: `C:\Program Files\Tesseract-OCR`

### 3. Verify Installation

```bash
# Check Tesseract version
tesseract --version

# Check installed languages
tesseract --list-langs
# Should show: eng, hin
```

### 4. Restart Backend Server

```bash
cd /Users/divyanshjha/Developer/Meta-Data-Tag-Generator/backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## How It Works

### Automatic Detection Flow

1. **PDF Upload** → System tries PyPDF2 first
2. **Text Check** → If < 50 chars/page extracted → Considered "scanned"
3. **OCR Fallback** → Automatically converts PDF to images and runs Tesseract
4. **Result** → Returns extracted text + OCR metadata

### Example Response

**Text-based PDF:**
```json
{
  "success": true,
  "document_title": "Annual Report 2023",
  "tags": ["annual report", "government", "2023"],
  "is_scanned": false,
  "extraction_method": "pypdf2",
  "ocr_confidence": null
}
```

**Scanned PDF:**
```json
{
  "success": true,
  "document_title": "स्वास्थ्य रिपोर्ट 2023",
  "tags": ["health report", "ministry", "2023"],
  "is_scanned": true,
  "extraction_method": "tesseract_ocr",
  "ocr_confidence": 87.5
}
```

## Testing

### Test with Sample PDFs

**Text PDF:**
```bash
curl -X POST "http://localhost:8000/api/single/process" \
  -F "pdf_file=@text_document.pdf" \
  -F 'config={"api_key":"YOUR_KEY","model_name":"google/gemini-flash-1.5","num_pages":3,"num_tags":8}'
```

**Scanned PDF:**
```bash
curl -X POST "http://localhost:8000/api/single/process" \
  -F "pdf_file=@scanned_document.pdf" \
  -F 'config={"api_key":"YOUR_KEY","model_name":"google/gemini-flash-1.5","num_pages":3,"num_tags":8}'
```

## Configuration

### Adjust OCR Sensitivity

Edit `backend/app/services/pdf_extractor.py`:

```python
# Increase threshold = more likely to use OCR
SCANNED_THRESHOLD_CHARS_PER_PAGE = 100  # Default: 50

# Change OCR languages
ocr_languages: str = "eng+hin+pan"  # Add Punjabi
```

### OCR Quality vs Speed

Edit `_extract_with_ocr()` method:

```python
# Higher DPI = Better quality, slower
images = convert_from_bytes(pdf_bytes, dpi=300)  # Default: 200
```

## Troubleshooting

### Error: "tesseract is not installed"
```bash
# Install Tesseract
brew install tesseract  # macOS
sudo apt-get install tesseract-ocr  # Linux
```

### Error: "Language 'hin' not found"
```bash
# Install Hindi language data
brew install tesseract-lang  # macOS
sudo apt-get install tesseract-ocr-hin  # Linux
```

### OCR is too slow
- Reduce `num_pages` in config (extract fewer pages)
- Lower DPI from 200 to 150
- Use faster model like `google/gemini-flash-1.5`

### Low OCR confidence
- Try higher DPI (250-300)
- Ensure PDF is high-resolution
- Check if document has poor scan quality

## Performance Notes

**PyPDF2 (Text PDF):**
- Speed: ~0.5-2 seconds
- Accuracy: 100% (native text)

**Tesseract OCR (Scanned PDF):**
- Speed: ~5-15 seconds per page
- Accuracy: 75-95% (depends on scan quality)
- Languages: Hindi + English supported

## API Documentation

Full interactive API docs available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Support

For issues or questions:
1. Check logs: Backend terminal shows detailed OCR info
2. Verify Tesseract: `tesseract --version`
3. Test languages: `tesseract --list-langs`
