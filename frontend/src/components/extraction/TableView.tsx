import { useState } from 'react'
import { Download, Table as TableIcon, Copy, Check } from 'lucide-react'
import type { TableSummary } from '@/types/extraction'

interface TableViewProps {
  table: TableSummary
  documentId?: string
  onDownloadCsv?: (tableId: string) => void
  onDownloadJson?: (tableId: string) => void
}

export const TableView = ({
  table,
  documentId: _documentId,
  onDownloadCsv,
  onDownloadJson,
}: TableViewProps) => {
  const [copied, setCopied] = useState(false)
  const [page, setPage] = useState(0)
  const pageSize = 10

  // Parse markdown representation or headers if rows not directly provided
  const headers = table.headers || []

  // If table has markdown, we can derive rows or provide copy
  const handleCopyMarkdown = async () => {
    if (table.markdown) {
      await navigator.clipboard.writeText(table.markdown)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Parse rows from markdown if available
  const parsedRows: string[][] = []
  if (table.markdown) {
    const lines = table.markdown.trim().split('\n')
    // Skip header and separator (lines 0 and 1)
    for (let i = 2; i < lines.length; i++) {
      const line = lines[i].trim()
      if (line.startsWith('|') && line.endsWith('|')) {
        const cells = line
          .slice(1, -1)
          .split('|')
          .map((c) => c.trim())
        parsedRows.push(cells)
      }
    }
  }

  const totalRows = parsedRows.length > 0 ? parsedRows.length : table.row_count
  const totalPages = Math.ceil(totalRows / pageSize)
  const paginatedRows = parsedRows.slice(page * pageSize, (page + 1) * pageSize)

  return (
    <div className="rounded-xl border border-border bg-card/60 overflow-hidden space-y-0">
      {/* Table Header Bar */}
      <div className="p-3.5 bg-muted/40 border-b border-border flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <TableIcon className="w-4 h-4 text-primary" />
          <span className="font-semibold text-xs text-foreground">
            {table.sheet_name ? `Sheet: ${table.sheet_name}` : `Table ${table.table_id || ''}`}
          </span>
          <span className="text-[11px] px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground font-mono">
            {table.row_count} rows × {table.column_count} cols
          </span>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {table.markdown && (
            <button
              type="button"
              onClick={handleCopyMarkdown}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg border border-border hover:bg-muted text-foreground transition-colors"
              title="Copy table as Markdown"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Markdown
                </>
              )}
            </button>
          )}

          {table.table_id && onDownloadCsv && (
            <button
              type="button"
              onClick={() => onDownloadCsv(table.table_id!)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              CSV
            </button>
          )}

          {table.table_id && onDownloadJson && (
            <button
              type="button"
              onClick={() => onDownloadJson(table.table_id!)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              JSON
            </button>
          )}
        </div>
      </div>

      {/* Table Body / Viewport */}
      <div className="overflow-x-auto max-h-96">
        {headers.length > 0 || paginatedRows.length > 0 ? (
          <table className="w-full text-left border-collapse text-xs">
            {headers.length > 0 && (
              <thead className="bg-muted/60 text-muted-foreground uppercase tracking-wider sticky top-0 border-b border-border">
                <tr>
                  <th className="p-2.5 w-10 text-center font-mono text-[10px] text-muted-foreground/60 border-r border-border/40">
                    #
                  </th>
                  {headers.map((h, i) => (
                    <th key={i} className="p-2.5 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody className="divide-y divide-border/60">
              {paginatedRows.length > 0 ? (
                paginatedRows.map((row, rIdx) => (
                  <tr key={rIdx} className="hover:bg-muted/30 transition-colors">
                    <td className="p-2.5 text-center font-mono text-[10px] text-muted-foreground/60 border-r border-border/40 bg-muted/10">
                      {page * pageSize + rIdx + 1}
                    </td>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} className="p-2.5 whitespace-pre-wrap max-w-xs break-words">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={headers.length + 1} className="p-6 text-center text-muted-foreground">
                    Table artifact exported ({table.row_count} rows, {table.column_count} columns)
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        ) : (
          <div className="p-6 text-center text-xs text-muted-foreground">
            No rows available in this table representation.
          </div>
        )}
      </div>

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="p-2.5 bg-muted/20 border-t border-border flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Showing {page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalRows)} of {totalRows} rows
          </span>
          <div className="flex gap-1.5">
            <button
              type="button"
              disabled={page === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-2 py-0.5 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              Prev
            </button>
            <span className="px-2 py-0.5 font-mono text-[11px]">
              {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
              className="px-2 py-0.5 rounded border border-border hover:bg-muted disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
