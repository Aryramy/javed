/**
 * TypeScript contract interfaces for FastAPI REST and WebSocket services.
 */

export type ConnectionState = 'connecting' | 'connected' | 'degraded' | 'disconnected' | 'reconnecting'

export interface LiveResponse {
  status: 'live'
  timestamp: string
}

export interface DependencyStatus {
  status: 'ready' | 'degraded' | 'not_ready'
  details: string | null
}

export interface ReadyResponse {
  status: 'ready' | 'not_ready'
  timestamp: string
  dependencies: Record<string, DependencyStatus>
}

export interface SystemStatusResponse {
  app_name: string
  backend_version: string
  api_version: string
  environment: string
  server_time: string
  uptime_seconds: number
  active_ws_connections: number
  capabilities: {
    rest_api: boolean
    websocket: boolean
    sse: boolean
    ai_chat: boolean
    tool_execution: boolean
    browser_automation: boolean
    document_extraction: boolean
    persistent_memory: boolean
    voice_multilingual: boolean
  }
}

export interface PingResponse {
  message: 'pong'
  timestamp: string
  echo: string | null
}

export interface EventEnvelope<T = Record<string, unknown>> {
  type: string
  version: string
  correlation_id: string | null
  timestamp: string
  payload: T
}

export interface TransportEvent {
  id: string
  timestamp: string
  type:
    | 'WS_CONNECTED'
    | 'WS_DISCONNECTED'
    | 'PING_ACK'
    | 'HEARTBEAT_ACK'
    | 'RECONNECT_ATTEMPT'
    | 'REST_CALL'
    | 'SERVER_EVENT'
    | 'ERROR'
  source: 'WebSocket' | 'REST' | 'SSE'
  details: string
  latencyMs?: number
  data?: unknown
}
