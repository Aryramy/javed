/**
 * Real-time WebSocket client with bounded exponential backoff, jitter, and heartbeat.
 */

import type { ConnectionState, EventEnvelope, TransportEvent } from './types'

export type StateChangeCallback = (state: ConnectionState) => void
export type EventCallback = (event: TransportEvent) => void
export type LatencyCallback = (latencyMs: number) => void

interface WebSocketClientOptions {
  baseDelayMs?: number
  maxDelayMs?: number
  backoffFactor?: number
  heartbeatIntervalMs?: number
  maxReconnectAttempts?: number
}

export class WebSocketClient {
  private ws: WebSocket | null = null
  private state: ConnectionState = 'disconnected'
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private pendingPings = new Map<string, number>()
  private intentionalDisconnect = false

  private readonly baseDelayMs: number
  private readonly maxDelayMs: number
  private readonly backoffFactor: number
  private readonly heartbeatIntervalMs: number
  private readonly maxReconnectAttempts: number

  private stateListeners: Set<StateChangeCallback> = new Set()
  private eventListeners: Set<EventCallback> = new Set()
  private latencyListeners: Set<LatencyCallback> = new Set()

  constructor(options: WebSocketClientOptions = {}) {
    this.baseDelayMs = options.baseDelayMs ?? 1000
    this.maxDelayMs = options.maxDelayMs ?? 15000
    this.backoffFactor = options.backoffFactor ?? 1.5
    this.heartbeatIntervalMs = options.heartbeatIntervalMs ?? 15000
    this.maxReconnectAttempts = options.maxReconnectAttempts ?? 20
  }

  public getState(): ConnectionState {
    return this.state
  }

  public getReconnectAttempts(): number {
    return this.reconnectAttempts
  }

  public onStateChange(cb: StateChangeCallback): () => void {
    this.stateListeners.add(cb)
    return () => this.stateListeners.delete(cb)
  }

  public onEvent(cb: EventCallback): () => void {
    this.eventListeners.add(cb)
    return () => this.eventListeners.delete(cb)
  }

  public onLatency(cb: LatencyCallback): () => void {
    this.latencyListeners.add(cb)
    return () => this.latencyListeners.delete(cb)
  }

  private setState(newState: ConnectionState): void {
    if (this.state !== newState) {
      this.state = newState
      this.stateListeners.forEach((cb) => cb(newState))
    }
  }

  private emitEvent(
    type: TransportEvent['type'],
    source: TransportEvent['source'],
    details: string,
    latencyMs?: number,
    data?: unknown
  ): void {
    const event: TransportEvent = {
      id: Math.random().toString(36).substring(7),
      timestamp: new Date().toISOString(),
      type,
      source,
      details,
      latencyMs,
      data,
    }
    this.eventListeners.forEach((cb) => cb(event))
  }

  private getWebSocketUrl(): string {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${window.location.host}/api/v1/ws`
  }

  public connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.CONNECTING || this.ws.readyState === WebSocket.OPEN)) {
      return
    }

    this.intentionalDisconnect = false
    this.clearTimers()

    this.setState(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting')

    try {
      const url = this.getWebSocketUrl()
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        this.setState('connected')
        this.startHeartbeat()
      }

      this.ws.onmessage = (event) => {
        this.handleMessage(event.data)
      }

      this.ws.onerror = (err) => {
        this.emitEvent('ERROR', 'WebSocket', 'WebSocket transport error', undefined, err)
      }

      this.ws.onclose = (event) => {
        this.stopHeartbeat()
        this.pendingPings.clear()
        this.ws = null

        if (this.intentionalDisconnect) {
          this.setState('disconnected')
          this.emitEvent('WS_DISCONNECTED', 'WebSocket', `Disconnected cleanly (code: ${event.code})`)
        } else {
          this.setState('disconnected')
          this.emitEvent(
            'WS_DISCONNECTED',
            'WebSocket',
            `Connection closed: ${event.reason || `code ${event.code}`}. Reconnecting...`
          )
          this.scheduleReconnect()
        }
      }
    } catch {
      this.setState('disconnected')
      this.scheduleReconnect()
    }
  }

  public disconnect(): void {
    this.intentionalDisconnect = true
    this.clearTimers()
    if (this.ws) {
      this.ws.close(1000, 'User initiated disconnect')
      this.ws = null
    }
    this.setState('disconnected')
  }

  public reconnect(): void {
    this.disconnect()
    this.reconnectAttempts = 0
    this.connect()
  }

  private scheduleReconnect(): void {
    if (this.intentionalDisconnect) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emitEvent('ERROR', 'WebSocket', `Max reconnect attempts (${this.maxReconnectAttempts}) reached.`)
      this.setState('disconnected')
      return
    }

    this.reconnectAttempts++
    // Exponential backoff with jitter
    const rawDelay = Math.min(
      this.maxDelayMs,
      this.baseDelayMs * Math.pow(this.backoffFactor, this.reconnectAttempts - 1)
    )
    const jitter = (Math.random() * 0.4 - 0.2) * rawDelay // +/- 20%
    const delay = Math.round(Math.max(this.baseDelayMs, rawDelay + jitter))

    this.setState('reconnecting')
    this.emitEvent(
      'RECONNECT_ATTEMPT',
      'WebSocket',
      `Scheduling reconnect attempt #${this.reconnectAttempts} in ${delay}ms`
    )

