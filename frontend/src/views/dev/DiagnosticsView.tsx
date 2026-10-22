import React, { useState } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Lock,
  Play,
  Radio,
  ShieldCheck,
  Sparkles,
  Terminal,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { useBackend } from '@/context'
import { apiService } from '@/services/api'
import { chatService } from '@/services/chatService'
import { cn } from '@/lib/utils'

export const DiagnosticsView: React.FC = () => {
  const { status, latencyMs, ping, reconnect, disconnect } = useBackend()

  const [consoleOutput, setConsoleOutput] = useState<string>(
    '// Diagnostic test output will appear here.\n// Click any test action above to execute real requests.'
  )
  const [activeAction, setActiveAction] = useState<string | null>(null)

  const runCheckStatus = async () => {
    setActiveAction('status')
    try {
      const start = performance.now()
      const data = await apiService.getSystemStatus()
      const duration = Math.round((performance.now() - start) * 10) / 10
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/system/status',
            _status: 200,
            _duration_ms: duration,
            ...data,
          },
          null,
          2
        )
      )
    } catch (err: unknown) {
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/system/status',
            _status: 'FAILED',
            error: err instanceof Error ? err.message : String(err),
          },
          null,
          2
        )
      )
    } finally {
      setActiveAction(null)
    }
  }

  const runCheckLive = async () => {
    setActiveAction('live')
    try {
      const start = performance.now()
      const data = await apiService.getLive()
      const duration = Math.round((performance.now() - start) * 10) / 10
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/health/live',
            _status: 200,
            _duration_ms: duration,
            ...data,
          },
          null,
          2
        )
      )
    } catch (err: unknown) {
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/health/live',
            _status: 'FAILED',
            error: err instanceof Error ? err.message : String(err),
          },
          null,
          2
        )
      )
    } finally {
      setActiveAction(null)
    }
  }

  const runCheckReady = async () => {
    setActiveAction('ready')
    try {
      const start = performance.now()
      const data = await apiService.getReady()
      const duration = Math.round((performance.now() - start) * 10) / 10
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/health/ready',
            _status: 200,
            _duration_ms: duration,
            ...data,
          },
          null,
          2
        )
      )
    } catch (err: unknown) {
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/health/ready',
            _status: 'FAILED',
            error: err instanceof Error ? err.message : String(err),
          },
          null,
          2
        )
      )
    } finally {
      setActiveAction(null)
    }
  }

  const runPing = async () => {
    setActiveAction('ping')
    try {
      const start = performance.now()
      const ms = await ping()
      const duration = Math.round((performance.now() - start) * 10) / 10
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'Round-Trip Latency Ping',
            _status: 'ACKNOWLEDGED',
            measured_rtt_ms: ms,
            total_call_duration_ms: duration,
            timestamp: new Date().toISOString(),
          },
          null,
          2
        )
      )
    } catch (err: unknown) {
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'Round-Trip Latency Ping',
            _status: 'FAILED',
            error: err instanceof Error ? err.message : String(err),
          },
          null,
          2
        )
      )
    } finally {
      setActiveAction(null)
    }
  }

  const runCheckModels = async () => {
    setActiveAction('models')
    try {
      const start = performance.now()
      const data = await chatService.getModels()
      const duration = Math.round((performance.now() - start) * 10) / 10
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/models',
            _status: 200,
            _duration_ms: duration,
            ...data,
          },
          null,
          2
        )
      )
    } catch (err: unknown) {
      setConsoleOutput(
        JSON.stringify(
          {
            _test: 'GET /api/v1/models',
            _status: 'FAILED',
            error: err instanceof Error ? err.message : String(err),
          },
          null,
          2
        )
      )
    } finally {
      setActiveAction(null)
    }
  }

  const runCheckOpenRouterStream = async () => {
    setActiveAction('stream')
    let output = '// Initiating live SSE stream to /api/v1/chat/stream...\n'
    setConsoleOutput(output)
    try {
      const start = performance.now()
      await chatService.streamChat({
        messages: [{ role: 'user', content: 'Respond with exactly: "Javed Live Streaming Verified"' }],
        onToken: (tok) => {
          output += tok
          setConsoleOutput(output)
        },
        onUsage: (u) => {
          output += `\n\n// Usage Telemetry:\n// Total Tokens: ${u.total_tokens} (prompt: ${u.prompt_tokens}, comp: ${u.completion_tokens})\n// Cost: $${u.cost_usd.toFixed(6)}`
          setConsoleOutput(output)
        },
        onDone: () => {
          const duration = Math.round((performance.now() - start) * 10) / 10
          output += `\n// Stream Completed in ${duration}ms`
          setConsoleOutput(output)
        },
        onError: (err) => {
          output += `\n// Stream Error: ${err}`
          setConsoleOutput(output)
        },
      })
    } catch (err: unknown) {
      setConsoleOutput(output + `\n// Exception: ${err}`)
    } finally {
      setActiveAction(null)
    }
  }

  const tiers = [
    {
      tier: 'Tier 0: Pure Informational',
      risk: 'Zero Risk',
      policy: 'Autonomous Execution',
      examples: 'Clock, state inspection, telemetry readings, documentation lookup',
      badgeColor: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
    },
    {
      tier: 'Tier 1: Read-Only Operations',
      risk: 'Low Risk',
      policy: 'Autonomous with Audit Logging',
      examples: 'Directory listing, file reading within workspace, web scraping (Crawl4AI)',
      badgeColor: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
    },
    {
      tier: 'Tier 2: Reversible Modifications',
      risk: 'Medium Risk',
      policy: 'Workspace Sandboxed with Pre-Operation Snapshot',
      examples: 'Creating/editing files inside workspace, downloading files to quarantine',
      badgeColor: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
    },
    {
      tier: 'Tier 3: Consequential & External Actions',
      risk: 'High / Critical Risk',
      policy: 'Mandatory Human-in-the-Loop (HITL) Modal via interrupt()',
      examples: 'Arbitrary shell execution, deleting workspace files, git commits, external mutations',
      badgeColor: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
    },
  ]

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
          <ShieldCheck className="w-4 h-4" />
          <span>Interactive Transport Testing & Sandbox Matrix</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Diagnostics & Live Transport Console
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Direct testing controls for REST endpoints, WebSocket lifecycle, and security boundaries.
        </p>
      </div>

      {/* Live Transport Testing Console */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/80 pb-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Radio className="w-4 h-4 text-primary" />
            <span>Interactive Transport Diagnostic Controls</span>
          </div>
          <div className="flex items-center gap-2 text-xs font-mono">
            <span className="text-muted-foreground">Socket State:</span>
            <span
              className={cn(
                'px-2 py-0.5 rounded font-bold uppercase text-[10px] border',
                status === 'connected'
                  ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
                  : 'bg-rose-500/10 text-rose-500 border-rose-500/20'
              )}
            >
              {status}
            </span>
            {latencyMs !== null && (
              <span className="text-muted-foreground">({latencyMs}ms)</span>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={runCheckStatus}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50 shadow-sm"
          >
            <Play className={cn('w-3.5 h-3.5', activeAction === 'status' && 'animate-spin')} />
            <span>Check System Status</span>
          </button>

          <button
            onClick={runCheckLive}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-border text-foreground hover:bg-secondary text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>Liveness Probe</span>
          </button>

          <button
            onClick={runCheckReady}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-border text-foreground hover:bg-secondary text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />
            <span>Readiness Probe</span>
          </button>

          <button
            onClick={runPing}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-border text-foreground hover:bg-secondary text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Activity className="w-3.5 h-3.5 text-primary" />
            <span>Measure Ping</span>
          </button>

          <button
            onClick={reconnect}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-border text-foreground hover:bg-secondary text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Wifi className="w-3.5 h-3.5 text-amber-500" />
            <span>Reconnect Socket</span>
          </button>

          <button
            onClick={disconnect}
            disabled={activeAction !== null || status === 'disconnected'}
            className="px-3 py-1.5 rounded-lg border border-border text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <WifiOff className="w-3.5 h-3.5" />
            <span>Disconnect Socket</span>
          </button>

          <button
            onClick={runCheckModels}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-400 hover:bg-cyan-500/20 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
            <span>Query Model Catalog</span>
          </button>

          <button
            onClick={runCheckOpenRouterStream}
            disabled={activeAction !== null}
            className="px-3 py-1.5 rounded-lg border border-purple-500/30 bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
          >
            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
            <span>Test Live LLM Stream</span>
          </button>
        </div>

        {/* Live Terminal Console Output */}
        <div className="bg-slate-950 text-slate-100 rounded-lg p-3 font-mono text-xs border border-border shadow-inner overflow-x-auto max-h-64">
          <div className="flex items-center justify-between text-[10px] text-slate-400 border-b border-slate-800 pb-1.5 mb-2">
            <span className="flex items-center gap-1">
              <Terminal className="w-3 h-3 text-primary" />
              <span>DIAGNOSTIC TEST RESPONSE</span>
            </span>
            <span>UTF-8 JSON</span>
          </div>
          <pre className="text-emerald-400 whitespace-pre-wrap">{consoleOutput}</pre>
        </div>
      </div>

      {/* Security Policies */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Lock className="w-4 h-4 text-primary" />
            <span>Filesystem Sandbox Protection</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Multi-layered boundary guards: realpath canonicalization, Windows junction rejection, NTFS Alternate Data Stream (ADS) colon blocking, and hard isolation preventing access to <code>.env</code> or system folders.
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <span>Prompt Injection Defense-in-Depth</span>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            XML tags alone are not an impenetrable sandbox. We enforce input bounds, structural neutralization, secondary LLM classification, and deterministic host Python gating.
          </p>
        </div>
      </div>

      {/* 4-Tier Matrix */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border/80 bg-secondary/30">
          <h3 className="text-xs font-semibold text-foreground uppercase tracking-wider">
            Verified 4-Tier Authorization Matrix
          </h3>
        </div>
        <div className="divide-y divide-border/60">
          {tiers.map((item, index) => (
            <div key={index} className="p-4 space-y-2 hover:bg-secondary/20 transition-colors">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                <span className="font-semibold text-xs text-foreground">{item.tier}</span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${item.badgeColor}`}>
                  {item.policy}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                <strong className="text-foreground/80">Examples:</strong> {item.examples}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
