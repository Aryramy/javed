import React, { useState } from 'react';
import {
  Server,
  Wrench,
  Clock,
  CheckCircle2,
  AlertCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
} from 'lucide-react';
import type { ToolActivityRecord, ToolLifecycleState } from '../../types/agent';
import { cn } from '../../lib/utils';

export interface ToolActivityCardProps {
  activity: ToolActivityRecord;
  className?: string;
}

export const ToolActivityCard: React.FC<ToolActivityCardProps> = ({
  activity,
  className,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const getStatusBadge = (status: ToolLifecycleState) => {
    switch (status) {
      case 'REQUESTED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-sky-500/10 text-sky-400 border border-sky-500/30">
            <Clock className="w-3 h-3 text-sky-400" />
            REQUESTED
          </span>
        );
      case 'AWAITING_APPROVAL':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse">
            <Clock className="w-3 h-3 text-amber-400" />
            AWAITING APPROVAL
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            APPROVED
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <XCircle className="w-3 h-3 text-rose-400" />
            REJECTED
          </span>
        );
      case 'EXECUTING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
            <Loader2 className="w-3 h-3 text-indigo-400 animate-spin" />
            EXECUTING
          </span>
        );
      case 'COMPLETED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            COMPLETED
          </span>
        );
      case 'FAILED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">
            <AlertCircle className="w-3 h-3 text-rose-400" />
            FAILED
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/30">
            <XCircle className="w-3 h-3 text-zinc-400" />
            CANCELLED
          </span>
        );
      case 'UNCERTAIN':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-orange-500/10 text-orange-400 border border-orange-500/30">
            <HelpCircle className="w-3 h-3 text-orange-400" />
            UNCERTAIN
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-zinc-500/10 text-zinc-400 border border-zinc-500/30">
            {status}
          </span>
        );
    }
  };

  const displayName = activity.tool_name || activity.tool_id;
  const hasArgs = activity.arguments && Object.keys(activity.arguments).length > 0;
  const hasResult = Boolean(activity.result_summary);
  const hasError = Boolean(activity.error_message);

  const formatTime = (ts?: string | null) => {
    if (!ts) return null;
    try {
      return new Date(ts).toLocaleTimeString();
    } catch {
      return ts;
    }
  };

  return (
    <div
      data-testid="tool-activity-card"
      data-tool-id={activity.tool_id}
      data-tool-status={activity.status}
      className={cn(
        'my-2 rounded-xl border border-zinc-800/80 bg-zinc-900/50 backdrop-blur-md p-3 text-xs shadow-md transition-all duration-200',
        activity.status === 'FAILED' && 'border-rose-900/50 bg-rose-950/20',
        activity.status === 'COMPLETED' && 'border-emerald-900/30 bg-emerald-950/10',
        activity.status === 'AWAITING_APPROVAL' && 'border-amber-900/50 bg-amber-950/20',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="p-1 rounded-lg bg-zinc-800/80 text-cyan-400 shrink-0">
            <Wrench className="w-3.5 h-3.5" />
          </div>
          <span
            data-testid="tool-activity-name"
            className="font-semibold text-zinc-200 truncate"
            title={displayName}
          >
            {displayName}
          </span>

          {activity.server_id && (
            <span
              data-testid="tool-activity-server"
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-zinc-800 text-[10px] text-zinc-400 shrink-0"
              title={`MCP Server: ${activity.server_id}`}
            >
              <Server className="w-2.5 h-2.5" />
              {activity.server_id}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {activity.elapsed_ms !== null && activity.elapsed_ms !== undefined && (
            <span
              data-testid="tool-activity-duration"
              className="text-[10px] text-zinc-400 flex items-center gap-0.5"
            >
              <Clock className="w-2.5 h-2.5" />
              {activity.elapsed_ms}ms
            </span>
          )}

          <div data-testid="tool-activity-status">
            {getStatusBadge(activity.status)}
          </div>

          <button
            type="button"
            data-testid="tool-activity-toggle"
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 text-zinc-400 hover:text-zinc-200 rounded hover:bg-zinc-800 transition-colors"
            title={isExpanded ? 'Collapse details' : 'Expand details'}
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Purpose / description */}
      {activity.description && (
        <p
          data-testid="tool-activity-purpose"
          className="mt-1 text-[11px] text-zinc-400 line-clamp-2"
        >
          {activity.description}
        </p>
      )}

      {/* Compact Status Details when collapsed but finished */}
      {!isExpanded && hasResult && (
        <div
          data-testid="tool-activity-result"
          className="mt-2 px-2.5 py-1.5 rounded-lg bg-zinc-950/70 border border-emerald-900/30 text-[11px] font-mono text-emerald-300 truncate"
        >
          {activity.result_summary}
        </div>
      )}

      {!isExpanded && hasError && (
        <div
          data-testid="tool-activity-error"
          className="mt-2 px-2.5 py-1.5 rounded-lg bg-zinc-950/70 border border-rose-900/40 text-[11px] font-mono text-rose-300 truncate"
        >
          {activity.error_message}
        </div>
      )}

      {/* Expanded details */}
      {isExpanded && (
        <div className="mt-2.5 pt-2 border-t border-zinc-800/80 space-y-2">
          {/* Timestamps */}
          <div
            data-testid="tool-activity-time"
            className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-zinc-400"
          >
            {activity.started_at && (
              <span>Started: {formatTime(activity.started_at)}</span>
            )}
            {activity.completed_at && (
              <span>Completed: {formatTime(activity.completed_at)}</span>
            )}
            {activity.approval_id && (
              <span>Approval ID: {activity.approval_id}</span>
            )}
          </div>

          {/* Arguments */}
          {hasArgs && (
            <div>
              <div className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider mb-1">
                Arguments
              </div>
              <pre
                data-testid="tool-activity-args"
                className="p-2 rounded-lg bg-zinc-950 border border-zinc-800/80 font-mono text-[11px] text-zinc-300 overflow-x-auto whitespace-pre-wrap max-h-36 overflow-y-auto"
              >
                {JSON.stringify(activity.arguments, null, 2)}
              </pre>
            </div>
          )}

          {/* Full Result */}
          {hasResult && (
            <div>
              <div className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">
                Result
              </div>
              <pre
                data-testid="tool-activity-result"
                className="p-2 rounded-lg bg-zinc-950 border border-emerald-900/30 font-mono text-[11px] text-emerald-300 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto"
              >
                {activity.result_summary}
              </pre>
            </div>
          )}

          {/* Full Error */}
          {hasError && (
            <div>
              <div className="text-[10px] font-semibold text-rose-400 uppercase tracking-wider mb-1">
                Error
              </div>
              <pre
                data-testid="tool-activity-error"
                className="p-2 rounded-lg bg-zinc-950 border border-rose-900/40 font-mono text-[11px] text-rose-300 overflow-x-auto whitespace-pre-wrap max-h-48 overflow-y-auto"
              >
                {activity.error_message}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
