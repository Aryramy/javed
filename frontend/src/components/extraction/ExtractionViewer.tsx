import { useState, useEffect, useRef } from 'react'
import {
  X,
  FileText,
  Calendar,
  Layers,
  Copy,
  Check,
  Download,
  AlertTriangle,
  Clock,
  Table as TableIcon,
  Code,
  History,
  ChevronLeft,
  ChevronRight,
  Eye,
  Info,
} from 'lucide-react'
import { TableView } from './TableView'
import { MarkdownContent } from '../chat/MarkdownContent'
import { extractionService } from '@/services/extractionService'
import type { DocumentDetailResponse, TableSummary } from '@/types/extraction'
import {
  formatDocumentDate,
  formatExtractionTimestamp,
  formatDuration,
  getStatusBadgeClasses,
  normalizePageMarkers,
} from '@/utils/formatters'

const PAGE_SIZE = 25000

interface ExtractionViewerProps {
  documentId: string | null
  isOpen: boolean
  onClose: () => void
}

type TabType = 'text' | 'markdown' | 'tables' | 'history'

export const ExtractionViewer = ({
  documentId,
  isOpen,
  onClose,
}: ExtractionViewerProps) => {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [activeTab, setActiveTab] = useState<TabType>('text')
  const [markdownMode, setMarkdownMode] = useState<'preview' | 'source'>('preview')
  const [detail, setDetail] = useState<DocumentDetailResponse | null>(null)
  const [currentOffset, setCurrentOffset] = useState<number>(0)
  const [loading, setLoading] = useState(false)
  const [pagingLoading, setPagingLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null)

  // Fetch document details when opened or when documentId changes
  useEffect(() => {
    if (!isOpen || !documentId) {
      setDetail(null)
      setCurrentOffset(0)
      return
    }

    let isMounted = true
    setLoading(true)
    setError(null)
    setCurrentOffset(0)

    extractionService
      .getDocumentDetails(documentId, PAGE_SIZE, 0)
      .then((data) => {
        if (isMounted) {
          setDetail(data)
          // Default to tables tab if document is primarily spreadsheet with tables
          if (data.document.source_type === 'xlsx' && data.tables.length > 0) {
            setActiveTab('tables')
          } else {
            setActiveTab('text')
          }
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed loading document details')
        }
      })
      .finally(() => {
        if (isMounted) {
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [isOpen, documentId])

  // Handle bounded pagination page turns
  const handlePageChange = async (newOffset: number) => {
    if (!documentId || newOffset < 0) return
    setPagingLoading(true)
    try {
      const data = await extractionService.getDocumentDetails(documentId, PAGE_SIZE, newOffset)
      setDetail(data)
      setCurrentOffset(newOffset)
    } catch (err) {
      alert(`Failed to load page: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setPagingLoading(false)
    }
  }

  // Native <dialog> lifecycle
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (isOpen) {
      if (!dialog.open) {
        try {
          dialog.showModal()
        } catch {
          // ignore if test environment doesn't implement showModal
        }
      }
    } else {
      if (dialog.open) {
        dialog.close()
      }
    }
  }, [isOpen])

  const handleBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === dialogRef.current) {
      onClose()
    }
  }

  if (!isOpen) return null

  const handleCopyPreview = async (content: string) => {
    await navigator.clipboard.writeText(content)
    const charCount = content.length
    setCopyFeedback(`Copied ${charCount.toLocaleString()} chars`)
    setTimeout(() => setCopyFeedback(null), 2500)
  }

  const handleDownloadRaw = async () => {
    if (!detail) return
    try {
      await extractionService.downloadRawDocument(
        detail.document.document_id,
        detail.document.original_display_name,
      )
    } catch (err) {
      alert(`Download failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const handleDownloadTableCsv = async (tableId: string) => {
    if (!detail) return
    try {
      const blob = await extractionService.getTableData(detail.document.document_id, tableId, 'csv')
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${tableId}.csv`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      alert(`Export failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  const handleDownloadTableJson = async (tableId: string) => {
    if (!detail) return
    try {
      const blob = await extractionService.getTableData(detail.document.document_id, tableId, 'json')
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${tableId}.json`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      alert(`Export failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  // Convert stored table info to table summary format for TableView component
  const tablesSummaries: TableSummary[] =
    detail?.tables?.map((t) => {
      let headers: string[] = []
      try {
        headers = JSON.parse(t.headers_json || '[]')
      } catch {
        headers = []
      }
      return {
        table_id: t.table_id,
        row_count: t.row_count,
        column_count: t.column_count,
        headers,
        sheet_name: t.sheet_name,
      }
    }) || []

  // Compute active preview content & pagination limits with graceful legacy fallback
  const fallbackText = (detail?.extractions?.[0] as unknown as { full_text?: string })?.full_text || ''
  const activeContent =
    activeTab === 'text'
      ? (detail?.text_preview ?? fallbackText)
      : (detail?.markdown_preview ?? fallbackText)
  const totalChars =
    activeTab === 'text'
      ? (detail?.total_text_chars || activeContent.length)
      : (detail?.total_markdown_chars || activeContent.length)

  const offset = detail?.offset_chars ?? currentOffset
  const showingStart = totalChars > 0 ? offset + 1 : 0
  const showingEnd = Math.min(offset + activeContent.length, totalChars)

  const hasNextPage = offset + activeContent.length < totalChars
  const hasPrevPage = offset > 0

  const isOutputsIdentical =
    Boolean(detail?.text_preview &&
    detail?.markdown_preview &&
    detail.text_preview === detail.markdown_preview &&
    detail.text_preview.length > 0)

  // Document actually exceeds 25,000 character limit
  const isDocTruncated = Boolean(detail?.is_truncated && (totalChars > PAGE_SIZE || activeContent.length >= PAGE_SIZE))

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={handleBackdropClick}
      aria-labelledby="viewer-title"
      className="fixed inset-0 m-auto z-50 w-full max-w-4xl h-[85vh] max-h-[85vh] p-0 rounded-2xl border border-zinc-800 bg-zinc-950 text-zinc-100 shadow-2xl flex flex-col overflow-hidden backdrop:bg-black/75 backdrop:backdrop-blur-sm"
      style={{ overscrollBehavior: 'contain' }}
    >
      {/* Header */}
      <div className="p-5 border-b border-zinc-800 bg-zinc-900/90 flex items-start justify-between gap-4 shrink-0">
        <div className="space-y-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs px-2 py-0.5 rounded font-mono uppercase font-semibold bg-primary/10 text-primary border border-primary/20">
              {detail?.document.source_type || 'DOC'}
            </span>
            <h2
              id="viewer-title"
              className="text-lg font-semibold text-foreground truncate"
              title={detail?.document.original_display_name}
            >
              {detail?.document.original_display_name || 'Document Details'}
            </h2>
          </div>

          {detail && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground font-mono">
              <span title="Document ID">ID: {detail.document.document_id}</span>
              <span>•</span>
              <span title="Content Hash">SHA: {detail.document.source_sha256.slice(0, 10)}...</span>
              <span>•</span>
              <span className="flex items-center gap-1" title="Last Ingested Date">
                <Calendar className="w-3 h-3" />
                {formatDocumentDate(detail.document.last_ingested_at)}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1" title="Document Version">
                <Layers className="w-3 h-3" />
                v{detail.document.version_count}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {detail?.document.artifact_available && (
            <button
              type="button"
              onClick={handleDownloadRaw}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border hover:bg-muted text-foreground transition-colors"
              title="Download original file"
            >
              <Download className="w-3.5 h-3.5" />
              Raw Source
            </button>
          )}

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Close document viewer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Tabs Bar */}
      <div className="px-5 border-b border-zinc-800 bg-zinc-900/50 flex items-center justify-between gap-4 shrink-0">
        <nav className="flex space-x-1" aria-label="Viewer tabs">
          <button
            type="button"
            onClick={() => setActiveTab('text')}
            className={`py-3 px-3.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'text'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            Plain Text
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('markdown')}
            className={`py-3 px-3.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'markdown'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Code className="w-3.5 h-3.5" />
            Markdown
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('tables')}
            className={`py-3 px-3.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'tables'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            Tables ({tablesSummaries.length})
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('history')}
            className={`py-3 px-3.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-colors ${
              activeTab === 'history'
                ? 'border-primary text-primary font-semibold'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <History className="w-3.5 h-3.5" />
            Extractions ({detail?.extractions.length || 0})
          </button>
        </nav>

        {/* Action Controls for Text/Markdown (Copy Preview & Pagination) */}
        {(activeTab === 'text' || activeTab === 'markdown') && detail && (
          <div className="flex items-center gap-2">
            {activeTab === 'markdown' && (
              <div className="flex items-center rounded-lg border border-zinc-800 bg-zinc-900 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setMarkdownMode('preview')}
                  className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
                    markdownMode === 'preview'
                      ? 'bg-primary/20 text-primary font-medium'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                  title="Render formatted preview"
                >
                  <Eye className="w-3 h-3" />
                  Preview
                </button>
                <button
                  type="button"
                  onClick={() => setMarkdownMode('source')}
                  className={`px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
                    markdownMode === 'source'
                      ? 'bg-primary/20 text-primary font-medium'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                  title="View raw markdown source"
                >
                  <Code className="w-3 h-3" />
                  Source
                </button>
              </div>
            )}

            <button
              type="button"
              onClick={() => handleCopyPreview(activeContent)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-border hover:bg-muted text-foreground transition-colors"
              title="Copy visible preview characters to clipboard"
            >
              {copyFeedback ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-emerald-400">{copyFeedback}</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Copy Preview
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 min-h-0 overflow-y-auto p-6 space-y-4">
        {loading && (
          <div className="py-12 flex flex-col items-center justify-center text-muted-foreground space-y-2">
            <Clock className="w-6 h-6 animate-spin text-primary" />
            <p className="text-xs">Loading document details...</p>
          </div>
        )}

        {error && (
          <div className="p-4 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold">Unable to load document</p>
              <p className="text-xs mt-1 opacity-90">{error}</p>
            </div>
          </div>
        )}

        {!loading && !error && !detail && (
          <div className="py-12 flex flex-col items-center justify-center text-muted-foreground text-xs space-y-2">
            <FileText className="w-8 h-8 opacity-40 mb-2" />
            <p className="font-medium text-foreground">No document details available</p>
            <p>Please select a document from the registry.</p>
          </div>
        )}

        {!loading && !error && detail && (
          <>
            {/* TAB 1: PLAIN TEXT */}
            {activeTab === 'text' && (
              <div className="space-y-3">
                {/* Truncation warning pill: strictly on text/markdown when document exceeds page */}
                {isDocTruncated && (
                  <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>Document text is bounded to 25,000 characters per page. Use navigation controls below to step through full content.</span>
                  </div>
                )}

                {isOutputsIdentical && (
                  <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs flex items-center gap-2 font-mono">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>Extractor produced identical plain text and markdown representations for this document.</span>
                  </div>
                )}

                {/* Character Counter & Bounded Pagination */}
                <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                  <span>
                    Showing {showingStart.toLocaleString()}–{showingEnd.toLocaleString()} of {totalChars.toLocaleString()} characters
                  </span>

                  {(hasPrevPage || hasNextPage) && (
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handlePageChange(Math.max(offset - PAGE_SIZE, 0))}
                        disabled={!hasPrevPage || pagingLoading}
                        className="p-1 rounded border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Previous page"
                        aria-label="Previous character page"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePageChange(offset + PAGE_SIZE)}
                        disabled={!hasNextPage || pagingLoading}
                        className="p-1 rounded border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Next page"
                        aria-label="Next character page"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>

                <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 font-mono text-xs text-zinc-200 whitespace-pre-wrap leading-relaxed select-text max-h-[55vh] overflow-y-auto">
                  {normalizePageMarkers(activeContent) || 'No plain text extracted for this document.'}
                </div>
              </div>
            )}

            {/* TAB 2: MARKDOWN */}
            {activeTab === 'markdown' && (
              <div className="space-y-3">
                {/* Truncation warning pill: strictly on text/markdown when document exceeds page */}
                {isDocTruncated && (
                  <div className="p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                    <span>Document markdown is bounded to 25,000 characters per page. Use navigation controls below to step through full content.</span>
                  </div>
                )}

                {isOutputsIdentical && (
                  <div className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs flex items-center gap-2 font-mono">
                    <Info className="w-3.5 h-3.5 shrink-0" />
                    <span>Extractor produced identical plain text and markdown representations for this document.</span>
                  </div>
                )}

                {/* Character Counter & Bounded Pagination */}
                <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                  <span>
                    Showing {showingStart.toLocaleString()}–{showingEnd.toLocaleString()} of {totalChars.toLocaleString()} characters
                  </span>

                  {(hasPrevPage || hasNextPage) && (
                    <div className="flex items-center gap-1.5">
                      <button
                        type="button"
                        onClick={() => handlePageChange(Math.max(offset - PAGE_SIZE, 0))}
                        disabled={!hasPrevPage || pagingLoading}
                        className="p-1 rounded border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Previous page"
                        aria-label="Previous character page"
                      >
                        <ChevronLeft className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={() => handlePageChange(offset + PAGE_SIZE)}
                        disabled={!hasNextPage || pagingLoading}
                        className="p-1 rounded border border-border hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Next page"
                        aria-label="Next character page"
                      >
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>

                {markdownMode === 'preview' ? (
                  <div className="p-5 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-200 select-text max-h-[55vh] overflow-y-auto">
                    <MarkdownContent content={normalizePageMarkers(activeContent) || 'No markdown extracted for this document.'} />
                  </div>
                ) : (
                  <div className="p-4 rounded-xl bg-zinc-900 border border-zinc-800 font-mono text-xs text-zinc-200 whitespace-pre-wrap leading-relaxed select-text max-h-[55vh] overflow-y-auto">
                    {activeContent || 'No markdown extracted for this document.'}
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: TABLES */}
            {activeTab === 'tables' && (
              <div className="space-y-6">
                {tablesSummaries.length > 0 ? (
                  tablesSummaries.map((table, idx) => (
                    <TableView
                      key={table.table_id || idx}
                      table={table}
                      documentId={detail.document.document_id}
                      onDownloadCsv={handleDownloadTableCsv}
                      onDownloadJson={handleDownloadTableJson}
                    />
                  ))
                ) : (
                  <div className="py-12 text-center text-muted-foreground text-xs space-y-1">
                    <TableIcon className="w-8 h-8 mx-auto opacity-40 mb-2" />
                    <p className="font-medium text-foreground">No structured tables extracted</p>
                    <p>This document did not contain table representations.</p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 4: EXTRACTIONS HISTORY */}
            {activeTab === 'history' && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">
                  Execution Run Ledger
                </h3>
                <div className="divide-y divide-zinc-800 border border-zinc-800 rounded-xl overflow-hidden bg-zinc-900">
                  {detail.extractions.map((rec) => {
                    const statusClass = getStatusBadgeClasses(rec.status)
                    const durationText = formatDuration(rec.duration_ms)
                    const timestampText = formatExtractionTimestamp(rec.extracted_at || rec.extraction_timestamp)

                    return (
                      <div key={rec.extraction_id} className="p-3.5 space-y-2 hover:bg-zinc-800/40 transition-colors">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold uppercase ${statusClass}`}
                            >
                              {rec.status}
                            </span>
                            <span className="text-xs font-medium text-foreground font-mono">
                              {rec.extractor_name} v{rec.extractor_version}
                            </span>
                            <span className="text-[10px] text-muted-foreground font-mono" title="Extraction ID">
                              ({rec.extraction_id.slice(0, 12)})
                            </span>
                          </div>
                          <span
                            className="text-[11px] text-muted-foreground font-mono flex items-center gap-1"
                            title="Execution duration"
                          >
                            <Clock className="w-3 h-3 text-cyan-400" />
                            {durationText}
                          </span>
                        </div>

                        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground font-mono">
                          <span title="Extraction timestamp">Timestamp: {timestampText}</span>
                          <span>Elements: {rec.element_count}</span>
                          <span>Tables: {rec.table_count}</span>
                          {rec.page_count && <span>Pages: {rec.page_count}</span>}
                          {rec.word_count && <span>Words: {rec.word_count.toLocaleString()}</span>}
                        </div>

                        {rec.error_message && (
                          <div className="p-2 rounded bg-destructive/10 text-destructive text-xs font-mono">
                            {rec.error_code && `[${rec.error_code}] `}
                            {rec.error_message}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </dialog>
  )
}
