import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { WebSocketClient } from '../services/websocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: (() => void) | null = null
  onclose: ((event: { code: number; reason: string }) => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: ((error: unknown) => void) | null = null
  sentMessages: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sentMessages.push(data)
  }

  close(code = 1000, reason = 'Normal closure') {
    this.readyState = 3 // CLOSED
    if (this.onclose) {
      this.onclose({ code, reason })
    }
  }

  // Helper to trigger open
  simulateOpen() {
    this.readyState = 1 // OPEN
    if (this.onopen) {
      this.onopen()
    }
  }

  // Helper to trigger message
  simulateMessage(data: object) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }
}

describe('WebSocketClient Service', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    // @ts-expect-error Mocking global WebSocket
    global.WebSocket = MockWebSocket
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('connects and transitions state to connected upon open', () => {
    const client = new WebSocketClient()
    const stateSpy = vi.fn()
    client.onStateChange(stateSpy)

    client.connect()
    expect(stateSpy).toHaveBeenCalledWith('connecting')

    const wsInstance = MockWebSocket.instances[0]
    expect(wsInstance).toBeDefined()

    wsInstance.simulateOpen()
    expect(stateSpy).toHaveBeenCalledWith('connected')
    expect(client.getState()).toBe('connected')
  })

  it('receives welcome handshake and emits event', () => {
    const client = new WebSocketClient()
    const eventSpy = vi.fn()
    client.onEvent(eventSpy)

    client.connect()
    const wsInstance = MockWebSocket.instances[0]
    wsInstance.simulateOpen()

    wsInstance.simulateMessage({
      type: 'connection_established',
      version: '1.0',
      payload: { client_id: 'test-client-123' },
    })

    expect(eventSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'WS_CONNECTED',
        details: expect.stringContaining('test-client-123'),
      })
    )
  })

  it('sends heartbeat periodically and handles ack', () => {
    const client = new WebSocketClient({ heartbeatIntervalMs: 5000 })
    client.connect()
    const wsInstance = MockWebSocket.instances[0]
    wsInstance.simulateOpen()

    // Advance clock to trigger heartbeat
    vi.advanceTimersByTime(5000)

    expect(wsInstance.sentMessages.length).toBeGreaterThan(0)
    const sentEnvelope = JSON.parse(wsInstance.sentMessages[0])
    expect(sentEnvelope.type).toBe('heartbeat')

    // Simulate ack response
    const latencySpy = vi.fn()
    client.onLatency(latencySpy)
    wsInstance.simulateMessage({
      type: 'heartbeat_ack',
      correlation_id: sentEnvelope.correlation_id,
      payload: { server_time: new Date().toISOString() },
    })

    expect(latencySpy).toHaveBeenCalled()
  })

  it('schedules bounded reconnection with backoff upon disconnect', () => {
    const client = new WebSocketClient({ baseDelayMs: 1000, maxDelayMs: 5000 })
    const stateSpy = vi.fn()
    client.onStateChange(stateSpy)

    client.connect()
    const wsInstance = MockWebSocket.instances[0]
    wsInstance.simulateOpen()

    // Simulate unexpected drop
    wsInstance.close(1006, 'Abnormal closure')
    expect(stateSpy).toHaveBeenCalledWith('disconnected')
    expect(client.getReconnectAttempts()).toBe(1)
    expect(client.getState()).toBe('reconnecting')

    // Advance timer past backoff delay
    vi.advanceTimersByTime(2000)

    // A second socket connection attempt should have been created
    expect(MockWebSocket.instances.length).toBe(2)
  })

  it('cancels reconnection on intentional disconnect()', () => {
    const client = new WebSocketClient()
    client.connect()
    const wsInstance = MockWebSocket.instances[0]
    wsInstance.simulateOpen()

    client.disconnect()
    expect(client.getState()).toBe('disconnected')

    // Advance time, no new sockets should be created
    vi.advanceTimersByTime(10000)
    expect(MockWebSocket.instances.length).toBe(1)
  })
})
