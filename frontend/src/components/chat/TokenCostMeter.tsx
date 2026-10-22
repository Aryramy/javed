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
  const displayCost = totals?.totalCostUsd ?? currentUsage?.cost_usd ?? 0;
  const displayTokens = totals?.totalTokens ?? currentUsage?.total_tokens ?? 0;
  const isEstimated =
    isStreaming ||
    (totals ? totals.isEstimated : (currentUsage?.is_estimated ?? false));
  const costSource = currentUsage?.cost_source ?? 'rate_card';

  const formatCost = (val: number): string => {
    if (val === 0) return '$0.0000';
    if (val < 0.01) return `$${val.toFixed(6)}`;
    return `$${val.toFixed(4)}`;
  };

  const formattedCost = `${isEstimated ? '~' : ''}${formatCost(displayCost)}`;

  const promptTokens = totals?.totalPromptTokens ?? currentUsage?.prompt_tokens ?? 0;
  const compTokens = totals?.totalCompletionTokens ?? currentUsage?.completion_tokens ?? 0;

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-300 ${className}`}
      title={`Prompt: ${promptTokens} | Completion: ${compTokens} | Source: ${costSource} | Status: ${
        isEstimated ? 'Estimated' : 'Provider-Reconciled'
      }`}
    >
      <div className="flex items-center gap-1 text-zinc-400">
        <Zap className="w-3.5 h-3.5 text-amber-400" />
        <span className="font-mono font-medium text-zinc-200">
          {displayTokens.toLocaleString()}
        </span>
        <span className="text-[10px] text-zinc-500">tok</span>
      </div>

      <div className="h-3 w-px bg-zinc-700/60" />

      <div className="flex items-center gap-1 text-zinc-400">
        <Coins className="w-3.5 h-3.5 text-emerald-400" />
        <span className="font-mono font-medium text-emerald-400">
          {formattedCost}
        </span>
      </div>

      {isEstimated && (
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
