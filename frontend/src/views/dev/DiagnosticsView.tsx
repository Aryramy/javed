import { AlertTriangle, Lock, ShieldCheck } from 'lucide-react'

export const DiagnosticsView: React.FC = () => {
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
          <span>Security Sandbox & Permission Architecture</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Security Sandbox & Diagnostics Matrix
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Authoritative 4-tier security taxonomy and human-in-the-loop interruption boundaries defined in docs/SECURITY.md.
        </p>
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
