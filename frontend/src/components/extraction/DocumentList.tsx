import { useState } from 'react'
import {
  FileText,
  Globe,
  Trash2,
  Eye,
  Download,
  FileType,
  Calendar,
  Layers,
  Table as TableIcon,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import type { SourceType, StoredDocumentSummary } from '@/types/extraction'

interface DocumentListProps {
  documents: StoredDocumentSummary[]
  total: number
  page: number
  pageSize: number
  selectedSourceType?: string
  loading?: boolean
  onSelectSourceType: (type: string) => void
  onPageChange: (newPage: number) => void
  onViewDocument: (documentId: string) => void
  onDownloadDocument: (document: StoredDocumentSummary) => void
  onDeleteDocument: (documentId: string) => void
}

const SOURCE_FILTERS: { label: string; value: string }[] = [
  { label: 'All Sources', value: 'all' },
  { label: 'PDF', value: 'pdf' },
  { label: 'Word (DOCX)', value: 'docx' },
  { label: 'Excel (XLSX)', value: 'xlsx' },
  { label: 'Web Pages', value: 'web_page' },
]

export const DocumentList = ({
  documents,
  total,
  page,
  pageSize,
  selectedSourceType = 'all',
  loading = false,
  onSelectSourceType,
  onPageChange,
  onViewDocument,
  onDownloadDocument,
  onDeleteDocument,
}: DocumentListProps) => {
  const [deleteTarget, setDeleteTarget] = useState<StoredDocumentSummary | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const totalPages = Math.ceil(total / pageSize)

  const getSourceIcon = (type: SourceType) => {
    switch (type) {
      case 'pdf':
        return <FileType className="w-4 h-4 text-red-500" />
      case 'docx':
        return <FileText className="w-4 h-4 text-blue-500" />
      case 'xlsx':
        return <TableIcon className="w-4 h-4 text-emerald-500" />
      case 'web_page':
        return <Globe className="w-4 h-4 text-indigo-500" />
      default:
        return <FileText className="w-4 h-4 text-muted-foreground" />
    }
  }

  const getSourceBadgeClass = (type: SourceType) => {
    switch (type) {
      case 'pdf':
        return 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
      case 'docx':
        return 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
      case 'xlsx':
        return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
      case 'web_page':
        return 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20'
      default:
        return 'bg-muted text-muted-foreground border-border'
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setIsDeleting(true)
    try {
      await onDeleteDocument(deleteTarget.document_id)
      setDeleteTarget(null)
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* Filter Chips Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-border/60">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter documents by source type">
          {SOURCE_FILTERS.map((filter) => (
            <button
              key={filter.value}
              type="button"
              onClick={() => onSelectSourceType(filter.value)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                selectedSourceType === filter.value
                  ? 'bg-primary text-primary-foreground font-semibold shadow-sm'
                  : 'bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>

        <span className="text-xs text-muted-foreground font-mono">
          {total} {total === 1 ? 'document' : 'documents'} found
        </span>
      </div>

      {/* Loading state */}
      {loading ? (
        <div className="py-16 text-center text-muted-foreground space-y-2">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-primary" />
          <p className="text-xs">Loading document registry...</p>
        </div>
      ) : documents.length === 0 ? (
        /* Empty State */
        <div className="py-16 text-center border-2 border-dashed border-border/60 rounded-2xl p-8 bg-card/20 space-y-3">
          <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto text-muted-foreground">
            <FileText className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-foreground">No documents found</h3>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto">
              {selectedSourceType !== 'all'
                ? `No documents match filter '${selectedSourceType}'. Try selecting 'All Sources'.`
                : 'Upload a document or crawl a web page above to begin extraction.'}
            </p>
          </div>
        </div>
      ) : (
        /* Documents Table */
        <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground uppercase tracking-wider text-[11px] font-semibold">
                <tr>
                  <th className="py-3 px-4">Document</th>
                  <th className="py-3 px-4">Source</th>
                  <th className="py-3 px-4">Ingested Date</th>
                  <th className="py-3 px-4 text-center">Versions</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {documents.map((doc) => (
                  <tr
                    key={doc.document_id}
                    className="hover:bg-muted/30 transition-colors group"
                  >
                    {/* Document Name & URI */}
                    <td className="py-3.5 px-4 max-w-xs">
                      <div className="flex items-center gap-2.5">
                        <div className="shrink-0">{getSourceIcon(doc.source_type)}</div>
                        <div className="min-w-0">
                          <button
                            type="button"
                            onClick={() => onViewDocument(doc.document_id)}
                            className="text-left font-medium text-foreground hover:text-primary transition-colors truncate block max-w-xs text-xs"
                            title={doc.original_display_name}
                          >
                            {doc.original_display_name}
                          </button>
                          {doc.source_uri && doc.source_uri !== doc.original_display_name && (
                            <span
                              className="text-[11px] text-muted-foreground font-mono truncate block max-w-xs"
                              title={doc.source_uri}
                            >
                              {doc.source_uri}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Source Type Badge */}
                    <td className="py-3.5 px-4 whitespace-nowrap">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono uppercase font-semibold border ${getSourceBadgeClass(
                          doc.source_type,
                        )}`}
                      >
                        {doc.source_type}
                      </span>
                    </td>

                    {/* Ingested Date */}
                    <td className="py-3.5 px-4 whitespace-nowrap text-muted-foreground font-mono text-[11px]">
                      <div className="flex items-center gap-1.5">
                        <Calendar className="w-3.5 h-3.5 text-muted-foreground/60" />
                        {new Date(doc.last_ingested_at).toLocaleDateString()}
                      </div>
                    </td>

                    {/* Version Count */}
                    <td className="py-3.5 px-4 text-center whitespace-nowrap">
                      <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground font-mono bg-muted px-2 py-0.5 rounded">
                        <Layers className="w-3 h-3" />
                        v{doc.version_count}
                      </span>
                    </td>

                    {/* Action Buttons */}
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => onViewDocument(doc.document_id)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                          title="Inspect document and tables"
                          aria-label={`View ${doc.original_display_name}`}
                        >
                          <Eye className="w-4 h-4" />
                        </button>

                        {doc.raw_artifact_path && (
                          <button
                            type="button"
                            onClick={() => onDownloadDocument(doc)}
                            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                            title="Download original file"
                            aria-label={`Download ${doc.original_display_name}`}
                          >
                            <Download className="w-4 h-4" />
                          </button>
                        )}

                        <button
                          type="button"
                          onClick={() => setDeleteTarget(doc)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="Delete document"
                          aria-label={`Delete ${doc.original_display_name}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="p-3 bg-muted/20 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
              <span>
                Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, total)} of {total} documents
              </span>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={page === 0}
                  onClick={() => onPageChange(page - 1)}
                  className="px-3 py-1 rounded border border-border hover:bg-muted text-foreground disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="px-2 py-1 font-mono text-[11px]">
                  {page + 1} / {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages - 1}
                  onClick={() => onPageChange(page + 1)}
                  className="px-3 py-1 rounded border border-border hover:bg-muted text-foreground disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
          className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
        >
          <div className="bg-zinc-950 border border-zinc-800 text-zinc-100 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-start gap-3 text-destructive">
              <div className="p-2 rounded-full bg-destructive/10">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <h3 id="delete-dialog-title" className="text-base font-semibold text-foreground">
                  Delete Ingested Document?
                </h3>
                <p className="text-xs text-muted-foreground">
                  Permanently deletes <span className="font-semibold text-foreground font-mono">{deleteTarget.original_display_name}</span>,
                  all associated execution records, canonical JSON files, and extracted table exports.
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-2.5 pt-2 border-t border-border">
              <button
                type="button"
                autoFocus
                onClick={() => setDeleteTarget(null)}
                disabled={isDeleting}
                className="px-4 py-2 text-xs font-medium rounded-lg border border-border hover:bg-muted text-foreground disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDelete}
                disabled={isDeleting}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-destructive hover:bg-destructive/90 text-destructive-foreground flex items-center gap-1.5 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Confirm Delete'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
