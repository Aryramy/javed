/**
 * TypeScript type definitions for Browser Automation, Viewport Streaming,
 * and Live Preview Panel components.
 */

export type BrowserConnectionStatus = 'CONNECTING' | 'CONNECTED' | 'DISCONNECTED' | 'ERROR'

export interface ViewportFramePayload {
  image: string
  title: string
  url: string
  format: string
  frame_number: number
  viewport_width: number
  viewport_height: number
  timestamp: string
  size_bytes?: number
}

export interface StreamerStatusPayload {
  has_page: boolean
  is_running: boolean
  subscribers: number
  interval_seconds: number
  quality: number
  total_frames_captured: number
  url: string
  title: string
}

export interface BrowserControlMessage {
  action: 'ping' | 'status' | 'pause' | 'resume' | 'unsubscribe' | 'subscribe'
  client_timestamp?: string
}

export interface BrowserStreamState {
  status: BrowserConnectionStatus
  currentUrl: string | null
  pageTitle: string | null
  frameImage: string | null
  frameNumber: number
  timestamp: string | null
  dimensions: { width: number; height: number } | null
  isStreaming: boolean
  lastLatencyMs: number | null
  error: string | null
  totalFrames: number
}

