import { useState, useRef, type DragEvent, type ChangeEvent } from 'react'
import {
  UploadCloud,
  FileText,
  AlertCircle,
  CheckCircle2,
  Loader2,
  FileType,
  X,
} from 'lucide-react'
import { extractionService } from '@/services/extractionService'
import type { ExtractionResponse } from '@/types/extraction'

interface DocumentUploadZoneProps {
  onUploadSuccess?: (response: ExtractionResponse) => void
  disabled?: boolean
}

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024 // 25 MB
const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.xlsx']

export const DocumentUploadZone = ({
  onUploadSuccess,
  disabled = false,
}: DocumentUploadZoneProps) => {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<ExtractionResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const validateFile = (file: File): string | null => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return `Unsupported file format '${ext}'. Allowed formats: ${ACCEPTED_EXTENSIONS.join(', ')}`
    }
    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeMb = (file.size / (1024 * 1024)).toFixed(1)
      return `File size (${sizeMb} MB) exceeds maximum allowed limit of 25 MB`
    }
    return null
  }

  const handleProcessFile = async (file: File) => {
    const errorMsg = validateFile(file)
    if (errorMsg) {
      setUploadError(errorMsg)
      setLastResult(null)
      return
    }

    setUploadError(null)
    setLastResult(null)
    setIsUploading(true)

    try {
      const response = await extractionService.uploadDocument(file)
      setLastResult(response)
      if (onUploadSuccess) {
        onUploadSuccess(response)
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Upload and extraction failed'
      setUploadError(message)
    } finally {
      setIsUploading(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!disabled && !isUploading) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    if (disabled || isUploading) return

    const files = e.dataTransfer.files
    if (files && files.length > 0) {
      handleProcessFile(files[0])
    }
  }

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleProcessFile(files[0])
    }
  }

  const openFileDialog = () => {
    if (!disabled && !isUploading && fileInputRef.current) {
      fileInputRef.current.click()
    }
  }

  return (
    <div className="w-full space-y-4">
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        className="hidden"
        onChange={handleFileInputChange}
        disabled={disabled || isUploading}
        data-testid="file-upload-input"
      />

      {/* Drop Zone Box */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={openFileDialog}
        className={`relative border-2 border-dashed rounded-xl p-6 sm:p-8 text-center cursor-pointer transition-all duration-200 select-none ${
          isDragging
            ? 'border-primary bg-primary/5 scale-[1.005]'
            : 'border-border/60 hover:border-primary/60 bg-card/40 hover:bg-card/70'
        } ${disabled || isUploading ? 'opacity-60 cursor-not-allowed' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Upload document drop zone"
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            openFileDialog()
          }
        }}
      >
        <div className="flex flex-col items-center justify-center space-y-3">
          <div
            className={`w-14 h-14 rounded-full flex items-center justify-center transition-colors ${
              isDragging ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
            }`}
          >
            {isUploading ? (
              <Loader2 className="w-7 h-7 animate-spin text-primary" />
            ) : (
              <UploadCloud className="w-7 h-7" />
            )}
          </div>

          <div className="space-y-1">
            <p className="text-base font-medium text-foreground">
              {isUploading ? 'Extracting document content...' : 'Drop PDF, DOCX, or XLSX file here'}
            </p>
            <p className="text-xs text-muted-foreground">
              {isUploading
                ? 'Running zero-trust preflight security checks and IBM Docling parser'
                : 'or click to browse from your computer (up to 25 MB)'}
            </p>
          </div>

          {/* Supported Format Pills */}
          <div className="flex items-center gap-2 pt-1 text-xs text-muted-foreground/80">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/60 border border-border/40 font-mono">
              <FileType className="w-3 h-3 text-red-400" /> PDF
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/60 border border-border/40 font-mono">
              <FileText className="w-3 h-3 text-blue-400" /> Word DOCX
            </span>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/60 border border-border/40 font-mono">
              <FileText className="w-3 h-3 text-emerald-400" /> Excel XLSX
            </span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {uploadError && (
        <div
          role="alert"
          className="flex items-start gap-3 p-4 rounded-lg bg-destructive/10 border border-destructive/30 text-destructive text-sm animate-in fade-in duration-200"
        >
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-medium">Ingestion Rejected</p>
            <p className="text-xs mt-0.5 opacity-90">{uploadError}</p>
          </div>
          <button
            type="button"
            onClick={() => setUploadError(null)}
            className="text-destructive hover:opacity-75 p-1 -mr-1"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Success Summary Banner */}
      {lastResult && (
        <div
          role="status"
          className="flex items-start gap-3 p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 text-sm animate-in fade-in duration-200"
        >
          <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5 text-emerald-500" />
          <div className="flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-foreground">
                {lastResult.original_display_name}
              </span>
              {lastResult.is_duplicate && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-600 dark:text-amber-400 font-medium">
                  Duplicate Content
                </span>
              )}
              {lastResult.is_new_version && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-600 dark:text-blue-400 font-medium">
                  New Version
                </span>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3 text-xs opacity-90 text-foreground/80">
              {lastResult.page_count !== null && lastResult.page_count !== undefined && (
                <span>Pages: {lastResult.page_count}</span>
              )}
              <span>Elements: {lastResult.element_count}</span>
              <span>Tables: {lastResult.table_count}</span>
              {lastResult.word_count !== null && lastResult.word_count !== undefined && (
                <span>Words: {lastResult.word_count.toLocaleString()}</span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => setLastResult(null)}
            className="hover:opacity-75 p-1 -mr-1"
            aria-label="Dismiss success message"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}

