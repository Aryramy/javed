import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { apiService } from '../services/api'

describe('apiService REST Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches live status successfully', async () => {
    const mockData = { status: 'live', timestamp: '2026-10-22T10:00:00Z' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const result = await apiService.getLive()
    expect(result).toEqual(mockData)
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/v1/health/live', expect.any(Object))
  })

  it('fetches ready status successfully', async () => {
    const mockData = {
      status: 'ready',
      timestamp: '2026-10-22T10:00:00Z',
      dependencies: {
        backend_runtime: { status: 'ready', details: 'All good' },
      },
    }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const result = await apiService.getReady()
    expect(result.status).toBe('ready')
    expect(result.dependencies.backend_runtime.status).toBe('ready')
  })

  it('fetches system status metadata', async () => {
    const mockData = {
      app_name: 'Javed — New JARVIS',
      backend_version: '0.1.0',
      api_version: 'v1',
      environment: 'development',
      server_time: '2026-10-22T10:00:00Z',
      uptime_seconds: 123.45,
      active_ws_connections: 1,
      capabilities: { rest_api: true, websocket: true, sse: true, ai_chat: false },
    }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const result = await apiService.getSystemStatus()
    expect(result.backend_version).toBe('0.1.0')
    expect(result.capabilities.ai_chat).toBe(false)
  })

  it('measures round-trip ping latency', async () => {
    const mockData = { message: 'pong', timestamp: '2026-10-22T10:00:00Z', echo: 'token123' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    })

    const { latencyMs, response } = await apiService.ping()
    expect(response.message).toBe('pong')
    expect(typeof latencyMs).toBe('number')
    expect(latencyMs).toBeGreaterThanOrEqual(0)
  })

  it('throws ApiError with server error details on HTTP 500', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: { code: 'INTERNAL_ERROR', message: 'Database failed' } }),
    })

    await expect(apiService.getLive()).rejects.toThrow('Database failed')
  })
})
