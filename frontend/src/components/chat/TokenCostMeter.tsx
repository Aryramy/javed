import React from 'react';
import { Coins, Zap } from 'lucide-react';
import type { ConversationTotals, StreamUsage } from '../../types/chat';

interface TokenCostMeterProps {
  currentUsage?: StreamUsage | null;
  totals?: ConversationTotals;
  isStreaming?: boolean;
  className?: string;
}

export const TokenCostMeter: React.FC<TokenCostMeterProps> = ({
  currentUsage,
  totals,
  isStreaming = false,
  className = '',
}) => {
  // Determine authoritative thread and current-call tokens and cost
  const hasTotals = totals && (totals.totalTokens > 0 || totals.messageCount > 0);
  const hasCurrent = currentUsage && currentUsage.total_tokens > 0;

  const displayTokens: number | null = hasTotals
    ? totals.totalTokens
    : hasCurrent
    ? currentUsage.total_tokens
    : null;

  const displayCost: number | null = hasTotals
    ? totals.totalCostUsd
    : hasCurrent
    ? currentUsage.cost_usd
    : null;

  const isEstimated =
    isStreaming ||
    (totals ? totals.isEstimated : (currentUsage?.is_estimated ?? false));
  const costSource = currentUsage?.cost_source ?? (isEstimated ? 'estimate' : 'provider_reconciled');

  const formatCost = (val: number | null): string => {
    if (val === null) return '—';
    if (val === 0) return '$0.0000';
    if (val < 0.01) return `$${val.toFixed(6)}`;
    return `$${val.toFixed(4)}`;
  };

  const formattedCost = displayCost !== null ? `${isEstimated ? '~' : ''}${formatCost(displayCost)}` : '—';
  const tokensText = displayTokens !== null ? displayTokens.toLocaleString() : '—';

  const turnLabel = currentUsage
    ? `${currentUsage.total_tokens} tokens (${formatCost(currentUsage.cost_usd)})`
    : 'Unavailable';
  const threadLabel = totals && (totals.totalTokens > 0 || totals.messageCount > 0)
    ? `${totals.totalTokens} tokens (${formatCost(totals.totalCostUsd)})`
    : hasCurrent
    ? `${currentUsage.total_tokens} tokens (${formatCost(currentUsage.cost_usd)})`
    : 'Unavailable';

  return (
    <div
      id="token-cost-meter"
      data-testid="token-cost-meter"
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-300 ${className}`}
      title={`[Current Turn] ${turnLabel} | [Current Thread] ${threadLabel} | Source: ${costSource} | Status: ${
        isEstimated ? 'Estimated' : 'Provider-Reconciled'
      }`}
    >
      <div className="flex items-center gap-1 text-zinc-400">
        <Zap className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-[10px] font-mono text-zinc-400 font-semibold uppercase">Thread:</span>
        <span className="font-mono font-medium text-zinc-200" id="meter-display-tokens" data-testid="meter-display-tokens">
          {tokensText}
        </span>
        <span className="text-[10px] text-zinc-500">tok</span>
      </div>

      <div className="h-3 w-px bg-zinc-700/60" />

      <div className="flex items-center gap-1 text-zinc-400">
        <Coins className="w-3.5 h-3.5 text-emerald-400" />
        <span className="font-mono font-medium text-emerald-400" id="meter-display-cost" data-testid="meter-display-cost">
          {formattedCost}
        </span>
      </div>

      {isEstimated && displayTokens !== null && (
        <span
          data-testid="cost-estimate-badge"
          className="text-[9px] uppercase tracking-wider font-semibold px-1 py-0.2 rounded bg-amber-500/10 text-amber-400/90 border border-amber-500/20"
        >
          Est
        </span>
      )}
    </div>
  );
};
