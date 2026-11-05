/**
 * TypeScript type definitions for chat completions, streaming, and model catalog.
 */

export type CostTier = 'low' | 'medium' | 'high' | 'xhigh' | 'max';
export const COST_TIERS: CostTier[] = ['low', 'medium', 'high', 'xhigh', 'max'];

export type ProviderId = 'auto' | 'openrouter' | 'cheaper_inference';

export type ProviderHealthState =
  | 'available'
  | 'degraded'
  | 'unavailable'
  | 'not_configured'
  | 'model_unavailable'
  | 'capability_mismatch';

export interface ProviderCapabilities {
  chat: boolean;
  agent: boolean;
  transcription?: boolean;
  translation?: boolean;
  speech?: boolean;
  realtime_voice?: boolean;
  live_voice?: boolean;
}

export interface ProviderInfo {
  id: ProviderId;
  display_name: string;
  configured: boolean;
  health: ProviderHealthState;
  chat_model: string | null;
  capabilities: ProviderCapabilities;
  safe_failure_code?: string | null;
}

export interface ProvidersResponse {
  default_provider: ProviderId;
  selection_enabled: boolean;
  providers: ProviderInfo[];
}

export interface ProviderSelectionRequest {
  provider_id: ProviderId;
  cost_tier?: CostTier;
  interaction_mode?: 'chat' | 'agent';
  current_thread_id?: string | null;
  create_new_thread?: boolean;
}

export interface ProviderBindingResponse {
  thread_id: string;
  provider_id: ProviderId;
  provider_mode: 'explicit' | 'auto';
  effective_model_id: string;
  configuration_version: string;
  display_name: string;
  capabilities: ProviderCapabilities;
}

export interface ChatRequest {
  messages: Array<{ role: string; content: string }>;
  model?: string;
  cost_tier?: CostTier;
  session_id?: string;
  stream?: boolean;
  provider_id?: ProviderId;
  thread_id?: string;
  configuration_version?: string;
}

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
  provider_id?: ProviderId;
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
  provider_id?: ProviderId;
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
  provider_id?: ProviderId;
}

export interface ConversationTotals {
  totalPromptTokens: number;
  totalCompletionTokens: number;
  totalTokens: number;
  totalCostUsd: number;
  messageCount: number;
  isEstimated?: boolean;
}
