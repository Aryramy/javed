import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Clock,
  Server,
  Terminal,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { ApprovalRecord } from '../../types/agent';
import { cn } from '../../lib/utils';

export interface ApprovalCardProps {
  approval: ApprovalRecord;
  onApprove: (approvalId: string) => Promise<void>;
  onReject: (approvalId: string, reason?: string) => Promise<void>;
  isProcessing?: boolean;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({
  approval,
  onApprove,
  onReject,
  isProcessing = false,
}) => {
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(true);

  const isPending = approval.status === 'pending';
  const isApproved = approval.status === 'approved';
  const isRejected = approval.status === 'rejected';
  const isCancelled = approval.status === 'cancelled';

  const handleApprove = async () => {
    setActionError(null);
    try {
      await onApprove(approval.approval_id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRejectConfirm = async () => {
    setActionError(null);
    try {
      await onReject(approval.approval_id, rejectReason.trim() || undefined);
      setShowRejectInput(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div
      id={`approval-card-${approval.approval_id}`}
      data-testid="approval-card"
      data-approval-status={approval.status}
      className={cn(
        'my-3 rounded-xl border backdrop-blur-md shadow-xl transition-all duration-200 overflow-hidden',
        isPending && 'border-amber-500/40 bg-amber-950/20 shadow-amber-950/20',
        isApproved && 'border-emerald-500/30 bg-emerald-950/20 shadow-emerald-950/10',
        isRejected && 'border-rose-500/30 bg-rose-950/20 shadow-rose-950/10',
        isCancelled && 'border-zinc-700 bg-zinc-900/50'
      )}
    >
      {/* Header bar */}
      <div
        className={cn(
          'flex items-center justify-between px-4 py-2.5 border-b select-none transition-colors',
          isPending && 'bg-amber-950/40 border-amber-500/20',
          isApproved && 'bg-emerald-950/40 border-emerald-500/20',
          isRejected && 'bg-rose-950/40 border-rose-500/20',
          isCancelled && 'bg-zinc-900/70 border-zinc-800'
        )}
      >
        <div className="flex items-center gap-2">
          {isPending && <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 animate-pulse" />}
          {isApproved && <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />}
          {isRejected && <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
          {isCancelled && <Clock className="w-4 h-4 text-zinc-400 shrink-0" />}

          <span
            className={cn(
              'text-xs font-semibold uppercase tracking-wider',
              isPending && 'text-amber-300',
              isApproved && 'text-emerald-300',
              isRejected && 'text-rose-300',
              isCancelled && 'text-zinc-400'
            )}
          >
            {isPending
              ? 'Human Approval Required'
              : isApproved
              ? 'Tool Execution Approved'
              : isRejected
              ? 'Tool Execution Rejected'
              : 'Tool Call Cancelled'}
          </span>

          <span
            id="approval-status-badge"
            data-testid="approval-status-badge"
            className={cn(
              'text-[10px] font-mono uppercase px-2 py-0.5 rounded-full border font-semibold',
              isPending && 'bg-amber-500/20 border-amber-500/40 text-amber-300',
              isApproved && 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300',
              isRejected && 'bg-rose-500/20 border-rose-500/40 text-rose-300',
              isCancelled && 'bg-zinc-800 border-zinc-700 text-zinc-400'
            )}
          >
            {approval.status}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-zinc-500 hidden sm:inline">
            ID: {approval.approval_id.slice(0, 8)}...
          </span>
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-zinc-400 hover:text-zinc-200 transition-colors p-0.5"
            aria-label={isExpanded ? 'Collapse card' : 'Expand card'}
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Main body */}
      {isExpanded && (
        <div className="p-3.5 space-y-3 text-xs">
          {/* Tool & Server identity pills */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="flex items-center gap-2 p-2 rounded-lg bg-zinc-900/60 border border-zinc-800">
              <Terminal className="w-3.5 h-3.5 text-blue-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-[10px] text-zinc-500 uppercase font-mono">Requested Tool</div>
                <div
                  id="approval-tool-name"
                  data-testid="approval-tool-name"
                  className="font-mono text-zinc-200 truncate font-medium"
                >
                  {approval.tool_id}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 p-2 rounded-lg bg-zinc-900/60 border border-zinc-800">
              <Server className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-[10px] text-zinc-500 uppercase font-mono">MCP Server</div>
                <div
                  id="approval-server-id"
                  data-testid="approval-server-id"
                  className="font-mono text-zinc-200 truncate font-medium"
                >
                  {approval.server_id}
                </div>
              </div>
            </div>
          </div>

          {/* Validated Arguments */}
          <div className="rounded-lg bg-zinc-950 border border-zinc-800/80 p-2.5">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase font-mono text-zinc-400 font-semibold tracking-wider">
                Validated Arguments
              </span>
              <span className="text-[9px] font-mono text-zinc-600">
                digest: {approval.argument_digest.slice(0, 10)}...
              </span>
            </div>
            <pre
              id="approval-arguments-view"
              data-testid="approval-arguments-view"
              className="font-mono text-[11px] text-zinc-300 overflow-x-auto whitespace-pre-wrap p-2 rounded bg-zinc-900/50 border border-zinc-800/50"
            >
              {Object.keys(approval.arguments || {}).length > 0
                ? JSON.stringify(approval.arguments, null, 2)
                : '{\n  /* No arguments required */\n}'}
            </pre>
          </div>

          {/* Execution / Dispatch Outcome (if completed or rejected) */}
          {approval.dispatch_status !== 'not_dispatched' && (
            <div
              className={cn(
                'p-2.5 rounded-lg border text-[11px] font-mono flex items-start gap-2',
                approval.dispatch_status === 'completed' && 'bg-emerald-950/30 border-emerald-500/30 text-emerald-200',
                approval.dispatch_status === 'failed' && 'bg-rose-950/30 border-rose-500/30 text-rose-200',
                approval.dispatch_status === 'in_flight' && 'bg-blue-950/30 border-blue-500/30 text-blue-200'
              )}
            >
              <div className="shrink-0 mt-0.5">
                {approval.dispatch_status === 'completed' && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                {approval.dispatch_status === 'failed' && <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />}
                {approval.dispatch_status === 'in_flight' && <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />}
              </div>
              <div className="flex-1 min-w-0">
                <span className="font-semibold uppercase tracking-wider text-[10px]">
                  Dispatch Status: {approval.dispatch_status}
                </span>
                {approval.result_summary && (
                  <div className="mt-1 text-zinc-300 break-words">{approval.result_summary}</div>
                )}
                {approval.error_message && (
                  <div className="mt-1 text-rose-300 break-words">{approval.error_message}</div>
                )}
              </div>
            </div>
          )}

          {/* Rejection reason display if rejected */}
          {isRejected && approval.rejection_reason && (
            <div className="p-2 rounded-lg bg-rose-950/30 border border-rose-500/20 text-rose-300 text-[11px]">
              <span className="font-semibold uppercase text-[10px] text-rose-400">Rejection Reason: </span>
              <span>{approval.rejection_reason}</span>
            </div>
          )}

          {/* Action error banner */}
          {actionError && (
            <div
              id="approval-action-error"
              data-testid="approval-action-error"
              className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs flex items-center gap-2"
            >
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>{actionError}</span>
            </div>
          )}

          {/* Controls (Pending Only) */}
          {isPending && (
            <div className="pt-2 border-t border-zinc-800/80 space-y-2">
              {showRejectInput ? (
                <div className="space-y-2">
                  <input
                    type="text"
                    id="reject-reason-input"
                    data-testid="reject-reason-input"
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Enter reason for rejection (optional)..."
                    className="w-full px-3 py-1.5 rounded-lg bg-zinc-950 border border-zinc-800 focus:border-rose-500/60 text-xs text-zinc-100 placeholder:text-zinc-600 outline-none"
                    disabled={isProcessing}
                  />
                  <div className="flex items-center gap-2 justify-end">
                    <button
                      type="button"
                      onClick={() => setShowRejectInput(false)}
                      disabled={isProcessing}
                      className="px-2.5 py-1 rounded-md text-xs text-zinc-400 hover:text-zinc-200"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      id="confirm-reject-button"
                      data-testid="confirm-reject-button"
                      onClick={handleRejectConfirm}
                      disabled={isProcessing}
                      className="px-3 py-1 rounded-md bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs flex items-center gap-1.5 transition-colors shadow-sm"
                    >
                      {isProcessing ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <XCircle className="w-3 h-3" />
                      )}
                      <span>Confirm Rejection</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-3">
                  <div className="text-[11px] text-zinc-400">
                    Host gate paused. Awaiting human confirmation to dispatch tool.
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      id="reject-tool-button"
                      data-testid="reject-tool-button"
                      onClick={() => setShowRejectInput(true)}
                      disabled={isProcessing}
                      className="px-3 py-1.5 rounded-lg border border-rose-500/30 bg-rose-950/30 hover:bg-rose-900/40 text-rose-300 font-medium text-xs flex items-center gap-1.5 transition-colors"
                      title="Reject tool execution and resume agent with refusal"
                    >
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                      <span>Reject</span>
                    </button>

                    <button
                      type="button"
                      id="approve-tool-button"
                      data-testid="approve-tool-button"
                      onClick={handleApprove}
                      disabled={isProcessing}
                      className="px-3.5 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs flex items-center gap-1.5 transition-all shadow-md shadow-emerald-950/40"
                      title="Authorize MCP tool execution and resume agent stream"
                    >
                      {isProcessing ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      )}
                      <span>Approve Tool Call</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
