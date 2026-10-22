import { Radio, Server, ShieldAlert } from 'lucide-react'

export const ConnectivityView: React.FC = () => {
  const connectionItems = [
    {
      name: 'FastAPI Backend Gateway',
      protocol: 'HTTP REST / WebSockets (Port 8000)',
      status: 'DISCONNECTED',
      badge: 'Scheduled for BRICK-002',
      detail: 'The FastAPI application and transport server are scheduled for implementation in BRICK-002.',
    },
    {
      name: 'Bidirectional Streaming Channel',
      protocol: 'Starlette WebSocket (ws://localhost:8000/ws)',
      status: 'OFFLINE',
      badge: 'Scheduled for BRICK-002',
      detail: 'Real-time agent observation events, browser frame streaming, and audio packets will stream over this channel.',
    },
    {
      name: 'OpenRouter Model Gateway',
      protocol: 'HTTPS Proxy (https://openrouter.ai/api/v1)',
      status: 'NOT CONFIGURED IN CLIENT',
      badge: 'Scheduled for BRICK-003',
      detail: 'Client-side code strictly avoids direct LLM API access to protect credentials stored safely in server .env.',
    },
    {
      name: 'Playwright Browser Automation Daemon',
      protocol: 'Python Subprocess Context',
      status: 'NOT INITIALIZED',
      badge: 'Scheduled for BRICK-006',
      detail: 'Headless Chromium execution engine and screen streamer will be activated in Stage 4.',
    },
    {
      name: 'SQLite State Persistence Store',
      protocol: 'aiosqlite (data/jarvis.db)',
      status: 'NOT INITIALIZED',
      badge: 'Scheduled for BRICK-004',
      detail: 'LangGraph SqliteSaver checkpointer and session store will be initialized in Stage 3.',
    },
  ]

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
          <Radio className="w-4 h-4" />
          <span>Transport & Subsystem Connectivity</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Subsystem Connectivity Monitor
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Honest, real-time connectivity status across all architectural layers.
        </p>
      </div>

      <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-amber-700 dark:text-amber-400 flex items-start gap-3">
        <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5 text-amber-500" />
        <div>
          <span className="font-semibold block mb-0.5">Rule 7 Governance Integrity Enforcement</span>
          Zero backend mock responders or fake "connected" pulses are permitted. All services remain explicitly offline until their scheduled bricks are implemented and verified.
        </div>
      </div>

      <div className="space-y-3">
        {connectionItems.map((item, index) => (
          <div key={index} className="bg-card border border-border rounded-xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Server className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-semibold text-foreground">{item.name}</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border">
                  {item.badge}
                </span>
              </div>
              <div className="text-xs text-muted-foreground font-mono">{item.protocol}</div>
              <p className="text-xs text-muted-foreground/80 max-w-lg">{item.detail}</p>
            </div>

            <div className="flex items-center gap-2 shrink-0 sm:self-center">
              <span className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-xs font-mono font-bold text-amber-600 dark:text-amber-400">
                {item.status}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
