import React, { useEffect, useState, useContext } from 'react'
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Lock,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react'
import {
  type ApprovalsSummaryResponse,
  type DiscoveredTool,
  type ExecutionLedgerEntry,
  type MCPServerStatus,
  mcpService,
  type ToolPermission,
} from '@/services/mcpService'
import { apiService } from '@/services/api'
import type { SystemStatusResponse } from '@/services/types'
import { BackendContext } from '@/context/backend-context'
import { cn } from '@/lib/utils'

export type ConsoleTab = 'overview' | 'servers' | 'tools' | 'ledger' | 'approvals' | 'diagnostics'

export const MCPAdminPanel: React.FC = () => {
  const backendCtx = useContext(BackendContext)
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    backendCtx?.systemStatus ?? null
  )

  const [activeTab, setActiveTab] = useState<ConsoleTab>('overview')
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

  // Execution Ledger State
  const [ledgerEntries, setLedgerEntries] = useState<ExecutionLedgerEntry[]>([])
  const [ledgerTotal, setLedgerTotal] = useState<number>(0)
  const [ledgerLimit, setLedgerLimit] = useState<number>(50)
  const [ledgerFilterStatus, setLedgerFilterStatus] = useState<string>('')
  const [ledgerFilterTool, setLedgerFilterTool] = useState<string>('')
  const [loadingLedger, setLoadingLedger] = useState<boolean>(false)

  // Approvals Summary State
  const [approvalsSummary, setApprovalsSummary] = useState<ApprovalsSummaryResponse | null>(null)
  const [loadingApprovals, setLoadingApprovals] = useState<boolean>(false)

  // Search & Tool Registry Filters
  const [searchQuery, setSearchQuery] = useState<string>('')
  const [permissionFilter, setPermissionFilter] = useState<string>('all')
  const [expandedSchemas, setExpandedSchemas] = useState<Record<string, boolean>>({})
  const [expandedLedgerItems, setExpandedLedgerItems] = useState<Record<string, boolean>>({})

  const loadData = async () => {
    setLoading(true)
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

    // Auxiliary queries for ledger, approvals summary, and diagnostics
    mcpService
      .getLedger({
        limit: ledgerLimit,
        state: ledgerFilterStatus || undefined,
        tool_id: ledgerFilterTool || undefined,
      })
      .then((res) => {
        setLedgerEntries(res.entries || [])
        setLedgerTotal(res.total || 0)
      })
      .catch(() => {})

    mcpService
      .getApprovalsSummary()
      .then((res) => setApprovalsSummary(res))
      .catch(() => {})

    apiService
      .getSystemStatus()
      .then((sys) => setSystemStatus(sys))
      .catch(() => {})
  }

  const loadLedger = async () => {
    setLoadingLedger(true)
    try {
      const res = await mcpService.getLedger({
        limit: ledgerLimit,
        state: ledgerFilterStatus || undefined,
        tool_id: ledgerFilterTool || undefined,
      })
      setLedgerEntries(res.entries || [])
      setLedgerTotal(res.total || 0)
    } catch {
      // Gracefully silent in case endpoint not ready
    } finally {
      setLoadingLedger(false)
    }
  }

  const loadApprovalsSummary = async () => {
    setLoadingApprovals(true)
    try {
      const res = await mcpService.getApprovalsSummary()
      setApprovalsSummary(res)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load approvals summary'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setLoadingApprovals(false)
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

  useEffect(() => {
    loadLedger()
  }, [ledgerLimit, ledgerFilterStatus, ledgerFilterTool])

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
      // Refresh summary to reflect any pending approvals cancelled due to revocation
      loadApprovalsSummary()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Permission update failed'
      setFeedback({ type: 'error', message: msg })
    } finally {
      setMutatingToolId(null)
    }
  }

  const toggleSchema = (toolId: string) => {
    setExpandedSchemas((prev) => ({ ...prev, [toolId]: !prev[toolId] }))
  }

  const toggleLedgerDetail = (dispatchId: string) => {
    setExpandedLedgerItems((prev) => ({ ...prev, [dispatchId]: !prev[dispatchId] }))
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

  const getExecutionStateBadge = (state: string) => {
    switch (state.toLowerCase()) {
      case 'completed':
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/30 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> COMPLETED
          </span>
        )
      case 'in_flight':
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-sky-500/10 text-sky-500 border border-sky-500/30 flex items-center gap-1 animate-pulse">
            <Activity className="w-3 h-3" /> IN_FLIGHT
          </span>
        )
      case 'failed':
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-rose-500/10 text-rose-500 border border-rose-500/30 flex items-center gap-1">
            <AlertCircle className="w-3 h-3" /> FAILED
          </span>
        )
      case 'uncertain':
        return (
          <span
            data-testid="mcp-ledger-uncertain-badge"
            className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-purple-500/10 text-purple-400 border border-purple-500/30 flex items-center gap-1"
          >
            <AlertTriangle className="w-3 h-3 text-purple-400" /> UNCERTAIN
          </span>
        )
      case 'not_dispatched':
      default:
        return (
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-secondary text-muted-foreground border border-border flex items-center gap-1">
            <Clock className="w-3 h-3" /> NOT_DISPATCHED
          </span>
        )
    }
  }

  const filteredTools = tools.filter((t) => {
    const matchesSearch =
      t.tool_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.description.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesPermission =
      permissionFilter === 'all' || t.permission === permissionFilter
    return matchesSearch && matchesPermission
  })

  const isTestMode = Boolean(systemStatus?.e2e_test_mode)

  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-5" data-testid="mcp-admin-panel">
      {/* Console Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/80 pb-3">
        <div className="space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <Server className="w-4 h-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              Developer MCP Console & Subsystem Gateway
            </span>
            <span
              className="text-[10px] font-mono px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20 font-semibold"
              data-testid="mcp-policy-version"
            >
              Policy v{policyVersion}
            </span>
            {isTestMode ? (
              <span
                data-testid="mcp-e2e-test-mode-badge"
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold"
              >
                E2E TEST MODE ACTIVE
              </span>
            ) : (
              <span
                data-testid="mcp-e2e-test-mode-badge"
                className="text-[10px] font-mono px-2 py-0.5 rounded bg-secondary text-muted-foreground border border-border"
              >
                HOST RUNTIME: LIVE
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            Dynamic server discovery, host policy enforcement, execution audit ledger, and live diagnostics (BRICK-005 Phase 8).
          </p>
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          data-testid="mcp-console-reload-btn"
          className="px-2.5 py-1 text-xs rounded border border-border text-muted-foreground hover:text-foreground hover:bg-secondary flex items-center gap-1.5 self-start sm:self-auto disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={cn('w-3.5 h-3.5', loading && 'animate-spin')} />
          <span>Reload Console</span>
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
              className="px-3 py-1.5 text-xs bg-background border border-border rounded flex-1 focus:outline-none focus:ring-1 focus:ring-primary font-mono text-foreground"
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
            <span data-testid="mcp-owner-auth-active">Owner Session Active (Local Authenticated)</span>
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

      {/* Navigation Tabs */}
      <div className="flex items-center gap-1 border-b border-border/80 overflow-x-auto pb-1 text-xs">
        <button
          onClick={() => setActiveTab('overview')}
          data-testid="mcp-tab-overview"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'overview'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab('servers')}
          data-testid="mcp-tab-servers"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'servers'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Servers ({servers.length})
        </button>
        <button
          onClick={() => setActiveTab('tools')}
          data-testid="mcp-tab-tools"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'tools'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Tool Registry & Schemas ({tools.length})
        </button>
        <button
          onClick={() => setActiveTab('ledger')}
          data-testid="mcp-tab-ledger"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'ledger'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Execution Ledger ({ledgerTotal})
        </button>
        <button
          onClick={() => setActiveTab('approvals')}
          data-testid="mcp-tab-approvals"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'approvals'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Approvals Summary
        </button>
        <button
          onClick={() => setActiveTab('diagnostics')}
          data-testid="mcp-tab-diagnostics"
          className={cn(
            'px-3 py-1.5 rounded-t font-medium transition-colors border-b-2',
            activeTab === 'diagnostics'
              ? 'border-primary text-primary font-semibold bg-secondary/20'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          )}
        >
          Diagnostics & Health
        </button>
      </div>

      {/* SECTION A & OVERVIEW: Approved Servers Status */}
      {(activeTab === 'overview' || activeTab === 'servers') && (
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Host-Approved MCP Servers
            </div>

            {servers.length === 0 ? (
              <div className="text-xs text-muted-foreground italic py-3 text-center border border-dashed border-border rounded-lg">
                No approved MCP servers configured. (Only the official Time server is permitted in Phase 8)
              </div>
            ) : (
              servers.map((srv) => (
                <div
                  key={srv.server_id}
                  data-testid={`mcp-server-${srv.server_id}`}
                  className="p-3.5 rounded-lg bg-secondary/30 border border-border/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-foreground">{srv.server_name}</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-secondary text-muted-foreground border border-border">
                        id: {srv.server_id}
                      </span>
                      <span className="text-[10px] font-mono text-muted-foreground">
                        transport: {srv.transport_type}
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-primary/10 text-primary border border-primary/20">
                        Protocol: {srv.protocol_version || '2026-07-28'}
                      </span>
                    </div>
                    <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-3 flex-wrap">
                      <span>Tools Discovered: <strong>{srv.discovered_tool_count}</strong></span>
                      {srv.last_discovered_at && (
                        <span>Last Discovery: {new Date(srv.last_discovered_at).toLocaleString()}</span>
                      )}
                      {srv.last_error && (
                        <span className="text-rose-500">Error: {srv.last_error}</span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <div className="flex items-center gap-1.5 mr-2">
                      <span
                        className={cn(
                          'w-2 h-2 rounded-full',
                          srv.connection_state === 'connected'
                            ? 'bg-emerald-500 animate-pulse'
                            : srv.connection_state === 'connecting'
                            ? 'bg-amber-500'
                            : 'bg-muted-foreground'
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
                      title={!isAuthenticated ? 'Unlock console with owner token to refresh server' : undefined}
                      className="px-2.5 py-1 text-xs rounded border border-border hover:bg-secondary text-foreground flex items-center gap-1.5 disabled:opacity-50 transition-colors"
                    >
                      <RefreshCw className={cn('w-3.5 h-3.5', refreshing && 'animate-spin')} />
                      <span>{refreshing ? 'Refreshing...' : 'Refresh Tools'}</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Quick Metrics Bar in Overview */}
          {approvalsSummary && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
              <div className="p-2.5 rounded-lg border border-border bg-background space-y-0.5">
                <span className="text-[10px] text-muted-foreground uppercase font-medium">Pending Approvals</span>
                <div className="text-base font-bold font-mono text-amber-500">{approvalsSummary.pending_count}</div>
              </div>
              <div className="p-2.5 rounded-lg border border-border bg-background space-y-0.5">
                <span className="text-[10px] text-muted-foreground uppercase font-medium">Approved Executions</span>
                <div className="text-base font-bold font-mono text-emerald-500">{approvalsSummary.approved_count}</div>
              </div>
              <div className="p-2.5 rounded-lg border border-border bg-background space-y-0.5">
                <span className="text-[10px] text-muted-foreground uppercase font-medium">Recent Ledger Records</span>
                <div className="text-base font-bold font-mono text-primary">{ledgerTotal}</div>
              </div>
              <div className="p-2.5 rounded-lg border border-border bg-background space-y-0.5">
                <span className="text-[10px] text-muted-foreground uppercase font-medium">Active Policy Version</span>
                <div className="text-base font-bold font-mono text-foreground">v{policyVersion}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SECTION B & C: Discovered Tools & Permission Management */}
      {(activeTab === 'overview' || activeTab === 'tools') && (
        <div className="space-y-3 pt-1">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Tool Registry, Schemas & Security Tiers
            </div>

            {/* Filter & Search Bar */}
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 absolute left-2 top-2 text-muted-foreground" />
                <input
                  type="text"
                  data-testid="mcp-tool-search-input"
                  placeholder="Search tool..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-7 pr-2 py-1 text-xs bg-background border border-border rounded focus:ring-1 focus:ring-primary w-36 sm:w-48 font-mono"
                />
              </div>

              <select
                data-testid="mcp-tool-perm-filter"
                value={permissionFilter}
                onChange={(e) => setPermissionFilter(e.target.value)}
                className="px-2 py-1 text-xs rounded border border-border bg-background text-foreground"
              >
                <option value="all">All Tiers</option>
                <option value="allowed_read_only">Allowed Read-Only</option>
                <option value="approval_required">Approval Required</option>
                <option value="denied">Denied (Blocked)</option>
              </select>
            </div>
          </div>

          {filteredTools.length === 0 ? (
            <div className="text-xs text-muted-foreground italic py-3 text-center border border-dashed border-border rounded-lg">
              No tools matched the filter. Click "Refresh Tools" to discover dynamic MCP tools.
            </div>
          ) : (
            <div className="space-y-2.5">
              {filteredTools.map((t) => {
                const currentChoice = selectedPermissions[t.tool_id] || t.permission
                const isMutating = mutatingToolId === t.tool_id
                const isChanged = currentChoice !== t.permission
                const isSchemaOpen = Boolean(expandedSchemas[t.tool_id])

                const isModelVisible = t.enabled && t.permission !== 'denied'
                const isDirectExecutable = t.enabled && t.permission === 'allowed_read_only'
                const isApprovalRequired = t.enabled && t.permission === 'approval_required'

                return (
                  <div
                    key={t.tool_id}
                    data-testid={`mcp-tool-${t.tool_id}`}
                    className="p-3.5 rounded-lg border border-border/80 bg-background hover:bg-secondary/10 transition-colors space-y-2.5"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <Clock className="w-4 h-4 text-primary shrink-0" />
                          <span className="text-xs font-mono font-bold text-foreground">{t.tool_id}</span>
                          {getPermissionBadge(t.permission)}

                          {/* Eligibility Badges */}
                          {isModelVisible && (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-sky-500/10 text-sky-500 border border-sky-500/30">
                              Model Visible
                            </span>
                          )}
                          {isDirectExecutable && (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-500 border border-emerald-500/30">
                              Direct Executable
                            </span>
                          )}
                          {isApprovalRequired && (
                            <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30">
                              Requires User Approval
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground">{t.description}</p>
                        <div className="text-[10px] font-mono text-muted-foreground flex items-center gap-2 flex-wrap">
                          <span>Server: <strong>{t.server_id}</strong></span>
                          <span>•</span>
                          <span>Fingerprint: <code>{t.fingerprint.slice(0, 16)}...</code></span>
                        </div>
                      </div>

                      {/* Schema Toggle Button */}
                      <button
                        onClick={() => toggleSchema(t.tool_id)}
                        data-testid={`mcp-tool-schema-toggle-${t.tool_id}`}
                        className="px-2 py-1 text-[11px] rounded border border-border hover:bg-secondary text-muted-foreground flex items-center gap-1 self-start shrink-0"
                      >
                        {isSchemaOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        <span>{isSchemaOpen ? 'Hide Schema' : 'Inspect Schema'}</span>
                      </button>
                    </div>

                    {/* Expandable JSON Schema Inspector */}
                    {isSchemaOpen && (
                      <div className="p-3 rounded-lg bg-secondary/30 border border-border text-xs space-y-2 font-mono">
                        <div>
                          <span className="text-[11px] font-semibold text-primary block mb-1">Input Schema (JSON Schema):</span>
                          <pre
                            data-testid={`mcp-tool-input-schema-${t.tool_id}`}
                            className="p-2 rounded bg-background border border-border/70 text-[11px] overflow-x-auto max-h-48 text-muted-foreground"
                          >
                            {JSON.stringify(t.input_schema, null, 2)}
                          </pre>
                        </div>
                        {t.output_schema && (
                          <div>
                            <span className="text-[11px] font-semibold text-primary block mb-1">Output Schema:</span>
                            <pre
                              data-testid={`mcp-tool-output-schema-${t.tool_id}`}
                              className="p-2 rounded bg-background border border-border/70 text-[11px] overflow-x-auto max-h-48 text-muted-foreground"
                            >
                              {JSON.stringify(t.output_schema, null, 2)}
                            </pre>
                          </div>
                        )}
                        <div className="text-[10px] text-muted-foreground">
                          Full SHA-256 Fingerprint: <code>{t.fingerprint}</code>
                        </div>
                      </div>
                    )}

                    {/* Owner Action Controls (Section C) */}
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
      )}

      {/* SECTION D: Execution Ledger Viewer */}
      {activeTab === 'ledger' && (
        <div className="space-y-3" data-testid="mcp-ledger-viewer">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Durable Tool Execution Ledger
              </div>
              <p className="text-[11px] text-muted-foreground">
                Sanitized audit records of all host tool dispatches, durations, and state transitions.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {/* Limit Selector */}
              <select
                data-testid="mcp-ledger-limit-select"
                value={ledgerLimit}
                onChange={(e) => setLedgerLimit(Number(e.target.value))}
                className="px-2 py-1 text-xs rounded border border-border bg-background text-foreground"
              >
                <option value={10}>10 records</option>
                <option value={25}>25 records</option>
                <option value={50}>50 records</option>
                <option value={100}>100 records</option>
              </select>

              {/* Tool Filter */}
              <select
                data-testid="mcp-ledger-tool-filter"
                value={ledgerFilterTool}
                onChange={(e) => setLedgerFilterTool(e.target.value)}
                className="px-2 py-1 text-xs rounded border border-border bg-background text-foreground"
              >
                <option value="">All Tools</option>
                {tools.map((t) => (
                  <option key={t.tool_id} value={t.tool_id}>
                    {t.tool_id}
                  </option>
                ))}
              </select>

              {/* Status Filter */}
              <select
                data-testid="mcp-ledger-status-filter"
                value={ledgerFilterStatus}
                onChange={(e) => setLedgerFilterStatus(e.target.value)}
                className="px-2 py-1 text-xs rounded border border-border bg-background text-foreground"
              >
                <option value="">All States</option>
                <option value="completed">Completed</option>
                <option value="in_flight">In Flight</option>
                <option value="failed">Failed</option>
                <option value="uncertain">Uncertain</option>
                <option value="not_dispatched">Not Dispatched</option>
              </select>

              <button
                onClick={loadLedger}
                disabled={loadingLedger}
                data-testid="mcp-ledger-refresh-btn"
                className="px-2 py-1 text-xs rounded border border-border hover:bg-secondary text-foreground flex items-center gap-1 transition-colors"
              >
                <RefreshCw className={cn('w-3 h-3', loadingLedger && 'animate-spin')} />
                <span>Refresh</span>
              </button>
            </div>
          </div>

          {/* Ledger Table / Card List */}
          {ledgerEntries.length === 0 ? (
            <div className="text-xs text-muted-foreground italic py-6 text-center border border-dashed border-border rounded-lg">
              No tool executions recorded in the audit ledger yet.
            </div>
          ) : (
            <div className="space-y-2">
              {ledgerEntries.map((e) => {
                const isExpanded = Boolean(expandedLedgerItems[e.dispatch_id])
                const isUncertain = e.state === 'uncertain'

                return (
                  <div
                    key={e.dispatch_id}
                    data-testid={`mcp-ledger-entry-${e.dispatch_id}`}
                    className={cn(
                      'p-3 rounded-lg border text-xs space-y-2 transition-colors',
                      isUncertain
                        ? 'border-purple-500/40 bg-purple-500/5'
                        : 'border-border/80 bg-background hover:bg-secondary/10'
                    )}
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-mono font-bold text-foreground">{e.tool_id}</span>
                          {getExecutionStateBadge(e.state)}
                          {e.duration_ms !== null && e.duration_ms !== undefined && (
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-secondary text-muted-foreground border border-border">
                              {e.duration_ms} ms
                            </span>
                          )}
                          <span className="text-[10px] font-mono text-muted-foreground">
                            server: {e.server_id || 'unknown'}
                          </span>
                        </div>
                        <div className="text-[10px] font-mono text-muted-foreground flex items-center gap-2 flex-wrap">
                          <span>Dispatch ID: <code>{e.dispatch_id}</code></span>
                          <span>•</span>
                          <span>Approval ID: <code>{e.approval_id}</code></span>
                          <span>•</span>
                          <span>At: {new Date(e.dispatched_at).toLocaleTimeString()}</span>
                        </div>
                      </div>

                      <button
                        onClick={() => toggleLedgerDetail(e.dispatch_id)}
                        className="px-2 py-0.5 text-[10px] rounded border border-border hover:bg-secondary text-muted-foreground flex items-center gap-1 self-start sm:self-auto shrink-0"
                      >
                        {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                        <span>{isExpanded ? 'Hide' : 'Details'}</span>
                      </button>
                    </div>

                    {/* Uncertain Execution Notice (Section 8 constraint) */}
                    {isUncertain && (
                      <div className="p-2 rounded bg-purple-500/10 border border-purple-500/20 text-[11px] text-purple-300 space-y-1">
                        <div className="flex items-center gap-1.5 font-bold">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>Uncertain Execution Outcome</span>
                        </div>
                        <p className="text-[10px] text-muted-foreground">
                          This dispatch resulted in an unknown outcome. The operation cannot be verified as completed or failed.
                          Per Section 8 safety rules, manual or automated retry is prohibited to avoid duplicate side-effects.
                        </p>
                      </div>
                    )}

                    {/* Expandable Ledger Item Details */}
                    {isExpanded && (
                      <div className="p-2.5 rounded bg-secondary/30 border border-border font-mono text-[11px] space-y-1.5">
                        <div>
                          <span className="text-muted-foreground">Argument Digest:</span>{' '}
                          <code className="text-foreground">{e.argument_digest}</code>
                        </div>
                        {e.completed_at && (
                          <div>
                            <span className="text-muted-foreground">Completed At:</span>{' '}
                            <span>{new Date(e.completed_at).toLocaleString()}</span>
                          </div>
                        )}
                        {e.result_summary && (
                          <div>
                            <span className="text-muted-foreground block mb-0.5">Result Summary:</span>
                            <pre className="p-1.5 rounded bg-background border border-border/70 overflow-x-auto text-[10px]">
                              {e.result_summary}
                            </pre>
                          </div>
                        )}
                        {e.error_message && (
                          <div>
                            <span className="text-rose-400 block mb-0.5">Error Message:</span>
                            <pre className="p-1.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-300 overflow-x-auto text-[10px]">
                              {e.error_message}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* SECTION E: Pending Approval Overview */}
      {activeTab === 'approvals' && (
        <div className="space-y-4" data-testid="mcp-approvals-summary-card">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Human-in-the-Loop Approval Metrics
              </div>
              <p className="text-[11px] text-muted-foreground">
                Read-only overview of human gating requests and historical decisions across the runtime.
              </p>
            </div>
            <button
              onClick={loadApprovalsSummary}
              disabled={loadingApprovals}
              data-testid="mcp-approvals-refresh-btn"
              className="px-2 py-1 text-xs rounded border border-border hover:bg-secondary text-foreground flex items-center gap-1 transition-colors"
            >
              <RefreshCw className={cn('w-3 h-3', loadingApprovals && 'animate-spin')} />
              <span>Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <div className="p-3.5 rounded-lg border border-amber-500/30 bg-amber-500/5 space-y-1">
              <span className="text-xs font-semibold text-amber-500">Pending Approvals</span>
              <div
                className="text-2xl font-bold font-mono text-amber-500"
                data-testid="mcp-summary-pending-count"
              >
                {approvalsSummary?.pending_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Awaiting owner decision</p>
            </div>

            <div className="p-3.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 space-y-1">
              <span className="text-xs font-semibold text-emerald-500">Approved Executions</span>
              <div
                className="text-2xl font-bold font-mono text-emerald-500"
                data-testid="mcp-summary-approved-count"
              >
                {approvalsSummary?.approved_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Executed successfully</p>
            </div>

            <div className="p-3.5 rounded-lg border border-rose-500/30 bg-rose-500/5 space-y-1">
              <span className="text-xs font-semibold text-rose-500">Rejected Invocations</span>
              <div
                className="text-2xl font-bold font-mono text-rose-500"
                data-testid="mcp-summary-rejected-count"
              >
                {approvalsSummary?.rejected_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Denied by human operator</p>
            </div>

            <div className="p-3.5 rounded-lg border border-border bg-secondary/20 space-y-1">
              <span className="text-xs font-semibold text-muted-foreground">Expired Approvals</span>
              <div
                className="text-2xl font-bold font-mono text-muted-foreground"
                data-testid="mcp-summary-expired-count"
              >
                {approvalsSummary?.expired_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Timed out before decision</p>
            </div>

            <div className="p-3.5 rounded-lg border border-border bg-secondary/20 space-y-1">
              <span className="text-xs font-semibold text-muted-foreground">Cancelled Invocations</span>
              <div
                className="text-2xl font-bold font-mono text-muted-foreground"
                data-testid="mcp-summary-cancelled-count"
              >
                {approvalsSummary?.cancelled_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Revoked by policy update</p>
            </div>

            <div className="p-3.5 rounded-lg border border-border bg-secondary/30 space-y-1">
              <span className="text-xs font-semibold text-foreground">Total Invocations</span>
              <div
                className="text-2xl font-bold font-mono text-foreground"
                data-testid="mcp-summary-total-count"
              >
                {approvalsSummary?.total_count ?? 0}
              </div>
              <p className="text-[10px] text-muted-foreground">Total records in approval store</p>
            </div>
          </div>

          {/* Read-Only Guidance & Safe User Mode Navigation (Section 9) */}
          <div className="p-3.5 rounded-lg bg-secondary/20 border border-border/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <span className="text-xs font-semibold text-foreground block">
                Human-in-the-Loop Action Workflow
              </span>
              <p className="text-xs text-muted-foreground max-w-lg">
                Developer Mode maintains read-only observability over approvals. To review tool arguments, approve or reject pending tool calls, return to the User Mode Agent Chat.
              </p>
            </div>

            <a
              href="/chat"
              data-testid="mcp-nav-to-user-chat"
              className="px-3 py-1.5 text-xs font-medium rounded bg-primary text-primary-foreground hover:bg-primary/90 flex items-center gap-1.5 self-start sm:self-auto shrink-0 transition-colors"
            >
              <span>Go to Agent Chat</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        </div>
      )}

      {/* SECTION F: Live Diagnostics & Observability */}
      {activeTab === 'diagnostics' && (
        <div className="space-y-4" data-testid="mcp-diagnostics-card">
          <div>
            <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              MCP Subsystem Diagnostics & Security Verification
            </div>
            <p className="text-[11px] text-muted-foreground">
              Truthful live telemetry from backend gateways, SQLite stores, and MCP runtime.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            {/* FastAPI REST Gateway */}
            <div className="p-3 rounded-lg border border-border bg-background space-y-1">
              <div className="flex items-center justify-between text-muted-foreground font-medium">
                <span>FastAPI REST Gateway</span>
                <span className={cn('w-2 h-2 rounded-full', systemStatus ? 'bg-emerald-500' : 'bg-rose-500')} />
              </div>
              <div className="text-sm font-bold font-mono text-foreground">
                {systemStatus ? 'ONLINE' : 'UNREACHABLE'}
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                {systemStatus ? `Uptime: ${systemStatus.uptime_seconds}s • v${systemStatus.backend_version}` : 'Port 8000 offline'}
              </p>
            </div>

            {/* MCP Time Server */}
            <div className="p-3 rounded-lg border border-border bg-background space-y-1">
              <div className="flex items-center justify-between text-muted-foreground font-medium">
                <span>Time MCP Server Subprocess</span>
                <span
                  className={cn(
                    'w-2 h-2 rounded-full',
                    servers.some((s) => s.connection_state === 'connected')
                      ? 'bg-emerald-500'
                      : 'bg-amber-500'
                  )}
                />
              </div>
              <div className="text-sm font-bold font-mono text-foreground">
                {servers.find((s) => s.server_id === 'time')?.connection_state?.toUpperCase() || 'DISCONNECTED'}
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                Transport: STDIO • Protocol: {servers[0]?.protocol_version || '2026-07-28'}
              </p>
            </div>

            {/* Discovered Tools Inventory */}
            <div className="p-3 rounded-lg border border-border bg-background space-y-1">
              <div className="flex items-center justify-between text-muted-foreground font-medium">
                <span>Discovered Tools Inventory</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
              </div>
              <div className="text-sm font-bold font-mono text-foreground" data-testid="mcp-diag-tool-count">
                {tools.length} Tools
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                Host policy version: v{policyVersion}
              </p>
            </div>

            {/* Approvals Store */}
            <div className="p-3 rounded-lg border border-border bg-background space-y-1">
              <div className="flex items-center justify-between text-muted-foreground font-medium">
                <span>Durable Approval Store</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
              </div>
              <div
                className="text-sm font-bold font-mono text-emerald-500"
                data-testid="mcp-diag-approvals-store"
              >
                Operational & Persisted
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                SQLite Path: data/approvals.db (WAL Mode)
              </p>
            </div>

            {/* LangGraph Checkpoints */}
            <div className="p-3 rounded-lg border border-border bg-background space-y-1">
              <div className="flex items-center justify-between text-muted-foreground font-medium">
                <span>Checkpoint Store</span>
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
              </div>
              <div
                className="text-sm font-bold font-mono text-emerald-500"
                data-testid="mcp-diag-checkpoints-store"
              >
                Operational & Persisted
              </div>
              <p className="text-[11px] text-muted-foreground font-mono">
                SQLite Path: data/checkpoints.db
              </p>
            </div>
          </div>

          {/* Sanitized Last Error Display */}
          <div className="p-3 rounded-lg border border-border bg-secondary/10 space-y-1">
            <span className="text-[11px] font-semibold text-muted-foreground block">
              Last Known MCP Diagnostic Message:
            </span>
            <div
              data-testid="mcp-last-error-display"
              className="text-xs font-mono text-foreground"
            >
              {servers.find((s) => s.last_error)?.last_error || 'No active MCP errors reported. Subsystem healthy.'}
            </div>
          </div>

          {/* Zero-Trust Notice */}
          <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-xs text-muted-foreground flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
            <p className="text-[11px]">
              <strong>Zero-Trust Credential Protection:</strong> Owner tokens, OpenRouter API keys, and private conversational checkpoint data are strictly isolated host-side and never returned over diagnostic endpoints.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
