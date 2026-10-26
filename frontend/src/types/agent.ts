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
  | 'approval_required'
  | 'approval_approved'
  | 'approval_rejected'
  | 'approval_cancelled'
  | 'agent_resumed'
  | 'tool_started'
  | 'tool_completed'
  | 'tool_failed'
  | 'run_completed'
  | 'run_cancelled'
  | 'run_failed';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled' | 'expired';
export type DispatchStatus = 'not_dispatched' | 'in_flight' | 'completed' | 'failed' | 'uncertain';

export interface ApprovalRecord {
  approval_id: string;
  interrupt_id: string;
  run_id: string;
  thread_id: string;
  server_id: string;
  tool_id: string;
  tool_call_id: string;
  arguments: Record<string, unknown>;
  argument_digest: string;
  tool_fingerprint: string;
  policy_version: number;
  created_at: string;
  expires_at?: string | null;
  status: ApprovalStatus;
  decision_at?: string | null;
  decision_by?: string | null;
  rejection_reason?: string | null;
  dispatch_status: DispatchStatus;
  dispatched_at?: string | null;
  completed_at?: string | null;
  result_summary?: string | null;
  error_message?: string | null;
}

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
    approval_id?: string;
    interrupt_id?: string;
    server_id?: string;
    tool_id?: string;
    tool_call_id?: string;
    arguments?: Record<string, unknown>;
    argument_digest?: string;
    tool_fingerprint?: string;
    policy_version?: number;
    status?: ApprovalStatus;
    tool?: string;
    input?: Record<string, unknown>;
    output?: string;
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
