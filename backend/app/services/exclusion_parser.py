from typing import Set
import logging

# Encoding detection
try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False
    print("⚠️ chardet not available. Install with: pip install chardet")

logger = logging.getLogger(__name__)


class ExclusionListParser:
    """Parse exclusion words from various file formats"""
    
    @staticmethod
    def parse_from_text(text: str) -> Set[str]:
        """
        Parse exclusion words from text content
        Supports:
        - One word/phrase per line
        - Comma-separated on same line
        - Mixed formats
        - Comments starting with #
        """
        words = set()
        
        # Split by newlines first
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Split by comma if present
            if ',' in line:
                parts = [p.strip().lower() for p in line.split(',')]
                words.update(p for p in parts if p and not p.startswith('#'))
            else:
                words.add(line.lower())
        
        logger.info(f"Parsed {len(words)} exclusion words from text")
        return words
    
    @staticmethod
    def parse_from_file(file_bytes: bytes, filename: str) -> Set[str]:
        """
        Parse exclusion list from uploaded file
        
        Supported formats:
        - .txt: Plain text file (one term per line or comma-separated)
        - .pdf: PDF file (extracts text and parses)
        
        Args:
            file_bytes: File content as bytes
            filename: Original filename
            
        Returns:
            Set of lowercase exclusion words/phrases
        """
        filename_lower = filename.lower()
        
        if filename_lower.endswith('.txt'):
            # Auto-detect encoding using chardet if available
            if CHARDET_AVAILABLE:
                try:
                    detected = chardet.detect(file_bytes)
                    encoding = detected['encoding']
                    confidence = detected['confidence']

                    logger.info(f"Detected encoding: {encoding} (confidence: {confidence:.2%})")

                    # Use detected encoding if confidence is reasonable
                    if confidence > 0.7:
                        try:
                            text = file_bytes.decode(encoding)
                            logger.info(f"Successfully decoded with {encoding}")
                            return ExclusionListParser.parse_from_text(text)
                        except Exception as e:
                            logger.warning(f"Failed to decode with detected encoding {encoding}: {e}")
                            # Fall through to manual attempts below

                except Exception as e:
                    logger.warning(f"Encoding detection failed: {e}")

            # Fallback: Try common encodings manually
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    text = file_bytes.decode(encoding)
                    logger.info(f"Successfully decoded with {encoding} (fallback)")
                    return ExclusionListParser.parse_from_text(text)
                except UnicodeDecodeError:
                    continue

            # Last resort: decode with errors='replace'
            logger.warning("All encoding attempts failed, using UTF-8 with error replacement")
            text = file_bytes.decode('utf-8', errors='replace')
            return ExclusionListParser.parse_from_text(text)
        
        elif filename_lower.endswith('.pdf'):
            # Reuse existing PDF extractor
            from app.services.pdf_extractor import PDFExtractor
            extractor = PDFExtractor()
            result = extractor.extract_text(file_bytes, num_pages=None)  # All pages
            
            if result['success']:
                return ExclusionListParser.parse_from_text(result['extracted_text'])
            else:
                raise ValueError(f"Failed to extract text from PDF: {result.get('error')}")
        
        else:
            raise ValueError(
                f"Unsupported file format: {filename}. "
                f"Supported formats: .txt, .pdf"
            )

