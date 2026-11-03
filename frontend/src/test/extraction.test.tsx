import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { DocumentUploadZone } from '@/components/extraction/DocumentUploadZone'
import { WebCrawlModal } from '@/components/extraction/WebCrawlModal'
import { TableView } from '@/components/extraction/TableView'
import { ExtractionViewer } from '@/components/extraction/ExtractionViewer'
import { DocumentList } from '@/components/extraction/DocumentList'
import { ExtractionTelemetryCard } from '@/components/extraction/ExtractionTelemetryCard'
import { DocumentsView } from '@/views/user/DocumentsView'
import { extractionService } from '@/services/extractionService'
import type {
  DocumentDetailResponse,
  ExtractionResponse,
  ExtractionTelemetryResponse,
  StoredDocumentSummary,
  TableSummary,
} from '@/types/extraction'

// Sample Mock Data
const mockTelemetry: ExtractionTelemetryResponse = {
  total_documents: 14,
  total_extractions: 28,
  total_tables: 42,
  storage_backend: 'sqlite_wal',
  storage_status: 'healthy',
  supported_document_formats: ['.pdf', '.docx', '.xlsx'],
  supported_web_strategies: ['static', 'rendered'],
  storage_healthy: true,
}

const mockDoc1: StoredDocumentSummary = {
  document_id: 'doc-001-pdf',
  source_type: 'pdf',
  source_uri: 'annual_report.pdf',
  original_display_name: 'annual_report.pdf',
  mime_type: 'application/pdf',
  source_sha256: 'a1b2c3d4e5f6',
  normalized_content_sha256: 'f6e5d4c3b2a1',
  first_ingested_at: '2026-11-01T10:00:00Z',
  last_ingested_at: '2026-11-02T12:00:00Z',
  version_count: 1,
  current_version_id: 'v1-hash',
  current_extraction_id: 'ext-001',
  artifact_available: true,
  artifact_id: 'a1b2c3d4e5f6',
}

const mockDoc2: StoredDocumentSummary = {
  document_id: 'doc-002-web',
  source_type: 'web_page',
  source_uri: 'https://news.ycombinator.com',
  original_display_name: 'Hacker News Frontpage',
  mime_type: 'text/html',
  source_sha256: 'b2c3d4e5f6a1',
  normalized_content_sha256: '1a2b3c4d5e6f',
  first_ingested_at: '2026-11-02T08:00:00Z',
  last_ingested_at: '2026-11-02T08:00:00Z',
  version_count: 1,
  current_version_id: 'v1-web',
  current_extraction_id: 'ext-002',
  artifact_available: false,
  artifact_id: null,
}

const mockDetail: DocumentDetailResponse = {
  document: mockDoc1,
  extractions: [
    {
      extraction_id: 'ext-001',
      document_id: 'doc-001-pdf',
      version_id: 'v1-hash',
      extractor_name: 'IBM Docling (NativePdfPipeline)',
      extractor_version: '2.144.0',
      extraction_timestamp: '2026-11-02T12:00:00Z',
      duration_ms: 1240,
      status: 'SUCCESS',
      exit_code: 0,
      element_count: 48,
      table_count: 2,
      page_count: 4,
      word_count: 1840,
      extraction_record_sha256: 'rec-sha-256',
    },
  ],
  tables: [
    {
      table_id: 'tbl_financials_1',
      extraction_id: 'ext-001',
      document_id: 'doc-001-pdf',
      sheet_name: 'Income Statement',
      row_count: 3,
      column_count: 2,
      headers_json: '["Metric", "Value"]',
      created_at: '2026-11-02T12:00:00Z',
    },
  ],
  text_preview: 'Quarterly Financial Summary 2026.\nRevenue grew by 24% year-over-year.',
  markdown_preview: '# Quarterly Financial Summary 2026\n\nRevenue grew by **24%** year-over-year.',
  is_truncated: false,
}

