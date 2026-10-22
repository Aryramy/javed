/**
 * Backend connection context providing real-time health, latency, and transport events.
 */

import React, { useEffect, useState, useCallback, useRef } from 'react'
import { apiService } from '@/services/api'
import { wsClient } from '@/services/websocket'
import type { ConnectionState, SystemStatusResponse, TransportEvent } from '@/services/types'
import { BackendContext, type BackendContextValue } from './backend-context'

const MAX_EVENT_RECORDS = 100

export const BackendProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<ConnectionState>('connecting')
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [lastHeartbeat, setLastHeartbeat] = useState<string | null>(null)
  const [clientId, setClientId] = useState<string | null>(null)
  const [reconnectAttempts, setReconnectAttempts] = useState<number>(0)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null)
  const [transportEvents, setTransportEvents] = useState<TransportEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const isMountedRef = useRef(true)

  // Append a new transport event, maintaining bounded size
  const appendEvent = useCallback((event: TransportEvent) => {
    if (!isMountedRef.current) return
    setTransportEvents((prev) => [event, ...prev.slice(0, MAX_EVENT_RECORDS - 1)])
  }, [])

  // Poll system status via REST
  const checkStatus = useCallback(async (): Promise<SystemStatusResponse | null> => {
    try {
      const data = await apiService.getSystemStatus()
      if (isMountedRef.current) {
        setSystemStatus(data)
        setError(null)
      }
      return data
    } catch (err: unknown) {
      if (isMountedRef.current) {
        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)
      }
      return null
    }
  }, [])

  // Trigger round-trip latency ping
  const ping = useCallback(async (): Promise<number> => {
    // Prefer WebSocket ping if connected
    if (wsClient.getState() === 'connected') {
      try {
        const ms = await wsClient.sendPing()
        if (isMountedRef.current) {
          setLatencyMs(ms)
          setLastHeartbeat(new Date().toISOString())
        }
        return ms
      } catch {
        // Fall back to REST ping
      }
    }

    try {
      const { latencyMs: ms } = await apiService.ping()
      if (isMountedRef.current) {
        setLatencyMs(ms)
        setLastHeartbeat(new Date().toISOString())
      }
      appendEvent({
        id: Math.random().toString(36).substring(7),
        timestamp: new Date().toISOString(),
        type: 'PING_ACK',
        source: 'REST',
        details: `REST ping acknowledged (${ms}ms)`,
        latencyMs: ms,
      })
      return ms
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      appendEvent({
        id: Math.random().toString(36).substring(7),
        timestamp: new Date().toISOString(),
        type: 'ERROR',
        source: 'REST',
        details: `Ping failed: ${msg}`,
      })
      throw err
    }
  }, [appendEvent])

  const reconnect = useCallback(() => {
    wsClient.reconnect()
    void checkStatus()
  }, [checkStatus])

  const disconnect = useCallback(() => {
    wsClient.disconnect()
  }, [])

  const clearEvents = useCallback(() => {
    setTransportEvents([])
  }, [])

  useEffect(() => {
    isMountedRef.current = true

    // Subscribe to WebSocket client events
    const unsubState = wsClient.onStateChange((newState) => {
      if (!isMountedRef.current) return
      setStatus(newState)
      setReconnectAttempts(wsClient.getReconnectAttempts())
      if (newState === 'connected') {
        void checkStatus()
      }
    })

    const unsubEvent = wsClient.onEvent((event) => {
      if (!isMountedRef.current) return
      appendEvent(event)
      if (event.type === 'WS_CONNECTED' && event.data) {
        const cid = (event.data as { client_id?: string })?.client_id
        if (cid) setClientId(cid)
      }
    })

    const unsubLatency = wsClient.onLatency((ms) => {
      if (!isMountedRef.current) return
      setLatencyMs(ms)
      setLastHeartbeat(new Date().toISOString())
    })

    // Initial connection attempt and status query in next microtask
    const initTimer = setTimeout(() => {
      wsClient.connect()
      void checkStatus()
    }, 0)

    // Periodic REST status sync every 30s
    const statusInterval = setInterval(() => {
      if (isMountedRef.current) {
        void checkStatus()
      }
    }, 30000)

    return () => {
      isMountedRef.current = false
      clearTimeout(initTimer)
      unsubState()
      unsubEvent()
      unsubLatency()
      clearInterval(statusInterval)
      wsClient.disconnect()
    }
  }, [appendEvent, checkStatus])

  const value: BackendContextValue = {
    status,
    latencyMs,
    lastHeartbeat,
    clientId,
    reconnectAttempts,
    systemStatus,
    transportEvents,
    error,
    ping,
    checkStatus,
    reconnect,
    disconnect,
    clearEvents,
    isBackendReady: status === 'connected' && systemStatus !== null,
  }

  return <BackendContext.Provider value={value}>{children}</BackendContext.Provider>
}
