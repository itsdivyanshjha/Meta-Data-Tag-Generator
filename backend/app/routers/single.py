from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import Response
from app.models import SinglePDFResponse, TaggingConfig
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
from app.services.exclusion_parser import ExclusionListParser
from typing import Optional
import time
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process", response_model=SinglePDFResponse)
async def process_single_pdf(
    pdf_file: Optional[UploadFile] = File(None),
    config: str = Form(...),
    exclusion_file: Optional[UploadFile] = File(None),
    pdf_url: Optional[str] = Form(None)
):
    """
    Process single PDF and generate tags with automatic OCR support and optional exclusion list
    
    Args:
        pdf_file: Uploaded PDF file (optional if pdf_url provided)
        config: JSON string of TaggingConfig
        exclusion_file: Optional file containing words/phrases to exclude from tags (.txt or .pdf)
        pdf_url: Optional URL to download PDF from (alternative to pdf_file)
    """
    start_time = time.time()
    
    try:
        # Parse config
        config_dict = json.loads(config)
        tagging_config = TaggingConfig(**config_dict)
        
        # Parse exclusion file if provided
        if exclusion_file and exclusion_file.filename:
            logger.info(f"Processing exclusion file: {exclusion_file.filename}")
            exclusion_bytes = await exclusion_file.read()
            
            try:
                parser = ExclusionListParser()
                exclusion_words = parser.parse_from_file(exclusion_bytes, exclusion_file.filename)
                tagging_config.exclusion_words = list(exclusion_words)
                logger.info(f"Loaded {len(exclusion_words)} exclusion words from {exclusion_file.filename}")
                logger.info(f"Sample exclusion words: {list(exclusion_words)[:10]}")
            except Exception as e:
                logger.error(f"Failed to parse exclusion file: {str(e)}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to parse exclusion file: {str(e)}"
                )
        
        logger.info(f"Using model: {tagging_config.model_name}")
        
        # Determine source and get PDF bytes
        pdf_bytes = None
        document_name = "Untitled"
        
        # Check if both file and URL provided
        if pdf_file and pdf_file.filename and pdf_url:
            raise HTTPException(
                status_code=400, 
                detail="Please provide either a PDF file OR a URL, not both."
            )
        
        # Option 1: File upload
        if pdf_file and pdf_file.filename:
            logger.info(f"Processing uploaded file: {pdf_file.filename}")
            
            # Validate file type
            if not pdf_file.filename.lower().endswith('.pdf'):
                raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
        
            pdf_bytes = await pdf_file.read()
            document_name = pdf_file.filename
            
            if not pdf_bytes:
                raise HTTPException(status_code=400, detail="Empty PDF file")
        
        # Option 2: URL download
        elif pdf_url:
            logger.info(f"Downloading PDF from URL: {pdf_url}")
            
            # Validate URL format
            if not pdf_url.startswith(('http://', 'https://')):
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid URL. Must start with http:// or https://"
                )
            
            # Download PDF from URL
            from app.services.file_handler import FileHandler
            handler = FileHandler()
            download_result = handler.download_file("url", pdf_url)
            
            if not download_result["success"]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to download PDF from URL: {download_result.get('error', 'Unknown error')}"
                )
            
            pdf_bytes = download_result["file_bytes"]
            
            # Extract document name from URL
            from urllib.parse import urlparse, unquote
            parsed_url = urlparse(pdf_url)
            document_name = unquote(parsed_url.path.split('/')[-1]) if parsed_url.path else "URL Document"
            
            if not document_name.endswith('.pdf'):
                document_name += '.pdf'
            
            logger.info(f"Downloaded {len(pdf_bytes)} bytes from URL")
        
        else:
            raise HTTPException(
                status_code=400, 
                detail="Please provide either a PDF file or a PDF URL."
            )
        
        # Extract text (with automatic OCR fallback)
        extractor = PDFExtractor()
        extraction_result = extractor.extract_text(pdf_bytes, tagging_config.num_pages)
        
        if not extraction_result["success"]:
            raise HTTPException(
                status_code=400, 
                detail=f"PDF extraction failed: {extraction_result.get('error', 'Unknown error')}"
            )
        
        logger.info(f"Extracted {len(extraction_result['extracted_text'])} characters")
        logger.info(f"Document title: {extraction_result.get('title', 'Unknown')}")
        logger.info(f"Extraction method: {extraction_result.get('extraction_method', 'unknown')}")
        
        if extraction_result.get('is_scanned'):
            logger.info(f"Scanned PDF detected. OCR confidence: {extraction_result.get('ocr_confidence', 'N/A')}%")
        
        # Check if we have enough text
        if len(extraction_result["extracted_text"].strip()) < 50:
            raise HTTPException(
                status_code=400, 
                detail="Could not extract sufficient text from PDF. The document might be scanned or image-based without OCR support."
            )
        
        # Generate tags with exclusion list and language awareness
        tagger = AITagger(
            tagging_config.api_key,
            tagging_config.model_name,
            exclusion_words=tagging_config.exclusion_words
        )
        tagging_result = tagger.generate_tags(
            title=extraction_result.get("title", document_name or "Untitled"),
            description="",
            content=extraction_result["extracted_text"],
            num_tags=tagging_config.num_tags,
            detected_language=extraction_result.get("detected_language"),
            language_name=extraction_result.get("language_name"),
            quality_info=extraction_result.get("quality_info")
        )
        
        logger.info(f"Tagging result success: {tagging_result['success']}")
        logger.info(f"Tags generated: {tagging_result.get('tags', [])}")
        logger.info(f"Raw response: {tagging_result.get('raw_response', 'N/A')}")
        
        if not tagging_result["success"]:
            raise HTTPException(
                status_code=500, 
                detail=f"Tag generation failed: {tagging_result.get('error', 'Unknown error')}"
            )
        
        processing_time = time.time() - start_time
        
        response = SinglePDFResponse(
            success=True,
            document_title=extraction_result.get("title", document_name or "Untitled"),
            tags=tagging_result["tags"],
            extracted_text_preview=extraction_result["extracted_text"][:500],
            processing_time=round(processing_time, 2),
            # OCR metadata
            is_scanned=extraction_result.get("is_scanned"),
            extraction_method=extraction_result.get("extraction_method"),
            ocr_confidence=extraction_result.get("ocr_confidence"),
            # Debug field
            raw_ai_response=tagging_result.get("raw_response", "N/A")
        )
        
        logger.info(f"Response tags count: {len(response.tags)}")
        
        return response
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid config JSON format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/preview")
async def preview_pdf_url(
    url: str = Query(..., description="URL of the PDF to preview")
):
    """
    Proxy endpoint to fetch and serve PDF from URL for preview purposes.
    This bypasses CORS restrictions by serving the PDF through our backend.
    """
    try:
        # Validate URL format
        if not url.startswith(('http://', 'https://')):
            raise HTTPException(
                status_code=400,
                detail="Invalid URL. Must start with http:// or https://"
            )
        
        # Download PDF from URL
        from app.services.file_handler import FileHandler
        handler = FileHandler()
        download_result = handler.download_file("url", url)
        
        if not download_result["success"]:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download PDF from URL: {download_result.get('error', 'Unknown error')}"
            )
        
        pdf_bytes = download_result["file_bytes"]
        
        # Return PDF with proper headers for iframe embedding
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "inline; filename=preview.pdf",
                "X-Content-Type-Options": "nosniff",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error proxying PDF for preview: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