    this.reconnectTimer = setTimeout(() => {
      this.connect()
    }, delay)
  }

  private startHeartbeat(): void {
    this.stopHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.sendHeartbeat()
    }, this.heartbeatIntervalMs)
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private clearTimers(): void {
    this.stopHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  public sendHeartbeat(): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return

    const correlationId = `hb-${Math.random().toString(36).substring(7)}`
    const sendTime = performance.now()
    this.pendingPings.set(correlationId, sendTime)

    const envelope: EventEnvelope = {
      type: 'heartbeat',
      version: '1.0',
      correlation_id: correlationId,
      timestamp: new Date().toISOString(),
      payload: { client_time: Date.now() },
    }

    this.ws.send(JSON.stringify(envelope))
  }

  public sendPing(): Promise<number> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        return reject(new Error('WebSocket is not connected'))
      }

      const correlationId = `ping-${Math.random().toString(36).substring(7)}`
      const sendTime = performance.now()
      this.pendingPings.set(correlationId, sendTime)

      const envelope: EventEnvelope = {
        type: 'ping',
        version: '1.0',
        correlation_id: correlationId,
        timestamp: new Date().toISOString(),
        payload: { client_time: Date.now() },
      }

      const timeout = setTimeout(() => {
        this.pendingPings.delete(correlationId)
        reject(new Error('Ping timeout'))
      }, 5000)

      const unregister = this.onEvent((event) => {
        if (event.type === 'PING_ACK' && event.data === correlationId) {
          clearTimeout(timeout)
          unregister()
          resolve(event.latencyMs ?? 0)
        }
      })

      this.ws.send(JSON.stringify(envelope))
    })
  }

  private handleMessage(rawData: string): void {
    try {
      const envelope = JSON.parse(rawData) as EventEnvelope
      const corrId = envelope.correlation_id

      if (envelope.type === 'connection_established') {
        const clientId = (envelope.payload as { client_id?: string }).client_id ?? 'unknown'
        this.emitEvent('WS_CONNECTED', 'WebSocket', `Connected with Client ID: ${clientId}`, undefined, envelope.payload)
      } else if (envelope.type === 'pong' || envelope.type === 'heartbeat_ack') {
        let latencyMs: number | undefined
        if (corrId && this.pendingPings.has(corrId)) {
          const sendTime = this.pendingPings.get(corrId)!
          this.pendingPings.delete(corrId)
          latencyMs = Math.round((performance.now() - sendTime) * 10) / 10
          this.latencyListeners.forEach((cb) => cb(latencyMs!))
        }

        const eventType = envelope.type === 'pong' ? 'PING_ACK' : 'HEARTBEAT_ACK'
        this.emitEvent(
          eventType,
          'WebSocket',
          `${envelope.type.toUpperCase()} acknowledged (latency: ${latencyMs ?? 'unknown'}ms)`,
          latencyMs,
          corrId
        )
      } else if (envelope.type === 'error') {
        this.emitEvent('ERROR', 'WebSocket', `Backend error: ${(envelope.payload as { message?: string }).message}`, undefined, envelope.payload)
      } else {
        this.emitEvent('SERVER_EVENT', 'WebSocket', `Event received: ${envelope.type}`, undefined, envelope.payload)
      }
    } catch (err: unknown) {
      this.emitEvent('ERROR', 'WebSocket', `Failed to parse message: ${err}`)
    }
  }
}

// Singleton client instance for the application
export const wsClient = new WebSocketClient()