const mockExtractionResponse: ExtractionResponse = {
  success: true,
  document_id: 'doc-new-123',
  extraction_id: 'ext-new-123',
  version_id: 'ver-new-123',
  original_display_name: 'quarterly_results.xlsx',
  mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  title: 'Quarterly Results 2026',
  is_duplicate: false,
  is_new_version: false,
  status: 'SUCCESS',
  element_count: 24,
  table_count: 3,
  page_count: 1,
  word_count: 650,
  tables: [
    {
      table_id: 'tbl_1',
      row_count: 10,
      column_count: 4,
      headers: ['Q1', 'Q2', 'Q3', 'Q4'],
      sheet_name: 'Quarterly Breakup',
      markdown: '| Q1 | Q2 | Q3 | Q4 |\n|---|---|---|---|\n| 10 | 20 | 30 | 40 |',
    },
  ],
  text_preview: 'Sample spreadsheet preview content',
  markdown_preview: '# Sample spreadsheet preview content',
  is_truncated: false,
  warnings: [],
}

describe('BRICK-007 Phase 9: React Extraction UI Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(extractionService, 'getTelemetry').mockResolvedValue(mockTelemetry)
    vi.spyOn(extractionService, 'listDocuments').mockResolvedValue({
      items: [mockDoc1, mockDoc2],
      total: 2,
      limit: 20,
      offset: 0,
    })
    vi.spyOn(extractionService, 'getDocumentDetails').mockResolvedValue(mockDetail)
  })

  // 1. DocumentUploadZone Tests
  describe('DocumentUploadZone Component', () => {
    it('renders drag-and-drop zone with format pills and upload button', () => {
      render(<DocumentUploadZone />)

      expect(screen.getByText(/Drop PDF, DOCX, or XLSX file here/i)).toBeInTheDocument()
      expect(screen.getByText('PDF', { exact: true })).toBeInTheDocument()
      expect(screen.getByText(/Word DOCX/i)).toBeInTheDocument()
      expect(screen.getByText(/Excel XLSX/i)).toBeInTheDocument()
    })

    it('rejects unsupported file extension immediately without API call', async () => {
      const uploadSpy = vi.spyOn(extractionService, 'uploadDocument')
      render(<DocumentUploadZone />)

      const fileInput = screen.getByTestId('file-upload-input')
      const invalidFile = new File(['binary content'], 'script.exe', { type: 'application/x-msdownload' })

      fireEvent.change(fileInput, { target: { files: [invalidFile] } })

      expect(await screen.findByRole('alert')).toHaveTextContent(/Unsupported file format '\.exe'/i)
      expect(uploadSpy).not.toHaveBeenCalled()
    })

    it('rejects files larger than 25 MB immediately without API call', async () => {
      const uploadSpy = vi.spyOn(extractionService, 'uploadDocument')
      render(<DocumentUploadZone />)

      const fileInput = screen.getByTestId('file-upload-input')
      // Create a 26 MB dummy file
      const largeFile = new File([new Uint8Array(26 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' })

      fireEvent.change(fileInput, { target: { files: [largeFile] } })

      expect(await screen.findByRole('alert')).toHaveTextContent(/exceeds maximum allowed limit of 25 MB/i)
      expect(uploadSpy).not.toHaveBeenCalled()
    })

    it('processes valid file upload and displays summary banner', async () => {
      const uploadSpy = vi.spyOn(extractionService, 'uploadDocument').mockResolvedValue(mockExtractionResponse)
      const onUploadSuccess = vi.fn()

      render(<DocumentUploadZone onUploadSuccess={onUploadSuccess} />)

      const fileInput = screen.getByTestId('file-upload-input')
      const validFile = new File(['valid pdf content'], 'test.pdf', { type: 'application/pdf' })

      fireEvent.change(fileInput, { target: { files: [validFile] } })

      expect(await screen.findByRole('status')).toBeInTheDocument()
      expect(screen.getByText('quarterly_results.xlsx')).toBeInTheDocument()
      expect(screen.getByText(/Tables: 3/i)).toBeInTheDocument()
      expect(uploadSpy).toHaveBeenCalledWith(validFile)
      expect(onUploadSuccess).toHaveBeenCalledWith(mockExtractionResponse)
    })
  })

  // 2. WebCrawlModal Tests
  describe('WebCrawlModal Component', () => {
    it('validates empty and non-http URLs', () => {
      render(<WebCrawlModal isOpen={true} onClose={vi.fn()} />)

      expect(screen.getByText('Crawl Public Web Page')).toBeInTheDocument()
      expect(screen.getByText(/Zero-Trust SSRF Policy Enforced/i)).toBeInTheDocument()

      const input = screen.getByLabelText(/Target URL/i)
      const submitBtn = screen.getByRole('button', { name: /Extract Web Page/i })

      fireEvent.change(input, { target: { value: 'ftp://invalidscheme.com' } })
      fireEvent.click(submitBtn)

      expect(screen.getByRole('alert')).toHaveTextContent(/URL must begin with http:\/\/ or https:\/\//i)
    })

    it('initiates streaming crawl and displays live progress', async () => {
      let registeredCallback: any = null
      vi.spyOn(extractionService, 'streamCrawlWebPage').mockImplementation((_req, onEvent) => {
        registeredCallback = onEvent
        return () => {}
      })

      const onCrawlSuccess = vi.fn()
      render(<WebCrawlModal isOpen={true} onClose={vi.fn()} onCrawlSuccess={onCrawlSuccess} />)

      const input = screen.getByLabelText(/Target URL/i)
      fireEvent.change(input, { target: { value: 'https://example.com/article' } })

      const submitBtn = screen.getByRole('button', { name: /Extract Web Page/i })
      fireEvent.click(submitBtn)

      // Verify streaming progress state
      expect(registeredCallback).not.toBeNull()
      act(() => {
        registeredCallback({ step: 'validating', message: 'Validating SSRF policy...' })
      })

      expect(await screen.findByText(/Validating Security.../i)).toBeInTheDocument()
      expect(screen.getByText(/Validating SSRF policy.../i)).toBeInTheDocument()

      // Complete stream
      act(() => {
        registeredCallback({ step: 'complete', result: mockExtractionResponse })
      })

      expect(onCrawlSuccess).toHaveBeenCalledWith(mockExtractionResponse)
    })
  })

  // 3. TableView Tests
  describe('TableView Component', () => {
    const sampleTable: TableSummary = {
      table_id: 'tbl_sample_1',
      row_count: 2,
      column_count: 3,
      headers: ['Region', 'Q1', 'Q2'],
      sheet_name: 'APAC Sales',
      markdown: '| Region | Q1 | Q2 |\n|---|---|---|\n| North | 100 | 120 |\n| South | 80 | 95 |',
    }

    it('renders table headers, rows, and sheet name', () => {
      render(<TableView table={sampleTable} />)

      expect(screen.getByText('Sheet: APAC Sales')).toBeInTheDocument()
      expect(screen.getByText('Region')).toBeInTheDocument()
      expect(screen.getByText('North')).toBeInTheDocument()
      expect(screen.getByText('100')).toBeInTheDocument()
      expect(screen.getByText('South')).toBeInTheDocument()
    })

    it('triggers CSV and JSON export callbacks', () => {
      const onDownloadCsv = vi.fn()
      const onDownloadJson = vi.fn()

      render(
        <TableView
          table={sampleTable}
          onDownloadCsv={onDownloadCsv}
          onDownloadJson={onDownloadJson}
        />,
      )

      fireEvent.click(screen.getByRole('button', { name: /CSV/i }))
      expect(onDownloadCsv).toHaveBeenCalledWith('tbl_sample_1')

      fireEvent.click(screen.getByRole('button', { name: /JSON/i }))
      expect(onDownloadJson).toHaveBeenCalledWith('tbl_sample_1')
    })
  })

  // 4. ExtractionViewer Tests
  describe('ExtractionViewer Component', () => {
    it('loads document details and switches across Plain Text, Markdown, Tables, and History tabs', async () => {
      render(<ExtractionViewer documentId="doc-001-pdf" isOpen={true} onClose={vi.fn()} />)

      // Wait for details to load
      expect(await screen.findByText('annual_report.pdf')).toBeInTheDocument()
      expect(screen.getByText(/Revenue grew by 24%/i)).toBeInTheDocument()

      // Switch to Markdown Tab
      fireEvent.click(screen.getByRole('button', { name: /Markdown/i }))
      expect(screen.getByText(/# Quarterly Financial Summary 2026/i)).toBeInTheDocument()

      // Switch to Tables Tab
      fireEvent.click(screen.getByRole('button', { name: /Tables/i }))
      expect(screen.getByText(/Sheet: Income Statement/i)).toBeInTheDocument()

      // Switch to History Tab
      fireEvent.click(screen.getByRole('button', { name: /Extractions/i }))
      expect(screen.getByText(/IBM Docling \(NativePdfPipeline\)/i)).toBeInTheDocument()
      expect(screen.getByText(/1240ms/i)).toBeInTheDocument()
    })

    it('supports copying text preview to clipboard', async () => {
      const writeTextMock = vi.fn().mockResolvedValue(undefined)
      Object.assign(navigator, {
        clipboard: {
          writeText: writeTextMock,
        },
      })

      render(<ExtractionViewer documentId="doc-001-pdf" isOpen={true} onClose={vi.fn()} />)

      expect(await screen.findByText('annual_report.pdf')).toBeInTheDocument()

      const copyBtn = screen.getByRole('button', { name: /Copy/i })
      fireEvent.click(copyBtn)

      expect(writeTextMock).toHaveBeenCalledWith(mockDetail.text_preview)
      expect(await screen.findByText(/Copied/i)).toBeInTheDocument()
    })
  })

  // 5. DocumentList Tests
  describe('DocumentList Component', () => {
    it('renders list of documents with source badges and action buttons', () => {
      const onView = vi.fn()
      const onDownload = vi.fn()
      const onDelete = vi.fn()

      render(
        <DocumentList
          documents={[mockDoc1, mockDoc2]}
          total={2}
          page={0}
          pageSize={20}
          onSelectSourceType={vi.fn()}
          onPageChange={vi.fn()}
          onViewDocument={onView}
          onDownloadDocument={onDownload}
          onDeleteDocument={onDelete}
        />,
      )

      expect(screen.getByText('annual_report.pdf')).toBeInTheDocument()
      expect(screen.getByText('Hacker News Frontpage')).toBeInTheDocument()
      expect(screen.getByText('pdf')).toBeInTheDocument()
      expect(screen.getByText('web_page')).toBeInTheDocument()

      // Click view button
      fireEvent.click(screen.getByLabelText(/View annual_report\.pdf/i))
      expect(onView).toHaveBeenCalledWith('doc-001-pdf')
    })

    it('opens delete confirmation dialog and confirms deletion', async () => {
      const onDelete = vi.fn().mockResolvedValue(undefined)

      render(
        <DocumentList
          documents={[mockDoc1]}
          total={1}
          page={0}
          pageSize={20}
          onSelectSourceType={vi.fn()}
          onPageChange={vi.fn()}
          onViewDocument={vi.fn()}
          onDownloadDocument={vi.fn()}
          onDeleteDocument={onDelete}
        />,
      )

      fireEvent.click(screen.getByLabelText(/Delete annual_report\.pdf/i))

      expect(await screen.findByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/Delete Ingested Document\?/i)).toBeInTheDocument()

      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Confirm Delete/i }))
      })
      expect(onDelete).toHaveBeenCalledWith('doc-001-pdf')
    })

    it('renders empty state when no documents match filter', () => {
      render(
        <DocumentList
          documents={[]}
          total={0}
          page={0}
          pageSize={20}
          selectedSourceType="xlsx"
          onSelectSourceType={vi.fn()}
          onPageChange={vi.fn()}
          onViewDocument={vi.fn()}
          onDownloadDocument={vi.fn()}
          onDeleteDocument={vi.fn()}
        />,
      )

      expect(screen.getByText('No documents found')).toBeInTheDocument()
      expect(screen.getByText(/No documents match filter 'xlsx'/i)).toBeInTheDocument()
    })
  })

  // 6. ExtractionTelemetryCard Tests
  describe('ExtractionTelemetryCard Component', () => {
    it('displays counts and storage health indicator', () => {
      render(<ExtractionTelemetryCard telemetry={mockTelemetry} />)

      expect(screen.getByText('14')).toBeInTheDocument() // Documents
      expect(screen.getByText('28')).toBeInTheDocument() // Extractions
      expect(screen.getByText('42')).toBeInTheDocument() // Tables
      expect(screen.getByText('Healthy')).toBeInTheDocument()
    })
  })

  // 7. Full DocumentsView Integration Test
  describe('DocumentsView Integration', () => {
    it('renders full hub with header, telemetry, upload zone, and document list', async () => {
      render(<DocumentsView />)

      expect(screen.getByText('Document Ingestion & Web Scraping')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Crawl Web Page/i })).toBeInTheDocument()

      // Documents loaded via service
      expect(await screen.findByText('annual_report.pdf')).toBeInTheDocument()
      expect(screen.getByText('Hacker News Frontpage')).toBeInTheDocument()

      // Open Crawl Modal
      fireEvent.click(screen.getByRole('button', { name: /Crawl Web Page/i }))
      expect(screen.getByText(/Crawl Public Web Page/i)).toBeInTheDocument()
    })
  })
})
