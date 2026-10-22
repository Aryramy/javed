import React from 'react';
import { Coins, Zap } from 'lucide-react';
import type { ConversationTotals, StreamUsage } from '../../types/chat';

interface TokenCostMeterProps {
  currentUsage?: StreamUsage | null;
  totals?: ConversationTotals;
  className?: string;
}

export const TokenCostMeter: React.FC<TokenCostMeterProps> = ({
  currentUsage,
  totals,
  className = '',
}) => {
  const displayCost = totals?.totalCostUsd ?? currentUsage?.cost_usd ?? 0;
  const displayTokens = totals?.totalTokens ?? currentUsage?.total_tokens ?? 0;

  const formattedCost =
    displayCost < 0.01 && displayCost > 0
      ? `$${displayCost.toFixed(6)}`
      : `$${displayCost.toFixed(4)}`;

  return (
    <div
      className={`inline-flex items-center gap-2.5 px-2.5 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-xs text-zinc-300 ${className}`}
      title={`Prompt: ${totals?.totalPromptTokens ?? currentUsage?.prompt_tokens ?? 0} | Completion: ${
        totals?.totalCompletionTokens ?? currentUsage?.completion_tokens ?? 0
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
    </div>
  );
};
