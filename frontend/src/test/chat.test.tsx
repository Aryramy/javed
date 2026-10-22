import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../context/ThemeContext';
import { ModeProvider } from '../context/ModeContext';
import { BackendProvider } from '../context/BackendContext';
import { ModelSelector } from '../components/chat/ModelSelector';
import { TokenCostMeter } from '../components/chat/TokenCostMeter';
import { ChatView } from '../views/user/ChatView';
import { chatService } from '../services/chatService';
import type { ModelInfo } from '../types/chat';

const MOCK_MODELS: ModelInfo[] = [
  {
    id: 'openai/gpt-4o-mini',
    name: 'OpenAI GPT-4o Mini',
    provider: 'OpenAI',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Fast, economical frontier model.',
    is_default: true,
  },
  {
    id: 'anthropic/claude-sonnet-4.5',
    name: 'Claude Sonnet 4.5',
    provider: 'Anthropic',
    context_length: 200000,
    pricing_prompt: 3.00,
    pricing_completion: 15.00,
    description: 'Deep reasoning and coding.',
    is_default: false,
  },
];

const renderWithProviders = (ui: React.ReactElement) => {
  return render(
    <ThemeProvider>
      <ModeProvider>
        <BackendProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </BackendProvider>
      </ModeProvider>
    </ThemeProvider>
  );
};

describe('ModelSelector Component', () => {
  it('renders selected model display name and provider badge', () => {
    const onSelect = vi.fn();
    render(
      <ModelSelector
        models={MOCK_MODELS}
        selectedModelId="openai/gpt-4o-mini"
        onSelectModel={onSelect}
      />
    );

    expect(screen.getByText('OpenAI GPT-4o Mini')).toBeInTheDocument();
    expect(screen.getByText('OpenAI')).toBeInTheDocument();
  });

  it('opens dropdown and allows selecting another model', async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <ModelSelector
        models={MOCK_MODELS}
        selectedModelId="openai/gpt-4o-mini"
        onSelectModel={onSelect}
      />
    );

    const trigger = screen.getByRole('button', { name: /OpenAI GPT-4o Mini/i });
    await user.click(trigger);

    expect(screen.getByText('OpenRouter')).toBeInTheDocument();
    expect(screen.getByText('Claude Sonnet 4.5')).toBeInTheDocument();

    const claudeButton = screen.getByRole('button', { name: /Claude Sonnet 4.5/i });
    await user.click(claudeButton);

    expect(onSelect).toHaveBeenCalledWith('anthropic/claude-sonnet-4.5');
  });
});

describe('TokenCostMeter Component', () => {
  it('renders tokens and cost accurately from usage', () => {
    render(
      <TokenCostMeter
        currentUsage={{
          prompt_tokens: 150,
          completion_tokens: 50,
          total_tokens: 200,
          cost_usd: 0.00015,
          upstream_cost: 0.00015,
        }}
      />
    );

    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('$0.000150')).toBeInTheDocument();
  });

  it('renders zero state cleanly when empty', () => {
    render(<TokenCostMeter />);
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('$0.0000')).toBeInTheDocument();
  });
});

