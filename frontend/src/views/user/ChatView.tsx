import { MessageSquare, Server, Wifi, WifiOff } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'
import { useBackend } from '@/context'
import { cn } from '@/lib/utils'

export const ChatView = () => {
  const { status, latencyMs, systemStatus } = useBackend()
  const isConnected = status === 'connected'

  return (
    <div className="space-y-4">
      {/* Real Backend Status Banner in User Mode */}
      <div
        className={cn(
          'p-3 rounded-xl border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-sm font-mono',
          isConnected
            ? 'bg-card border-border text-foreground'
            : 'bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400'
        )}
      >
        <div className="flex items-center gap-2">
          {isConnected ? (
            <Wifi className="w-4 h-4 text-emerald-500 shrink-0" />
          ) : (
            <WifiOff className="w-4 h-4 text-rose-500 shrink-0" />
          )}
          <span>
            {isConnected ? (
              <>
                <strong className="text-emerald-500">BACKEND CONNECTED:</strong>{' '}
                {systemStatus ? `Javed v${systemStatus.backend_version}` : '127.0.0.1:8000'}
                {latencyMs !== null && (
                  <span className="text-muted-foreground ml-2">({latencyMs}ms RTT)</span>
                )}
              </>
            ) : (
              <>
                <strong>BACKEND DISCONNECTED:</strong> Local FastAPI server is unreachable.
              </>
            )}
          </span>
        </div>

        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Server className="w-3.5 h-3.5 text-primary" />
          <span>Stage 1 Transport Verified • AI Gateway Scheduled for BRICK-003</span>
        </div>
      </div>

      <EmptyState
        icon={MessageSquare}
        title="Conversational AI Gateway"
        description="Interactive streaming chat powered by Deep Agents and LangGraph will connect directly to OpenRouter once the model adapter layer is established in BRICK-003."
        scheduledBrick="BRICK-003: OpenRouter Integration & Streaming Chat"
        stage="Stage 2: Intelligence & Models"
        prerequisites={[
          'BRICK-001: Reproducible Foundation & Real React UI Shell (VERIFIED)',
          'BRICK-002: FastAPI Integration & Real-Time Communication (ACTIVE)',
          'BRICK-003: OpenRouter Adapter & assistant-ui Thread Integration (NEXT)',
        ]}
        architectureNote="Architecture Reference: Section 3.1 & 3.4 of docs/ARCHITECTURE.md. Chat UI will pair assistant-ui with FastAPI WebSockets."
      />
    </div>
  )
}
