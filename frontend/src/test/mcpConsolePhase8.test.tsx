import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MCPAdminPanel } from '../components/dev/MCPAdminPanel'
import {
  mcpService,
  type DiscoveredTool,
  type ExecutionLedgerEntry,
  type MCPServerStatus,
  type ApprovalsSummaryResponse,
} from '../services/mcpService'
import { apiService } from '../services/api'

describe('Developer MCP Console — Phase 8 Full Capabilities', () => {
  const mockServer: MCPServerStatus = {
    server_id: 'time',
    server_name: 'Time Reference Server',
    transport_type: 'stdio',
    connection_state: 'connected',
    protocol_version: '2026-07-28',
    discovered_tool_count: 2,
    last_connected_at: '2026-10-27T08:00:00Z',
    last_discovered_at: '2026-10-27T08:00:00Z',
  }

  const mockTool1: DiscoveredTool = {
    tool_id: 'time__get_current_time',
    server_id: 'time',
    original_name: 'get_current_time',
    description: 'Get current time in timezone',
    input_schema: {
      type: 'object',
      properties: {
        timezone: { type: 'string', description: 'IANA timezone name' },
      },
      required: ['timezone'],
    },
    output_schema: {
      type: 'object',
      properties: {
        datetime: { type: 'string' },
      },
    },
    fingerprint: 'fp_get_time_123456789012345678901234',
    permission: 'allowed_read_only',
    enabled: true,
    discovered_at: '2026-10-27T08:00:00Z',
  }

  const mockTool2: DiscoveredTool = {
    tool_id: 'time__convert_time',
    server_id: 'time',
    original_name: 'convert_time',
    description: 'Convert time between timezones',
    input_schema: {
      type: 'object',
      properties: {
        source_timezone: { type: 'string' },
        target_timezone: { type: 'string' },
        time: { type: 'string' },
      },
      required: ['source_timezone', 'target_timezone', 'time'],
    },
    fingerprint: 'fp_convert_time_12345678901234567890',
    permission: 'approval_required',
    enabled: true,
    discovered_at: '2026-10-27T08:00:00Z',
  }

  const mockLedgerEntries: ExecutionLedgerEntry[] = [
    {
      dispatch_id: 'disp_101',
      approval_id: 'appr_101',
      tool_id: 'time__get_current_time',
      server_id: 'time',
      argument_digest: 'sha256:digest101',
      state: 'completed',
      dispatched_at: '2026-10-27T08:01:00Z',
      completed_at: '2026-10-27T08:01:00.150Z',
      duration_ms: 150.0,
      result_summary: '{"datetime": "2026-10-27T08:01:00Z"}',
    },
    {
      dispatch_id: 'disp_102',
      approval_id: 'appr_102',
      tool_id: 'time__convert_time',
      server_id: 'time',
      argument_digest: 'sha256:digest102',
      state: 'uncertain',
      dispatched_at: '2026-10-27T08:02:00Z',
      completed_at: '2026-10-27T08:02:05Z',
      duration_ms: 5000.0,
      error_message: 'Subprocess transport timed out during execution',
    },
    {
      dispatch_id: 'disp_103',
      approval_id: 'appr_103',
      tool_id: 'time__convert_time',
      server_id: 'time',
      argument_digest: 'sha256:digest103',
      state: 'failed',
      dispatched_at: '2026-10-27T08:03:00Z',
      completed_at: '2026-10-27T08:03:00.050Z',
      duration_ms: 50.0,
      error_message: 'Invalid timezone parameter',
    },
  ]

  const mockApprovalsSummary: ApprovalsSummaryResponse = {
    pending_count: 2,
    approved_count: 14,
    rejected_count: 3,
    expired_count: 1,
    cancelled_count: 4,
    total_count: 24,
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
      policy_version: 5,
      total: 2,
    })
    vi.spyOn(mcpService, 'getLedger').mockResolvedValue({
      entries: mockLedgerEntries,
      total: 3,
    })
    vi.spyOn(mcpService, 'getApprovalsSummary').mockResolvedValue(mockApprovalsSummary)
    vi.spyOn(mcpService, 'checkSession').mockResolvedValue({ authenticated: true })
    vi.spyOn(apiService, 'getSystemStatus').mockResolvedValue({
      app_name: 'Javed Control Center',
      backend_version: '0.1.0',
      api_version: 'v1',
      environment: 'development',
      server_time: '2026-10-27T08:00:00Z',
      uptime_seconds: 3600,
      active_ws_connections: 1,
      e2e_test_mode: false,
      capabilities: {
        rest_api: true,
        websocket: true,
        sse: true,
        ai_chat: true,
        tool_execution: true,
        browser_automation: false,
        document_extraction: false,
        persistent_memory: false,
        voice_multilingual: false,
      },
    })
  })

  it('renders all navigation tabs and navigates between views', async () => {
    const user = userEvent.setup()
    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-admin-panel')).toBeInTheDocument()
    })

    expect(screen.getByTestId('mcp-tab-overview')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-tab-tools')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-tab-ledger')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-tab-approvals')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-tab-diagnostics')).toBeInTheDocument()

    // Switch to Execution Ledger tab
    await user.click(screen.getByTestId('mcp-tab-ledger'))
    await waitFor(() => {
      expect(screen.getByTestId('mcp-ledger-viewer')).toBeInTheDocument()
    })
    expect(screen.getByTestId('mcp-ledger-entry-disp_101')).toBeInTheDocument()
    expect(screen.getByTestId('mcp-ledger-entry-disp_102')).toBeInTheDocument()

    // Switch to Approvals tab
    await user.click(screen.getByTestId('mcp-tab-approvals'))
    await waitFor(() => {
      expect(screen.getByTestId('mcp-approvals-summary-card')).toBeInTheDocument()
    })
    expect(screen.getByTestId('mcp-summary-pending-count')).toHaveTextContent('2')
    expect(screen.getByTestId('mcp-summary-approved-count')).toHaveTextContent('14')
    expect(screen.getByTestId('mcp-summary-total-count')).toHaveTextContent('24')

    // Switch to Diagnostics tab
    await user.click(screen.getByTestId('mcp-tab-diagnostics'))
    await waitFor(() => {
      expect(screen.getByTestId('mcp-diagnostics-section')).toBeInTheDocument()
    })
    expect(screen.getByText('Durable Approval Store')).toBeInTheDocument()
    expect(screen.getByText('Checkpoint Store')).toBeInTheDocument()
  })

  it('inspects JSON input and output schemas for discovered tools', async () => {
    const user = userEvent.setup()
    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-tool-time__get_current_time')).toBeInTheDocument()
    })

    const toggleBtn = screen.getByTestId('mcp-tool-schema-toggle-time__get_current_time')
    expect(toggleBtn).toBeInTheDocument()

    // Toggle schema inspection
    await user.click(toggleBtn)

    await waitFor(() => {
      expect(
        screen.getByTestId('mcp-tool-input-schema-time__get_current_time')
      ).toBeInTheDocument()
    })
    expect(
      screen.getByTestId('mcp-tool-input-schema-time__get_current_time')
    ).toHaveTextContent('IANA timezone name')
    expect(
      screen.getByTestId('mcp-tool-output-schema-time__get_current_time')
    ).toBeInTheDocument()
  })

  it('filters tools by search term and permission tier', async () => {
    const user = userEvent.setup()
    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-tool-time__get_current_time')).toBeInTheDocument()
      expect(screen.getByTestId('mcp-tool-time__convert_time')).toBeInTheDocument()
    })

    // Search for "convert"
    const searchInput = screen.getByTestId('mcp-tool-search-input')
    await user.type(searchInput, 'convert')

    expect(screen.queryByTestId('mcp-tool-time__get_current_time')).not.toBeInTheDocument()
    expect(screen.getByTestId('mcp-tool-time__convert_time')).toBeInTheDocument()

    // Clear search and filter by permission "allowed_read_only"
    await user.clear(searchInput)
    const permFilter = screen.getByTestId('mcp-tool-perm-filter')
    await user.selectOptions(permFilter, 'allowed_read_only')

    expect(screen.getByTestId('mcp-tool-time__get_current_time')).toBeInTheDocument()
    expect(screen.queryByTestId('mcp-tool-time__convert_time')).not.toBeInTheDocument()
  })

  it('renders execution ledger with distinct UNCERTAIN outcome notice and no retry button', async () => {
    const user = userEvent.setup()
    render(<MCPAdminPanel />)

    await user.click(screen.getByTestId('mcp-tab-ledger'))
    await waitFor(() => {
      expect(screen.getByTestId('mcp-ledger-viewer')).toBeInTheDocument()
    })

    // Verify completed entry
    expect(screen.getByTestId('mcp-ledger-entry-disp_101')).toHaveTextContent('COMPLETED')
    expect(screen.getByTestId('mcp-ledger-entry-disp_101')).toHaveTextContent('150 ms')

    // Verify uncertain entry and explicit banner
    const uncertainEntry = screen.getByTestId('mcp-ledger-entry-disp_102')
    expect(uncertainEntry).toBeInTheDocument()
    expect(uncertainEntry).toHaveTextContent('UNCERTAIN')
    expect(uncertainEntry).toHaveTextContent(/Uncertain Execution Outcome/i)
    expect(uncertainEntry).toHaveTextContent(/Per Section 8 safety rules, manual or automated retry is prohibited/i)

    // Verify NO manual retry button exists for the uncertain record (Section 8 constraint)
    expect(within(uncertainEntry).queryByRole('button', { name: /retry/i })).toBeNull()
  })

  it('displays E2E Test Mode badge truthfully when test mode is active', async () => {
    vi.spyOn(apiService, 'getSystemStatus').mockResolvedValue({
      app_name: 'Javed Control Center',
      backend_version: '0.1.0',
      api_version: 'v1',
      environment: 'test',
      server_time: '2026-10-27T08:00:00Z',
      uptime_seconds: 120,
      active_ws_connections: 1,
      e2e_test_mode: true,
      capabilities: {
        rest_api: true,
        websocket: true,
        sse: true,
        ai_chat: false,
        tool_execution: false,
        browser_automation: false,
        document_extraction: false,
        persistent_memory: false,
        voice_multilingual: false,
      },
    })

    render(<MCPAdminPanel />)

    await waitFor(() => {
      expect(screen.getByTestId('mcp-e2e-test-mode-badge')).toHaveTextContent(
        'E2E TEST MODE ACTIVE'
      )
    })
  })
})
