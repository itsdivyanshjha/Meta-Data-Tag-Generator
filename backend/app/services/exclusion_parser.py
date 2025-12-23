from typing import Set
import logging

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
            try:
                text = file_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Try with different encoding
                text = file_bytes.decode('latin-1')
            
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

