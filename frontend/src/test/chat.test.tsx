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
});
