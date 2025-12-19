import PyPDF2
from io import BytesIO
from typing import Dict, Any
import re


class PDFExtractor:
    """Extract text from PDF documents"""
    
    @staticmethod
    def extract_text(pdf_bytes: bytes, num_pages: int = 3) -> Dict[str, Any]:
        """
        Extract text from PDF
        
        Args:
            pdf_bytes: PDF file as bytes
            num_pages: Number of pages to extract (default 3)
            
        Returns:
            dict with extracted_text, page_count, title
        """
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
            return {
                "success": False,
                "error": str(e),
                "extracted_text": "",
                "page_count": 0,
                "pages_extracted": 0,
                "title": "Untitled Document"
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
        
        # Try to extract from first few lines of content
        if extracted_text:
            lines = extracted_text.split('\n')
            for line in lines[:5]:  # Check first 5 lines
                line = line.strip()
                # Look for lines that might be titles (length between 10-100 chars, has some substance)
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
