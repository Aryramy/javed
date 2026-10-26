import React, { useState } from 'react'
import { Activity, AlertCircle, CheckCircle2, Clock, Cpu, Radio, RefreshCw, Server, Wifi, WifiOff } from 'lucide-react'
import { useBackend } from '@/context'
import { cn } from '@/lib/utils'
import { MCPAdminPanel } from '@/components/dev/MCPAdminPanel'

export const ConnectivityView: React.FC = () => {
  const {
    status,
    latencyMs,
    lastHeartbeat,
    clientId,
    reconnectAttempts,
    systemStatus,
    error,
    ping,
    checkStatus,
    reconnect,
  } = useBackend()

  const [isPinging, setIsPinging] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleManualPing = async () => {
    setIsPinging(true)
    try {
      await ping()
    } catch {
      // Handled in context
    } finally {
      setIsPinging(false)
    }
  }

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      await checkStatus()
    } finally {
      setIsRefreshing(false)
    }
  }

  const isConnected = status === 'connected'

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      {/* Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
            <Radio className="w-4 h-4" />
            <span>Transport & Subsystem Connectivity</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Subsystem Connectivity Monitor
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time live telemetry, heartbeat measurements, and connection diagnostics.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={handleManualPing}
            disabled={isPinging}
            className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-secondary flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Activity className={cn('w-3.5 h-3.5 text-primary', isPinging && 'animate-spin')} />
            <span>{isPinging ? 'Pinging...' : 'Measure Ping'}</span>
          </button>
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-secondary flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isRefreshing && 'animate-spin')} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Disconnection Warning Banner */}
      {!isConnected && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-xs text-rose-700 dark:text-rose-400 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <WifiOff className="w-5 h-5 shrink-0 mt-0.5 text-rose-500" />
            <div>
              <span className="font-semibold block mb-0.5">Backend Service Unavailable</span>
              The FastAPI backend at <code>http://127.0.0.1:8000</code> is currently unreachable. Start the backend with <code>uvicorn javed.main:app --port 8000</code> to restore live communication.
              {error && <div className="mt-1 font-mono text-[11px] opacity-90">Error: {error}</div>}
            </div>
          </div>
          <button
            onClick={reconnect}
            className="px-3 py-1 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-600 dark:text-rose-300 font-semibold shrink-0"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Primary Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* REST API Status */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>REST Gateway</span>
            <Server className="w-4 h-4" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground flex items-center gap-2">
            {systemStatus ? (
              <span className="text-emerald-500 flex items-center gap-1.5">
                <CheckCircle2 className="w-5 h-5" /> Online
              </span>
            ) : (
              <span className="text-rose-500 flex items-center gap-1.5">
                <AlertCircle className="w-5 h-5" /> Offline
              </span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground font-mono">
            {systemStatus ? `v${systemStatus.backend_version} (API ${systemStatus.api_version})` : 'Port 8000 Unreachable'}
          </p>
        </div>

        {/* WebSocket Status */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>WebSocket Status</span>
            <Wifi className="w-4 h-4" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground uppercase">
            <span
              className={cn(
                status === 'connected' && 'text-emerald-500',
                (status === 'connecting' || status === 'reconnecting') && 'text-amber-500',
                status === 'disconnected' && 'text-rose-500'
              )}
            >
              {status}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground font-mono truncate">
            {clientId ? `ID: ${clientId.substring(0, 8)}...` : reconnectAttempts > 0 ? `Attempts: ${reconnectAttempts}` : 'Not connected'}
          </p>
        </div>

        {/* Latency RTT */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Latest RTT Latency</span>
            <Activity className="w-4 h-4" />
          </div>
          <div className="text-xl font-bold font-mono text-foreground">
            {latencyMs !== null ? (
              <span
                className={cn(
                  latencyMs < 50
                    ? 'text-emerald-500'
                    : latencyMs < 150
                    ? 'text-amber-500'
                    : 'text-rose-500'
                )}
              >
                {latencyMs} ms
              </span>
            ) : (
              <span className="text-muted-foreground">-- ms</span>
            )}
          </div>
          <p className="text-[11px] text-muted-foreground">
            {latencyMs !== null ? 'Live round-trip time' : 'Awaiting ping'}
          </p>
        </div>

        {/* Last Heartbeat */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Last Heartbeat</span>
            <Clock className="w-4 h-4" />
          </div>
          <div className="text-sm font-semibold font-mono text-foreground pt-1 truncate">
            {lastHeartbeat ? lastHeartbeat.split('T')[1]?.slice(0, 8) + ' UTC' : 'Never'}
          </div>
          <p className="text-[11px] text-muted-foreground">
            Interval: 15s • Auto-sync
          </p>
        </div>
      </div>

      {/* Subsystem Layers Breakdown */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
          Architectural Subsystem Status
        </h3>

        {/* 1. FastAPI REST Gateway */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">FastAPI REST Gateway</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold">
                BRICK-002 Active
              </span>
            </div>
            <div className="text-xs text-muted-foreground font-mono">
              http://127.0.0.1:8000/api/v1 (CORS & Body Size Limiter Enabled)
            </div>
            <p className="text-xs text-muted-foreground/80 max-w-lg">
              {systemStatus
                ? `Uptime: ${systemStatus.uptime_seconds}s • Env: ${systemStatus.environment} • Server UTC: ${systemStatus.server_time}`
                : 'Backend process is currently stopped or not responding to HTTP probes.'}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0 sm:self-center">
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                systemStatus ? 'bg-emerald-500' : 'bg-rose-500'
              )}
            />
            <span
              className={cn(
                'text-xs font-mono font-bold',
                systemStatus ? 'text-emerald-500' : 'text-rose-500'
              )}
            >
              {systemStatus ? 'ONLINE' : 'UNAVAILABLE'}
            </span>
          </div>
        </div>

        {/* 2. WebSocket Real-Time Channel */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Wifi className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">WebSocket Transport Channel</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold">
                BRICK-002 Active
              </span>
            </div>
            <div className="text-xs text-muted-foreground font-mono">
              ws://127.0.0.1:8000/api/v1/ws (Origin Enforcement & Heartbeats)
            </div>
            <p className="text-xs text-muted-foreground/80 max-w-lg">
              {isConnected
                ? `Active Session • Client ID: ${clientId ?? 'unknown'} • Latency: ${latencyMs ?? 0}ms`
                : status === 'reconnecting'
                ? `Reconnection in progress (Attempt #${reconnectAttempts}). Bounded backoff active.`
                : 'WebSocket channel disconnected.'}
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0 sm:self-center">
            <span
              className={cn(
                'w-2 h-2 rounded-full',
                isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
              )}
            />
            <span
              className={cn(
                'text-xs font-mono font-bold uppercase',
                isConnected ? 'text-emerald-500' : 'text-rose-500'
              )}
            >
              {status}
            </span>
          </div>
        </div>

        {/* 3. SSE Stream */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">Server-Sent Events (SSE) Stream</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
                BRICK-002 Active
              </span>
            </div>
            <div className="text-xs text-muted-foreground font-mono">
              GET /api/v1/events (text/event-stream)
            </div>
            <p className="text-xs text-muted-foreground/80 max-w-lg">
              Lightweight unidirectional server broadcast stream for system notifications and diagnostic logs.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0 sm:self-center">
            <span className={cn('w-2 h-2 rounded-full', systemStatus ? 'bg-emerald-500' : 'bg-muted-foreground')} />
            <span className="text-xs font-mono font-bold text-muted-foreground">
              {systemStatus ? 'READY' : 'OFFLINE'}
            </span>
          </div>
        </div>

        {/* 4. Future AI Subsystems (Honest Stage Boundaries) */}
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm opacity-60 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Server className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-semibold text-foreground">OpenRouter Model Gateway</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
                Scheduled: BRICK-003
              </span>
            </div>
            <div className="text-xs text-muted-foreground font-mono">HTTPS Proxy (https://openrouter.ai/api/v1)</div>
            <p className="text-xs text-muted-foreground">
              Client-side code strictly avoids direct LLM API access to protect credentials in server .env.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0 sm:self-center">
            <span className="w-2 h-2 rounded-full bg-muted-foreground/50" />
            <span className="text-xs font-mono font-bold text-muted-foreground">NOT STARTED</span>
          </div>
        </div>
      </div>

      {/* Phase 6: Minimal MCP Host Administration */}
      <MCPAdminPanel />
    </div>
  )
}
