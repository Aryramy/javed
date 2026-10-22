/**
 * Chat and streaming client service for Project Javed.
 */

import type { ChatStreamEvent, ModelCatalogResponse, StreamUsage } from '../types/chat';

export interface StreamChatParams {
  messages: { role: 'user' | 'assistant' | 'system'; content: string }[];
  model?: string;
  temperature?: number;
  max_tokens?: number;
  signal?: AbortSignal;
  onToken: (token: string) => void;
  onUsage?: (usage: StreamUsage) => void;
  onError?: (error: string) => void;
  onDone?: () => void;
}

const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && window.location?.origin && window.location.origin !== 'null') {
    return window.location.origin;
  }
  return 'http://localhost:5173';
};

export const chatService = {
  /**
   * Fetch the list of available models and account credit telemetry.
   */
  async getModels(params?: {
    search?: string;
    favorites_only?: boolean;
    force_refresh?: boolean;
  }): Promise<ModelCatalogResponse> {
    const url = new URL(`${getBaseUrl()}/api/v1/models`);
    if (params?.search) url.searchParams.set('search', params.search);
    if (params?.favorites_only) url.searchParams.set('favorites_only', 'true');
    if (params?.force_refresh) url.searchParams.set('force_refresh', 'true');

    const res = await fetch(url.toString(), {
      headers: {
        Accept: 'application/json',
      },
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Failed to load model catalog (HTTP ${res.status}): ${errText}`);
    }

    return (await res.json()) as ModelCatalogResponse;
  },

  /**
   * Initiate a streaming chat completion over Server-Sent Events (SSE).
   */
  async streamChat(params: StreamChatParams): Promise<void> {
    const { messages, model, temperature, max_tokens, signal, onToken, onUsage, onError, onDone } = params;

    const response = await fetch(`${getBaseUrl()}/api/v1/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({
        messages,
        model,
        temperature: temperature ?? 0.7,
        max_tokens,
        stream: true,
      }),
      signal,
    });

    if (!response.ok) {
      let errorMsg = `Server error (HTTP ${response.status})`;
      try {
        const errorJson = await response.json();
        if (errorJson.detail) {
          errorMsg = errorJson.detail;
        } else if (errorJson.error?.message) {
          errorMsg = errorJson.error.message;
        }
      } catch {
        // Fallback to generic status text
      }
      onError?.(errorMsg);
      throw new Error(errorMsg);
    }

    if (!response.body) {
      const err = 'Response body is not readable for streaming.';
      onError?.(err);
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
            onDone?.();
            return;
          }

          try {
            const event = JSON.parse(jsonStr) as ChatStreamEvent;
            switch (event.type) {
              case 'token':
                if (event.content) {
                  onToken(event.content);
                }
                break;
              case 'usage':
                if (event.usage) {
                  onUsage?.(event.usage);
                }
                break;
              case 'error':
                if (event.error) {
                  onError?.(event.error);
                }
                break;
              case 'done':
                onDone?.();
                break;
            }
          } catch {
            // Ignore non-json or fragmented lines
          }
        }
      }

      onDone?.();
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // Aborted by user - do not treat as unhandled error
        return;
      }
      const msg = err instanceof Error ? err.message : String(err);
      onError?.(msg);
      throw err;
    } finally {
      reader.releaseLock();
    }
  },
};
