import React, { useEffect, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Lock,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import {
  type DiscoveredTool,
  type MCPServerStatus,
  mcpService,
  type ToolPermission,
} from '@/services/mcpService'
import { cn } from '@/lib/utils'

export const MCPAdminPanel: React.FC = () => {
  const [servers, setServers] = useState<MCPServerStatus[]>([])
  const [tools, setTools] = useState<DiscoveredTool[]>([])
  const [policyVersion, setPolicyVersion] = useState<number>(0)
  const [loading, setLoading] = useState<boolean>(true)
  const [refreshing, setRefreshing] = useState<boolean>(false)
  const [mutatingToolId, setMutatingToolId] = useState<string | null>(null)
  const [selectedPermissions, setSelectedPermissions] = useState<Record<string, ToolPermission>>({})
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null)
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false)
  const [ownerTokenInput, setOwnerTokenInput] = useState<string>('')
  const [isAuthenticating, setIsAuthenticating] = useState<boolean>(false)

  const loadData = async () => {
    try {
      const [serversRes, toolsRes] = await Promise.all([
        mcpService.getServers(),
        mcpService.getTools(),
      ])
      setServers(serversRes.servers || [])
      setTools(toolsRes.tools || [])
      setPolicyVersion(toolsRes.policy_version || 0)

      const initialPerms: Record<string, ToolPermission> = {}
      for (const t of toolsRes.tools || []) {
        initialPerms[t.tool_id] = t.permission
      }
      setSelectedPermissions(initialPerms)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load MCP administration data'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setLoading(false)
    }
  }

  const checkAuth = async () => {
    try {
      const res = await mcpService.checkSession()
      setIsAuthenticated(res.authenticated)
    } catch {
      setIsAuthenticated(false)
    }
  }

  useEffect(() => {
    loadData()
    checkAuth()
  }, [])

  const handleOwnerLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ownerTokenInput.trim()) return
    setIsAuthenticating(true)
    setFeedback(null)
    try {
      await mcpService.loginOwner(ownerTokenInput.trim())
      setIsAuthenticated(true)
      setOwnerTokenInput('')
      setFeedback({
        type: 'success',
        message: 'Local owner session authenticated successfully.',
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Authentication failed'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setIsAuthenticating(false)
    }
  }

  const handleOwnerLogout = async () => {
    await mcpService.logoutOwner()
    setIsAuthenticated(false)
    setFeedback({
      type: 'success',
      message: 'Owner session terminated. Console locked.',
    })
  }

  const handleRefreshDiscovery = async (serverId: string) => {
    setRefreshing(true)
    setFeedback(null)
    try {
      const res = await mcpService.refreshServer(serverId)
      await loadData()
      setFeedback({
        type: 'success',
        message: `Discovered ${res.tool_count} tool(s) successfully for '${serverId}'.`,
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Refresh discovery failed'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setRefreshing(false)
    }
  }

  const handlePermissionChange = (toolId: string, perm: ToolPermission) => {
    setSelectedPermissions((prev) => ({ ...prev, [toolId]: perm }))
  }

  const handleApplyPermission = async (tool: DiscoveredTool) => {
    const targetPerm = selectedPermissions[tool.tool_id] || tool.permission
    setMutatingToolId(tool.tool_id)
    setFeedback(null)
    try {
      const res = await mcpService.updateToolPermission(
        tool.tool_id,
        targetPerm,
        targetPerm !== 'denied',
        policyVersion,
        tool.fingerprint
      )
      setPolicyVersion(res.policy_version)
      setTools((prev) => prev.map((t) => (t.tool_id === tool.tool_id ? res.tool : t)))
      setSelectedPermissions((prev) => ({ ...prev, [tool.tool_id]: res.tool.permission }))
      setFeedback({
        type: 'success',
        message: `Updated '${tool.tool_id}' to ${res.tool.permission.toUpperCase()} (Host Policy Version: ${res.policy_version}).`,
      })
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Permission update failed'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setMutatingToolId(null)
    }
  }

  const getPermissionBadge = (permission: ToolPermission) => {
    switch (permission) {
      case 'allowed_read_only':
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/30 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> ALLOWED_READ_ONLY
          </span>
        )
      case 'approval_required':
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 flex items-center gap-1">
            <ShieldCheck className="w-3 h-3" /> APPROVAL_REQUIRED
          </span>
        )
      case 'denied':
      default:
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-rose-500/10 text-rose-500 border border-rose-500/30 flex items-center gap-1">
            <Lock className="w-3 h-3" /> DENIED
          </span>
        )
    }
  }

  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4" data-testid="mcp-admin-panel">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <Server className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              MCP Extensible Subsystem & Host Policy Management
            </span>
            <span
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold"
              data-testid="mcp-policy-version"
            >
              Policy v{policyVersion}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Host-side gating, dynamic discovery inspection, and Human-in-the-Loop permission controls (BRICK-005 Phase 6).
          </p>
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          className="px-2.5 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1.5 self-start sm:self-auto disabled:opacity-50"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          <span>Reload</span>
        </button>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          data-testid="mcp-admin-feedback"
          className={cn(
            'p-3 rounded-lg text-xs flex items-center gap-2 border',
            feedback.type === 'success'
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'
          )}
        >
          {feedback.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Owner Authentication Card */}
      {!isAuthenticated ? (
        <div
          data-testid="mcp-owner-auth-card"
          className="p-3.5 rounded-lg border border-amber-500/30 bg-amber-500/5 space-y-2"
        >
          <div className="flex items-center gap-2 text-amber-500 text-xs font-semibold">
            <Lock className="w-4 h-4" />
            <span>Owner Authentication Required for Policy Mutations</span>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Enter your local owner token (configured via JAVED_OWNER_TOKEN) to unlock MCP administration and policy mutations.
          </p>
          <form onSubmit={handleOwnerLogin} className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 pt-1">
            <input
              type="password"
              data-testid="mcp-owner-token-input"
              value={ownerTokenInput}
              onChange={(e) => setOwnerTokenInput(e.target.value)}
              placeholder="Enter JAVED_OWNER_TOKEN"
              className="px-3 py-1.5 text-xs bg-background border border-border rounded flex-1 focus:outline-none focus:ring-1 focus:ring-primary font-mono"
            />
            <button
              type="submit"
              data-testid="mcp-owner-token-submit-btn"
              disabled={isAuthenticating || !ownerTokenInput.trim()}
              className="px-3 py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {isAuthenticating ? 'Verifying...' : 'Unlock Console'}
            </button>
          </form>
        </div>
      ) : (
        <div
          data-testid="mcp-owner-auth-card"
          className="p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/5 flex items-center justify-between gap-2"
        >
          <div className="flex items-center gap-2 text-emerald-500 text-xs font-semibold">
            <ShieldCheck className="w-4 h-4" />
            <span>Owner Session Active (Local Authenticated)</span>
          </div>
          <button
            onClick={handleOwnerLogout}
            data-testid="mcp-owner-logout-btn"
            className="px-2 py-1 text-[11px] rounded border border-border hover:bg-secondary text-muted-foreground transition-colors"
          >
            Lock Console
          </button>
        </div>
      )}

      {/* Approved Servers Status */}
      <div className="space-y-2">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Approved MCP Servers
        </div>

        {servers.length === 0 ? (
          <div className="text-xs text-muted-foreground italic py-2">No approved MCP servers configured.</div>
        ) : (
          servers.map((srv) => (
            <div
              key={srv.server_id}
              data-testid={`mcp-server-${srv.server_id}`}
              className="p-3 rounded-lg bg-secondary/30 border border-border/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-foreground">{srv.server_name}</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-secondary text-muted-foreground border border-border">
                    id: {srv.server_id}
                  </span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    transport: {srv.transport_type}
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-3">
                  <span>Tools: {srv.discovered_tool_count}</span>
                  <span>Protocol: {srv.protocol_version || '2026-07-28'}</span>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <div className="flex items-center gap-1.5 mr-2">
                  <span
                    className={cn(
                      'w-2 h-2 rounded-full',
                      srv.connection_state === 'connected' ? 'bg-emerald-500' : 'bg-muted-foreground'
                    )}
                  />
                  <span className="text-xs font-mono font-bold uppercase text-foreground">
                    {srv.connection_state}
                  </span>
                </div>

                <button
                  data-testid={`mcp-refresh-${srv.server_id}`}
                  onClick={() => handleRefreshDiscovery(srv.server_id)}
                  disabled={refreshing || !isAuthenticated}
                  title={!isAuthenticated ? 'Unlock console to refresh server' : undefined}
                  className="px-2.5 py-1 text-xs rounded border border-border hover:bg-secondary text-foreground flex items-center gap-1.5 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
                  <span>Refresh Tools</span>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Discovered Tools & Permission Management */}
      <div className="space-y-2 pt-2">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Discovered Tools & Effective Host Permissions
        </div>

        {tools.length === 0 ? (
          <div className="text-xs text-muted-foreground italic py-3 text-center border border-dashed border-border rounded-lg">
            No tools discovered. Click "Refresh Tools" to query the server.
          </div>
        ) : (
          <div className="space-y-2.5">
            {tools.map((t) => {
              const currentChoice = selectedPermissions[t.tool_id] || t.permission
              const isMutating = mutatingToolId === t.tool_id
              const isChanged = currentChoice !== t.permission

              return (
                <div
                  key={t.tool_id}
                  data-testid={`mcp-tool-${t.tool_id}`}
                  className="p-3.5 rounded-lg border border-border/80 bg-background hover:bg-secondary/10 transition-colors space-y-2.5"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Clock className="w-4 h-4 text-primary shrink-0" />
                        <span className="text-xs font-mono font-bold text-foreground">{t.tool_id}</span>
                        {getPermissionBadge(t.permission)}
                      </div>
                      <p className="text-xs text-muted-foreground">{t.description}</p>
                      <div className="text-[10px] font-mono text-muted-foreground">
                        Fingerprint: <code>{t.fingerprint.slice(0, 16)}...</code>
                      </div>
                    </div>
                  </div>

                  {/* Owner Action Controls */}
                  <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/40">
                    <label className="text-[11px] font-medium text-muted-foreground">Permission:</label>
                    <select
                      data-testid={`mcp-perm-select-${t.tool_id}`}
                      value={currentChoice}
                      onChange={(e) => handlePermissionChange(t.tool_id, e.target.value as ToolPermission)}
                      disabled={isMutating || !isAuthenticated}
                      className="px-2 py-1 text-xs rounded border border-border bg-card text-foreground focus:ring-1 focus:ring-primary disabled:opacity-50"
                    >
                      <option value="denied">DENIED (Blocked)</option>
                      <option value="allowed_read_only">ALLOWED_READ_ONLY (Immediate)</option>
                      <option value="approval_required">APPROVAL_REQUIRED (HITL Prompt)</option>
                    </select>

                    <button
                      data-testid={`mcp-perm-update-btn-${t.tool_id}`}
                      onClick={() => handleApplyPermission(t)}
                      disabled={isMutating || !isAuthenticated || (!isChanged && t.permission === currentChoice)}
                      className={cn(
                        'px-3 py-1 text-xs rounded font-medium flex items-center gap-1.5 transition-colors',
                        isChanged && isAuthenticated
                          ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                          : 'bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50'
                      )}
                    >
                      <Zap className={cn('w-3.5 h-3.5', isMutating && 'animate-spin')} />
                      <span>{isMutating ? 'Applying...' : 'Apply Permission'}</span>
                    </button>

                    {!isAuthenticated && (
                      <span className="text-[10px] text-amber-500 italic ml-2">
                        Unlock console to mutate permission
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
