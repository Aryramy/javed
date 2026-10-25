/**
 * TypeScript type definitions for Deep Agents & LangGraph runtime.
 */

import type { CostTier, StreamUsage } from './chat';

export type AgentTodoStatus = 'pending' | 'in_progress' | 'completed';

export interface AgentTodoItem {
  id: string;
  content: string;
  status: AgentTodoStatus;
}

export type AgentStreamEventType =
  | 'run_started'
  | 'planning'
  | 'plan_updated'
  | 'model_streaming'
  | 'checkpoint_saved'
  | 'run_completed'
  | 'run_cancelled'
  | 'run_failed';

export interface AgentStreamEvent {
  event: AgentStreamEventType;
  data: {
    run_id?: string;
    thread_id?: string;
    model?: string;
    cost_tier?: CostTier;
    session_id?: string;
    delta?: string;
    index?: number;
    todos?: AgentTodoItem[];
    content?: string;
    usage?: StreamUsage;
    elapsed_ms?: number;
    checkpoint_id?: string;
    error?: string;
    reason?: string;
    [key: string]: unknown;
  };
  timestamp: string;
}

export interface AgentThreadStateResponse {
  thread_id: string;
  messages: { role: 'user' | 'assistant' | 'system'; content: string }[];
  todos: AgentTodoItem[];
  checkpoint_id: string | null;
  exists: boolean;
}

export interface AgentRuntimeStatusResponse {
  status: string;
  checkpointer: string;
  checkpoint_db_path: string;
  security_profile: string;
  allowed_tools: string[];
  excluded_tools: string[];
}

export interface AgentRunTelemetry {
  runId?: string;
  threadId?: string;
  status?: 'idle' | 'running' | 'planning' | 'streaming' | 'completed' | 'cancelled' | 'failed';
  todos?: AgentTodoItem[];
  checkpointId?: string;
  model?: string;
  costTier?: CostTier;
  usage?: StreamUsage;
  elapsedMs?: number;
  lastEventTime?: string;
}
