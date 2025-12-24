import { TaggingConfig, SinglePDFResponse, BatchProcessResponse, HealthCheckResponse } from './types';

// Default to localhost for development, can be overridden via env var for production
const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export class APIError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public details?: string
  ) {
    super(message);
    this.name = 'APIError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorMessage = 'Request failed';
    let details: string | undefined;
    
    try {
      const errorData = await response.json();
      errorMessage = errorData.detail || errorData.message || errorMessage;
      details = JSON.stringify(errorData);
    } catch {
      errorMessage = response.statusText || errorMessage;
    }
    
    throw new APIError(errorMessage, response.status, details);
  }
  
  return response.json();
}

export async function processSinglePDF(
  file: File | null,
  config: TaggingConfig,
  exclusionFile?: File | null,
  pdfUrl?: string
): Promise<SinglePDFResponse> {
  const formData = new FormData();
  
  if (file) {
  formData.append('pdf_file', file);
  }
  
  if (pdfUrl) {
    formData.append('pdf_url', pdfUrl);
  }
  
  formData.append('config', JSON.stringify(config));
  
  if (exclusionFile) {
    formData.append('exclusion_file', exclusionFile);
  }

  const response = await fetch(`${API_BASE}/api/single/process`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<SinglePDFResponse>(response);
}

export async function processBatchCSV(
  file: File,
  config: TaggingConfig,
  exclusionFile?: File | null
): Promise<BatchProcessResponse> {
  const formData = new FormData();
  formData.append('csv_file', file);
  formData.append('config', JSON.stringify(config));
  
  if (exclusionFile) {
    formData.append('exclusion_file', exclusionFile);
  }

  const response = await fetch(`${API_BASE}/api/batch/process`, {
    method: 'POST',
    body: formData,
  });

  return handleResponse<BatchProcessResponse>(response);
}

export async function checkHealth(): Promise<HealthCheckResponse> {
  const response = await fetch(`${API_BASE}/api/health`);
  return handleResponse<HealthCheckResponse>(response);
}

export async function getCSVTemplate(): Promise<{ template: string; columns: Array<{ name: string; required: boolean; description: string }> }> {
  const response = await fetch(`${API_BASE}/api/batch/template`);
  return handleResponse(response);
}

export function downloadCSV(dataUrl: string, filename: string = 'tagged_documents.csv'): void {
  const link = document.createElement('a');
  link.href = dataUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

/**
 * Get preview URL for a PDF URL.
 * Uses the proxy endpoint to bypass CORS restrictions.
 */
export function getPdfPreviewUrl(pdfUrl: string): string {
  return `${API_BASE}/api/single/preview?url=${encodeURIComponent(pdfUrl)}`;
}

