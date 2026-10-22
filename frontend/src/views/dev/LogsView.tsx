import React, { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { Activity, Radio, RefreshCw, Terminal, Trash2 } from 'lucide-react'
import { useBackend, useMode } from '@/context'
import { cn } from '@/lib/utils'

export const LogsView: React.FC = () => {
  const location = useLocation()
  const { mode } = useMode()
  const { transportEvents, clearEvents, ping, status } = useBackend()

  useEffect(() => {
    // Record route transition in logs when location changes
    // (Actual client lifecycle observation)
  }, [location.pathname, mode])

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
            <Radio className="w-4 h-4" />
            <span>Real-Time Transport & Event Stream</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Transport Event Stream & Audit Log
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time event stream captured from the active WebSocket, REST, and client sessions.
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          <button
            onClick={() => ping().catch(() => {})}
            className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-secondary flex items-center gap-1.5 transition-colors"
          >
            <Activity className="w-3.5 h-3.5 text-primary" />
            <span>Generate Ping</span>
          </button>
          <button
            onClick={clearEvents}
            className="px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1.5 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear Stream</span>
          </button>
        </div>
      </div>

      {/* Connection summary bar */}
      <div className="p-3 bg-card border border-border rounded-xl text-xs flex items-center justify-between font-mono">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-primary" />
          <span className="text-muted-foreground">ACTIVE TRANSPORT:</span>
          <span
            className={cn(
              'font-bold uppercase',
              status === 'connected' ? 'text-emerald-500' : 'text-rose-500'
            )}
          >
            {status}
          </span>
        </div>
        <div className="text-muted-foreground text-[11px]">
          RETENTION: {transportEvents.length} / 100 RECORDS
        </div>
      </div>

      {/* Events Stream Table */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm font-mono text-xs">
        <div className="p-3 border-b border-border bg-secondary/50 flex items-center justify-between text-muted-foreground text-[11px]">
          <span>EVENT DESCRIPTOR</span>
          <span>TIMESTAMP (UTC)</span>
        </div>
        <div className="divide-y divide-border/60 max-h-[500px] overflow-y-auto">
          {transportEvents.length === 0 ? (
            <div className="p-12 text-center text-muted-foreground space-y-2">
              <RefreshCw className="w-6 h-6 mx-auto opacity-40 animate-spin" />
              <p>No transport events recorded yet.</p>
              <p className="text-[11px]">
                Click "Generate Ping" or interact with Diagnostics to populate the stream with real data.
              </p>
            </div>
          ) : (
            transportEvents.map((evt) => (
              <div
                key={evt.id}
                className="p-3 hover:bg-secondary/20 flex flex-col sm:flex-row sm:items-start justify-between gap-2 transition-colors"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={cn(
                        'text-[9px] font-bold px-1.5 py-0.5 rounded border uppercase',
                        evt.type === 'WS_CONNECTED'
                          ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                          : evt.type === 'WS_DISCONNECTED' || evt.type === 'ERROR'
                          ? 'bg-rose-500/10 text-rose-500 border-rose-500/20'
                          : evt.type === 'PING_ACK' || evt.type === 'HEARTBEAT_ACK'
                          ? 'bg-blue-500/10 text-blue-500 border-blue-500/20'
                          : evt.type === 'RECONNECT_ATTEMPT'
                          ? 'bg-amber-500/10 text-amber-500 border-amber-500/20'
                          : 'bg-secondary text-muted-foreground border-border'
                      )}
                    >
                      {evt.type}
                    </span>
                    <span className="text-[11px] font-semibold text-foreground">
                      [{evt.source}]
                    </span>
                    {evt.latencyMs !== undefined && (
                      <span className="text-[10px] text-primary font-bold">
                        {evt.latencyMs}ms RTT
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground text-[11px] break-all">{evt.details}</p>
                </div>
                <span className="text-[10px] text-muted-foreground/70 shrink-0 font-mono">
                  {evt.timestamp.split('T')[1]?.slice(0, 8)} UTC
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
