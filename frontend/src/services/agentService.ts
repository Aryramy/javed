/**
 * Deep Agents & LangGraph runtime service for stateful agent streaming and thread state recovery.
 */

import type {
  AgentRuntimeStatusResponse,
  AgentStreamEvent,
  AgentThreadStateResponse,
  AgentTodoItem,
} from '../types/agent';
import type { CostTier, StreamUsage } from '../types/chat';

export interface StreamAgentParams {
  thread_id: string;
  message: string;
  model?: string;
  cost_tier?: CostTier;
  session_id?: string;
  signal?: AbortSignal;
  onRunStarted?: (data: { run_id: string; thread_id: string; model?: string; cost_tier?: CostTier }) => void;
  onPlanning?: (todos: AgentTodoItem[]) => void;
  onPlanUpdated?: (todos: AgentTodoItem[]) => void;
  onToken?: (token: string) => void;
  onCheckpointSaved?: (checkpointId: string) => void;
  onApprovalRequired?: (approval: import('../types/agent').ApprovalRecord) => void;
  onApprovalApproved?: (data: { approval_id: string; thread_id: string }) => void;
  onApprovalRejected?: (data: { approval_id: string; thread_id: string; reason?: string }) => void;
  onAgentResumed?: (data: { approval_id: string; thread_id: string; decision: string }) => void;
  onToolStarted?: (data: { tool: string; input: Record<string, unknown> }) => void;
  onToolCompleted?: (data: { tool: string; output: string }) => void;
  onRunCompleted?: (data: {
    run_id: string;
    content: string;
    todos: AgentTodoItem[];
    usage?: StreamUsage;
    elapsed_ms?: number;
  }) => void;
  onRunCancelled?: () => void;
  onRunFailed?: (error: string) => void;
}

export interface ResumeApprovalParams {
  approval_id: string;
  thread_id: string;
  decision: 'approve' | 'reject';
  reason?: string;
  signal?: AbortSignal;
  onToken?: (token: string) => void;
  onApprovalApproved?: (data: { approval_id: string; thread_id: string }) => void;
  onApprovalRejected?: (data: { approval_id: string; thread_id: string; reason?: string }) => void;
  onAgentResumed?: (data: { approval_id: string; thread_id: string; decision: string }) => void;
  onToolStarted?: (data: { tool: string; input: Record<string, unknown> }) => void;
  onToolCompleted?: (data: { tool: string; output: string }) => void;
  onRunCompleted?: (data: {
    run_id: string;
    content: string;
    todos: AgentTodoItem[];
    elapsed_ms?: number;
  }) => void;
  onRunCancelled?: () => void;
  onRunFailed?: (error: string) => void;
}

const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.location?.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }
  return 'http://localhost:5173';
};

