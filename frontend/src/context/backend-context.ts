import { createContext } from 'react'
import type { ConnectionState, SystemStatusResponse, TransportEvent } from '@/services/types'

export interface BackendContextValue {
  status: ConnectionState
  latencyMs: number | null
  lastHeartbeat: string | null
  clientId: string | null
  reconnectAttempts: number
  systemStatus: SystemStatusResponse | null
  transportEvents: TransportEvent[]
  error: string | null
  ping: () => Promise<number>
  checkStatus: () => Promise<SystemStatusResponse | null>
  reconnect: () => void
  disconnect: () => void
  clearEvents: () => void
  isBackendReady: boolean
}

export const BackendContext = createContext<BackendContextValue | undefined>(undefined)
