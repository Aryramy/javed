/**
 * REST client for Secure MCP Administration APIs (BRICK-005 Phase 6).
 */

export interface MCPServerStatus {
  server_id: string
  server_name: string
  transport_type: string
  connection_state: 'disconnected' | 'connecting' | 'connected' | 'error'
  protocol_version?: string | null
  discovered_tool_count: number
  last_connected_at?: string | null
  last_discovered_at?: string | null
  last_error?: string | null
}

export type ToolPermission = 'denied' | 'allowed_read_only' | 'approval_required'

export interface DiscoveredTool {
  tool_id: string
  server_id: string
  original_name: string
  description: string
  input_schema: Record<string, unknown>
  output_schema?: Record<string, unknown> | null
  fingerprint: string
  permission: ToolPermission
  enabled: boolean
  discovered_at: string
  last_verified_at?: string | null
  last_executed_at?: string | null
  last_error?: string | null
}

export interface ServerListResponse {
  servers: MCPServerStatus[]
  total: number
}

export interface ToolListResponse {
  tools: DiscoveredTool[]
  server_count: number
  policy_version: number
  total: number
}

export interface ToolDetailResponse {
  tool: DiscoveredTool
  policy_version: number
  policy?: {
    tool_id: string
    permission: ToolPermission
    approved_fingerprint: string
    approved_at: string
    approved_by: string
  } | null
}

let activeSessionToken: string | null = null

export const mcpService = {
  /**
   * Set or clear the in-memory active session token.
   */
  setSessionToken(token: string | null): void {
    activeSessionToken = token
  },

  /**
   * Retrieve current in-memory session token.
   */
  getSessionToken(): string | null {
    return activeSessionToken
  },

  /**
   * Check whether current caller has an active authenticated session.
   */
  async checkSession(): Promise<{ authenticated: boolean; expires_in?: number | null }> {
    const headers: Record<string, string> = {}
    if (activeSessionToken) {
      headers['X-Javed-Owner-Token'] = activeSessionToken
    }
    const res = await fetch('/api/v1/mcp/auth/session', { headers })
    if (!res.ok) {
      return { authenticated: false }
    }
    return res.json()
  },

  /**
   * Authenticate with master owner token to obtain a short-lived session token.
   */
  async loginOwner(ownerToken: string): Promise<{ session_token: string; expires_in: number }> {
    const res = await fetch('/api/v1/mcp/auth/session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ owner_token: ownerToken }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || 'Owner authentication failed')
    }
    const data = await res.json()
    activeSessionToken = data.session_token
    return data
  },

  /**
   * Terminate active owner session.
   */
  async logoutOwner(): Promise<void> {
    if (activeSessionToken) {
      await fetch('/api/v1/mcp/auth/logout', {
        method: 'POST',
        headers: {
          'X-Javed-Owner-Token': activeSessionToken,
        },
      }).catch(() => {})
      activeSessionToken = null
    }
  },

  /**
   * Fetch approved MCP servers and status.
   */
  async getServers(): Promise<ServerListResponse> {
    const res = await fetch('/api/v1/mcp/servers')
    if (!res.ok) {
      throw new Error(`Failed to load MCP servers (HTTP ${res.status})`)
    }
    return res.json()
  },

  /**
   * Fetch dynamic MCP tool catalog and effective permissions.
   */
  async getTools(): Promise<ToolListResponse> {
    const res = await fetch('/api/v1/mcp/tools')
    if (!res.ok) {
      throw new Error(`Failed to load MCP tools (HTTP ${res.status})`)
    }
    return res.json()
  },

  /**
   * Fetch details, schema, and policy for a single MCP tool.
   */
  async getTool(toolId: string): Promise<ToolDetailResponse> {
    const res = await fetch(`/api/v1/mcp/tools/${encodeURIComponent(toolId)}`)
    if (!res.ok) {
      throw new Error(`Failed to load tool '${toolId}' (HTTP ${res.status})`)
    }
    return res.json()
  },

  /**
   * Refresh tool discovery on an approved MCP server.
   */
  async refreshServer(serverId: string): Promise<{ tool_count: number; message: string }> {
    if (!activeSessionToken) {
      throw new Error('Owner authentication required. Please unlock with your owner token.')
    }
    const res = await fetch(`/api/v1/mcp/servers/${encodeURIComponent(serverId)}/refresh`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Javed-Owner-Token': activeSessionToken,
      },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Failed to refresh server '${serverId}'`)
    }
    return res.json()
  },

  /**
   * Privileged mutation of tool execution permissions with optimistic concurrency.
   */
  async updateToolPermission(
    toolId: string,
    permission: ToolPermission,
    enabled: boolean,
    expectedPolicyVersion: number,
    expectedFingerprint: string
  ): Promise<ToolDetailResponse> {
    if (!activeSessionToken) {
      throw new Error('Owner authentication required. Please unlock with your owner token.')
    }
    const res = await fetch(`/api/v1/mcp/tools/${encodeURIComponent(toolId)}/permission`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Javed-Owner-Token': activeSessionToken,
      },
      body: JSON.stringify({
        permission,
        enabled,
        expected_policy_version: expectedPolicyVersion,
        expected_fingerprint: expectedFingerprint,
      }),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Failed to update permission for '${toolId}' (HTTP ${res.status})`)
    }
    return res.json()
  },
}
