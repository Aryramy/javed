import { useState, useEffect, useRef } from 'react'
import { Globe, X, Loader2, AlertCircle, ShieldAlert } from 'lucide-react'
import { extractionService } from '@/services/extractionService'
import type { CrawlProgressEvent, ExtractionResponse, WebCrawlStrategy } from '@/types/extraction'

interface WebCrawlModalProps {
  isOpen: boolean
  onClose: () => void
  onCrawlSuccess?: (response: ExtractionResponse) => void
}

export const WebCrawlModal = ({
  isOpen,
  onClose,
  onCrawlSuccess,
}: WebCrawlModalProps) => {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [url, setUrl] = useState('')
  const [strategy, setStrategy] = useState<WebCrawlStrategy>('static')
  const [maxChars, setMaxChars] = useState(25000)
  const [isCrawling, setIsCrawling] = useState(false)
  const [progressState, setProgressState] = useState<CrawlProgressEvent | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const cancelStreamRef = useRef<(() => void) | null>(null)

  // Synchronize modal state with native <dialog>
  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    if (isOpen) {
      if (!dialog.open) {
        dialog.showModal()
      }
    } else {
      if (dialog.open) {
        dialog.close()
      }
    }
  }, [isOpen])

  // Handle native backdrop and Esc cancellation
  const handleDialogClose = () => {
    if (cancelStreamRef.current) {
      cancelStreamRef.current()
      cancelStreamRef.current = null
    }
    setIsCrawling(false)
    setProgressState(null)
    setErrorMessage(null)
    onClose()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const trimmedUrl = url.trim()
    if (!trimmedUrl) {
      setErrorMessage('Target URL cannot be empty')
      return
    }

    if (!trimmedUrl.startsWith('http://') && !trimmedUrl.startsWith('https://')) {
      setErrorMessage('Target URL must begin with http:// or https://')
      return
    }

    setErrorMessage(null)
    setIsCrawling(true)
    setProgressState({ step: 'validating', message: 'Initiating SSRF validation...' })

    // Use SSE streaming for live feedback
    const cancelFn = extractionService.streamCrawlWebPage(
      {
        url: trimmedUrl,
        strategy,
        max_chars: maxChars,
      },
      (event: CrawlProgressEvent) => {
        setProgressState(event)

        if (event.step === 'complete' && event.result) {
          setIsCrawling(false)
          if (onCrawlSuccess) {
            onCrawlSuccess(event.result)
          }
          handleDialogClose()
        } else if (event.step === 'error') {
          setIsCrawling(false)
          setErrorMessage(event.error || 'Web crawl operation failed')
        }
      },
    )

    cancelStreamRef.current = cancelFn
  }

  const handleCancelCrawl = () => {
    if (cancelStreamRef.current) {
      cancelStreamRef.current()
      cancelStreamRef.current = null
    }
    setIsCrawling(false)
    setProgressState(null)
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={handleDialogClose}
      aria-labelledby="crawl-modal-title"
      className="backdrop:bg-black/60 backdrop:backdrop-blur-sm bg-card border border-border text-card-foreground rounded-2xl p-0 w-full max-w-lg shadow-2xl overflow-hidden m-auto"
      style={{ overscrollBehavior: 'contain' }}
    >
      <div className="p-6 space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Globe className="w-5 h-5" />
            </div>
            <div>
              <h2 id="crawl-modal-title" className="text-lg font-semibold text-foreground">
                Crawl Public Web Page
              </h2>
              <p className="text-xs text-muted-foreground">
                Acquire and extract clean markdown & tables via Crawl4AI
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleDialogClose}
            disabled={isCrawling}
            className="p-1 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Target URL */}
          <div className="space-y-1.5">
            <label htmlFor="target-url" className="text-xs font-medium text-foreground">
              Target URL
            </label>
            <input
              id="target-url"
              type="url"
              placeholder="https://example.com/article"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              disabled={isCrawling}
              required
              className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent disabled:opacity-60"
            />
          </div>

          {/* Strategy Selection */}
          <div className="space-y-1.5">
            <span className="text-xs font-medium text-foreground block">Acquisition Strategy</span>
            <div className="grid grid-cols-2 gap-3">
              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  strategy === 'static'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-border hover:bg-muted/50 text-foreground'
                } ${isCrawling ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                <input
                  type="radio"
                  name="crawl-strategy"
                  value="static"
                  checked={strategy === 'static'}
                  onChange={() => setStrategy('static')}
                  disabled={isCrawling}
                  className="mt-0.5 text-primary focus:ring-primary"
                />
                <div>
                  <span className="text-xs font-medium block">Static (Fast)</span>
                  <span className="text-[11px] text-muted-foreground block leading-tight mt-0.5">
                    Lightweight HTTP. Best for static blogs, documentation, and articles.
                  </span>
                </div>
              </label>

              <label
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  strategy === 'rendered'
                    ? 'border-primary bg-primary/5 text-primary'
                    : 'border-border hover:bg-muted/50 text-foreground'
                } ${isCrawling ? 'opacity-60 cursor-not-allowed' : ''}`}
              >
                <input
                  type="radio"
                  name="crawl-strategy"
                  value="rendered"
                  checked={strategy === 'rendered'}
                  onChange={() => setStrategy('rendered')}
                  disabled={isCrawling}
                  className="mt-0.5 text-primary focus:ring-primary"
                />
                <div>
                  <span className="text-xs font-medium block">Rendered (Chromium)</span>
                  <span className="text-[11px] text-muted-foreground block leading-tight mt-0.5">
                    Headless Chromium. Executes JavaScript for dynamic SPA content.
                  </span>
                </div>
              </label>
            </div>
          </div>

          {/* Max Characters Slider */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <label htmlFor="max-chars" className="font-medium text-foreground">
                Max Preview Characters
              </label>
              <span className="text-muted-foreground font-mono">
                {maxChars.toLocaleString()} chars
              </span>
            </div>
            <input
              id="max-chars"
              type="range"
              min="1000"
              max="100000"
              step="1000"
              value={maxChars}
              onChange={(e) => setMaxChars(Number(e.target.value))}
              disabled={isCrawling}
              className="w-full accent-primary"
            />
          </div>

          {/* Security Notice */}
          <div className="flex items-start gap-2.5 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-xs">
            <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              Zero-Trust SSRF Policy Enforced: Private subnets (RFC 1918), loopback, link-local,
              cloud metadata, and non-HTTP protocols are blocked fail-closed.
            </p>
          </div>

          {/* Live Streaming Progress */}
          {isCrawling && progressState && (
            <div className="p-3.5 rounded-lg bg-primary/5 border border-primary/20 space-y-2 animate-in fade-in">
              <div className="flex items-center justify-between text-xs font-medium text-primary">
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {progressState.step === 'validating' ? 'Validating Security...' : 'Acquiring Content...'}
                </span>
                <button
                  type="button"
                  onClick={handleCancelCrawl}
                  className="text-muted-foreground hover:text-foreground text-[11px] underline"
                >
                  Cancel
                </button>
              </div>
              {progressState.message && (
                <p className="text-xs text-muted-foreground/90 font-mono truncate">
                  {progressState.message}
                </p>
              )}
            </div>
          )}

          {/* Error Banner */}
          {errorMessage && (
            <div
              role="alert"
              className="flex items-start gap-2.5 p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-xs"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <p className="flex-1">{errorMessage}</p>
            </div>
          )}

          {/* Form Actions */}
          <div className="flex justify-end gap-2.5 pt-2 border-t border-border">
            <button
              type="button"
              onClick={handleDialogClose}
              disabled={isCrawling}
              className="px-4 py-2 text-xs font-medium rounded-lg border border-border hover:bg-muted text-foreground disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isCrawling || !url.trim()}
              className="px-4 py-2 text-xs font-medium rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground flex items-center gap-2 disabled:opacity-50"
            >
              {isCrawling ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Extracting...
                </>
              ) : (
                'Extract Web Page'
              )}
            </button>
          </div>
        </form>
      </div>
    </dialog>
  )
}
