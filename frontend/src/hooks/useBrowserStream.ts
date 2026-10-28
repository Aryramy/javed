/**
 * Custom React hook for connecting to the Javed Playwright Browser Viewport Stream.
 *
 * Provides real-time frame streaming, connection lifecycle management,
 * latency measurement, and stream pause/resume controls.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  BrowserControlMessage,
  BrowserStreamState,
  ViewportFramePayload,
} from '../types/browser'

export interface UseBrowserStreamOptions {
  url?: string
  autoConnect?: boolean
  reconnect?: boolean
  reconnectIntervalMs?: number
  maxReconnectAttempts?: number
  onFrame?: (frame: ViewportFramePayload) => void
  onError?: (error: Event) => void
}

export interface UseBrowserStreamReturn extends BrowserStreamState {
  connect: () => void
  disconnect: () => void
  sendPing: () => void
  requestStatus: () => void
  toggleStream: () => void
  pauseStream: () => void
  resumeStream: () => void
  emergencyStop: () => void
}

export function getDefaultBrowserWsUrl(): string {
  if (typeof window === 'undefined') return 'ws://127.0.0.1:8000/ws/browser'
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/browser`
}

export function useBrowserStream(options: UseBrowserStreamOptions = {}): UseBrowserStreamReturn {
  const {
    url,
    autoConnect = true,
    reconnect = true,
    reconnectIntervalMs = 2000,
    maxReconnectAttempts = 10,
    onFrame,
    onError,
  } = options

  const [state, setState] = useState<BrowserStreamState>({
    status: 'DISCONNECTED',
    currentUrl: null,
    pageTitle: null,
    frameImage: null,
    frameNumber: 0,
    timestamp: null,
    dimensions: null,
    isStreaming: true,
    lastLatencyMs: null,
    error: null,
    totalFrames: 0,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalDisconnectRef = useRef(false)
  const pendingPingTimestampRef = useRef<number | null>(null)

  // Keep latest callbacks in refs to avoid reconnection on callback mutation
  const onFrameRef = useRef(onFrame)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onFrameRef.current = onFrame
    onErrorRef.current = onError
  }, [onFrame, onError])

  const clearTimers = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const sendMessage = useCallback((msg: BrowserControlMessage) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const sendPing = useCallback(() => {
    pendingPingTimestampRef.current = Date.now()
    sendMessage({
      action: 'ping',
      client_timestamp: new Date().toISOString(),
    })
  }, [sendMessage])

  const requestStatus = useCallback(() => {
    sendMessage({ action: 'status' })
  }, [sendMessage])

  const pauseStream = useCallback(() => {
    sendMessage({ action: 'pause' })
    setState((prev) => ({ ...prev, isStreaming: false }))
  }, [sendMessage])

  const resumeStream = useCallback(() => {
    sendMessage({ action: 'resume' })
    setState((prev) => ({ ...prev, isStreaming: true }))
  }, [sendMessage])

  const toggleStream = useCallback(() => {
    if (state.isStreaming) {
      pauseStream()
    } else {
      resumeStream()
    }
  }, [state.isStreaming, pauseStream, resumeStream])

  const disconnect = useCallback(() => {
    intentionalDisconnectRef.current = true
    clearTimers()
    if (wsRef.current) {
      wsRef.current.close(1000, 'User initiated disconnect')
      wsRef.current = null
    }
    setState((prev) => ({
      ...prev,
      status: 'DISCONNECTED',
      isStreaming: false,
    }))
  }, [clearTimers])

  const emergencyStop = useCallback(() => {
    // Send immediate pause signal before closing socket
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ action: 'pause' }))
      } catch {
        // ignore send error during emergency shutdown
      }
    }
    disconnect()
  }, [disconnect])

  const connectRef = useRef<() => void>(() => {})

  const connect = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.CONNECTING ||
        wsRef.current.readyState === WebSocket.OPEN)
    ) {
      return
    }

    clearTimers()
    intentionalDisconnectRef.current = false
    const targetUrl = url || getDefaultBrowserWsUrl()

    setState((prev) => ({
      ...prev,
      status: 'CONNECTING',
      error: null,
    }))

    try {
      const ws = new WebSocket(targetUrl)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
        setState((prev) => ({
          ...prev,
          status: 'CONNECTED',
          error: null,
          isStreaming: true,
        }))
      }

      ws.onmessage = (event: MessageEvent) => {
        try {
          const envelope = JSON.parse(event.data)
          const envelopeType = envelope.type || envelope.action

          if (envelopeType === 'connection_established') {
            setState((prev) => ({
              ...prev,
              status: 'CONNECTED',
              isStreaming: true,
              error: null,
            }))
          } else if (envelopeType === 'viewport_frame' && envelope.payload) {
            const payload: ViewportFramePayload = envelope.payload
            setState((prev) => ({
              ...prev,
              currentUrl: payload.url || prev.currentUrl,
              pageTitle: payload.title || prev.pageTitle,
              frameImage: payload.image || prev.frameImage,
              frameNumber: payload.frame_number ?? prev.frameNumber + 1,
              timestamp: payload.timestamp || new Date().toISOString(),
              dimensions:
                payload.viewport_width && payload.viewport_height
                  ? { width: payload.viewport_width, height: payload.viewport_height }
                  : prev.dimensions,
              totalFrames: prev.totalFrames + 1,
            }))
            if (onFrameRef.current) {
              onFrameRef.current(payload)
            }
          } else if (envelopeType === 'pong') {
            if (pendingPingTimestampRef.current) {
              const latency = Date.now() - pendingPingTimestampRef.current
              setState((prev) => ({ ...prev, lastLatencyMs: latency }))
              pendingPingTimestampRef.current = null
            }
          } else if (envelopeType === 'stream_paused') {
            setState((prev) => ({ ...prev, isStreaming: false }))
          } else if (envelopeType === 'stream_resumed') {
            setState((prev) => ({ ...prev, isStreaming: true }))
          }
        } catch {
          // Ignore unparseable non-JSON messages
        }
      }

      ws.onerror = (evt: Event) => {
        setState((prev) => ({
          ...prev,
          status: 'ERROR',
          error: 'WebSocket transport error',
        }))
        if (onErrorRef.current) {
          onErrorRef.current(evt)
        }
      }

      ws.onclose = () => {
        wsRef.current = null
        if (!intentionalDisconnectRef.current) {
          setState((prev) => ({
            ...prev,
            status: 'DISCONNECTED',
          }))

          if (reconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
            reconnectAttemptsRef.current += 1
            const delay = reconnectIntervalMs * Math.min(reconnectAttemptsRef.current, 3)
            reconnectTimerRef.current = setTimeout(() => {
              connectRef.current()
            }, delay)
          }
        } else {
          setState((prev) => ({
            ...prev,
            status: 'DISCONNECTED',
          }))
        }
      }
    } catch (err) {
      setState((prev) => ({
        ...prev,
        status: 'ERROR',
        error: err instanceof Error ? err.message : 'Failed to establish WebSocket',
      }))
    }
  }, [url, clearTimers, reconnect, maxReconnectAttempts, reconnectIntervalMs])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  useEffect(() => {
    if (autoConnect) {
      connect()
    }
    return () => {
      intentionalDisconnectRef.current = true
      clearTimers()
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted')
        wsRef.current = null
      }
    }
  }, [autoConnect, connect, clearTimers])

  return {
    ...state,
    connect,
    disconnect,
    sendPing,
    requestStatus,
    toggleStream,
    pauseStream,
    resumeStream,
    emergencyStop,
  }
}
