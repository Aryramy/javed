import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Send,
  Square,
  Trash2,
  Bot,
  User,
  Sparkles,
  AlertCircle,
  Clock,
  Zap,
  Server,
  Wifi,
  WifiOff,
} from 'lucide-react';
import { ModelSelector } from '../../components/chat/ModelSelector';
import { TokenCostMeter } from '../../components/chat/TokenCostMeter';
import { MarkdownContent } from '../../components/chat/MarkdownContent';
import { chatService } from '../../services/chatService';
import { useBackend } from '../../context';
import { cn } from '../../lib/utils';
import { AssistantRuntimeProvider, useExternalStoreRuntime } from '@assistant-ui/react';
import type {
  ChatMessage,
  ConversationTotals,
  ModelCatalogResponse,
  ModelInfo,
  StreamUsage,
} from '../../types/chat';

const DEFAULT_MODELS: ModelInfo[] = [
  {
    id: 'openai/gpt-4o-mini',
    name: 'OpenAI GPT-4o Mini',
    provider: 'OpenAI',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Fast, economical frontier model ideal for daily tasks.',
    is_default: true,
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
  },
];

const SUGGESTIONS = [
  'Explain quantum entanglement in simple terms',
  'Write an async Python client using httpx with exponential retry',
  'Compare Redis with SQLite in-memory for sub-millisecond caching',
  'Summarize the core architectural rules of Project Javed',
];

let msgCounter = 0;
function generateMessageId(role: string): string {
  msgCounter += 1;
  return `${role}-${msgCounter}`;
}

export const ChatView: React.FC = () => {
  const { status, latencyMs, systemStatus } = useBackend();
  const isConnected = status === 'connected';

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [models, setModels] = useState<ModelInfo[]>(DEFAULT_MODELS);
  const [selectedModelId, setSelectedModelId] = useState<string>('openai/gpt-4o-mini');
  const [catalogMeta, setCatalogMeta] = useState<ModelCatalogResponse | null>(null);
  const [input, setInput] = useState<string>('');
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
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
  }, [messages, isStreaming]);

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

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsStreaming(false);

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
    setCurrentUsage(null);
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
        timestamp: nowIso,
        status: 'complete',
      };

      const initialAssistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: '',
        timestamp: nowIso,
        status: 'streaming',
      };

      const newMessages = [...messages, userMessage];
      setMessages([...newMessages, initialAssistantMessage]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      // Build message payload for API
      const historyPayload = newMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      try {
        await chatService.streamChat({
          messages: historyPayload,
          model: selectedModelId,
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
        // Aborts or unhandled errors are already flagged in onError / finally
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [input, isStreaming, messages, selectedModelId]
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

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className="space-y-3">
      {/* Real Backend Status Banner in User Mode */}
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
          <span>Stage 1 Transport Verified • AI Gateway Active (BRICK-003)</span>
        </div>
      </div>

      <div className="flex flex-col h-[calc(100vh-190px)] max-h-[1000px] rounded-xl border border-zinc-800 bg-zinc-950/70 backdrop-blur-xl shadow-2xl overflow-hidden">
        {/* Header Toolbar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-800/80 bg-zinc-900/60 text-xs">
          <div className="flex items-center gap-3">
            <ModelSelector
              models={models}
              selectedModelId={selectedModelId}
              onSelectModel={setSelectedModelId}
              disabled={isStreaming}
            />
            <TokenCostMeter currentUsage={currentUsage} totals={totals} isStreaming={isStreaming} />
          </div>

          <div className="flex items-center gap-2">
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
              title="Clear conversation history"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          </div>
        </div>

        {/* Message Thread Viewport */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center max-w-lg mx-auto text-center py-12">
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center mb-4 text-cyan-400 shadow-lg shadow-cyan-500/10">
                <Bot className="w-6 h-6" />
              </div>
              <h2 className="text-lg font-semibold text-zinc-100 tracking-tight mb-1">
                Conversational AI Gateway
              </h2>
              <p className="text-xs text-zinc-400 mb-2 leading-relaxed">
                Interactive streaming chat powered by Deep Agents and OpenRouter LLM inference.
              </p>
              <div className="mb-6 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-[11px] font-mono">
                <Sparkles className="w-3 h-3" />
                <span>BRICK-003: OpenRouter Integration & Streaming Chat (ACTIVE)</span>
              </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => handleSubmit(suggestion)}
                  className="p-3 rounded-lg border border-zinc-800/80 bg-zinc-900/40 hover:bg-zinc-900 hover:border-cyan-500/40 transition-all text-xs text-zinc-300 hover:text-cyan-200 group flex items-start gap-2"
                >
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0 mt-0.5 group-hover:scale-110 transition-transform" />
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
                  <div className="w-7 h-7 rounded-lg bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center shrink-0 text-cyan-400 mt-0.5">
                    <Bot className="w-4 h-4" />
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
                          <MarkdownContent content={message.content} />
                          {message.status === 'streaming' && (
                            <span className="inline-block w-1.5 h-4 ml-1 bg-cyan-400 animate-pulse align-middle" />
                          )}
                        </>
                      )}

                      {/* Per-message telemetry pill */}
                      {message.usage && (
                        <div className="mt-2.5 pt-2 border-t border-zinc-800/80 flex items-center gap-3 text-[10px] text-zinc-500 font-mono">
                          <span className="flex items-center gap-1 text-zinc-400">
                            <Zap className="w-3 h-3 text-amber-400" />
                            {message.usage.total_tokens} tokens
                          </span>
                          <span>•</span>
                          <span className="text-emerald-400 font-semibold">
                            ${message.usage.cost_usd.toFixed(6)}
                          </span>
                          {message.ttftMs && (
                            <>
                              <span>•</span>
                              <span className="flex items-center gap-1 text-zinc-400">
                                <Clock className="w-3 h-3 text-cyan-400" />
                                {message.ttftMs}ms TTFT
                              </span>
                            </>
                          )}
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
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? 'Javed is streaming response...'
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
                disabled={!input.trim()}
                className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                  input.trim()
                    ? 'bg-cyan-500 hover:bg-cyan-400 text-zinc-950 font-bold shadow-md shadow-cyan-500/20'
                    : 'bg-zinc-800/60 text-zinc-600 cursor-not-allowed'
                }`}
                title="Send message"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </form>

        <div className="flex items-center justify-between mt-2 px-1 text-[10px] text-zinc-500">
          <span>Active Model: <strong className="text-zinc-400">{selectedModelId}</strong></span>
          <span>Shift + Enter for new line • Enter to submit</span>
        </div>
      </div>
    </div>
  </div>
  </AssistantRuntimeProvider>
  );
};
