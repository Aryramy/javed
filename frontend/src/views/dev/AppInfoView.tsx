import { Layers, Package, Terminal } from 'lucide-react'

export const AppInfoView: React.FC = () => {
  const metadata = [
    { label: 'Project Name', value: 'Javed (JARVIS)' },
    { label: 'Current Stage', value: 'Stage 1 — Foundations & Core Capabilities' },
    { label: 'Active Brick', value: 'BRICK-001: Reproducible Foundation & Real React UI Shell' },
    { label: 'Last Verified Milestone', value: 'BRICK-000: Master Architecture & Planning (2026-10-22)' },
    { label: 'Frontend Framework', value: 'React 19.3.1 + TypeScript (Strict Mode)' },
    { label: 'Bundler & Dev Server', value: 'Vite 8.3.4 with @tailwindcss/vite' },
    { label: 'Styling & Design System', value: 'Tailwind CSS v4.0 + shadcn/ui Design Tokens' },
    { label: 'Iconography', value: 'Lucide React' },
    { label: 'Backend Runtime', value: 'Python 3.12.15 (Managed in user space via uv 0.13.5)' },
    { label: 'Host Platform', value: 'Windows 11 (Non-Administrator Environment)' },
    { label: 'Primary API Gateway', value: 'OpenRouter (https://openrouter.ai/api/v1)' },
    { label: 'License Policy', value: 'Permissive Free & Open-Source (MIT / Apache 2.0 / BSD)' },
  ]

  return (
    <div className="space-y-6 max-w-4xl mx-auto py-2">
      <div>
        <div className="flex items-center gap-2 text-xs font-semibold text-primary uppercase tracking-wider mb-1">
          <Terminal className="w-4 h-4" />
          <span>Developer Diagnostic Console</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Application Architecture & System Information
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Authoritative technical specifications and package version metadata for the verified JARVIS foundation.
        </p>
      </div>

      {/* Metadata Table Card */}
      <div className="bg-card border border-border rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border/80 bg-secondary/30 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
            <Package className="w-4 h-4 text-primary" />
            <span>Verified System Properties & Runtime Baseline</span>
          </div>
          <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
            AUDITED BASELINE
          </span>
        </div>
        <div className="divide-y divide-border/60">
          {metadata.map((item, index) => (
            <div key={index} className="p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-xs hover:bg-secondary/20 transition-colors">
              <span className="font-medium text-muted-foreground">{item.label}</span>
              <span className="font-mono text-foreground font-semibold sm:text-right">{item.value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 14-Brick Roadmap Sequence Card */}
      <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Layers className="w-4 h-4 text-primary" />
          <span>Architectural Milestone Progression (Rule 5 Discipline)</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Development proceeds strictly one vertical slice at a time. Advance to subsequent bricks occurs only after verified live UI acceptance.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2">
          <div className="p-2.5 rounded-lg border border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400">
            <div className="text-[10px] font-mono font-semibold">BRICK-000</div>
            <div className="text-xs font-bold mt-0.5">Architecture</div>
            <div className="text-[10px] uppercase font-semibold text-emerald-500 mt-1">VERIFIED</div>
          </div>
          <div className="p-2.5 rounded-lg border border-primary/40 bg-primary/10 text-primary">
            <div className="text-[10px] font-mono font-semibold">BRICK-001</div>
            <div className="text-xs font-bold mt-0.5">UI Shell & uv</div>
            <div className="text-[10px] uppercase font-semibold text-primary mt-1">IN PROGRESS</div>
          </div>
          <div className="p-2.5 rounded-lg border border-border bg-secondary/30 text-muted-foreground">
            <div className="text-[10px] font-mono font-semibold">BRICK-002</div>
            <div className="text-xs font-bold mt-0.5">FastAPI & WS</div>
            <div className="text-[10px] uppercase font-semibold text-muted-foreground mt-1">BLOCKED</div>
          </div>
          <div className="p-2.5 rounded-lg border border-border bg-secondary/30 text-muted-foreground">
            <div className="text-[10px] font-mono font-semibold">BRICK-003</div>
            <div className="text-xs font-bold mt-0.5">OpenRouter Chat</div>
            <div className="text-[10px] uppercase font-semibold text-muted-foreground mt-1">BLOCKED</div>
          </div>
        </div>
      </div>
    </div>
  )
}
