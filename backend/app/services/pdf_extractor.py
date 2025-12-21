import PyPDF2
from io import BytesIO
from typing import Dict, Any, Optional
import re
import logging

# OCR imports with graceful fallback
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)


class PDFExtractor:
    """
    Hybrid PDF text extractor with automatic OCR fallback for scanned documents
    
    Features:
    - Primary: PyPDF2 for text-based PDFs (fast)
    - Fallback: Tesseract OCR for scanned PDFs (slower but handles images)
    - Auto-detection: Determines if PDF is scanned based on text extraction results
    - Multi-language: Supports English and Hindi
    """
    
    # Threshold: if we extract less than this many chars per page, consider it scanned
    SCANNED_THRESHOLD_CHARS_PER_PAGE = 50
    
    @staticmethod
    def extract_text(
        pdf_bytes: bytes, 
        num_pages: int = 3,
        ocr_languages: str = "eng+hin"  # English + Hindi
    ) -> Dict[str, Any]:
        """
        Extract text from PDF with automatic OCR fallback
        
        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract (default 3)
            ocr_languages: Tesseract language codes (default: eng+hin)
            
        Returns:
            dict with extracted_text, page_count, title, and OCR metadata
        """
        try:
            # Step 1: Try PyPDF2 first (fast path)
            pypdf_result = PDFExtractor._extract_with_pypdf(pdf_bytes, num_pages)
            
            if not pypdf_result["success"]:
                return pypdf_result
            
            # Step 2: Check if we got enough text (detect if scanned)
            text_length = len(pypdf_result["extracted_text"].strip())
            pages_extracted = pypdf_result["pages_extracted"]
            avg_chars_per_page = text_length / pages_extracted if pages_extracted > 0 else 0
            
            is_scanned = avg_chars_per_page < PDFExtractor.SCANNED_THRESHOLD_CHARS_PER_PAGE
            
            logger.info(f"PyPDF2 extracted {text_length} chars from {pages_extracted} pages "
                       f"(avg: {avg_chars_per_page:.1f} chars/page). Scanned: {is_scanned}")
            
            # Step 3: If not scanned, return PyPDF2 results
            if not is_scanned:
                pypdf_result["is_scanned"] = False
                pypdf_result["extraction_method"] = "pypdf2"
                pypdf_result["ocr_confidence"] = None
                return pypdf_result
            
            # Step 4: If scanned, try OCR fallback
            logger.info("Document appears to be scanned. Attempting OCR extraction...")
            
            if not OCR_AVAILABLE:
                logger.warning("OCR libraries not available. Install pytesseract, pdf2image, Pillow")
                pypdf_result["is_scanned"] = True
                pypdf_result["extraction_method"] = "pypdf2_failed"
                pypdf_result["ocr_confidence"] = None
                pypdf_result["error"] = "Document is scanned but OCR libraries not installed"
                return pypdf_result
            
            ocr_result = PDFExtractor._extract_with_ocr(
                pdf_bytes, 
                num_pages, 
                ocr_languages
            )
            
            if ocr_result["success"]:
                # Use the better title from PyPDF2 if available
                if pypdf_result["title"] != "Untitled Document":
                    ocr_result["title"] = pypdf_result["title"]
                return ocr_result
            else:
                # OCR failed, return PyPDF2 results with warning
                pypdf_result["is_scanned"] = True
                pypdf_result["extraction_method"] = "pypdf2_low_confidence"
                pypdf_result["ocr_confidence"] = None
                pypdf_result["error"] = f"OCR extraction failed: {ocr_result.get('error', 'Unknown')}"
                return pypdf_result
            
        except Exception as e:
            logger.error(f"Error in extract_text: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document",
                "is_scanned": None,
                "extraction_method": "failed",
                "ocr_confidence": None
            }
    
    @staticmethod
    def _extract_with_pypdf(pdf_bytes: bytes, num_pages: int) -> Dict[str, Any]:
        """Extract text using PyPDF2 (fast, for text-based PDFs)"""
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            page_count = len(pdf_reader.pages)
            pages_to_extract = min(num_pages, page_count)
            
            # Extract text from specified pages
            extracted_text = ""
            for i in range(pages_to_extract):
                page = pdf_reader.pages[i]
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
            
            # Clean text
            extracted_text = PDFExtractor._clean_text(extracted_text)
            
            # Try to get title from metadata or extract from content
            title = PDFExtractor._extract_title(pdf_reader, extracted_text)
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": page_count,
                "pages_extracted": pages_to_extract,
                "title": title
            }
            
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document"
            }
    
    @staticmethod
    def _extract_with_ocr(
        pdf_bytes: bytes, 
        num_pages: int, 
        languages: str = "eng+hin"
    ) -> Dict[str, Any]:
        """Extract text using Tesseract OCR (slower, for scanned PDFs)"""
        try:
            logger.info(f"Starting OCR extraction with languages: {languages}")
            
            # Convert PDF to images
            images = convert_from_bytes(
                pdf_bytes,
                first_page=1,
                last_page=num_pages,
                dpi=200  # Balance between quality and performance
            )
            
            logger.info(f"Converted PDF to {len(images)} images")
            
            # OCR each image
            extracted_text = ""
            confidence_scores = []
            
            for idx, image in enumerate(images):
                logger.info(f"Processing page {idx + 1}/{len(images)} with OCR...")
                
                # Perform OCR
                ocr_data = pytesseract.image_to_data(
                    image, 
                    lang=languages,
                    output_type=pytesseract.Output.DICT
                )
                
                # Extract text and confidence
                page_text = " ".join([
                    word for word, conf in zip(ocr_data['text'], ocr_data['conf'])
                    if conf > 0  # Filter out low-confidence results
                ])
                
                # Calculate average confidence for this page
                valid_confidences = [c for c in ocr_data['conf'] if c > 0]
                if valid_confidences:
                    avg_confidence = sum(valid_confidences) / len(valid_confidences)
                    confidence_scores.append(avg_confidence)
                
                extracted_text += page_text + "\n"
            
            # Clean text
            extracted_text = PDFExtractor._clean_text(extracted_text)
            
            # Calculate overall OCR confidence
            overall_confidence = (
                sum(confidence_scores) / len(confidence_scores) 
                if confidence_scores else 0
            )
            
            # Extract title from OCR'd text
            title = PDFExtractor._extract_title_from_text(extracted_text)
            
            logger.info(f"OCR extraction complete. Confidence: {overall_confidence:.1f}%")
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": len(images),
                "pages_extracted": len(images),
                "title": title,
                "is_scanned": True,
                "extraction_method": "tesseract_ocr",
                "ocr_confidence": round(overall_confidence, 2)
            }
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document",
                "is_scanned": True,
                "extraction_method": "ocr_failed",
                "ocr_confidence": None
            }
    
    @staticmethod
    def _extract_title(pdf_reader, extracted_text: str) -> str:
        """Extract title from metadata or content"""
        # Try metadata first
        if pdf_reader.metadata:
            metadata_title = pdf_reader.metadata.get('/Title')
            if metadata_title and str(metadata_title).strip():
                title = str(metadata_title).strip()
                if title and title.lower() not in ['untitled', 'document', 'untitled document']:
                    return title
        
        # Try to extract from content
        return PDFExtractor._extract_title_from_text(extracted_text)
    
    @staticmethod
    def _extract_title_from_text(text: str) -> str:
        """Extract title from first few lines of text"""
        if text:
            lines = text.split('\n')
            for line in lines[:5]:  # Check first 5 lines
                line = line.strip()
                # Look for lines that might be titles (length between 10-100 chars)
                if 10 <= len(line) <= 100 and not line.isdigit():
                    # Remove common prefixes
                    line = re.sub(r'^(title|subject|report|document):\s*', '', line, flags=re.IGNORECASE)
                    if len(line) >= 10:
                        return line
        
        return "Untitled Document"
    
    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters (keep basic punctuation)
        text = re.sub(r'[^\w\s.,;:!?()\-\'\"@#$%&*/+=<>]', '', text)
        
        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)
        
        # Limit length (keep first 2000 words for cost efficiency)
        words = text.split()
        if len(words) > 2000:
            text = ' '.join(words[:2000])
        
        return text.strip()
    
    @staticmethod
    def get_pdf_info(pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Get PDF metadata without extracting full text
        
        Args:
            pdf_bytes: PDF file as bytes
            
        Returns:
            dict with PDF metadata
        """
        try:
            pdf_file = BytesIO(pdf_bytes)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            metadata = {}
            if pdf_reader.metadata:
                for key, value in pdf_reader.metadata.items():
                    metadata[key] = str(value)
            
            return {
                "success": True,
                "page_count": len(pdf_reader.pages),
                "metadata": metadata
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
