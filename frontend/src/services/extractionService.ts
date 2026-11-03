/**
 * Frontend Extraction Service for document ingestion, web scraping, and metadata catalog.
 */

import type {
  CrawlProgressEvent,
  CrawlRequest,
  DeleteDocumentResponse,
  DocumentDetailResponse,
  DocumentListResponse,
  ExtractionResponse,
  ExtractionTelemetryResponse,
  StoredExtractionRecord,
  StoredTableInfo,
} from '@/types/extraction'

const DEFAULT_TIMEOUT_MS = 60000 // 60s for extraction operations

export class ExtractionServiceError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ExtractionServiceError'
    this.status = status
    this.code = code
  }
}

async function requestJson<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...options.headers,
      },
    })

    if (!res.ok) {
      let code = 'EXTRACTION_ERROR'
      let message = `Request failed with status ${res.status}`
      try {
        const errorData = await res.json()
        if (typeof errorData?.detail === 'string') {
          message = errorData.detail
        } else if (errorData?.detail?.message) {
          message = errorData.detail.message
          code = errorData.detail.code || code
        } else if (errorData?.error?.message) {
          message = errorData.error.message
          code = errorData.error.code || code
        }
      } catch {
        // Response was not JSON
      }
      throw new ExtractionServiceError(message, res.status, code)
    }

    return (await res.json()) as T
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ExtractionServiceError(`Extraction request timed out after ${timeoutMs}ms`, 408, 'TIMEOUT')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export const extractionService = {
  /**
   * Upload a local document file (PDF, DOCX, XLSX) and extract structured content.
   */
  async uploadDocument(file: File, maxChars = 25000): Promise<ExtractionResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const url = `/api/v1/extraction/upload?max_chars=${encodeURIComponent(maxChars)}`

    return requestJson<ExtractionResponse>(url, {
      method: 'POST',
      body: formData,
      // Do not set Content-Type header; browser sets multipart boundary automatically
    }, 120000) // 120s max for heavy document parsing
  },

  /**
   * Crawl and extract structured content from a public web page.
   */
  async crawlWebPage(req: CrawlRequest): Promise<ExtractionResponse> {
    return requestJson<ExtractionResponse>('/api/v1/extraction/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }, (req.timeout_seconds || 30) * 1000 + 5000)
  },

  /**
   * Stream real-time progress events during web crawling using Server-Sent Events (SSE).
   */
  streamCrawlWebPage(
    req: CrawlRequest,
    onEvent: (event: CrawlProgressEvent) => void,
  ): () => void {
    const controller = new AbortController()

    const executeStream = async () => {
      try {
        const res = await fetch('/api/v1/extraction/crawl/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(req),
          signal: controller.signal,
        })

        if (!res.ok) {
          let errText = `Server returned status ${res.status}`
          try {
            const errJson = await res.json()
            errText = errJson.detail || errText
          } catch {
            // ignore
          }
          onEvent({ step: 'error', error: errText })
          return
        }

        const reader = res.body?.getReader()
        if (!reader) {
          onEvent({ step: 'error', error: 'Response body is not readable' })
          return
        }

        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')
          buffer = parts.pop() || ''

          for (const block of parts) {
            const lines = block.split('\n')
            let eventType = 'message'
            let eventData = ''

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                eventType = line.slice(7).trim()
              } else if (line.startsWith('data: ')) {
                eventData = line.slice(6).trim()
              }
            }

            if (eventData) {
              try {
                const parsed = JSON.parse(eventData)
                if (eventType === 'progress') {
                  onEvent({ step: parsed.step || 'fetching', message: parsed.message })
                } else if (eventType === 'complete') {
                  onEvent({ step: 'complete', result: parsed })
                } else if (eventType === 'error') {
                  onEvent({ step: 'error', error: parsed.error })
                }
              } catch {
                // Ignore malformed json
              }
            }
          }
        }
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') {
          return // User cancelled
        }
        onEvent({ step: 'error', error: err instanceof Error ? err.message : String(err) })
      }
    }

    executeStream()

    return () => {
      controller.abort()
    }
  },

  /**
   * List ingested documents with pagination and optional source type filtering.
   */
  async listDocuments(
    limit = 50,
    offset = 0,
    sourceType?: string,
  ): Promise<DocumentListResponse> {
    const params = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    })
    if (sourceType && sourceType !== 'all') {
      params.set('source_type', sourceType)
    }

    return requestJson<DocumentListResponse>(`/api/v1/extraction/documents?${params.toString()}`)
  },

  /**
   * Retrieve full document details including metadata, historical extractions, and preview.
   */
  async getDocumentDetails(documentId: string, maxChars = 25000): Promise<DocumentDetailResponse> {
    return requestJson<DocumentDetailResponse>(
      `/api/v1/extraction/documents/${encodeURIComponent(documentId)}?max_chars=${encodeURIComponent(maxChars)}`,
    )
  },

  /**
   * Retrieve historical extraction records for a document.
   */
  async listDocumentExtractions(documentId: string): Promise<StoredExtractionRecord[]> {
    return requestJson<StoredExtractionRecord[]>(
      `/api/v1/extraction/documents/${encodeURIComponent(documentId)}/extractions`,
    )
  },

  /**
   * Retrieve standalone exported tables for a document.
   */
  async listDocumentTables(documentId: string): Promise<StoredTableInfo[]> {
    return requestJson<StoredTableInfo[]>(
      `/api/v1/extraction/documents/${encodeURIComponent(documentId)}/tables`,
    )
  },

  /**
   * Download table export data in JSON or CSV format.
   */
  async getTableData(
    documentId: string,
    tableId: string,
    format: 'json' | 'csv' = 'json',
  ): Promise<Blob> {
    const res = await fetch(
      `/api/v1/extraction/documents/${encodeURIComponent(documentId)}/tables/${encodeURIComponent(tableId)}?format=${format}`,
    )
    if (!res.ok) {
      throw new ExtractionServiceError(`Failed exporting table: ${res.statusText}`, res.status)
    }
    return res.blob()
  },

  /**
   * Download unaltered raw source document file.
   */
  async downloadRawDocument(documentId: string, filename?: string): Promise<void> {
    const res = await fetch(`/api/v1/extraction/documents/${encodeURIComponent(documentId)}/download`)
    if (!res.ok) {
      throw new ExtractionServiceError(`Failed downloading document: ${res.statusText}`, res.status)
    }

    const blob = await res.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || `document_${documentId}`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  },

  /**
   * Permanently delete a document entity and associated artifacts.
   */
  async deleteDocument(documentId: string): Promise<DeleteDocumentResponse> {
    return requestJson<DeleteDocumentResponse>(
      `/api/v1/extraction/documents/${encodeURIComponent(documentId)}`,
      { method: 'DELETE' },
    )
  },

  /**
   * Retrieve developer mode extraction telemetry and health.
   */
  async getTelemetry(): Promise<ExtractionTelemetryResponse> {
    return requestJson<ExtractionTelemetryResponse>('/api/v1/extraction/telemetry')
  },
}

