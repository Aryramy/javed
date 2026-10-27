/**
 * TypeScript type definitions for chat completions, streaming, and model catalog.
 */

export type CostTier = 'low' | 'medium' | 'high' | 'xhigh' | 'max';
export const COST_TIERS: CostTier[] = ['low', 'medium', 'high', 'xhigh', 'max'];

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  reasoning?: string;
  session_id?: string;
  timestamp: string;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
  usage?: StreamUsage;
  ttftMs?: number;
  durationMs?: number;
  selected_model?: string;
  requested_model?: string;
  cost_tier?: CostTier;
}

export interface ModelInfo {
  id: string;
  name: string;
  provider: string;
  context_length: number;
  pricing_prompt: number;      // USD per 1M tokens
  pricing_completion: number;  // USD per 1M tokens
  description: string;
  is_default: boolean;
  is_favorite?: boolean;
  is_router?: boolean;
  cost_tier?: CostTier;
  supports_tools?: boolean;
  supported_parameters?: string[];
}

export interface ModelCatalogResponse {
  models: ModelInfo[];
  default_model: string;
  authenticated: boolean;
  quota_remaining_usd: number | null;
  daily_budget_usd: number | null;
  total_models?: number;
  is_dynamic?: boolean;
}

export interface StreamUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  upstream_cost: number | null;
  is_estimated?: boolean;
  cost_source?: 'upstream' | 'rate_card' | 'character_estimate';
  selected_model?: string;
  requested_model?: string;
  cost_tier?: CostTier;
  session_id?: string;
}

export interface ChatStreamEvent {
  type: 'token' | 'reasoning' | 'usage' | 'error' | 'done';
  content?: string;
  reasoning?: string;
  session_id?: string;
  usage?: StreamUsage;
  error?: string;
  selected_model?: string;
  requested_model?: string;
  cost_tier?: CostTier;
}

export interface ConversationTotals {
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  totalCostUsd: number;
  messageCount: number;
  isEstimated?: boolean;
}
