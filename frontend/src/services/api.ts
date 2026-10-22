/**
 * REST API client service for Project Javed.
 */

import type { LiveResponse, PingResponse, ReadyResponse, SystemStatusResponse } from './types'

const DEFAULT_TIMEOUT_MS = 5000

class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function requestWithTimeout<T>(url: string, options: RequestInit = {}, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    if (!res.ok) {
      let code = 'HTTP_ERROR'
      let message = `Request failed with status ${res.status}`
      try {
        const errorData = await res.json()
        if (errorData?.error?.message) {
          message = errorData.error.message
          code = errorData.error.code || code
        }
      } catch {
        // Response wasn't json
      }
      throw new ApiError(message, res.status, code)
    }

    return (await res.json()) as T
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError(`Request timeout after ${timeoutMs}ms`, 408, 'TIMEOUT')
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export const apiService = {
  /**
   * Check if backend process is alive.
   */
  async getLive(): Promise<LiveResponse> {
    return requestWithTimeout<LiveResponse>('/api/v1/health/live')
  },

  /**
   * Check if backend dependencies are ready.
   */
  async getReady(): Promise<ReadyResponse> {
    return requestWithTimeout<ReadyResponse>('/api/v1/health/ready')
  },

  /**
   * Fetch safe system status metadata.
   */
  async getSystemStatus(): Promise<SystemStatusResponse> {
    return requestWithTimeout<SystemStatusResponse>('/api/v1/system/status')
  },

  /**
   * Send round-trip ping and measure actual latency in milliseconds.
   */
  async ping(): Promise<{ latencyMs: number; response: PingResponse }> {
    const start = performance.now()
    const echoToken = Math.random().toString(36).substring(7)
    const response = await requestWithTimeout<PingResponse>(`/api/v1/ping?echo=${echoToken}`)
    const latencyMs = Math.round((performance.now() - start) * 10) / 10
    return { latencyMs, response }
  },
}
