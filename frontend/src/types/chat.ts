/**
 * TypeScript type definitions for chat completions, streaming, and model catalog.
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  status?: 'sending' | 'streaming' | 'complete' | 'error';
  usage?: StreamUsage;
  ttftMs?: number;
  durationMs?: number;
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
}

export interface ModelCatalogResponse {
  models: ModelInfo[];
  default_model: string;
  authenticated: boolean;
  quota_remaining_usd: number | null;
  daily_budget_usd: number;
}

export interface StreamUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  upstream_cost: number | null;
}

export interface ChatStreamEvent {
  type: 'token' | 'usage' | 'error' | 'done';
  content?: string;
  usage?: StreamUsage;
  error?: string;
}

export interface ConversationTotals {
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  totalCostUsd: number;
  messageCount: number;
}
