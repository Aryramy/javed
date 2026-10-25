import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send,
  Square,
  Trash2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  Server,
  Wifi,
  WifiOff,
  Route,
  RefreshCw,
  Workflow,
} from 'lucide-react';
import { ModelSelector } from '../../components/chat/ModelSelector';
import { TokenCostMeter } from '../../components/chat/TokenCostMeter';
import { MarkdownContent } from '../../components/chat/MarkdownContent';
import { TaskPlanPanel } from '../../components/chat/TaskPlanPanel';
import { chatService } from '../../services/chatService';
import { agentService } from '../../services/agentService';
import { useBackend, useMode } from '../../context';
import { cn } from '../../lib/utils';
import { AssistantRuntimeProvider, useExternalStoreRuntime } from '@assistant-ui/react';
import type {
  ChatMessage,
  ConversationTotals,
  CostTier,
  ModelCatalogResponse,
  ModelInfo,
  StreamUsage,
} from '../../types/chat';
import type { AgentRunTelemetry, AgentTodoItem } from '../../types/agent';

const DEFAULT_MODELS: ModelInfo[] = [
  {
    id: 'openrouter/auto',
    name: 'OpenRouter Auto Router',
    provider: 'OpenRouter',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Dynamic auto-router with cost tiers (low, medium, high, xhigh, max).',
    is_default: true,
    is_favorite: true,
    is_router: true,
    cost_tier: 'low',
  },
  {
    id: 'openai/gpt-4o-mini',
    name: 'OpenAI GPT-4o Mini',
    provider: 'OpenAI',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Fast, economical frontier model ideal for daily tasks.',
    is_default: false,
    is_favorite: true,
  },
  {
    id: 'openai/gpt-4o',
    name: 'OpenAI GPT-4o',
    provider: 'OpenAI',
    context_length: 128000,
    pricing_prompt: 2.50,
    pricing_completion: 10.00,
    description: 'Flagship multimodal intelligence for high-complexity analysis.',
    is_default: false,
    is_favorite: true,
  },
  {
    id: 'anthropic/claude-sonnet-4.5',
    name: 'Claude Sonnet 4.5',
    provider: 'Anthropic',
    context_length: 200000,
    pricing_prompt: 3.00,
    pricing_completion: 15.00,
    description: 'Deep reasoning, nuanced code architecture, and high-fidelity output.',
    is_default: false,
    is_favorite: true,
  },
  {
    id: 'google/gemini-2.5-flash',
    name: 'Gemini 2.5 Flash',
    provider: 'Google',
    context_length: 1048576,
    pricing_prompt: 0.30,
    pricing_completion: 2.50,
    description: 'High-velocity inference with massive 1M token context window.',
    is_default: false,
    is_favorite: true,
  },
  {
    id: 'deepseek/deepseek-chat',
    name: 'DeepSeek Chat V3',
    provider: 'DeepSeek',
    context_length: 64000,
    pricing_prompt: 0.26,
    pricing_completion: 1.03,
    description: 'High-efficiency open-weights architecture with strong reasoning.',
    is_default: false,
    is_favorite: true,
  },
];

const CHAT_SUGGESTIONS = [
  'Explain quantum entanglement in simple terms',
  'Write an async Python client using httpx with exponential retry',
  'Compare Redis with SQLite in-memory for sub-millisecond caching',
  'Summarize the core architectural rules of Project Javed',
];

const AGENT_SUGGESTIONS = [
  'Explain what a Power BI measure is in two sentences.',
  'Create a five-step implementation plan for a Power BI project using SharePoint data, including validation checkpoints.',
  'For this conversation, remember that our sample project is called Project Orchid.',
  'Delete a file from my Desktop.',
];

let msgCounter = 0;
function generateMessageId(role: string): string {
  msgCounter += 1;
  return `${role}-${msgCounter}`;
}

