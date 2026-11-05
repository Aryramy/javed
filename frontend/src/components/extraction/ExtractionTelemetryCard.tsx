import { FileText, Table as TableIcon, History, HardDrive, CheckCircle2, AlertCircle } from 'lucide-react'
import type { ExtractionTelemetryResponse } from '@/types/extraction'

interface ExtractionTelemetryCardProps {
  telemetry: ExtractionTelemetryResponse | null
  loading?: boolean
}

export const ExtractionTelemetryCard = ({
  telemetry,
  loading = false,
}: ExtractionTelemetryCardProps) => {
  if (!telemetry && !loading) return null

  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 shadow-sm flex flex-wrap items-center justify-between gap-4">
      {/* Metric 1: Documents */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
          <FileText className="w-5 h-5" />
        </div>
        <div>
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
            Documents
          </span>
          <span className="text-lg font-bold text-foreground">
            {loading ? '—' : telemetry?.total_documents.toLocaleString()}
          </span>
        </div>
      </div>

      <div className="h-8 w-px bg-border/60 hidden sm:block" />

      {/* Metric 2: Extractions */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-blue-500/10 text-blue-500 flex items-center justify-center shrink-0">
          <History className="w-5 h-5" />
        </div>
        <div>
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
            Extractions
          </span>
          <span className="text-lg font-bold text-foreground">
            {loading ? '—' : telemetry?.total_extractions.toLocaleString()}
          </span>
        </div>
      </div>

      <div className="h-8 w-px bg-border/60 hidden sm:block" />

      {/* Metric 3: Tables */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center shrink-0">
          <TableIcon className="w-5 h-5" />
        </div>
        <div>
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
            Tables
          </span>
          <span className="text-lg font-bold text-foreground">
            {loading ? '—' : telemetry?.total_tables.toLocaleString()}
          </span>
        </div>
      </div>

      <div className="h-8 w-px bg-border/60 hidden sm:block" />

      {/* Metric 4: Storage Health */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-500/10 text-purple-500 flex items-center justify-center shrink-0">
          <HardDrive className="w-5 h-5" />
        </div>
        <div>
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider block">
            Storage Status
          </span>
          <div className="flex items-center gap-1.5 mt-0.5">
            {telemetry?.storage_healthy ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                  Healthy
                </span>
              </>
            ) : (
              <>
                <AlertCircle className="w-4 h-4 text-destructive" />
                <span className="text-xs font-semibold text-destructive">
                  Degraded
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

