/**
 * Type definitions for Document Ingestion, Web Extraction, and Metadata Registry.
 */

export type SourceType = 'web_page' | 'pdf' | 'docx' | 'xlsx'

export type WebCrawlStrategy = 'static' | 'rendered'

export interface TableSummary {
  table_id?: string | null
  row_count: number
  column_count: number
  headers: string[]
  sheet_name?: string | null
  markdown?: string
}

export interface StoredDocumentSummary {
  document_id: string
  source_type: SourceType
  source_uri?: string | null
  relative_source_ref?: string | null
  original_display_name: string
  source_title?: string | null
  mime_type: string
  source_sha256: string
  normalized_content_sha256: string
  first_ingested_at: string
  last_ingested_at: string
  version_count: number
  current_version_id: string
  current_extraction_id: string
  artifact_available: boolean
  artifact_id?: string | null
  metadata_json?: string | null
}

export interface StoredExtractionRecord {
  extraction_id: string
  document_id: string
  version_id: string
  extractor_name: string
  extractor_version: string
  extracted_at?: string
  extraction_timestamp?: string
  duration_ms?: number | null
  status: string
  exit_code?: number
  element_count: number
  table_count: number
  page_count?: number | null
  word_count?: number | null
  character_count?: number | null
  raw_byte_count?: number | null
  extraction_record_sha256: string
  canonical_json_available?: boolean
  canonical_json_id?: string | null
  error_code?: string | null
  error_message?: string | null
  warnings_json?: string | null
  execution_metadata_json?: string | null
}

export interface StoredTableInfo {
  table_id: string
  extraction_id: string
  document_id: string
  sheet_name?: string | null
  row_count: number
  column_count: number
  headers_json: string
  csv_available?: boolean
  json_available?: boolean
  created_at: string
}

export interface ExtractionResponse {
  success: boolean
  document_id: string
  extraction_id: string
  version_id: string
  source_uri?: string | null
  original_display_name: string
  mime_type: string
  title?: string | null
  is_duplicate: boolean
  is_new_version: boolean
  status: string
  element_count: number
  table_count: number
  page_count?: number | null
  word_count?: number | null
  tables: TableSummary[]
  text_preview: string
  markdown_preview: string
  is_truncated: boolean
  warnings: string[]
}

export interface DocumentListResponse {
  items: StoredDocumentSummary[]
  total: number
  limit: number
  offset: number
}

export interface DocumentDetailResponse {
  document: StoredDocumentSummary
  extractions: StoredExtractionRecord[]
  tables: StoredTableInfo[]
  text_preview: string
  markdown_preview: string
  is_truncated: boolean
  offset_chars?: number
  total_text_chars?: number
  total_markdown_chars?: number
}

export interface ExtractionTelemetryResponse {
  total_documents: number
  total_extractions: number
  total_tables: number
  storage_backend: string
  storage_status: string
  supported_document_formats: string[]
  supported_web_strategies: string[]
  storage_healthy: boolean
}

export interface DeleteDocumentResponse {
  success: boolean
  document_id: string
  deleted: boolean
  message: string
}

export interface CrawlRequest {
  url: string
  strategy: WebCrawlStrategy
  max_chars?: number
  timeout_seconds?: number
}

export interface CrawlProgressEvent {
  step: 'validating' | 'fetching' | 'complete' | 'error'
  message?: string
  error?: string
  result?: ExtractionResponse
}

