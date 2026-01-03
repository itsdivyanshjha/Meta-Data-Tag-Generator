import pandas as pd
from io import BytesIO, StringIO
from typing import Dict, Any, List
import base64
from app.models import TaggingConfig, BatchDocument
from app.services.pdf_extractor import PDFExtractor
from app.services.ai_tagger import AITagger
from app.services.file_handler import FileHandler


class CSVProcessor:
    """Process batch CSV files with multiple documents"""
    
    REQUIRED_COLUMNS = ['title', 'file_source_type', 'file_path']
    OPTIONAL_COLUMNS = ['description', 'publishing_date', 'file_size']
    
    def __init__(self, config: TaggingConfig):
        self.config = config
        self.extractor = PDFExtractor()
        self.tagger = AITagger(config.api_key, config.model_name, exclusion_words=config.exclusion_words)
        self.file_handler = FileHandler()
    
    def process_csv(self, csv_content: bytes) -> Dict[str, Any]:
        """
        Process CSV file and generate tags for each document
        
        Args:
            csv_content: CSV file content as bytes
            
        Returns:
            dict with processing results and output CSV
        """
        results = {
            "success": False,
            "total_documents": 0,
            "processed_count": 0,
            "failed_count": 0,
            "output_csv_url": "",
            "summary": {
                "documents": [],
                "errors": []
            }
        }
        
        try:
            # Parse CSV
            df = self._parse_csv(csv_content)
            
            if df is None or df.empty:
                results["summary"]["errors"].append("Empty or invalid CSV file")
                return results
            
            # Validate columns
            validation_error = self._validate_columns(df)
            if validation_error:
                results["summary"]["errors"].append(validation_error)
                return results
            
            results["total_documents"] = len(df)
            
            # Process each document
            processed_results = []
            for idx, row in df.iterrows():
                doc_result = self._process_document(row, idx)
                processed_results.append(doc_result)
                
                if doc_result["success"]:
                    results["processed_count"] += 1
                else:
                    results["failed_count"] += 1
                
                results["summary"]["documents"].append({
                    "title": doc_result["title"],
                    "success": doc_result["success"],
                    "tags": doc_result.get("tags", []),
                    "error": doc_result.get("error")
                })
            
            # Add tags column to dataframe
            df['generated_tags'] = [
                ', '.join(r.get('tags', [])) for r in processed_results
            ]
            df['tagging_status'] = [
                'success' if r['success'] else f"failed: {r.get('error', 'unknown')}" 
                for r in processed_results
            ]
            
            # Generate output CSV
            output_csv = self._generate_output_csv(df)
            results["output_csv_url"] = output_csv
            
            results["success"] = results["processed_count"] > 0
            
            # Add summary statistics
            results["summary"]["statistics"] = {
                "total": results["total_documents"],
                "processed": results["processed_count"],
                "failed": results["failed_count"],
                "success_rate": f"{(results['processed_count'] / max(results['total_documents'], 1)) * 100:.1f}%"
            }
            
            return results
            
        except Exception as e:
            results["summary"]["errors"].append(f"Processing error: {str(e)}")
            return results
    
    def _parse_csv(self, csv_content: bytes) -> pd.DataFrame:
        """Parse CSV content into DataFrame"""
        try:
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    content_str = csv_content.decode(encoding)
                    df = pd.read_csv(StringIO(content_str))
                    return df
                except UnicodeDecodeError:
                    continue
            
            # If all encodings fail
            return None
            
        except Exception:
            return None
    
    def _validate_columns(self, df: pd.DataFrame) -> str:
        """Validate CSV has required columns"""
        missing_columns = []
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                missing_columns.append(col)
        
        if missing_columns:
            return f"Missing required columns: {', '.join(missing_columns)}"
        
        return ""
    
    def _process_document(self, row: pd.Series, index: int) -> Dict[str, Any]:
        """Process a single document from CSV row"""
        result = {
            "index": index,
            "title": str(row.get('title', f'Document {index + 1}')),
            "success": False,
            "tags": [],
            "error": None
        }
        
        try:
            # Get file info
            source_type = str(row.get('file_source_type', '')).strip()
            file_path = str(row.get('file_path', '')).strip()
            description = str(row.get('description', '')) if pd.notna(row.get('description')) else ''
            
            if not source_type or not file_path:
                result["error"] = "Missing file_source_type or file_path"
                return result
            
            # Download file
            download_result = self.file_handler.download_file(source_type, file_path)
            
            if not download_result["success"]:
                result["error"] = f"Download failed: {download_result.get('error')}"
                return result
            
            # Extract text from PDF
            pdf_bytes = download_result["file_bytes"]
            extraction_result = self.extractor.extract_text(pdf_bytes, self.config.num_pages)
            
            if not extraction_result["success"]:
                result["error"] = f"Text extraction failed: {extraction_result.get('error')}"
                return result
            
            if len(extraction_result["extracted_text"].strip()) < 50:
                result["error"] = "Insufficient text extracted from document"
                return result
            
            # Generate tags with language awareness
            tagging_result = self.tagger.generate_tags(
                title=result["title"],
                description=description,
                content=extraction_result["extracted_text"],
                num_tags=self.config.num_tags,
                detected_language=extraction_result.get("detected_language"),
                language_name=extraction_result.get("language_name"),
                quality_info=extraction_result.get("quality_info")
            )
            
            if not tagging_result["success"]:
                result["error"] = f"Tag generation failed: {tagging_result.get('error')}"
                return result
            
            result["success"] = True
            result["tags"] = tagging_result["tags"]
            
            return result
            
        except Exception as e:
            result["error"] = f"Processing error: {str(e)}"
            return result
    
    def _generate_output_csv(self, df: pd.DataFrame) -> str:
        """Generate output CSV as base64 data URL"""
        try:
            output = StringIO()
            df.to_csv(output, index=False)
            csv_bytes = output.getvalue().encode('utf-8')
            base64_csv = base64.b64encode(csv_bytes).decode('utf-8')
            return f"data:text/csv;base64,{base64_csv}"
        except Exception:
            return ""