describe('ChatView Full-Stack Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(chatService, 'getModels').mockResolvedValue({
      models: MOCK_MODELS,
      default_model: 'openai/gpt-4o-mini',
      authenticated: true,
      quota_remaining_usd: 48.5,
      daily_budget_usd: 5.0,
    });
  });

  it('renders chat toolbar, suggested prompt chips, and composer', () => {
    renderWithProviders(<ChatView />);

    expect(screen.getByText('Conversational AI Gateway')).toBeInTheDocument();
    expect(screen.getByText(/BRICK-003: OpenRouter Integration & Streaming Chat/i)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Message Javed/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /clear/i })).toBeInTheDocument();
  });

  it('submits a message and handles token streaming lifecycle', async () => {
    const user = userEvent.setup();

    // Mock streamChat to simulate real SSE event stream
    vi.spyOn(chatService, 'streamChat').mockImplementation(async (params) => {
      params.onToken('Hello');
      params.onToken(' world');
      params.onUsage?.({
        prompt_tokens: 10,
        completion_tokens: 2,
        total_tokens: 12,
        cost_usd: 0.00001,
        upstream_cost: 0.00001,
      });
      params.onDone?.();
    });

    renderWithProviders(<ChatView />);

    const textarea = screen.getByPlaceholderText(/Message Javed/i);
    await user.type(textarea, 'Test prompt');

    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    // Verify user bubble rendered
    expect(screen.getByText('Test prompt')).toBeInTheDocument();

    // Verify streamed tokens assembled in assistant bubble
    await waitFor(() => {
      expect(screen.getByText('Hello world')).toBeInTheDocument();
    });

    // Verify per-message usage pill rendered
    await waitFor(() => {
      expect(screen.getByText(/12 tokens/i)).toBeInTheDocument();
    });
  });

  it('clears conversation when Clear button is clicked', async () => {
    const user = userEvent.setup();
    vi.spyOn(chatService, 'streamChat').mockImplementation(async (params) => {
      params.onToken('Response text');
      params.onDone?.();
    });

    renderWithProviders(<ChatView />);

    const textarea = screen.getByPlaceholderText(/Message Javed/i);
    await user.type(textarea, 'Ephemeral message');

    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    await waitFor(() => {
      expect(screen.getByText('Response text')).toBeInTheDocument();
    });

    const clearButton = screen.getByRole('button', { name: /clear/i });
    await user.click(clearButton);

    expect(screen.queryByText('Ephemeral message')).not.toBeInTheDocument();
    expect(screen.queryByText('Response text')).not.toBeInTheDocument();
    expect(screen.getByText('Conversational AI Gateway')).toBeInTheDocument();
  });

  it('supports selecting openrouter/auto, switching cost tier, and displaying routed model badge', async () => {
    const user = userEvent.setup();
    const routerModel: ModelInfo = {
      id: 'openrouter/auto',
      name: 'Auto Router',
      provider: 'openrouter',
      context_length: 128000,
      pricing_prompt: 0,
      pricing_completion: 0,
      description: 'Intelligent multi-tier router.',
      is_default: false,
      is_favorite: true,
      is_router: true,
    };

    vi.spyOn(chatService, 'getModels').mockResolvedValue({
      models: [routerModel, ...MOCK_MODELS],
      default_model: 'openrouter/auto',
      authenticated: true,
      quota_remaining_usd: 50.0,
      daily_budget_usd: null,
    });

    let capturedParams: any = null;
    vi.spyOn(chatService, 'streamChat').mockImplementation(async (params) => {
      capturedParams = params;
      params.onToken('Auto routed answer');
      params.onUsage?.({
        prompt_tokens: 15,
        completion_tokens: 8,
        total_tokens: 23,
        cost_usd: 0.000005,
        upstream_cost: 0.000005,
        selected_model: 'deepseek/deepseek-v4.1-flash',
        requested_model: 'openrouter/auto',
        cost_tier: params.cost_tier ?? 'low',
      });
      params.onDone?.();
    });

    renderWithProviders(<ChatView />);

    // Verify Auto Router trigger and default 'low' tier badge
    await waitFor(() => {
      expect(screen.getByText('Auto Router')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'low' })).toBeInTheDocument();
    });

    // Switch cost tier to medium
    const mediumTierButton = screen.getByRole('button', { name: 'medium' });
    await user.click(mediumTierButton);

    // Send a message
    const textarea = screen.getByPlaceholderText(/Message Javed/i);
    await user.type(textarea, 'Auto route this query');
    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    // Verify streamChat was called with cost_tier 'medium' and model 'openrouter/auto'
    await waitFor(() => {
      expect(capturedParams).not.toBeNull();
      expect(capturedParams.model).toBe('openrouter/auto');
      expect(capturedParams.cost_tier).toBe('medium');
    });

    // Verify routed model badge rendered in the UI with selected model and tier
    await waitFor(() => {
      expect(screen.getByText('Auto routed answer')).toBeInTheDocument();
      expect(screen.getByText('deepseek/deepseek-v4.1-flash')).toBeInTheDocument();
      expect(screen.getAllByText(/\(medium\)/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('validates all five cost tiers at the UI level without live calls', async () => {
    const user = userEvent.setup();
    const routerModel: ModelInfo = {
      id: 'openrouter/auto',
      name: 'OpenRouter Auto Router',
      provider: 'OpenRouter',
      context_length: 128000,
      pricing_prompt: 0.15,
      pricing_completion: 0.60,
      description: 'Auto router.',
      is_default: true,
      is_router: true,
      cost_tier: 'low',
    };

    vi.spyOn(chatService, 'getModels').mockResolvedValue({
      models: [routerModel],
      default_model: 'openrouter/auto',
      authenticated: true,
      quota_remaining_usd: 50.0,
      daily_budget_usd: null,
    });

    renderWithProviders(<ChatView />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'low' })).toBeInTheDocument();
    });

    const tiers = ['low', 'medium', 'high', 'xhigh', 'max'] as const;
    for (const tier of tiers) {
      const tierButton = screen.getByRole('button', { name: tier });
      expect(tierButton).toBeInTheDocument();
      await user.click(tierButton);
      expect(tierButton).toHaveClass('bg-emerald-500');
    }
  });

  it('isolates reasoning traces from ordinary assistant response content', async () => {
    const user = userEvent.setup();
    vi.spyOn(chatService, 'getModels').mockResolvedValue({
      models: MOCK_MODELS,
      default_model: 'openai/gpt-4o-mini',
      authenticated: true,
      quota_remaining_usd: 50.0,
      daily_budget_usd: null,
    });

    vi.spyOn(chatService, 'streamChat').mockImplementation(async (params) => {
      params.onReasoning?.('Thinking through reasoning process step 1...');
      params.onToken('Direct final answer.');
      params.onDone?.();
    });

    renderWithProviders(<ChatView />);

    const textarea = screen.getByPlaceholderText(/Message Javed/i);
    await user.type(textarea, 'Explain problem');
    const sendButton = screen.getByRole('button', { name: /send message/i });
    await user.click(sendButton);

    // In ordinary User Mode, answer content is visible, but raw reasoning trace is NOT exposed by default
    await waitFor(() => {
      expect(screen.getByText('Direct final answer.')).toBeInTheDocument();
      expect(screen.queryByText('Thinking through reasoning process step 1...')).not.toBeInTheDocument();
      expect(screen.getByText('View reasoning trace')).toBeInTheDocument();
    });

    // Clicking View reasoning trace exposes the isolated reasoning trace
    const viewTraceButton = screen.getByText('View reasoning trace');
    await user.click(viewTraceButton);

    await waitFor(() => {
      expect(screen.getByText('Model Reasoning Trace')).toBeInTheDocument();
      expect(screen.getByText('Thinking through reasoning process step 1...')).toBeInTheDocument();
    });
  });
});