export const ChatView: React.FC = () => {
  const { status, latencyMs, systemStatus } = useBackend();
  const { mode } = useMode();
  const isConnected = status === 'connected';

  // Interaction Mode: Chat Mode vs Agent Mode
  const [interactionMode, setInteractionMode] = useState<'chat' | 'agent'>(() => {
    if (typeof window !== 'undefined') {
      return (localStorage.getItem('javed_interaction_mode') as 'chat' | 'agent') || 'chat';
    }
    return 'chat';
  });

  // Stateful Agent Thread ID & Checkpoints
  const [threadId, setThreadId] = useState<string>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('javed_active_thread_id');
      if (saved) return saved;
    }
    return `thread-${crypto.randomUUID().slice(0, 8)}`;
  });
  const [agentTodos, setAgentTodos] = useState<AgentTodoItem[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<
    'idle' | 'running' | 'planning' | 'streaming' | 'completed' | 'cancelled' | 'error'
  >('idle');
  const [checkpointId, setCheckpointId] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [models, setModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [selectedModelId, setSelectedModelId] = useState<string>('openrouter/auto');
  const [costTier, setCostTier] = useState<CostTier>('low');
  const [sessionId, setSessionId] = useState<string>(() => `session-${crypto.randomUUID()}`);
  const [catalogMeta, setCatalogMeta] = useState<ModelCatalogResponse | null>(null);
  const [input, setInput] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [showReasoning, setShowReasoning] = useState<boolean>(false);
  const [currentUsage, setCurrentUsage] = useState<StreamUsage | null>(null);
  const [totals, setTotals] = useState<ConversationTotals>({
    totalPromptTokens: 0,
    totalCompletionTokens: 0,
    totalTokens: 0,
    totalCostUsd: 0,
    messageCount: 0,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom of conversation
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView?.({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming, agentTodos]);

  // Load models catalog on mount
  useEffect(() => {
    async function loadCatalog() {
      try {
        const catalog = await chatService.getModels();
        setCatalogMeta(catalog);
        if (catalog.models && catalog.models.length > 0) {
          setModels(catalog.models);
        }
        if (catalog.default_model) {
          setSelectedModelId(catalog.default_model);
        }
      } catch (e) {
        console.warn('Using default models list; catalog endpoint not ready:', e);
      }
    }
    loadCatalog();
  }, []);

  // Save interaction mode & thread ID to localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('javed_interaction_mode', interactionMode);
      localStorage.setItem('javed_active_thread_id', threadId);
    }
  }, [interactionMode, threadId]);

  // Restore thread state when in Agent Mode
  const restoreThreadState = useCallback(async (targetThreadId: string) => {
    try {
      const state = await agentService.getThreadState(targetThreadId);
      if (state.exists) {
        if (state.messages && state.messages.length > 0) {
          setMessages(
            state.messages.map((m, idx) => ({
              id: `thread-${idx}-${m.role}`,
              role: m.role,
              content: m.content,
              timestamp: new Date().toISOString(),
              status: 'complete' as const,
            }))
          );
        }
        if (state.todos) {
          setAgentTodos(state.todos);
        }
        if (state.checkpoint_id) {
          setCheckpointId(state.checkpoint_id);
        }
      }
    } catch (e) {
      console.warn('Could not restore thread state for', targetThreadId, e);
    }
  }, []);

  useEffect(() => {
    if (interactionMode === 'agent') {
      restoreThreadState(threadId);
    }
  }, [interactionMode, threadId, restoreThreadState]);

  const handleModeChange = (newMode: 'chat' | 'agent') => {
    if (newMode === interactionMode) return;
    if (isStreaming) {
      handleStop();
    }
    setInteractionMode(newMode);
    if (newMode === 'agent') {
      restoreThreadState(threadId);
    } else {
      setAgentTodos([]);
      setAgentStatus('idle');
    }
  };

  const handleNewThread = () => {
    if (isStreaming) {
      handleStop();
    }
    const newId = `thread-${crypto.randomUUID().slice(0, 8)}`;
    setThreadId(newId);
    setMessages([]);
    setAgentTodos([]);
    setActiveRunId(null);
    setCheckpointId(null);
    setAgentStatus('idle');
    setCurrentUsage(null);
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);
      setAgentStatus('cancelled');

      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant' && last.status === 'streaming') {
          const estCompTokens = Math.max(1, Math.round(last.content.length / 4));
          const userMsg = prev[prev.length - 2];
          const estPromptTokens = Math.max(1, Math.round((userMsg?.content?.length ?? 10) / 4));
          const cancelledUsage: StreamUsage = {
            prompt_tokens: estPromptTokens,
            completion_tokens: estCompTokens,
            total_tokens: estPromptTokens + estCompTokens,
            cost_usd: Number(((estPromptTokens * 0.15 + estCompTokens * 0.6) / 1_000_000).toFixed(8)),
            upstream_cost: null,
            is_estimated: true,
            cost_source: 'character_estimate',
          };
          setCurrentUsage(cancelledUsage);
          setTotals((t) => ({
            ...t,
            totalPromptTokens: t.totalPromptTokens + estPromptTokens,
            totalCompletionTokens: t.totalCompletionTokens + estCompTokens,
            totalTokens: t.totalTokens + estPromptTokens + estCompTokens,
            totalCostUsd: Number((t.totalCostUsd + cancelledUsage.cost_usd).toFixed(8)),
            isEstimated: true,
          }));
          return [
            ...prev.slice(0, -1),
            { ...last, status: 'complete' as const, usage: cancelledUsage },
          ];
        }
        return prev;
      });
    }
  };

  const handleClear = () => {
    if (isStreaming) {
      handleStop();
    }
    setMessages([]);
    setAgentTodos([]);
    setActiveRunId(null);
    setCheckpointId(null);
    setAgentStatus('idle');
    setCurrentUsage(null);
    setSessionId(`session-${crypto.randomUUID()}`);
    setTotals({
      totalPromptTokens: 0,
      totalCompletionTokens: 0,
      totalTokens: 0,
      totalCostUsd: 0,
      messageCount: 0,
    });
  };

  const handleSubmit = useCallback(
    async (textToSend?: string) => {
      const promptText = (textToSend ?? input).trim();
      if (!promptText || isStreaming) return;

      setInput('');

      const userMessageId = generateMessageId('user');
      const assistantMessageId = generateMessageId('assistant');
      const startTime = performance.now();
      let ttftRecorded: number | null = null;
      const nowIso = new Date().toISOString();

      const userMessage: ChatMessage = {
        id: userMessageId,
        role: 'user',
        content: promptText,
        session_id: sessionId,
        timestamp: nowIso,
        status: 'complete',
      };

      const initialAssistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        session_id: sessionId,
        timestamp: nowIso,
        status: 'streaming',
      };

      const newMessages = [...messages, userMessage];
      setMessages([...newMessages, initialAssistantMessage]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      // ==========================================
      // AGENT MODE EXECUTION (BRICK-004)
      // ==========================================
      if (interactionMode === 'agent') {
        setAgentStatus('running');
        try {
          await agentService.streamAgent({
            thread_id: threadId,
            message: promptText,
            model: selectedModelId,
            cost_tier: selectedModelId === 'openrouter/auto' ? costTier : undefined,
            session_id: sessionId,
            signal: controller.signal,
            onRunStarted: (data) => {
              setActiveRunId(data.run_id);
              setAgentStatus('running');
            },
            onPlanning: (todos) => {
              setAgentTodos(todos);
              setAgentStatus('planning');
            },
            onPlanUpdated: (todos) => {
              setAgentTodos(todos);
            },
            onToken: (token) => {
              setAgentStatus('streaming');
              if (ttftRecorded === null) {
                ttftRecorded = Math.round(performance.now() - startTime);
              }
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === assistantMessageId);
                if (index === -1) return prev;
                const target = prev[index];
                const updated = {
                  ...target,
                  content: target.content + token,
                  ttftMs: ttftRecorded ?? target.ttftMs,
                };
                return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
              });
            },
            onCheckpointSaved: (cpId) => {
              setCheckpointId(cpId);
            },
            onRunCompleted: (data) => {
              const duration = Math.round(performance.now() - startTime);
              setAgentStatus('completed');
              if (data.todos && data.todos.length > 0) {
                setAgentTodos(data.todos);
              }
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === assistantMessageId);
                if (index === -1) return prev;
                const updated = {
                  ...prev[index],
                  content: prev[index].content || data.content,
                  status: 'complete' as const,
                  usage: data.usage,
                  durationMs: duration,
                };
                return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
              });

              if (data.usage) {
                setCurrentUsage(data.usage);
                setTotals((prev) => ({
                  totalPromptTokens: prev.totalPromptTokens + data.usage!.prompt_tokens,
                  totalCompletionTokens: prev.totalCompletionTokens + data.usage!.completion_tokens,
                  totalTokens: prev.totalTokens + data.usage!.total_tokens,
                  totalCostUsd: Number((prev.totalCostUsd + data.usage!.cost_usd).toFixed(6)),
                  messageCount: prev.messageCount + 1,
                }));
              }

              // Store live telemetry for Developer Mode inspection
              try {
                const telemetry: AgentRunTelemetry = {
                  runId: data.run_id,
                  threadId,
                  status: 'completed',
                  todos: data.todos,
                  checkpointId: checkpointId || undefined,
                  model: selectedModelId,
                  costTier,
                  usage: data.usage,
                  elapsedMs: data.elapsed_ms || duration,
                  lastEventTime: new Date().toISOString(),
                };
                localStorage.setItem('javed_agent_telemetry', JSON.stringify(telemetry));
              } catch {
                // ignore
              }

              setIsStreaming(false);
              abortControllerRef.current = null;
            },
            onRunCancelled: () => {
              setAgentStatus('cancelled');
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === assistantMessageId);
                if (index === -1) return prev;
                return [
                  ...prev.slice(0, index),
                  { ...prev[index], status: 'complete' as const },
                  ...prev.slice(index + 1),
                ];
              });
              setIsStreaming(false);
              abortControllerRef.current = null;
            },
            onRunFailed: (errText) => {
              setAgentStatus('error');
              setMessages((prev) => {
                const index = prev.findIndex((m) => m.id === assistantMessageId);
                if (index === -1) return prev;
                return [
                  ...prev.slice(0, index),
                  {
                    ...prev[index],
                    status: 'error' as const,
                    content: prev[index].content || `Agent execution error: ${errText}`,
                  },
                  ...prev.slice(index + 1),
                ];
              });
              setIsStreaming(false);
              abortControllerRef.current = null;
            },
          });
        } catch {
          setIsStreaming(false);
          abortControllerRef.current = null;
        }
        return;
      }

      // ==========================================
      // CHAT MODE EXECUTION (BRICK-003 Baseline)
      // ==========================================
      const historyPayload = newMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        await chatService.streamChat({
          messages: historyPayload,
          model: selectedModelId,
          cost_tier: selectedModelId === 'openrouter/auto' ? costTier : undefined,
          session_id: sessionId,
          signal: controller.signal,
          onToken: (token: string) => {
            if (ttftRecorded === null) {
              ttftRecorded = Math.round(performance.now() - startTime);
            }
            setMessages((prev) => {
              const index = prev.findIndex((m) => m.id === assistantMessageId);
              if (index === -1) return prev;
              const target = prev[index];
              const updated = {
                ...target,
                content: target.content + token,
                ttftMs: ttftRecorded ?? target.ttftMs,
              };
              return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
            });
          },
          onReasoning: (reasoningChunk: string) => {
            setMessages((prev) => {
              const index = prev.findIndex((m) => m.id === assistantMessageId);
              if (index === -1) return prev;
              const target = prev[index];
              const updated = {
                ...target,
                reasoning: (target.reasoning || '') + reasoningChunk,
              };
              return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
            });
          },
          onUsage: (usage: StreamUsage) => {
            setCurrentUsage(usage);
            const duration = Math.round(performance.now() - startTime);

            setMessages((prev) => {
              const index = prev.findIndex((m) => m.id === assistantMessageId);
              if (index === -1) return prev;
              const updated = {
                ...prev[index],
                usage,
                durationMs: duration,
                selected_model: usage.selected_model,
                requested_model: usage.requested_model,
                cost_tier: usage.cost_tier,
              };
              return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
            });

            setTotals((prev) => ({
              totalPromptTokens: prev.totalPromptTokens + usage.prompt_tokens,
              totalCompletionTokens: prev.totalCompletionTokens + usage.completion_tokens,
              totalTokens: prev.totalTokens + usage.total_tokens,
              totalCostUsd: Number((prev.totalCostUsd + usage.cost_usd).toFixed(6)),
              messageCount: prev.messageCount + 1,
            }));
          },
          onError: (errorText: string) => {
            setMessages((prev) => {
              const index = prev.findIndex((m) => m.id === assistantMessageId);
              if (index === -1) return prev;
              const updated = {
                ...prev[index],
                status: 'error' as const,
                content: prev[index].content || `Error: ${errorText}`,
              };
              return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
            });
            setIsStreaming(false);
          },
          onDone: () => {
            setMessages((prev) => {
              const index = prev.findIndex((m) => m.id === assistantMessageId);
              if (index === -1) return prev;
              const updated = {
                ...prev[index],
                status: 'complete' as const,
                durationMs: Math.round(performance.now() - startTime),
              };
              return [...prev.slice(0, index), updated, ...prev.slice(index + 1)];
            });
            setIsStreaming(false);
            abortControllerRef.current = null;
          },
        });
      } catch {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [input, isStreaming, messages, selectedModelId, costTier, sessionId, interactionMode, threadId, checkpointId]
  );

  const runtime = useExternalStoreRuntime({
    messages,
    isRunning: isStreaming,
    onNew: async (msg) => {
      const content =
        typeof msg.content === 'string'
          ? msg.content
          : Array.isArray(msg.content)
            ? msg.content.map((c: any) => ('text' in c ? c.text : '')).join('')
            : '';
      if (content) {
        await handleSubmit(content);
      }
    },
    onCancel: async () => {
      handleStop();
    },
    convertMessage: (msg: ChatMessage) => ({
      id: msg.id,
      role: msg.role,
      content: msg.content,
      createdAt: new Date(msg.timestamp),
    }),
  });

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const suggestions = interactionMode === 'agent' ? AGENT_SUGGESTIONS : CHAT_SUGGESTIONS;

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="space-y-3">
        {/* Real Backend Status Banner */}
        <div
          className={cn(
            'p-3 rounded-xl border text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-sm font-mono',
            isConnected
              ? 'bg-card border-border text-foreground'
              : 'bg-rose-500/10 border-rose-500/20 text-rose-600 dark:text-rose-400'
          )}
        >
          <div className="flex items-center gap-2">
            {isConnected ? (
              <Wifi className="w-4 h-4 text-emerald-500 shrink-0" />
            ) : (
              <WifiOff className="w-4 h-4 text-rose-500 shrink-0" />
            )}
            <span>
              {isConnected ? (
                <>
                  <strong className="text-emerald-500">BACKEND CONNECTED:</strong>{' '}
                  {systemStatus ? `Javed v${systemStatus.backend_version}` : '127.0.0.1:8000'}
                  {latencyMs !== null && (
                    <span className="text-muted-foreground ml-2">({latencyMs}ms RTT)</span>
                  )}
                </>
              ) : (
                <>
                  <strong>BACKEND DISCONNECTED:</strong> Local FastAPI server is unreachable.
                </>
              )}
            </span>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Server className="w-3.5 h-3.5 text-primary" />
            <span>
              {interactionMode === 'agent'
                ? 'Stage 1 Transport Verified • Deep Agents Runtime Active (BRICK-004)'
                : 'Stage 1 Transport Verified • AI Gateway Active (BRICK-003)'}
            </span>
          </div>
        </div>

        <div className="flex flex-col h-[calc(100vh-190px)] max-h-[1000px] rounded-xl border border-zinc-800 bg-zinc-950/70 backdrop-blur-xl shadow-2xl overflow-hidden">
          {/* Header Toolbar */}
          <div className="flex flex-wrap items-center justify-between px-4 py-2.5 border-b border-zinc-800/80 bg-zinc-900/60 text-xs gap-2">
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              {/* Interaction Mode Toggle */}
              <div
                className="flex items-center p-0.5 rounded-lg bg-zinc-900 border border-zinc-800 text-xs font-medium"
                role="radiogroup"
                aria-label="Runtime interaction mode"
              >
                <button
                  type="button"
                  id="mode-toggle-chat"
                  data-testid="mode-toggle-chat"
                  onClick={() => handleModeChange('chat')}
                  className={cn(
                    'px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5',
                    interactionMode === 'chat'
                      ? 'bg-zinc-800 text-zinc-100 shadow-sm font-semibold'
                      : 'text-zinc-400 hover:text-zinc-200'
                  )}
                >
                  <Bot className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Chat Mode</span>
                </button>
                <button
                  type="button"
                  id="mode-toggle-agent"
                  data-testid="mode-toggle-agent"
                  onClick={() => handleModeChange('agent')}
                  className={cn(
                    'px-2.5 py-1 rounded-md transition-all flex items-center gap-1.5',
                    interactionMode === 'agent'
                      ? 'bg-blue-600/30 text-blue-300 border border-blue-500/40 shadow-sm font-semibold'
                      : 'text-zinc-400 hover:text-zinc-200'
                  )}
                >
                  <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                  <span>Agent Mode</span>
                </button>
              </div>

              {/* Agent Mode Status Badge */}
              {interactionMode === 'agent' && (
                <div
                  id="agent-status-badge"
                  data-testid="agent-status-badge"
                  className={cn(
                    'flex items-center gap-1.5 px-2.5 py-1 rounded-lg border font-mono text-[11px] transition-colors',
                    agentStatus === 'planning' && 'bg-amber-500/10 border-amber-500/30 text-amber-300',
                    agentStatus === 'streaming' && 'bg-blue-500/10 border-blue-500/30 text-blue-300',
                    agentStatus === 'completed' && 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300',
                    agentStatus === 'error' && 'bg-rose-500/10 border-rose-500/30 text-rose-300',
                    agentStatus === 'cancelled' && 'bg-zinc-800 border-zinc-700 text-zinc-400',
                    agentStatus === 'idle' && 'bg-zinc-900 border-zinc-800 text-zinc-400'
                  )}
                >
                  <Workflow className="w-3 h-3 text-blue-400" />
                  <span className="font-semibold uppercase tracking-wider">
                    {agentStatus === 'idle'
                      ? 'Ready'
                      : agentStatus}
                  </span>
                </div>
              )}

              <ModelSelector
                models={models}
                selectedModelId={selectedModelId}
                onSelectModel={setSelectedModelId}
                costTier={costTier}
                onSelectCostTier={setCostTier}
                disabled={isStreaming}
              />
              <TokenCostMeter currentUsage={currentUsage} totals={totals} isStreaming={isStreaming} />
            </div>

            <div className="flex items-center gap-2">
              {interactionMode === 'agent' && (
                <button
                  type="button"
                  id="new-thread-button"
                  data-testid="new-thread-button"
                  onClick={handleNewThread}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-blue-500/30 bg-blue-950/30 hover:bg-blue-900/40 text-blue-300 transition-colors shadow-sm text-xs font-medium"
                  title="Start a new agent conversation thread (clears thread state)"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">New Thread</span>
                </button>
              )}

              {catalogMeta?.quota_remaining_usd !== null && catalogMeta?.quota_remaining_usd !== undefined && (
                <div
                  className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-900/80 border border-zinc-800 text-zinc-400 font-mono text-[11px]"
                  title="OpenRouter account credit limit remaining"
                >
                  <span className="text-zinc-500">Balance:</span>
                  <span className="text-emerald-400 font-semibold">${catalogMeta.quota_remaining_usd.toFixed(2)}</span>
                </div>
              )}

              <button
                type="button"
                id="clear-chat-button"
                onClick={handleClear}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-zinc-800 bg-zinc-900/80 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 transition-colors shadow-sm"
                title="Clear conversation messages"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Clear</span>
              </button>
            </div>
          </div>

          {/* Message Thread Viewport */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Real Task Plan Panel when todos exist in Agent Mode */}
            {interactionMode === 'agent' && agentTodos.length > 0 && (
              <TaskPlanPanel
                todos={agentTodos}
                activeRunId={activeRunId ?? undefined}
                isStreaming={isStreaming}
              />
            )}

            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center py-12">
                <div
                  className={cn(
                    'w-12 h-12 rounded-2xl flex items-center justify-center mb-4 shadow-lg',
                    interactionMode === 'agent'
                      ? 'bg-blue-500/10 border border-blue-500/30 text-blue-400 shadow-blue-500/10'
                      : 'bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-cyan-500/10'
                  )}
                >
                  {interactionMode === 'agent' ? (
                    <Workflow className="w-6 h-6" />
                  ) : (
                    <Bot className="w-6 h-6" />
                  )}
                </div>
                <h2 className="text-lg font-semibold text-zinc-100 tracking-tight mb-1">
                  {interactionMode === 'agent'
                    ? 'Stateful Agent Runtime'
                    : 'Conversational AI Gateway'}
                </h2>
                <p className="text-xs text-zinc-400 mb-2 leading-relaxed">
                  {interactionMode === 'agent'
                    ? 'Stateful planning and reasoning powered by Deep Agents and LangGraph SQLite persistence.'
                    : 'Interactive streaming chat powered by Deep Agents and OpenRouter LLM inference.'}
                </p>
                <div
                  className={cn(
                    'mb-6 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-mono',
                    interactionMode === 'agent'
                      ? 'bg-blue-500/10 border border-blue-500/30 text-blue-300'
                      : 'bg-cyan-500/10 border border-cyan-500/20 text-cyan-400'
                  )}
                >
                  <Sparkles className="w-3 h-3" />
                  <span>
                    {interactionMode === 'agent'
                      ? 'BRICK-004: Deep Agents + LangGraph Runtime (ACTIVE)'
                      : 'BRICK-003: OpenRouter Integration & Streaming Chat (ACTIVE)'}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
                  {suggestions.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => handleSubmit(suggestion)}
                      className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-900 hover:border-blue-500/40 transition-all text-xs text-zinc-300 hover:text-blue-200 group flex items-start gap-2"
                    >
                      <Sparkles className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform" />
                      <span className="line-clamp-2">{suggestion}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((message) => {
                const isUser = message.role === 'user';
                return (
                  <div
                    key={message.id}
                    className={`flex gap-3 text-sm ${isUser ? 'justify-end' : 'justify-start'}`}
                  >
                    {!isUser && (
                      <div
                        className={cn(
                          'w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5 border',
                          interactionMode === 'agent'
                            ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                            : 'bg-cyan-500/15 border-cyan-500/30 text-cyan-400'
                        )}
                      >
                        {interactionMode === 'agent' ? (
                          <Workflow className="w-4 h-4" />
                        ) : (
                          <Bot className="w-4 h-4" />
                        )}
                      </div>
                    )}

                    <div
                      className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-4 py-3 shadow-md ${
                        isUser
                          ? 'bg-cyan-600/90 text-white rounded-tr-none'
                          : 'bg-zinc-900/90 border border-zinc-800 text-zinc-200 rounded-tl-none'
                      }`}
                    >
                      {isUser ? (
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
                      ) : (
                        <div>
                          {message.status === 'error' ? (
                            <div className="flex items-center gap-2 text-rose-400 text-xs">
                              <AlertCircle className="w-4 h-4 shrink-0" />
                              <span>{message.content}</span>
                            </div>
                          ) : (
                            <>
                              {message.reasoning && (
                                (mode === 'dev' || showReasoning) ? (
                                  <details
                                    id={`reasoning-trace-${message.id}`}
                                    className="mb-2.5 rounded-lg border border-zinc-800/80 bg-zinc-950/70 p-2.5 text-xs text-zinc-400 group"
                                    open={mode === 'dev' ? false : true}
                                  >
                                    <summary className="cursor-pointer font-mono text-[11px] text-zinc-500 hover:text-cyan-400 flex items-center justify-between select-none font-medium">
                                      <div className="flex items-center gap-1.5">
                                        <Sparkles className="w-3 h-3 text-cyan-400 shrink-0" />
                                        <span>Model Reasoning Trace</span>
                                      </div>
                                      {mode === 'user' && (
                                        <span
                                          className="text-[10px] text-zinc-500 hover:text-zinc-300 cursor-pointer"
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            setShowReasoning(false);
                                          }}
                                        >
                                          [hide]
                                        </span>
                                      )}
                                    </summary>
                                    <div className="mt-2 text-zinc-400 text-xs font-mono whitespace-pre-wrap pl-2 border-l border-zinc-800 leading-relaxed">
                                      {message.reasoning}
                                    </div>
                                  </details>
                                ) : (
                                  <div className="mb-2">
                                    <button
                                      type="button"
                                      id={`toggle-reasoning-${message.id}`}
                                      onClick={() => setShowReasoning(true)}
                                      className="text-[11px] text-zinc-500 hover:text-cyan-400 font-mono inline-flex items-center gap-1 transition-colors"
                                      title="Model reasoning metadata available. Click to view trace."
                                    >
                                      <Sparkles className="w-3 h-3 text-cyan-400/60" />
                                      <span>View reasoning trace</span>
                                    </button>
                                  </div>
                                )
                              )}
                              <MarkdownContent content={message.content} />
                              {message.status === 'streaming' && (
                                <span className="inline-block w-1.5 h-4 ml-1 bg-cyan-400 animate-pulse align-middle" />
                              )}
                            </>
                          )}

                          {/* Per-message telemetry pill */}
                          {message.usage && (
                            <div className="mt-2.5 pt-2 border-t border-zinc-800/80 flex flex-wrap items-center gap-2 text-[10px] text-zinc-500 font-mono">
                              {message.usage.selected_model && (
                                <span
                                  id="message-routed-model-badge"
                                  className="inline-flex items-center gap-1 text-emerald-400 bg-emerald-950/40 px-1.5 py-0.5 rounded border border-emerald-800/40"
                                  title={`Requested: ${message.usage.requested_model || 'openrouter/auto'}`}
                                >
                                  <Route className="w-3 h-3 text-emerald-400" />
                                  <span className="text-zinc-400">Routed:</span>
                                  <span className="font-semibold text-emerald-300">{message.usage.selected_model}</span>
                                  {message.usage.cost_tier && (
                                    <span className="text-[9px] text-emerald-400/80 font-bold uppercase">
                                      ({message.usage.cost_tier})
                                    </span>
                                  )}
                                </span>
                              )}
                              <span>•</span>
                              <span>{message.usage.total_tokens} tokens</span>
                              <span>•</span>
                              <span>${message.usage.cost_usd.toFixed(6)}</span>
                              {message.usage.is_estimated && (
                                <span className="text-amber-400 text-[9px] bg-amber-500/10 px-1 py-0.2 rounded border border-amber-500/20">
                                  est
                                </span>
                              )}
                              {message.ttftMs && <span>• TTFT: {message.ttftMs}ms</span>}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {isUser && (
                      <div className="w-7 h-7 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center shrink-0 text-zinc-300 mt-0.5">
                        <User className="w-4 h-4" />
                      </div>
                    )}
                  </div>
                );
              })
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer Input Area */}
          <div className="p-3 border-t border-zinc-800/80 bg-zinc-900/60">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSubmit();
              }}
              className="relative flex items-center gap-2"
            >
              <textarea
                ref={textareaRef}
                id="chat-input-textarea"
                data-testid="chat-input-textarea"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isStreaming
                    ? interactionMode === 'agent'
                      ? 'Agent is planning and executing...'
                      : 'Javed is streaming response...'
                    : interactionMode === 'agent'
                    ? 'Instruct Javed Agent (Enter to submit, Shift+Enter for new line)...'
                    : 'Message Javed (Enter to send, Shift+Enter for new line)...'
                }
                rows={1}
                disabled={isStreaming}
                className="flex-1 max-h-32 min-h-[44px] py-2.5 pl-3.5 pr-12 rounded-xl bg-zinc-950 border border-zinc-800 focus:border-cyan-500/60 focus:ring-1 focus:ring-cyan-500/40 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none transition-all resize-none font-sans"
              />

              <div className="absolute right-2 flex items-center">
                {isStreaming ? (
                  <button
                    type="button"
                    id="stop-generation-button"
                    data-testid="stop-generation-button"
                    onClick={handleStop}
                    className="w-8 h-8 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-400 flex items-center justify-center transition-colors shadow-sm"
                    title="Stop generation"
                  >
                    <Square className="w-3.5 h-3.5 fill-rose-400" />
                  </button>
                ) : (
                  <button
                    type="submit"
                    id="send-message-button"
                    data-testid="send-message-button"
                    disabled={!input.trim()}
                    className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                      input.trim()
                        ? interactionMode === 'agent'
                          ? 'bg-blue-600 hover:bg-blue-500 text-white font-bold shadow-md shadow-blue-500/20'
                          : 'bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-bold shadow-md shadow-cyan-500/20'
                        : 'bg-zinc-800/60 text-zinc-600 cursor-not-allowed'
                    }`}
                    title="Send message"
                    onClick={() => handleSubmit()}
                  >
                    <Send className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </form>

            <div className="flex items-center justify-between mt-2 px-1 text-[10px] text-zinc-500">
              <span className="flex items-center gap-2">
                <span>
                  Runtime:{' '}
                  <strong className={interactionMode === 'agent' ? 'text-blue-400' : 'text-cyan-400'}>
                    {interactionMode === 'agent' ? 'Deep Agents + LangGraph' : 'Direct LLM'}
                  </strong>
                </span>
                {interactionMode === 'agent' && (
                  <span className="font-mono text-zinc-600">({threadId})</span>
                )}
              </span>
              <span>Shift + Enter for new line • Enter to submit</span>
            </div>
          </div>
        </div>
      </div>
    </AssistantRuntimeProvider>
  );
};
