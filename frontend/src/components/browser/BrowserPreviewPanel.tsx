/**
 * React Live Browser Preview Panel for Project Javed.
 *
 * Renders the live viewport frame stream over WebSocket, simulated browser
 * navigation bar (URL bar, lock indicator, title), frame metadata HUD,
 * and emergency stop/disconnect controls.
 */

import React, { useState } from 'react'
import {
  Compass,
  Globe,
  Lock,
  Pause,
  Play,
  Power,
  RefreshCw,
  Shield,
  Maximize2,
  Minimize2,
  Activity,
} from 'lucide-react'
import {
  useBrowserStream,
  type UseBrowserStreamReturn,
} from '../../hooks/useBrowserStream'
import { cn } from '../../lib/utils'

export interface BrowserPreviewPanelProps {
  stream?: UseBrowserStreamReturn
  wsUrl?: string
  autoConnect?: boolean
  className?: string
}

export const BrowserPreviewPanel: React.FC<BrowserPreviewPanelProps> = ({
  stream: customStream,
  wsUrl,
  autoConnect = true,
  className,
}) => {
  const defaultStream = useBrowserStream({ url: wsUrl, autoConnect })
  const stream = customStream || defaultStream

  const [isFullscreen, setIsFullscreen] = useState(false)
  const [copiedUrl, setCopiedUrl] = useState(false)

  const {
    status,
    currentUrl,
    pageTitle,
    frameImage,
    frameNumber,
    timestamp,
    dimensions,
    isStreaming,
    lastLatencyMs,
    error,
    connect,
    toggleStream,
    sendPing,
    requestStatus,
    emergencyStop,
  } = stream

  const isConnected = status === 'CONNECTED'
  const isConnecting = status === 'CONNECTING'
  const displayUrl = currentUrl || 'about:blank'

  const handleCopyUrl = () => {
    if (currentUrl && typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(currentUrl)
      setCopiedUrl(true)
      setTimeout(() => setCopiedUrl(false), 2000)
    }
  }

  const handleRefresh = () => {
    sendPing()
    requestStatus()
  }

  const getStatusBadge = () => {
    switch (status) {
      case 'CONNECTED':
        return (
          <span
            data-testid="browser-status-connected"
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Live Stream
          </span>
        )
      case 'CONNECTING':
        return (
          <span
            data-testid="browser-status-connecting"
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30"
          >
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            Connecting
          </span>
        )
      case 'ERROR':
        return (
          <span
            data-testid="browser-status-error"
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30"
          >
            <span className="w-2 h-2 rounded-full bg-rose-400" />
            Error
          </span>
        )
      case 'DISCONNECTED':
      default:
        return (
          <span
            data-testid="browser-status-disconnected"
            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700"
          >
            <span className="w-2 h-2 rounded-full bg-zinc-500" />
            Offline
          </span>
        )
    }
  }

  return (
    <div
      data-testid="browser-preview-panel"
      className={cn(
        'flex flex-col bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden shadow-xl transition-all duration-200',
        isFullscreen ? 'fixed inset-4 z-50 rounded-lg' : 'w-full',
        className
      )}
    >
      {/* 1. Header & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between px-4 py-2.5 bg-zinc-950/80 border-b border-zinc-800 gap-2">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Compass className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-zinc-100">
                Playwright Viewport
              </span>
              {getStatusBadge()}
            </div>
            {pageTitle && (
              <span
                data-testid="browser-page-title"
                className="text-xs text-zinc-400 max-w-[280px] sm:max-w-md truncate block"
                title={pageTitle}
              >
                {pageTitle}
              </span>
            )}
          </div>
        </div>

        {/* Telemetry badges & Controls */}
        <div className="flex items-center gap-2">
          {dimensions && (
            <span
              data-testid="browser-dimensions-badge"
              className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-zinc-800/80 text-zinc-300 border border-zinc-700/50"
            >
              {dimensions.width}×{dimensions.height}
            </span>
          )}

          {frameNumber > 0 && (
            <span
              data-testid="browser-frame-badge"
              className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-zinc-800/80 text-zinc-400 border border-zinc-700/50"
            >
              Frame #{frameNumber}
            </span>
          )}

          {lastLatencyMs !== null && (
            <span
              data-testid="browser-latency-badge"
              className="hidden lg:inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono bg-zinc-800/80 text-zinc-400 border border-zinc-700/50"
            >
              <Activity className="w-3 h-3 text-emerald-400" />
              {lastLatencyMs}ms
            </span>
          )}

          {/* Stream pause/resume */}
          {isConnected && (
            <button
              type="button"
              data-testid="browser-stream-toggle"
              onClick={toggleStream}
              aria-label={isStreaming ? 'Pause stream' : 'Resume stream'}
              title={isStreaming ? 'Pause Live Stream' : 'Resume Live Stream'}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-colors border border-transparent hover:border-zinc-700"
            >
              {isStreaming ? (
                <Pause className="w-4 h-4 text-amber-400" />
              ) : (
                <Play className="w-4 h-4 text-emerald-400" />
              )}
            </button>
          )}

          {/* Ping / Refresh */}
          {isConnected && (
            <button
              type="button"
              data-testid="browser-refresh-btn"
              onClick={handleRefresh}
              aria-label="Refresh telemetry"
              title="Ping & Refresh Telemetry"
              className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-colors border border-transparent hover:border-zinc-700"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}

          {/* Fullscreen toggle */}
          <button
            type="button"
            data-testid="browser-fullscreen-toggle"
            onClick={() => setIsFullscreen(!isFullscreen)}
            aria-label={isFullscreen ? 'Exit full screen' : 'Full screen'}
            title={isFullscreen ? 'Exit Fullscreen' : 'Expand Fullscreen'}
            className="p-1.5 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-lg transition-colors border border-transparent hover:border-zinc-700"
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>

          {/* Emergency Stop / Connect button */}
          {isConnected || isConnecting ? (
            <button
              type="button"
              data-testid="browser-disconnect-btn"
              onClick={emergencyStop}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 border border-rose-500/30 transition-colors"
              title="Immediately Disconnect & Halt Viewport Streaming"
            >
              <Power className="w-3.5 h-3.5 text-rose-400" />
              <span>Emergency Stop</span>
            </button>
          ) : (
            <button
              type="button"
              data-testid="browser-connect-btn"
              onClick={connect}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 border border-indigo-500/30 transition-colors"
            >
              <Power className="w-3.5 h-3.5 text-indigo-400" />
              <span>Connect</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Simulated Browser Navigation Bar */}
      <div className="flex items-center px-4 py-2 bg-zinc-950/50 border-b border-zinc-800/80 gap-2">
        <div className="flex items-center gap-1.5 text-zinc-500">
          <div className="w-2.5 h-2.5 rounded-full bg-rose-500/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-amber-500/60" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/60" />
        </div>

        {/* URL Input Box */}
        <div className="flex-1 flex items-center bg-zinc-900 border border-zinc-800 rounded-md px-3 py-1 text-xs text-zinc-300">
          {displayUrl.startsWith('https:') ? (
            <Lock className="w-3.5 h-3.5 text-emerald-400 mr-2 shrink-0" />
          ) : (
            <Globe className="w-3.5 h-3.5 text-zinc-500 mr-2 shrink-0" />
          )}
          <input
            type="text"
            readOnly
            value={displayUrl}
            data-testid="browser-url-input"
            onClick={handleCopyUrl}
            title="Click to copy current URL"
            aria-label="Browser current URL"
            className="w-full bg-transparent border-none outline-none font-mono text-xs text-zinc-200 cursor-pointer selection:bg-indigo-500/30"
          />
          {copiedUrl && (
            <span className="text-[10px] text-emerald-400 font-medium ml-2">
              Copied!
            </span>
          )}
        </div>
      </div>

      {/* 3. Live Viewport Frame Canvas */}
      <div
        className={cn(
          'relative bg-zinc-950 overflow-hidden flex items-center justify-center min-h-[380px]',
          isFullscreen ? 'flex-1 h-full' : 'h-[520px]'
        )}
      >
        {frameImage ? (
          <div className="relative w-full h-full flex items-center justify-center p-2">
            <img
              src={frameImage}
              alt={pageTitle || 'Live Browser Viewport Frame'}
              data-testid="browser-viewport-frame"
              className="max-h-full max-w-full object-contain rounded shadow-lg select-none border border-zinc-800/60"
            />

            {/* Overlaid HUD Watermark */}
            <div className="absolute bottom-4 right-4 flex items-center gap-2 px-2 py-1 rounded bg-zinc-950/80 backdrop-blur-sm border border-zinc-800 text-[10px] font-mono text-zinc-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>LIVE</span>
              {timestamp && (
                <span>
                  • {new Date(timestamp).toLocaleTimeString()}
                </span>
              )}
            </div>

            {!isStreaming && (
              <div
                data-testid="browser-paused-overlay"
                className="absolute inset-0 bg-zinc-950/60 backdrop-blur-xs flex flex-col items-center justify-center gap-2 text-zinc-300"
              >
                <Pause className="w-8 h-8 text-amber-400" />
                <span className="text-sm font-medium">Stream Paused</span>
                <button
                  type="button"
                  onClick={toggleStream}
                  className="px-3 py-1 rounded text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 transition-colors"
                >
                  Resume
                </button>
              </div>
            )}
          </div>
        ) : (
          <div
            data-testid="browser-empty-state"
            className="flex flex-col items-center justify-center p-8 text-center max-w-md"
          >
            <div className="flex items-center justify-center w-14 h-14 rounded-2xl bg-zinc-900 border border-zinc-800 text-zinc-500 mb-4 shadow-inner">
              <Compass className="w-7 h-7 text-indigo-400 animate-spin-slow" />
            </div>
            <h3 className="text-base font-medium text-zinc-200 mb-1.5">
              {isConnected
                ? 'Awaiting Browser Automation Navigation'
                : 'Browser Stream Offline'}
            </h3>
            <p className="text-xs text-zinc-400 leading-relaxed mb-4">
              {isConnected
                ? 'When an agent executes navigation (e.g. browser_navigate) or interacts with a page, live viewport frames will render here at 3–5 fps.'
                : 'Connect to the backend WebSocket to monitor automated Playwright browser tasks in real time.'}
            </p>

            {error && (
              <div
                data-testid="browser-error-banner"
                className="mb-4 px-3 py-1.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-400 text-xs text-left w-full"
              >
                {error}
              </div>
            )}

            {!isConnected && (
              <button
                type="button"
                onClick={connect}
                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow"
              >
                <Power className="w-3.5 h-3.5" />
                <span>Connect Viewport Stream</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* 4. Footer & Security Status Bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-950/90 border-t border-zinc-800 text-[11px] text-zinc-500">
        <div className="flex items-center gap-1.5">
          <Shield className="w-3.5 h-3.5 text-indigo-400" />
          <span>
            Ephemeral Isolation Active • Zero Credentials Saved • SSRF Protected
          </span>
        </div>
        <span className="font-mono text-zinc-600">BRICK-006 Phase 6</span>
      </div>
    </div>
  )
}

