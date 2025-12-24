export interface TaggingConfig {
  api_key: string;
  model_name: string;
  num_pages: number;
  num_tags: number;
  exclusion_words?: string[];
}

export interface SinglePDFResponse {
  success: boolean;
  document_title: string;
  tags: string[];
  extracted_text_preview: string;
  processing_time: number;
  // OCR metadata
  is_scanned?: boolean;
  extraction_method?: string;
  ocr_confidence?: number;
  // Debug field
  raw_ai_response?: string;
  error?: string;
}

export interface BatchDocumentResult {
  title: string;
  success: boolean;
  tags: string[];
  error?: string;
}

export interface BatchSummary {
  documents: BatchDocumentResult[];
  errors: string[];
  statistics?: {
    total: number;
    processed: number;
    failed: number;
    success_rate: string;
  };
}

export interface BatchProcessResponse {
  success: boolean;
  total_documents: number;
  processed_count: number;
  failed_count: number;
  output_csv_url: string;
  summary_report: BatchSummary;
  processing_time: number;
}

export interface HealthCheckResponse {
  status: string;
  version: string;
  message: string;
}

export type ProcessingMode = 'single' | 'batch';
