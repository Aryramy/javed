import { useState, useEffect, useCallback } from 'react'
import {
  Globe,
  RefreshCw,
  FolderOpen,
} from 'lucide-react'
import { DocumentUploadZone } from '@/components/extraction/DocumentUploadZone'
import { DocumentList } from '@/components/extraction/DocumentList'
import { ExtractionViewer } from '@/components/extraction/ExtractionViewer'
import { WebCrawlModal } from '@/components/extraction/WebCrawlModal'
import { ExtractionTelemetryCard } from '@/components/extraction/ExtractionTelemetryCard'
import { extractionService } from '@/services/extractionService'
import type {
  ExtractionResponse,
  ExtractionTelemetryResponse,
  StoredDocumentSummary,
} from '@/types/extraction'

export const DocumentsView = () => {
  const [documents, setDocuments] = useState<StoredDocumentSummary[]>([])
  const [totalDocuments, setTotalDocuments] = useState(0)
  const [page, setPage] = useState(0)
  const [pageSize] = useState(20)
  const [sourceType, setSourceType] = useState('all')
  const [loading, setLoading] = useState(false)
  const [telemetry, setTelemetry] = useState<ExtractionTelemetryResponse | null>(null)
  const [telemetryLoading, setTelemetryLoading] = useState(false)

  // Viewer & Modal State
  const [viewerDocId, setViewerDocId] = useState<string | null>(null)
  const [isViewerOpen, setIsViewerOpen] = useState(false)
  const [isCrawlModalOpen, setIsCrawlModalOpen] = useState(false)

  const loadDocuments = useCallback(async () => {
    setLoading(true)
    try {
      const data = await extractionService.listDocuments(
        pageSize,
        page * pageSize,
        sourceType,
      )
      setDocuments(data.items)
      setTotalDocuments(data.total)
    } catch (err) {
      console.error('Failed loading documents:', err)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, sourceType])

  const loadTelemetry = useCallback(async () => {
    setTelemetryLoading(true)
    try {
      const data = await extractionService.getTelemetry()
      setTelemetry(data)
    } catch (err) {
      console.error('Failed loading telemetry:', err)
    } finally {
      setTelemetryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  useEffect(() => {
    loadTelemetry()
  }, [loadTelemetry])

  const handleRefreshAll = () => {
    loadDocuments()
    loadTelemetry()
  }

  const handleUploadSuccess = (response: ExtractionResponse) => {
    handleRefreshAll()
    // Open viewer for newly ingested document
    setViewerDocId(response.document_id)
    setIsViewerOpen(true)
  }

  const handleCrawlSuccess = (response: ExtractionResponse) => {
    handleRefreshAll()
    // Open viewer for newly crawled document
    setViewerDocId(response.document_id)
    setIsViewerOpen(true)
  }

  const handleViewDocument = (documentId: string) => {
    setViewerDocId(documentId)
    setIsViewerOpen(true)
  }

  const handleDownloadDocument = async (doc: StoredDocumentSummary) => {
    try {
      await extractionService.downloadRawDocument(doc.document_id, doc.original_display_name)
    } catch (err) {
      alert(`Download failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const handleDeleteDocument = async (documentId: string) => {
    try {
      await extractionService.deleteDocument(documentId)
      handleRefreshAll()
    } catch (err) {
      alert(`Delete failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const handleFilterChange = (newType: string) => {
    setSourceType(newType)
    setPage(0)
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-border">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-primary/10 text-primary">
              <FolderOpen className="w-5 h-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">
              Document Ingestion & Web Scraping
            </h1>
          </div>
          <p className="text-xs text-muted-foreground">
            Local PDF, Word DOCX, and Excel XLSX extraction via IBM Docling and public web extraction via Crawl4AI
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <button
            type="button"
            onClick={() => setIsCrawlModalOpen(true)}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-xs font-semibold rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm transition-colors"
          >
            <Globe className="w-4 h-4" />
            Crawl Web Page
          </button>

          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={loading || telemetryLoading}
            className="p-2 rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            title="Refresh documents"
            aria-label="Refresh documents"
          >
            <RefreshCw className={`w-4 h-4 ${loading || telemetryLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Telemetry Status Card */}
      <ExtractionTelemetryCard telemetry={telemetry} loading={telemetryLoading} />

      {/* Document Upload Zone */}
      <div className="space-y-2">
        <h2 className="text-xs font-semibold text-foreground uppercase tracking-wider">
          Upload New Document
        </h2>
        <DocumentUploadZone onUploadSuccess={handleUploadSuccess} />
      </div>

      {/* Document Registry Table */}
      <div className="space-y-2 pt-2">
        <h2 className="text-xs font-semibold text-foreground uppercase tracking-wider">
          Ingested Documents Registry
        </h2>
        <DocumentList
          documents={documents}
          total={totalDocuments}
          page={page}
          pageSize={pageSize}
          selectedSourceType={sourceType}
          loading={loading}
          onSelectSourceType={handleFilterChange}
          onPageChange={setPage}
          onViewDocument={handleViewDocument}
          onDownloadDocument={handleDownloadDocument}
          onDeleteDocument={handleDeleteDocument}
        />
      </div>

      {/* Extraction Detail Viewer Modal */}
      <ExtractionViewer
        documentId={viewerDocId}
        isOpen={isViewerOpen}
        onClose={() => {
          setIsViewerOpen(false)
          setViewerDocId(null)
        }}
      />

      {/* Web Crawl Modal */}
      <WebCrawlModal
        isOpen={isCrawlModalOpen}
        onClose={() => setIsCrawlModalOpen(false)}
        onCrawlSuccess={handleCrawlSuccess}
      />
    </div>
  )
}
