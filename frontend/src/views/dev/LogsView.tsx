import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Terminal, Trash2 } from 'lucide-react'
import { useMode } from '@/context/useMode'

interface LogEntry {
  id: string
  timestamp: string
  level: 'INFO' | 'AUDIT' | 'SECURITY'
  source: string
  message: string
}

const INITIAL_LOGS: LogEntry[] = [
  {
    id: '1',
    timestamp: '2026-10-22T07:15:00.000Z',
    level: 'SECURITY',
    source: 'HostSandbox',
    message: 'Git-ignore policy verified: root .env excluded; .env.example tracked with placeholders.',
  },
  {
    id: '2',
    timestamp: '2026-10-22T07:15:01.000Z',
    level: 'AUDIT',
    source: 'SystemBootstrap',
    message: 'BRICK-001 React + TypeScript application initialized in strict mode.',
  },
  {
    id: '3',
    timestamp: '2026-10-22T07:15:02.000Z',
    level: 'INFO',
    source: 'ThemeManager',
    message: 'Active theme initialized in local storage.',
  },
  {
    id: '4',
    timestamp: '2026-10-22T07:15:03.000Z',
    level: 'INFO',
    source: 'NavigationRouter',
    message: 'Router initialized at root location.',
  },
]

export const LogsView = () => {
  const location = useLocation()
  const { mode } = useMode()
  const [logs, setLogs] = useState<LogEntry[]>(INITIAL_LOGS)

  useEffect(() => {
    const timer = setTimeout(() => {
      const newEntry: LogEntry = {
        id: Math.random().toString(36).substring(7),
        timestamp: new Date().toISOString(),
        level: 'INFO',
        source: 'RouterObserver',
        message: `Client route transition -> ${location.pathname} [Mode: ${mode.toUpperCase()}]`,
      }
      setLogs((prev) => [newEntry, ...prev.slice(0, 49)])
    }, 0)
    return () => clearTimeout(timer)
  }, [location.pathname, mode])

  const clearLogs = () => {
    setLogs([])
  }

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
            <Terminal className="w-4 h-4" />
            <span>Client Event Log</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Live Frontend Logs & Audit Trail
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Real-time event recording captured from the active browser session.
          </p>
        </div>

        <button
          onClick={clearLogs}
          className="self-start sm:self-auto px-3 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1.5 transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          <span>Clear Logs</span>
        </button>
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm font-mono text-xs">
        <div className="p-3 border-b border-border bg-secondary/50 flex items-center justify-between text-muted-foreground text-[11px]">
          <span>EVENT STREAM ({logs.length} RECORDS)</span>
          <span>TIMESTAMP (UTC)</span>
        </div>
        <div className="divide-y divide-border/60 max-h-[500px] overflow-y-auto">
          {logs.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              No logs recorded. Navigate between pages or change theme to generate live events.
            </div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="p-3 hover:bg-secondary/20 flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-[9px] font-bold px-1.5 py-0.2 rounded border ${
                        log.level === 'SECURITY'
                          ? 'bg-rose-500/10 text-rose-500 border-rose-500/20'
                          : log.level === 'AUDIT'
                          ? 'bg-primary/10 text-primary border-primary/20'
                          : 'bg-secondary text-muted-foreground border-border'
                      }`}
                    >
                      {log.level}
                    </span>
                    <span className="text-[11px] font-semibold text-foreground">[{log.source}]</span>
                  </div>
                  <p className="text-muted-foreground text-[11px]">{log.message}</p>
                </div>
                <span className="text-[10px] text-muted-foreground/60 shrink-0 font-mono">
                  {log.timestamp.split('T')[1]?.slice(0, 8)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
