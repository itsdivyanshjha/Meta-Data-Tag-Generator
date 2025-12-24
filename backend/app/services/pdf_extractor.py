import PyPDF2
from io import BytesIO
from typing import Dict, Any, Optional
import re
import logging

# OCR imports with graceful fallback
try:
    import pytesseract
    from pdf2image import convert_from_bytes
    from PIL import Image, ImageEnhance
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

# EasyOCR import with graceful fallback
try:
    import easyocr
    import numpy as np
    EASYOCR_AVAILABLE = True
except ImportError as e:
    EASYOCR_AVAILABLE = False
    print(f"⚠️ EasyOCR not available: {e}")

logger = logging.getLogger(__name__)

# Log availability status on module load
logger.info(f"📦 OCR Availability: Tesseract={OCR_AVAILABLE}, EasyOCR={EASYOCR_AVAILABLE}")


class PDFExtractor:
    """
    Hybrid PDF text extractor with automatic OCR fallback for scanned documents
    
    Features:
    - Primary: PyPDF2 for text-based PDFs (fastest)
    - Fallback 1: Tesseract OCR for scanned PDFs (fast, good for Hindi)
    - Fallback 2: EasyOCR for complex Indian languages (slower but more accurate)
    - Auto-detection: Determines if PDF is scanned based on text extraction results
    - Multi-language: Supports 80+ languages including all Indian languages
    """
    
    # Threshold: if we extract less than this many chars per page, consider it scanned
    SCANNED_THRESHOLD_CHARS_PER_PAGE = 150
    
    # Confidence threshold to try EasyOCR after Tesseract
    TESSERACT_CONFIDENCE_THRESHOLD = 60
    
    # EasyOCR reader instance (loaded once, reused)
    _easyocr_reader = None
    
    @classmethod
    def get_easyocr_reader(cls, languages=['hi', 'en']):
        """
        Lazy load EasyOCR reader (loads model into memory once)
        
        Args:
            languages: List of language codes (e.g., ['hi', 'en'] for Hindi + English)
            
        Returns:
            EasyOCR Reader instance or None if not available
        """
        if not EASYOCR_AVAILABLE:
            logger.warning("EasyOCR not available. Install: pip install easyocr torch torchvision")
            return None
        
        if cls._easyocr_reader is None:
            try:
                logger.info(f"Loading EasyOCR with languages: {languages}")
                # gpu=False for compatibility, set to True if GPU available
                cls._easyocr_reader = easyocr.Reader(languages, gpu=False, verbose=False)
                logger.info("EasyOCR loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load EasyOCR: {str(e)}")
                return None
        
        return cls._easyocr_reader
    
    @staticmethod
    def extract_text(
        pdf_bytes: bytes, 
        num_pages: int = 3,
        ocr_languages: str = "hin+eng"  # Hindi first, then English for better Hindi detection
    ) -> Dict[str, Any]:
        """
        Extract text from PDF with automatic OCR fallback
        
        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract (default 3)
            ocr_languages: Tesseract language codes (default: hin+eng for Hindi priority)
            
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
            
            # Step 4: If scanned, try OCR fallback (Tesseract first, then EasyOCR if needed)
            logger.info("Document appears to be scanned. Attempting OCR extraction...")
            
            if not OCR_AVAILABLE:
                logger.warning("OCR libraries not available. Install pytesseract, pdf2image, Pillow")
                pypdf_result["is_scanned"] = True
                pypdf_result["extraction_method"] = "pypdf2_failed"
                pypdf_result["ocr_confidence"] = None
                pypdf_result["error"] = "Document is scanned but OCR libraries not installed"
                return pypdf_result
            
            # Try Tesseract first (faster)
            tesseract_result = PDFExtractor._extract_with_ocr(
                pdf_bytes, 
                num_pages, 
                ocr_languages
            )
            
            # Check if Tesseract was successful and had good confidence
            if tesseract_result["success"]:
                tesseract_confidence = tesseract_result.get("ocr_confidence", 0)
                tesseract_text_length = len(tesseract_result.get("extracted_text", "").strip())
                
                logger.info(f"Tesseract OCR completed. Confidence: {tesseract_confidence}%, Text length: {tesseract_text_length}")
                
                # If Tesseract confidence is good, use it
                if tesseract_confidence >= PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD and tesseract_text_length > 100:
                    logger.info(f"Using Tesseract result (good confidence: {tesseract_confidence}%)")
                    # Use better title from PyPDF2 if available
                    if pypdf_result["title"] != "Untitled Document":
                        tesseract_result["title"] = pypdf_result["title"]
                    return tesseract_result
                
                # If Tesseract confidence is low, try EasyOCR for better accuracy
                logger.info(f"🔄 Tesseract confidence low ({tesseract_confidence}% < {PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD}%). Trying EasyOCR for better accuracy...")
            else:
                logger.warning("🔄 Tesseract OCR failed. Trying EasyOCR...")
            
            # Step 5: Try EasyOCR as fallback or for better accuracy
            logger.info(f"🔍 Checking EasyOCR availability: {EASYOCR_AVAILABLE}")
            if EASYOCR_AVAILABLE:
                logger.info("✅ EasyOCR is available. Starting EasyOCR extraction...")
                easyocr_result = PDFExtractor._extract_with_easyocr(pdf_bytes, num_pages)
                
                if easyocr_result["success"]:
                    easyocr_text_length = len(easyocr_result.get("extracted_text", "").strip())
                    easyocr_confidence = easyocr_result.get("ocr_confidence", 0)
                    
                    # Compare EasyOCR with Tesseract if both succeeded
                    if tesseract_result["success"]:
                        tesseract_confidence = tesseract_result.get("ocr_confidence", 0)
                        
                        # If Tesseract confidence is below threshold, prioritize EasyOCR
                        if tesseract_confidence < PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD:
                            # Prefer EasyOCR unless it extracts significantly less text (< 50% of Tesseract)
                            if easyocr_text_length >= tesseract_text_length * 0.5:
                                logger.info(f"Using EasyOCR result (Tesseract confidence {tesseract_confidence}% < threshold {PDFExtractor.TESSERACT_CONFIDENCE_THRESHOLD}%. "
                                          f"EasyOCR: {easyocr_text_length} chars, {easyocr_confidence}% confidence)")
                                if pypdf_result["title"] != "Untitled Document":
                                    easyocr_result["title"] = pypdf_result["title"]
                                return easyocr_result
                            else:
                                logger.warning(f"EasyOCR extracted too little text ({easyocr_text_length} vs {tesseract_text_length}). "
                                             f"Using Tesseract despite low confidence ({tesseract_confidence}%)")
                                if pypdf_result["title"] != "Untitled Document":
                                    tesseract_result["title"] = pypdf_result["title"]
                                return tesseract_result
                        else:
                            # Tesseract confidence is good, compare text lengths
                            if easyocr_text_length > tesseract_text_length * 0.8:
                                logger.info(f"Using EasyOCR result (extracted {easyocr_text_length} chars vs Tesseract {tesseract_text_length})")
                                if pypdf_result["title"] != "Untitled Document":
                                    easyocr_result["title"] = pypdf_result["title"]
                                return easyocr_result
                            else:
                                logger.info(f"Using Tesseract result (better than EasyOCR: {tesseract_text_length} vs {easyocr_text_length} chars)")
                                if pypdf_result["title"] != "Untitled Document":
                                    tesseract_result["title"] = pypdf_result["title"]
                                return tesseract_result
                    else:
                        # Tesseract failed, use EasyOCR
                        logger.info("Using EasyOCR result (Tesseract failed)")
                        if pypdf_result["title"] != "Untitled Document":
                            easyocr_result["title"] = pypdf_result["title"]
                        return easyocr_result
            else:
                logger.warning("❌ EasyOCR not available. Install with: pip install easyocr torch torchvision")
            
            # Fallback to Tesseract if EasyOCR not available or failed
            if tesseract_result["success"]:
                logger.info("Using Tesseract result (EasyOCR not available or failed)")
                if pypdf_result["title"] != "Untitled Document":
                    tesseract_result["title"] = pypdf_result["title"]
                return tesseract_result
            
            # Last resort: return PyPDF2 result with error
            pypdf_result["is_scanned"] = True
            pypdf_result["extraction_method"] = "pypdf2_ocr_all_failed"
            pypdf_result["ocr_confidence"] = None
            pypdf_result["error"] = "All OCR methods failed"
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
            
            # Extract text from specified pages with proper encoding
            extracted_text = ""
            for i in range(pages_to_extract):
                page = pdf_reader.pages[i]
                page_text = page.extract_text()
                if page_text:
                    # Ensure proper UTF-8 encoding
                    try:
                        # Try to encode/decode to fix encoding issues
                        page_text = page_text.encode('utf-8', errors='ignore').decode('utf-8')
                    except:
                        # If fails, use as is
                        pass
                    extracted_text += page_text + "\n"
            
            # Check if text looks corrupted (has lots of non-standard ASCII but not proper Unicode)
            # This indicates encoding issues
            is_likely_corrupted = PDFExtractor._is_text_corrupted(extracted_text)
            
            if is_likely_corrupted:
                logger.warning("Detected corrupted/wrong encoding in PyPDF2 extraction")
                # Force OCR for better results
                return {
                    "success": True,
                    "extracted_text": "",  # Empty to trigger OCR
                    "page_count": page_count,
                    "pages_extracted": 0,  # Zero to trigger OCR fallback
                    "title": "Untitled Document"
                }
            
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
        languages: str = "hin+eng"
    ) -> Dict[str, Any]:
        """Extract text using Tesseract OCR (slower, for scanned PDFs)"""
        try:
            logger.info(f"Starting OCR extraction with languages: {languages}")
            
            # Convert PDF to images with optimal DPI
            # Note: Too high DPI on low-quality scans makes it worse
            images = convert_from_bytes(
                pdf_bytes,
                first_page=1,
                last_page=num_pages,
                dpi=300  # Optimal for most government PDFs (not too high, not too low)
            )
            
            logger.info(f"Converted PDF to {len(images)} images")
            
            # OCR each image
            extracted_text = ""
            confidence_scores = []
            
            for idx, image in enumerate(images):
                logger.info(f"Processing page {idx + 1}/{len(images)} with OCR...")
                
                # Preprocess image for better OCR
                try:
                    # Convert to grayscale and enhance contrast
                    image = image.convert('L')  # Grayscale
                    
                    # Apply contrast enhancement for low-quality scans
                    enhancer = ImageEnhance.Contrast(image)
                    image = enhancer.enhance(2.0)  # Increase contrast
                except Exception as prep_error:
                    logger.warning(f"Image preprocessing failed: {prep_error}, using original")
                
                # Perform OCR with proper Hindi/Devanagari support
                try:
                    # Try multiple PSM modes for better results
                    # PSM 3: Automatic page segmentation (usually best for mixed content)
                    page_text = pytesseract.image_to_string(
                        image,
                        lang=languages,
                        config='--psm 3 --oem 1'  # PSM 3: auto, OEM 1: neural nets LSTM
                    )
                    
                    # Get confidence scores
                    ocr_data = pytesseract.image_to_data(
                        image, 
                        lang=languages,
                        output_type=pytesseract.Output.DICT
                    )
                    
                    # Calculate average confidence for this page
                    valid_confidences = [c for c in ocr_data['conf'] if c > 0]
                    if valid_confidences:
                        avg_confidence = sum(valid_confidences) / len(valid_confidences)
                        confidence_scores.append(avg_confidence)
                    
                    extracted_text += page_text + "\n"
                    
                    # Log first 200 chars to check encoding
                    logger.info(f"OCR text sample: {page_text[:200]}")
                    
                except Exception as page_error:
                    logger.error(f"Error OCR'ing page {idx + 1}: {str(page_error)}")
                    continue
            
            # Light cleaning - preserve Hindi characters
            extracted_text = PDFExtractor._clean_text_unicode_safe(extracted_text)
            
            # Check for gibberish in OCR output
            if PDFExtractor._is_gibberish(extracted_text):
                logger.warning("⚠️ Detected gibberish in Tesseract OCR output. Quality may be poor.")
            
            # Calculate overall OCR confidence
            overall_confidence = (
                sum(confidence_scores) / len(confidence_scores) 
                if confidence_scores else 0
            )
            
            # Extract title from OCR'd text
            title = PDFExtractor._extract_title_from_text(extracted_text)
            
            logger.info(f"OCR extraction complete. Confidence: {overall_confidence:.1f}%")
            logger.info(f"Extracted text length: {len(extracted_text)} chars")
            
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
    def _extract_with_easyocr(pdf_bytes: bytes, num_pages: int) -> Dict[str, Any]:
        """
        Extract text using EasyOCR (best for complex Indian languages)
        
        EasyOCR supports 80+ languages including:
        - All Indian languages (Hindi, Tamil, Telugu, Bengali, Kannada, Malayalam, etc.)
        - Complex scripts and ligatures
        - Better accuracy on low-quality scans
        
        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract
            
        Returns:
            dict with extracted_text and OCR metadata
        """
        try:
            logger.info("Starting EasyOCR extraction...")
            
            # Convert PDF to images
            images = convert_from_bytes(
                pdf_bytes,
                first_page=1,
                last_page=num_pages,
                dpi=300  # Optimal DPI for OCR
            )
            
            logger.info(f"Converted PDF to {len(images)} images for EasyOCR")
            
            # Get EasyOCR reader (supports Hindi + English by default)
            # Can be extended to support more languages: ['hi', 'ta', 'te', 'bn', 'en']
            reader = PDFExtractor.get_easyocr_reader(['hi', 'en'])
            
            if not reader:
                return {
                    "success": False,
                    "error": "EasyOCR reader not available",
                    "extracted_text": "",
                    "page_count": 0,
                    "pages_extracted": 0,
                    "title": "Untitled Document",
                    "is_scanned": True,
                    "extraction_method": "easyocr_failed",
                    "ocr_confidence": None
                }
            
            # OCR each image
            extracted_text = ""
            confidence_scores = []
            
            for idx, image in enumerate(images):
                logger.info(f"EasyOCR processing page {idx + 1}/{len(images)}...")
                
                # Convert PIL image to numpy array (required by EasyOCR)
                img_array = np.array(image)
                
                # Apply same preprocessing as Tesseract for consistency
                try:
                    # Convert to grayscale
                    if len(img_array.shape) == 3:
                        from PIL import Image as PILImage
                        pil_img = PILImage.fromarray(img_array)
                        pil_img = pil_img.convert('L')
                        
                        # Enhance contrast
                        enhancer = ImageEnhance.Contrast(pil_img)
                        pil_img = enhancer.enhance(2.0)
                        
                        img_array = np.array(pil_img)
                except Exception as prep_error:
                    logger.warning(f"Image preprocessing failed: {prep_error}, using original")
                
                # Run EasyOCR
                # Returns: list of ([bbox], text, confidence)
                results = reader.readtext(img_array, detail=1)
                
                # Extract text and confidence
                page_text_parts = []
                page_confidences = []
                
                for (bbox, text, conf) in results:
                    if text.strip():  # Only add non-empty text
                        page_text_parts.append(text)
                        page_confidences.append(conf * 100)  # Convert to percentage
                
                # Join text parts with spaces
                page_text = ' '.join(page_text_parts)
                extracted_text += page_text + "\n"
                
                # Calculate average confidence for this page
                if page_confidences:
                    avg_page_conf = sum(page_confidences) / len(page_confidences)
                    confidence_scores.append(avg_page_conf)
                
                logger.info(f"EasyOCR page {idx + 1}: extracted {len(page_text)} chars, "
                          f"confidence: {avg_page_conf:.1f}%" if page_confidences else "no confidence data")
            
            # Calculate overall confidence
            overall_confidence = (
                sum(confidence_scores) / len(confidence_scores) 
                if confidence_scores else 0
            )
            
            # Clean text (preserve Unicode for Indian languages)
            extracted_text = PDFExtractor._clean_text_unicode_safe(extracted_text)
            
            # Check for gibberish in EasyOCR output
            if PDFExtractor._is_gibberish(extracted_text):
                logger.warning("⚠️ Detected gibberish in EasyOCR output. Document may have very poor scan quality.")
            
            # Extract title
            title = PDFExtractor._extract_title_from_text(extracted_text)
            
            logger.info(f"EasyOCR extraction complete. Extracted {len(extracted_text)} chars, "
                       f"overall confidence: {overall_confidence:.1f}%")
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "page_count": len(images),
                "pages_extracted": len(images),
                "title": title,
                "is_scanned": True,
                "extraction_method": "easyocr",
                "ocr_confidence": round(overall_confidence, 2)
            }
            
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document",
                "is_scanned": True,
                "extraction_method": "easyocr_failed",
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
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            for line in lines[:5]:  # Check first 5 non-empty lines
                # Look for lines that might be titles (length between 10-100 chars)
                if 10 <= len(line) <= 100:
                    return line
        
        return "Untitled Document"
    
    @staticmethod
    def _clean_text_unicode_safe(text: str) -> str:
        """
        Clean extracted text while preserving Unicode characters (Hindi/Devanagari)
        """
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
        text = re.sub(r'\n\n+', '\n', text)  # Multiple newlines to single
        
        # Remove only truly problematic characters, keep Devanagari (U+0900-U+097F)
        # Keep: Latin, Devanagari, numbers, basic punctuation
        # Remove: Control characters, weird symbols
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Limit length (keep first 2500 words for better context)
        words = text.split()
        if len(words) > 2500:
            text = ' '.join(words[:2500])
        
        return text.strip()
    
    @staticmethod
    def _is_gibberish(text: str) -> bool:
        """
        Detect if extracted text is gibberish/nonsensical
        
        Checks for patterns indicating OCR failure:
        1. High ratio of consonant clusters (xgy, hfd, vubf)
        2. Repeated random character patterns
        3. Very low vowel ratio in English text
        4. Excessive special characters
        """
        if not text or len(text) < 20:
            return False
        
        # Sample for analysis
        sample = text[:1000].lower()
        
        # Count vowels vs consonants for English text
        vowels = sum(1 for c in sample if c in 'aeiou')
        letters = sum(1 for c in sample if c.isalpha())
        
        if letters > 50:  # Only check if we have enough letters
            vowel_ratio = vowels / letters
            # English text typically has 35-45% vowels
            # If less than 20%, likely gibberish
            if vowel_ratio < 0.20:
                logger.warning(f"Detected gibberish: vowel ratio too low ({vowel_ratio:.2%})")
                return True
        
        # Check for excessive consonant clusters (3+ consonants in a row)
        consonant_clusters = re.findall(r'[bcdfghjklmnpqrstvwxyz]{3,}', sample)
        if len(consonant_clusters) > 10:
            logger.warning(f"Detected gibberish: {len(consonant_clusters)} consonant clusters: {consonant_clusters[:5]}")
            return True
        
        # Check for repeated nonsense patterns
        words = re.findall(r'\b[a-z]{3,}\b', sample)
        if len(words) > 20:
            # Count how many words are "pronounceable" (have vowels)
            pronounceable = sum(1 for word in words if any(v in word for v in 'aeiou'))
            pronounceable_ratio = pronounceable / len(words)
            if pronounceable_ratio < 0.60:  # Less than 60% pronounceable
                logger.warning(f"Detected gibberish: only {pronounceable_ratio:.2%} pronounceable words")
                return True
        
        return False
    
    @staticmethod
    def _is_text_corrupted(text: str) -> bool:
        """
        Detect if extracted text is corrupted/wrong encoding
        
        Specifically detects:
        1. Krutidev/legacy Hindi fonts (common in government docs)
        2. Wrong character encoding
        3. Mixed garbage characters
        """
        if not text or len(text) < 50:
            return False
        
        # Sample first 1000 chars for better detection
        sample = text[:1000]
        
        # KRUTIDEV DETECTION - This is the main issue!
        # Krutidev fonts use specific ASCII patterns for Hindi
        # Common Krutidev characters: k, [k, jk, ns, esa, ds, etc.
        krutidev_patterns = [
            'lkekftd',  # सामाजिक in Krutidev
            'iQjojh',   # फरवरी in Krutidev  
            'lans\'k',  # संदेश in Krutidev
            'jfonkl',   # रविदास in Krutidev
            'U;k;',     # न्याय in Krutidev
            'lar',      # संत in Krutidev
            'xka/kh',   # गांधी in Krutidev
            'Hkkjr',    # भारत in Krutidev
            'ea=ky;',   # मंत्रालय in Krutidev
        ]
        
        # If we find ANY Krutidev pattern, it's corrupted
        for pattern in krutidev_patterns:
            if pattern in sample:
                logger.warning(f"Detected Krutidev encoding pattern: '{pattern}'")
                return True
        
        # Additional check: lots of special chars like @ {} [] 
        special_char_count = sum(1 for c in sample if c in '@#$%^&*~`|\\{}[]')
        if len(sample) > 0 and (special_char_count / len(sample)) > 0.05:
            logger.info(f"Detected high special character ratio: {special_char_count}/{len(sample)}")
            return True
        
        # Check for patterns of lowercase consonants with diacritics (Krutidev style)
        # Krutidev uses patterns like: dk, dks, dh, nh, etc.
        krutidev_style_patterns = 0
        for i in range(len(sample) - 1):
            if sample[i:i+2] in ['dk', 'dh', 'ds', 'nh', 'fk', 'jk', 'uk', 'vk', 'lk']:
                krutidev_style_patterns += 1
        
        if len(sample) > 0 and (krutidev_style_patterns / len(sample)) > 0.02:
            logger.warning(f"Detected Krutidev-style patterns: {krutidev_style_patterns}")
            return True
        
        return False
    
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
