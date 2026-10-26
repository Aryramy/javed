import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MCPAdminPanel } from '../components/dev/MCPAdminPanel'
import { mcpService, type DiscoveredTool, type MCPServerStatus } from '../services/mcpService'

describe('MCPAdminPanel Component (Phase 6 Developer Mode)', () => {
  const mockServer: MCPServerStatus = {
    server_id: 'time',
    server_name: 'Time Reference Server',
    transport_type: 'stdio',
    connection_state: 'connected',
    protocol_version: '2026-07-28',
    discovered_tool_count: 2,
  }

  const mockTool1: DiscoveredTool = {
    tool_id: 'time__get_current_time',
    server_id: 'time',
    original_name: 'get_current_time',
    description: 'Get current time in timezone',
    input_schema: { type: 'object' },
    fingerprint: 'fp_get_time_123456789012345678901234',
    permission: 'denied',
    enabled: false,
    discovered_at: new Date().toISOString(),
  }

  const mockTool2: DiscoveredTool = {
    tool_id: 'time__convert_time',
    server_id: 'time',
    original_name: 'convert_time',
    description: 'Convert time between timezones',
    input_schema: { type: 'object' },
    fingerprint: 'fp_convert_time_12345678901234567890',
    permission: 'denied',
    enabled: false,
    discovered_at: new Date().toISOString(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(mcpService, 'getServers').mockResolvedValue({
      servers: [mockServer],
      total: 1,
    })
    vi.spyOn(mcpService, 'getTools').mockResolvedValue({
      tools: [mockTool1, mockTool2],
      server_count: 1,
      policy_version: 0,
      total: 2,
    })
  })

  it('renders MCP server status and shows owner authentication required banner when unauthenticated', async () => {
    vi.spyOn(mcpService, 'checkSession').mockResolvedValue({ authenticated: false })
    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-admin-panel')).toBeInTheDocument()
    })

    expect(screen.getByTestId('mcp-policy-version')).toHaveTextContent('Policy v0')
    expect(screen.getByTestId('mcp-server-time')).toBeInTheDocument()
    expect(screen.getByText('Time Reference Server')).toBeInTheDocument()
    expect(screen.getByText(/2026-07-28/)).toBeInTheDocument()

    expect(screen.getByTestId('mcp-tool-time__get_current_time')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-tool-time__convert_time')).toBeInTheDocument()

    // Owner auth card is rendered and mutation controls are disabled
    expect(screen.getByTestId('mcp-owner-auth-card')).toHaveTextContent(/Owner Authentication Required/i)
    expect(screen.getByTestId('mcp-perm-select-time__get_current_time')).toBeDisabled()
    expect(screen.getByTestId('mcp-perm-update-btn-time__get_current_time')).toBeDisabled()
  })

  it('authenticates with owner token, unlocks controls, and mutates tool permission', async () => {
    const user = userEvent.setup()
    vi.spyOn(mcpService, 'checkSession').mockResolvedValue({ authenticated: false })
    const loginSpy = vi.spyOn(mcpService, 'loginOwner').mockResolvedValue({
      session_token: 'jvd_sess_mock123',
      expires_in: 3600,
    })
    const updateSpy = vi.spyOn(mcpService, 'updateToolPermission').mockResolvedValue({
      tool: {
        ...mockTool1,
        permission: 'allowed_read_only',
        enabled: true,
      },
      policy_version: 1,
    })

    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-owner-token-input')).toBeInTheDocument()
    })

    // Enter owner token and unlock
    const tokenInput = screen.getByTestId('mcp-owner-token-input')
    await user.type(tokenInput, 'valid-owner-secret')
    const unlockBtn = screen.getByTestId('mcp-owner-token-submit-btn')
    await user.click(unlockBtn)

    expect(loginSpy).toHaveBeenCalledWith('valid-owner-secret')

    await waitFor(() => {
      expect(screen.getByTestId('mcp-owner-auth-card')).toHaveTextContent(/Owner Session Active/i)
    })

    // Mutation select is now enabled
    const select = screen.getByTestId('mcp-perm-select-time__get_current_time')
    expect(select).toBeEnabled()
    await user.selectOptions(select, 'allowed_read_only')

    // Click Apply Permission
    const applyBtn = screen.getByTestId('mcp-perm-update-btn-time__get_current_time')
    expect(applyBtn).toBeEnabled()
    await user.click(applyBtn)

    expect(updateSpy).toHaveBeenCalledWith(
      'time__get_current_time',
      'allowed_read_only',
      true,
      0,
      mockTool1.fingerprint
    )

    await waitFor(() => {
      expect(screen.getByTestId('mcp-policy-version')).toHaveTextContent('Policy v1')
      expect(screen.getByTestId('mcp-admin-feedback')).toHaveTextContent(/Updated 'time__get_current_time' to ALLOWED_READ_ONLY/i)
    })
  })

  it('handles failed owner authentication cleanly with error banner', async () => {
    const user = userEvent.setup()
    vi.spyOn(mcpService, 'checkSession').mockResolvedValue({ authenticated: false })
    vi.spyOn(mcpService, 'loginOwner').mockRejectedValue(new Error('Invalid owner credentials.'))

    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-owner-token-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('mcp-owner-token-input'), 'wrong-token')
    await user.click(screen.getByTestId('mcp-owner-token-submit-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('mcp-admin-feedback')).toHaveTextContent(/Invalid owner credentials/i)
    })
  })

  it('handles server refresh action when authenticated and supports logout', async () => {
    const user = userEvent.setup()
    vi.spyOn(mcpService, 'checkSession').mockResolvedValue({ authenticated: true, expires_in: 3600 })
    const refreshSpy = vi.spyOn(mcpService, 'refreshServer').mockResolvedValue({
      tool_count: 2,
      message: 'Refreshed successfully',
    })
    const logoutSpy = vi.spyOn(mcpService, 'logoutOwner').mockResolvedValue()

    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-refresh-time')).toBeEnabled()
    })

    // Refresh tools
    const refreshBtn = screen.getByTestId('mcp-refresh-time')
    await user.click(refreshBtn)

    expect(refreshSpy).toHaveBeenCalledWith('time')
    await waitFor(() => {
      expect(screen.getByTestId('mcp-admin-feedback')).toHaveTextContent(/Discovered 2 tool\(s\)/i)
    })

    // Lock console (logout)
    const lockBtn = screen.getByTestId('mcp-owner-logout-btn')
    await user.click(lockBtn)

    expect(logoutSpy).toHaveBeenCalled()
    await waitFor(() => {
      expect(screen.getByTestId('mcp-owner-auth-card')).toHaveTextContent(/Owner Authentication Required/i)
    })
  })
})
