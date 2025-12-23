from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from app.models import BatchProcessResponse, TaggingConfig
from app.services.csv_processor import CSVProcessor
from app.services.exclusion_parser import ExclusionListParser
from typing import Optional
import time
import json
import base64
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/process", response_model=BatchProcessResponse)
async def process_batch_csv(
    csv_file: UploadFile = File(...),
    config: str = Form(...),
    exclusion_file: Optional[UploadFile] = File(None)
):
    """
    Process batch CSV with multiple documents and optional exclusion list
    
    Args:
        csv_file: Uploaded CSV file
        config: JSON string of TaggingConfig
        exclusion_file: Optional file containing words/phrases to exclude from tags (.txt or .pdf)
    """
    start_time = time.time()
    
    try:
        # Parse config
        config_dict = json.loads(config)
        tagging_config = TaggingConfig(**config_dict)
        
        # Parse exclusion file if provided
        if exclusion_file and exclusion_file.filename:
            logger.info(f"Processing exclusion file for batch: {exclusion_file.filename}")
            exclusion_bytes = await exclusion_file.read()
            
            try:
                parser = ExclusionListParser()
                exclusion_words = parser.parse_from_file(exclusion_bytes, exclusion_file.filename)
                tagging_config.exclusion_words = list(exclusion_words)
                logger.info(f"Loaded {len(exclusion_words)} exclusion words for batch processing")
            except Exception as e:
                logger.error(f"Failed to parse exclusion file: {str(e)}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to parse exclusion file: {str(e)}"
                )
        
        # Validate file type
        if not csv_file.filename or not csv_file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV file.")
        
        # Read CSV
        csv_content = await csv_file.read()
        
        if not csv_content:
            raise HTTPException(status_code=400, detail="Empty CSV file")
        
        # Process batch
        processor = CSVProcessor(tagging_config)
        result = processor.process_csv(csv_content)
        
        processing_time = time.time() - start_time
        
        return BatchProcessResponse(
            success=result["success"],
            total_documents=result["total_documents"],
            processed_count=result["processed_count"],
            failed_count=result["failed_count"],
            output_csv_url=result["output_csv_url"],
            summary_report=result["summary"],
            processing_time=round(processing_time, 2)
        )
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid config JSON format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/template")
async def get_csv_template():
    """
    Get a sample CSV template for batch processing
    """
    template = """title,description,file_source_type,file_path,publishing_date,file_size
"Training Manual","PMSPECIAL training document",url,https://example.com/doc1.pdf,2025-01-15,1.2MB
"Annual Report 2024","Financial report",url,https://example.com/doc2.pdf,2024-12-31,2.5MB
"Policy Guidelines","New policy document",url,https://example.com/policy.pdf,2025-02-01,850KB"""
    
    return JSONResponse(
        content={
            "template": template,
            "columns": [
                {"name": "title", "required": True, "description": "Document title"},
                {"name": "description", "required": False, "description": "Document description"},
                {"name": "file_source_type", "required": True, "description": "Source type: url, s3, or local"},
                {"name": "file_path", "required": True, "description": "Path or URL to the file"},
                {"name": "publishing_date", "required": False, "description": "Publication date"},
                {"name": "file_size", "required": False, "description": "File size"}
            ]
        }
    )

