import type { ComponentType } from 'react'
import { AlertCircle, Clock, ShieldAlert, Sparkles } from 'lucide-react'

interface EmptyStateProps {
  icon: ComponentType<{ className?: string }>
  title: string
  description: string
  scheduledBrick: string
  stage: string
  prerequisites: string[]
  architectureNote?: string
}

export const EmptyState = ({
  icon: Icon,
  title,
  description,
  scheduledBrick,
  stage,
  prerequisites,
  architectureNote,
}: EmptyStateProps) => {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] p-6 text-center max-w-2xl mx-auto animate-fade-in">
      <div className="relative mb-6">
        <div className="w-20 h-20 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shadow-lg shadow-primary/5">
          <Icon className="w-10 h-10" />
        </div>
        <div className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-500">
          <Clock className="w-3.5 h-3.5" />
        </div>
      </div>

      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-secondary text-xs font-medium text-muted-foreground border border-border mb-3">
        <Sparkles className="w-3 h-3 text-primary" />
        <span>Planned for {scheduledBrick} ({stage})</span>
      </div>

      <h2 className="text-2xl font-bold tracking-tight text-foreground mb-2">
        {title}
      </h2>

      <p className="text-muted-foreground text-sm leading-relaxed mb-6 max-w-lg">
        {description}
      </p>

      {/* Honest Boundary Notice Card */}
      <div className="w-full bg-card/60 backdrop-blur border border-border/80 rounded-xl p-4 text-left shadow-sm mb-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground uppercase tracking-wider mb-2">
          <ShieldAlert className="w-4 h-4 text-primary" />
          <span>Governance & Architectural Integrity Notice</span>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Per <strong>Rule 7 (No Mocked Success)</strong> and <strong>Rule 5 (Brick-by-Brick Workflow)</strong>, this capability is not yet operational. We strictly avoid generating simulated chat messages, fake completions, or mock telemetry until the required backend services are implemented and verified.
        </p>

        {architectureNote && (
          <p className="text-xs text-primary/90 mt-2 font-mono bg-primary/5 p-2 rounded border border-primary/10">
            {architectureNote}
          </p>
        )}
      </div>

      {/* Prerequisites Checklist */}
      <div className="w-full bg-secondary/40 border border-border/60 rounded-xl p-4 text-left">
        <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
          Scheduled Delivery Prerequisites
        </h4>
        <ul className="text-xs space-y-1.5 text-muted-foreground">
          {prerequisites.map((prereq, index) => (
            <li key={index} className="flex items-start gap-2">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted-foreground/60 mt-1.5 shrink-0" />
              <span>{prereq}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
