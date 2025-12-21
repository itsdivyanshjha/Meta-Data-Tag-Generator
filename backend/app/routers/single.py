from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from app.models import SinglePDFResponse, TaggingConfig
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
import time
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process", response_model=SinglePDFResponse)
async def process_single_pdf(
    pdf_file: UploadFile = File(...),
    config: str = Form(...)
):
    """
    Process single PDF and generate tags with automatic OCR support
    
    Args:
        pdf_file: Uploaded PDF file
        config: JSON string of TaggingConfig
    """
    start_time = time.time()
    
    try:
        # Parse config
        config_dict = json.loads(config)
        tagging_config = TaggingConfig(**config_dict)
        
        logger.info(f"Processing PDF: {pdf_file.filename}")
        logger.info(f"Using model: {tagging_config.model_name}")
        
        # Validate file type
        if not pdf_file.filename or not pdf_file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF file.")
        
        # Read PDF
        pdf_bytes = await pdf_file.read()
        
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Empty PDF file")
        
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
        
        # Generate tags
        tagger = AITagger(tagging_config.api_key, tagging_config.model_name)
        tagging_result = tagger.generate_tags(
            title=extraction_result.get("title", pdf_file.filename or "Untitled"),
            description="",
            content=extraction_result["extracted_text"],
            num_tags=tagging_config.num_tags
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
            document_title=extraction_result.get("title", pdf_file.filename or "Untitled"),
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