export const agentService = {
  /**
   * Fetch active Deep Agents runtime diagnostic status and tool boundaries.
   */
  async getStatus(): Promise<AgentRuntimeStatusResponse> {
    const res = await fetch(`${getBaseUrl()}/api/v1/agent/status`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`Failed to query agent status (HTTP ${res.status}): ${await res.text()}`);
    }
    return (await res.json()) as AgentRuntimeStatusResponse;
  },

  /**
   * Retrieve saved messages, task plan, and checkpoint ID for a thread.
   */
  async getThreadState(threadId: string): Promise<AgentThreadStateResponse> {
    const res = await fetch(`${getBaseUrl()}/api/v1/agent/threads/${encodeURIComponent(threadId)}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      throw new Error(`Failed to retrieve thread state for ${threadId} (HTTP ${res.status}): ${await res.text()}`);
    }
    return (await res.json()) as AgentThreadStateResponse;
  },

  /**
   * Stream agent execution via Server-Sent Events (SSE).
   */
  async streamAgent(params: StreamAgentParams): Promise<void> {
    const {
      thread_id,
      message,
      model,
      cost_tier,
      session_id,
      signal,
      onRunStarted,
      onPlanning,
      onPlanUpdated,
      onToken,
      onCheckpointSaved,
      onApprovalRequired,
      onApprovalApproved,
      onApprovalRejected,
      onAgentResumed,
      onToolStarted,
      onToolCompleted,
      onRunCompleted,
      onRunCancelled,
      onRunFailed,
    } = params;

    const response = await fetch(`${getBaseUrl()}/api/v1/agent/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        thread_id,
        message,
        model,
        cost_tier,
        session_id,
      }),
      signal,
    });

    if (!response.ok) {
      let errorMsg = `Agent runtime error (HTTP ${response.status})`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMsg = errorJson.detail;
        } else if (errorJson.error?.message) {
          errorMsg = errorJson.error.message;
        }
      } catch {
        // Fallback
      }
      onRunFailed?.(errorMsg);
      throw new Error(errorMsg);
    }

    if (!response.body) {
      const err = 'Response body is not readable for agent streaming.';
      onRunFailed?.(err);
      throw new Error(err);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          const jsonStr = trimmed.slice(6).trim();
          if (jsonStr === '[DONE]') {
            return;
          }

          try {
            const event = JSON.parse(jsonStr) as AgentStreamEvent;
            switch (event.event) {
              case 'run_started':
                onRunStarted?.({
                  run_id: event.data.run_id ?? '',
                  thread_id: event.data.thread_id ?? thread_id,
                  model: event.data.model,
                  cost_tier: event.data.cost_tier,
                });
                break;

              case 'planning':
                if (event.data.todos) {
                  onPlanning?.(event.data.todos);
                }
                break;

              case 'plan_updated':
                if (event.data.todos) {
                  onPlanUpdated?.(event.data.todos);
                }
                break;

              case 'model_streaming':
                if (event.data.delta) {
                  onToken?.(event.data.delta);
                }
                break;

              case 'approval_required':
                if (event.data.approval_id) {
                  onApprovalRequired?.({
                    approval_id: event.data.approval_id,
                    interrupt_id: event.data.interrupt_id ?? '',
                    run_id: event.data.run_id ?? '',
                    thread_id: event.data.thread_id ?? thread_id,
                    server_id: event.data.server_id ?? '',
                    tool_id: event.data.tool_id ?? '',
                    tool_call_id: event.data.tool_call_id ?? '',
                    arguments: (event.data.arguments as Record<string, unknown>) ?? {},
                    argument_digest: event.data.argument_digest ?? '',
                    tool_fingerprint: event.data.tool_fingerprint ?? '',
                    policy_version: event.data.policy_version ?? 0,
                    created_at: (event.data.created_at as string) ?? new Date().toISOString(),
                    status: 'pending',
                    dispatch_status: 'not_dispatched',
                  });
                }
                break;

              case 'approval_approved':
                onApprovalApproved?.({
                  approval_id: event.data.approval_id ?? '',
                  thread_id: event.data.thread_id ?? thread_id,
                });
                break;

              case 'approval_rejected':
                onApprovalRejected?.({
                  approval_id: event.data.approval_id ?? '',
                  thread_id: event.data.thread_id ?? thread_id,
                  reason: event.data.reason,
                });
                break;

              case 'agent_resumed':
                onAgentResumed?.({
                  approval_id: event.data.approval_id ?? '',
                  thread_id: event.data.thread_id ?? thread_id,
                  decision: (event.data.decision as string) ?? '',
                });
                break;

              case 'tool_started':
                onToolStarted?.({
                  tool: event.data.tool ?? '',
                  input: (event.data.input as Record<string, unknown>) ?? {},
                });
                break;

              case 'tool_completed':
                onToolCompleted?.({
                  tool: event.data.tool ?? '',
                  output: event.data.output ?? '',
                });
                break;

              case 'checkpoint_saved':
                if (event.data.checkpoint_id) {
                  onCheckpointSaved?.(event.data.checkpoint_id);
                }
                break;

              case 'run_completed':
                onRunCompleted?.({
                  run_id: event.data.run_id ?? '',
                  content: event.data.content ?? '',
                  todos: event.data.todos ?? [],
                  usage: event.data.usage,
                  elapsed_ms: event.data.elapsed_ms,
                });
                break;

              case 'run_cancelled':
                onRunCancelled?.();
                break;

              case 'run_failed':
                onRunFailed?.(event.data.error ?? 'Unknown agent failure');
                break;
            }
          } catch {
            // Non-JSON or fragmented line
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        onRunCancelled?.();
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      onRunFailed?.(msg);
      throw err;
    } finally {
      reader.releaseLock();
    }
  },

  /**
   * List pending tool call approvals, optionally filtered by thread.
   */
  async listPendingApprovals(threadId?: string): Promise<import('../types/agent').ApprovalRecord[]> {
    const url = threadId
      ? `${getBaseUrl()}/api/v1/agent/approvals/pending?thread_id=${encodeURIComponent(threadId)}`
      : `${getBaseUrl()}/api/v1/agent/approvals/pending`;
    const res = await fetch(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`Failed to list approvals: ${await res.text()}`);
    const data = await res.json();
    return data.approvals || [];
  },

  /**
   * Retrieve details for a specific approval record.
   */
  async getApproval(approvalId: string): Promise<import('../types/agent').ApprovalRecord> {
    const res = await fetch(`${getBaseUrl()}/api/v1/agent/approvals/${encodeURIComponent(approvalId)}`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) throw new Error(`Failed to fetch approval: ${await res.text()}`);
    const data = await res.json();
    return data.approval;
  },

  /**
   * Record human decision without resuming the stream.
   */
  async submitDecision(
    approvalId: string,
    decision: 'approve' | 'reject',
    threadId: string,
    reason?: string
  ): Promise<import('../types/agent').ApprovalRecord> {
    const res = await fetch(
      `${getBaseUrl()}/api/v1/agent/approvals/${encodeURIComponent(approvalId)}/decision`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ decision, thread_id: threadId, reason }),
      }
    );
    if (!res.ok) throw new Error(`Decision submission failed (HTTP ${res.status}): ${await res.text()}`);
    const data = await res.json();
    return data.approval;
  },

  /**
   * Cancel a pending approval invocation.
   */
  async cancelApproval(
    approvalId: string,
    threadId: string
  ): Promise<import('../types/agent').ApprovalRecord> {
    const res = await fetch(
      `${getBaseUrl()}/api/v1/agent/approvals/${encodeURIComponent(approvalId)}/cancel`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ thread_id: threadId }),
      }
    );
    if (!res.ok) throw new Error(`Approval cancellation failed: ${await res.text()}`);
    const data = await res.json();
    return data.approval;
  },

  /**
   * Submit decision and stream resumed agent execution over SSE.
   */
  async resumeApprovalStream(params: ResumeApprovalParams): Promise<void> {
    const {
      approval_id,
      thread_id,
      decision,
      reason,
      signal,
      onToken,
      onApprovalApproved,
      onApprovalRejected,
      onAgentResumed,
      onToolStarted,
      onToolCompleted,
      onRunCompleted,
      onRunCancelled,
      onRunFailed,
    } = params;

    const response = await fetch(
      `${getBaseUrl()}/api/v1/agent/approvals/${encodeURIComponent(approval_id)}/resume`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({
          decision,
          thread_id,
          reason,
        }),
        signal,
      }
    );

    if (!response.ok) {
      let errorMsg = `Approval resumption error (HTTP ${response.status})`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMsg = errorJson.detail;
        }
      } catch {
        // Fallback
      }
      onRunFailed?.(errorMsg);
      throw new Error(errorMsg);
    }

    if (!response.body) {
      const err = 'Response body is not readable for resumption stream.';
      onRunFailed?.(err);
      throw new Error(err);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed || !trimmed.startsWith('data: ')) continue;

          const jsonStr = trimmed.slice(6).trim();
          if (jsonStr === '[DONE]') {
            return;
          }

          try {
            const event = JSON.parse(jsonStr) as AgentStreamEvent;
            switch (event.event) {
              case 'approval_approved':
                onApprovalApproved?.({
                  approval_id: event.data.approval_id ?? approval_id,
                  thread_id: event.data.thread_id ?? thread_id,
                });
                break;

              case 'approval_rejected':
                onApprovalRejected?.({
                  approval_id: event.data.approval_id ?? approval_id,
                  thread_id: event.data.thread_id ?? thread_id,
                  reason: event.data.reason,
                });
                break;

              case 'agent_resumed':
                onAgentResumed?.({
                  approval_id: event.data.approval_id ?? approval_id,
                  thread_id: event.data.thread_id ?? thread_id,
                  decision: (event.data.decision as string) ?? decision,
                });
                break;

              case 'tool_started':
                onToolStarted?.({
                  tool: event.data.tool ?? '',
                  input: (event.data.input as Record<string, unknown>) ?? {},
                });
                break;

              case 'tool_completed':
                onToolCompleted?.({
                  tool: event.data.tool ?? '',
                  output: event.data.output ?? '',
                });
                break;

              case 'model_streaming':
                if (event.data.delta) {
                  onToken?.(event.data.delta);
                }
                break;

              case 'run_completed':
                onRunCompleted?.({
                  run_id: event.data.run_id ?? '',
                  content: event.data.content ?? '',
                  todos: event.data.todos ?? [],
                  elapsed_ms: event.data.elapsed_ms,
                });
                break;

              case 'run_cancelled':
                onRunCancelled?.();
                break;

              case 'run_failed':
                onRunFailed?.(event.data.error ?? 'Unknown resumption failure');
                break;
            }
          } catch {
            // Non-JSON or fragmented line
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        onRunCancelled?.();
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      onRunFailed?.(msg);
      throw err;
    } finally {
      reader.releaseLock();
    }
  },
};
