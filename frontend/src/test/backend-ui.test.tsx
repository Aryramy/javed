import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider, ModeProvider, BackendProvider } from '@/context'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { ConnectivityView } from '@/views/dev/ConnectivityView'
import { DiagnosticsView } from '@/views/dev/DiagnosticsView'
import { ChatView } from '@/views/user/ChatView'

describe('Backend UI Integration Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks()

    // Mock global fetch
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health/live')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: 'live', timestamp: '2026-10-22T10:00:00Z' }),
        })
      }
      if (url.includes('/health/ready')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            status: 'ready',
            timestamp: '2026-10-22T10:00:00Z',
            dependencies: { backend_runtime: { status: 'ready', details: null } },
          }),
        })
      }
      if (url.includes('/system/status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            app_name: 'Javed — New JARVIS',
            backend_version: '0.1.0',
            api_version: 'v1',
            environment: 'development',
            server_time: '2026-10-22T10:00:00Z',
            uptime_seconds: 42.0,
            active_ws_connections: 1,
            capabilities: { rest_api: true, websocket: true, sse: true, ai_chat: false },
          }),
        })
      }
      if (url.includes('/ping')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ message: 'pong', timestamp: '2026-10-22T10:00:00Z', echo: 'test' }),
        })
      }
      return Promise.reject(new Error(`Unhandled URL: ${url}`))
    })
  })

  const renderWithProviders = (ui: React.ReactElement) => {
    return render(
      <ThemeProvider>
        <ModeProvider>
          <BackendProvider>
            <MemoryRouter>{ui}</MemoryRouter>
          </BackendProvider>
        </ModeProvider>
      </ThemeProvider>
    )
  }

  it('renders Header with live backend connection indicator', async () => {
    renderWithProviders(<Header mobileMenuOpen={false} setMobileMenuOpen={() => {}} />)

    // The header should contain the connection button/pill
    const statusButton = screen.getByRole('button', { name: /backend connection status/i })
    expect(statusButton).toBeInTheDocument()
  })

  it('renders Header and Sidebar with consistent verified backend connection state', async () => {
    renderWithProviders(
      <div>
        <Header mobileMenuOpen={false} setMobileMenuOpen={() => {}} />
        <Sidebar mobileOpen={false} setMobileOpen={() => {}} />
      </div>
    )

    const statusButton = screen.getByRole('button', { name: /backend connection status/i })
    expect(statusButton).toBeInTheDocument()

    const sidebarStatus = screen.getByTestId('sidebar-connection-status')
    expect(sidebarStatus).toBeInTheDocument()
  })

  it('renders ConnectivityView with subsystem monitor and live telemetry', async () => {
    renderWithProviders(<ConnectivityView />)

    expect(screen.getByText(/Subsystem Connectivity Monitor/i)).toBeInTheDocument()
    expect(screen.getByText(/FastAPI REST Gateway/i)).toBeInTheDocument()
    expect(screen.getByText(/WebSocket Transport Channel/i)).toBeInTheDocument()
  })

  it('renders DiagnosticsView and executes Check System Status action', async () => {
    renderWithProviders(<DiagnosticsView />)

    const checkButton = screen.getByRole('button', { name: /Check System Status/i })
    expect(checkButton).toBeInTheDocument()

    fireEvent.click(checkButton)

    await waitFor(() => {
      expect(screen.getByText(/GET \/api\/v1\/system\/status/i)).toBeInTheDocument()
    })
  })

  it('renders DiagnosticsView and executes Liveness Probe action', async () => {
    renderWithProviders(<DiagnosticsView />)

    const liveButton = screen.getByRole('button', { name: /Liveness Probe/i })
    fireEvent.click(liveButton)

    await waitFor(() => {
      expect(screen.getByText(/GET \/api\/v1\/health\/live/i)).toBeInTheDocument()
    })
  })

  it('renders ChatView with real backend status banner', async () => {
    renderWithProviders(<ChatView />)

    expect(screen.getAllByText(/BACKEND/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Stage 1 Transport Verified/i)).toBeInTheDocument()
    expect(screen.getByText(/Conversational AI Gateway/i)).toBeInTheDocument()
  })
})
