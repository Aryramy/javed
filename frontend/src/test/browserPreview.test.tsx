/**
 * Vitest unit tests for BrowserPreviewPanel and useBrowserStream hook.
 *
 * Verifies:
 * 1. Hook connection lifecycle, frame payload parsing, and control messaging.
 * 2. Live viewport image rendering, URL bar display, and dimensions badge.
 * 3. Emergency stop, stream pause/resume controls, and clean unmount cleanup.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderHook } from '@testing-library/react'

import { useBrowserStream, type UseBrowserStreamReturn } from '../hooks/useBrowserStream'
import { BrowserPreviewPanel } from '../components/browser/BrowserPreviewPanel'
import { BrowserView } from '../views/user/BrowserView'

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
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose({ code, reason })
    }
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    if (this.onopen) {
      this.onopen()
    }
  }

  simulateMessage(data: object) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) })
    }
  }

  simulateError(err: unknown = new Event('error')) {
    if (this.onerror) {
      this.onerror(err)
    }
  }
}

describe('Browser Viewport Streaming & Preview Panel', () => {
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

  describe('useBrowserStream Hook', () => {
    it('initializes and connects to target WebSocket URL on mount', () => {
      const { result } = renderHook(() =>
        useBrowserStream({ url: 'ws://localhost:8000/ws/browser' })
      )

      expect(MockWebSocket.instances).toHaveLength(1)
      expect(MockWebSocket.instances[0].url).toBe('ws://localhost:8000/ws/browser')
      expect(result.current.status).toBe('CONNECTING')

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      expect(result.current.status).toBe('CONNECTED')
      expect(result.current.isStreaming).toBe(true)
    })

    it('parses viewport_frame envelope and updates frame state and callbacks', () => {
      const onFrameSpy = vi.fn()
      const { result } = renderHook(() =>
        useBrowserStream({
          url: 'ws://localhost:8000/ws/browser',
          onFrame: onFrameSpy,
        })
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      const testPayload = {
        type: 'viewport_frame',
        payload: {
          image: 'data:image/jpeg;base64,mockJpegData12345',
          title: 'Example Domain',
          url: 'https://example.com',
          format: 'jpeg',
          frame_number: 1,
          viewport_width: 1280,
          viewport_height: 720,
          timestamp: '2026-10-28T12:00:00Z',
          size_bytes: 4096,
        },
      }

      act(() => {
        MockWebSocket.instances[0].simulateMessage(testPayload)
      })

      expect(result.current.currentUrl).toBe('https://example.com')
      expect(result.current.pageTitle).toBe('Example Domain')
      expect(result.current.frameImage).toBe('data:image/jpeg;base64,mockJpegData12345')
      expect(result.current.frameNumber).toBe(1)
      expect(result.current.totalFrames).toBe(1)
      expect(result.current.dimensions).toEqual({ width: 1280, height: 720 })
      expect(onFrameSpy).toHaveBeenCalledWith(testPayload.payload)
    })

    it('calculates roundtrip latency on pong message', () => {
      const { result } = renderHook(() =>
        useBrowserStream({ url: 'ws://localhost:8000/ws/browser' })
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
      })

      act(() => {
        result.current.sendPing()
      })

      expect(MockWebSocket.instances[0].sentMessages).toHaveLength(1)
      const sent = JSON.parse(MockWebSocket.instances[0].sentMessages[0])
      expect(sent.action).toBe('ping')

      // Advance clock by 45ms
      act(() => {
        vi.advanceTimersByTime(45)
        MockWebSocket.instances[0].simulateMessage({
          type: 'pong',
          payload: { timestamp: '2026-10-28T12:00:00Z' },
        })
      })

      expect(result.current.lastLatencyMs).toBe(45)
    })

    it('sends pause, resume, and requestStatus messages', () => {
      const { result } = renderHook(() =>
        useBrowserStream({ url: 'ws://localhost:8000/ws/browser' })
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
        result.current.pauseStream()
      })

      expect(result.current.isStreaming).toBe(false)
      const pauseMsg = JSON.parse(
        MockWebSocket.instances[0].sentMessages[
          MockWebSocket.instances[0].sentMessages.length - 1
        ]
      )
      expect(pauseMsg.action).toBe('pause')

      act(() => {
        result.current.resumeStream()
      })

      expect(result.current.isStreaming).toBe(true)
      const resumeMsg = JSON.parse(
        MockWebSocket.instances[0].sentMessages[
          MockWebSocket.instances[0].sentMessages.length - 1
        ]
      )
      expect(resumeMsg.action).toBe('resume')

      act(() => {
        result.current.requestStatus()
      })

      const statusMsg = JSON.parse(
        MockWebSocket.instances[0].sentMessages[
          MockWebSocket.instances[0].sentMessages.length - 1
        ]
      )
      expect(statusMsg.action).toBe('status')
    })

    it('executes emergencyStop cleanly by sending pause and disconnecting', () => {
      const { result } = renderHook(() =>
        useBrowserStream({ url: 'ws://localhost:8000/ws/browser' })
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
        result.current.emergencyStop()
      })

      expect(result.current.status).toBe('DISCONNECTED')
      expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED)
      const sentActions = MockWebSocket.instances[0].sentMessages.map(
        (m) => JSON.parse(m).action
      )
      expect(sentActions).toContain('pause')
    })

    it('handles clean unmount without leaving dangling connections', () => {
      const { unmount } = renderHook(() =>
        useBrowserStream({ url: 'ws://localhost:8000/ws/browser' })
      )

      act(() => {
        MockWebSocket.instances[0].simulateOpen()
        unmount()
      })

      expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED)
    })
  })

  describe('BrowserPreviewPanel Component', () => {
    it('renders empty state, URL bar, and connection status when disconnected', () => {
      render(
        <BrowserPreviewPanel
          wsUrl="ws://localhost:8000/ws/browser"
          autoConnect={false}
        />
      )

      expect(screen.getByTestId('browser-preview-panel')).toBeInTheDocument()
      expect(screen.getByTestId('browser-status-disconnected')).toBeInTheDocument()
      expect(screen.getByTestId('browser-url-input')).toHaveValue('about:blank')
      expect(screen.getByTestId('browser-empty-state')).toBeInTheDocument()
      expect(screen.getByTestId('browser-connect-btn')).toBeInTheDocument()
    })

    it('renders live viewport frame image, title, and metadata badges', () => {
      const mockStream: UseBrowserStreamReturn = {
        status: 'CONNECTED',
        currentUrl: 'https://news.ycombinator.com',
        pageTitle: 'Hacker News',
        frameImage: 'data:image/jpeg;base64,mockHackerNewsFrame',
        frameNumber: 42,
        timestamp: '2026-10-28T12:00:00Z',
        dimensions: { width: 1280, height: 720 },
        isStreaming: true,
        lastLatencyMs: 14,
        error: null,
        totalFrames: 42,
        connect: vi.fn(),
        disconnect: vi.fn(),
        sendPing: vi.fn(),
        requestStatus: vi.fn(),
        toggleStream: vi.fn(),
        pauseStream: vi.fn(),
        resumeStream: vi.fn(),
        emergencyStop: vi.fn(),
      }

      render(<BrowserPreviewPanel stream={mockStream} />)

      expect(screen.getByTestId('browser-status-connected')).toBeInTheDocument()
      expect(screen.getByTestId('browser-page-title')).toHaveTextContent('Hacker News')
      expect(screen.getByTestId('browser-url-input')).toHaveValue(
        'https://news.ycombinator.com'
      )
      expect(screen.getByTestId('browser-dimensions-badge')).toHaveTextContent(
        '1280×720'
      )
      expect(screen.getByTestId('browser-frame-badge')).toHaveTextContent('Frame #42')
      expect(screen.getByTestId('browser-latency-badge')).toHaveTextContent('14ms')

      const img = screen.getByTestId('browser-viewport-frame')
      expect(img).toBeInTheDocument()
      expect(img).toHaveAttribute('src', 'data:image/jpeg;base64,mockHackerNewsFrame')
    })

    it('invokes emergencyStop when clicking Emergency Stop button', async () => {
      vi.useRealTimers()
      const user = userEvent.setup()
      const emergencyStopSpy = vi.fn()

      const mockStream: UseBrowserStreamReturn = {
        status: 'CONNECTED',
        currentUrl: 'https://example.com',
        pageTitle: 'Example',
        frameImage: 'data:image/jpeg;base64,mockData',
        frameNumber: 1,
        timestamp: '2026-10-28T12:00:00Z',
        dimensions: { width: 1280, height: 720 },
        isStreaming: true,
        lastLatencyMs: 10,
        error: null,
        totalFrames: 1,
        connect: vi.fn(),
        disconnect: vi.fn(),
        sendPing: vi.fn(),
        requestStatus: vi.fn(),
        toggleStream: vi.fn(),
        pauseStream: vi.fn(),
        resumeStream: vi.fn(),
        emergencyStop: emergencyStopSpy,
      }

      render(<BrowserPreviewPanel stream={mockStream} />)

      const stopBtn = screen.getByTestId('browser-disconnect-btn')
      expect(stopBtn).toHaveTextContent(/Emergency Stop/i)

      await user.click(stopBtn)
      expect(emergencyStopSpy).toHaveBeenCalledTimes(1)
    })

    it('invokes toggleStream when clicking stream pause/resume button', async () => {
      vi.useRealTimers()
      const user = userEvent.setup()
      const toggleStreamSpy = vi.fn()

      const mockStream: UseBrowserStreamReturn = {
        status: 'CONNECTED',
        currentUrl: 'https://example.com',
        pageTitle: 'Example',
        frameImage: 'data:image/jpeg;base64,mockData',
        frameNumber: 1,
        timestamp: '2026-10-28T12:00:00Z',
        dimensions: null,
        isStreaming: true,
        lastLatencyMs: null,
        error: null,
        totalFrames: 1,
        connect: vi.fn(),
        disconnect: vi.fn(),
        sendPing: vi.fn(),
        requestStatus: vi.fn(),
        toggleStream: toggleStreamSpy,
        pauseStream: vi.fn(),
        resumeStream: vi.fn(),
        emergencyStop: vi.fn(),
      }

      render(<BrowserPreviewPanel stream={mockStream} />)

      const toggleBtn = screen.getByTestId('browser-stream-toggle')
      await user.click(toggleBtn)
      expect(toggleStreamSpy).toHaveBeenCalledTimes(1)
    })

    it('renders stream paused overlay when isStreaming is false', () => {
      const mockStream: UseBrowserStreamReturn = {
        status: 'CONNECTED',
        currentUrl: 'https://example.com',
        pageTitle: 'Example',
        frameImage: 'data:image/jpeg;base64,mockData',
        frameNumber: 1,
        timestamp: '2026-10-28T12:00:00Z',
        dimensions: null,
        isStreaming: false,
        lastLatencyMs: null,
        error: null,
        totalFrames: 1,
        connect: vi.fn(),
        disconnect: vi.fn(),
        sendPing: vi.fn(),
        requestStatus: vi.fn(),
        toggleStream: vi.fn(),
        pauseStream: vi.fn(),
        resumeStream: vi.fn(),
        emergencyStop: vi.fn(),
      }

      render(<BrowserPreviewPanel stream={mockStream} />)
      expect(screen.getByTestId('browser-paused-overlay')).toBeInTheDocument()
      expect(screen.getByText('Stream Paused')).toBeInTheDocument()
    })

    it('renders BrowserView successfully hosting BrowserPreviewPanel', () => {
      render(<BrowserView />)
      expect(screen.getByText('Browser Automation Console')).toBeInTheDocument()
      expect(screen.getByTestId('browser-preview-panel')).toBeInTheDocument()
    })
  })
})

