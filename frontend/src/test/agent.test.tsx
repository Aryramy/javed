import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '../context/ThemeContext';
import { ModeProvider } from '../context/ModeContext';
import { BackendProvider } from '../context/BackendContext';
import { ChatView } from '../views/user/ChatView';
import { TaskPlanPanel } from '../components/chat/TaskPlanPanel';
import { agentService } from '../services/agentService';
import { chatService } from '../services/chatService';
import type { AgentTodoItem, AgentThreadStateResponse } from '../types/agent';

const MOCK_MODELS = [
  {
    id: 'openrouter/auto',
    name: 'OpenRouter Auto Router',
    provider: 'OpenRouter',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Dynamic auto-router with cost tiers.',
    is_default: true,
    is_favorite: true,
    is_router: true,
  },
  {
    id: 'openai/gpt-4o-mini',
    name: 'OpenAI GPT-4o Mini',
    provider: 'OpenAI',
    context_length: 128000,
    pricing_prompt: 0.15,
    pricing_completion: 0.60,
    description: 'Fast, economical frontier model.',
    is_default: false,
    is_favorite: true,
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

describe('TaskPlanPanel Component', () => {
  const sampleTodos: AgentTodoItem[] = [
    { id: '1', content: 'Step 1: Ingest SharePoint metadata', status: 'completed' },
    { id: '2', content: 'Step 2: Define calculation measures', status: 'in_progress' },
    { id: '3', content: 'Step 3: Verification checkpoint', status: 'pending' },
  ];

  it('renders structured todos with their respective status badges', () => {
    render(
      <TaskPlanPanel
        todos={sampleTodos}
        activeRunId="run-test-123"
        isStreaming={false}
      />
    );

    expect(screen.getByText('Structured Agent Plan')).toBeInTheDocument();
    expect(screen.getByText('Step 1: Ingest SharePoint metadata')).toBeInTheDocument();
    expect(screen.getByText('Step 2: Define calculation measures')).toBeInTheDocument();
    expect(screen.getByText('Step 3: Verification checkpoint')).toBeInTheDocument();
    expect(screen.getByText('1/3 Completed')).toBeInTheDocument();
    expect(screen.getByText('run-test-123')).toBeInTheDocument();
  });

  it('allows collapsing and expanding the task plan panel', async () => {
    const user = userEvent.setup();
    render(<TaskPlanPanel todos={sampleTodos} />);

    const toggleButton = screen.getByRole('button', { name: /collapse plan/i });
    expect(toggleButton).toBeInTheDocument();

    await user.click(toggleButton);
    expect(screen.queryByText('Step 1: Ingest SharePoint metadata')).not.toBeInTheDocument();

    const expandButton = screen.getByRole('button', { name: /expand plan/i });
    await user.click(expandButton);
    expect(screen.getByText('Step 1: Ingest SharePoint metadata')).toBeInTheDocument();
  });
});

describe('ChatView Agent Mode Integration', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();

    vi.spyOn(chatService, 'getModels').mockResolvedValue({
      models: MOCK_MODELS,
      default_model: 'openrouter/auto',
      authenticated: true,
      quota_remaining_usd: 50.0,
      daily_budget_usd: 10.0,
    });

    vi.spyOn(agentService, 'getThreadState').mockResolvedValue({
      thread_id: 'test-thread',
      exists: false,
      checkpoint_id: null,
      messages: [],
      todos: [],
    });
  });

  it('switches between Chat Mode and Agent Mode cleanly', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ChatView />);

    // Initially Chat Mode is active
    expect(screen.getByText('Conversational AI Gateway')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Chat Mode/i })).toBeInTheDocument();

    const agentToggle = screen.getByTestId('mode-toggle-agent');
    await user.click(agentToggle);

    // After switching, Agent Mode UI elements are displayed
    expect(screen.getByText('Stateful Agent Runtime')).toBeInTheDocument();
    expect(screen.getByText(/BRICK-004: Deep Agents \+ LangGraph Runtime \(ACTIVE\)/i)).toBeInTheDocument();
    expect(screen.getByTestId('agent-status-badge')).toBeInTheDocument();
    expect(screen.getByTestId('new-thread-button')).toBeInTheDocument();
  });

  it('executes agent streaming workflow with real task planning and token streaming', async () => {
    const user = userEvent.setup();

    const mockTodos: AgentTodoItem[] = [
      { id: 't1', content: 'Analyze schema requirements', status: 'completed' },
      { id: 't2', content: 'Generate DAX formulas', status: 'in_progress' },
    ];

    vi.spyOn(agentService, 'streamAgent').mockImplementation(async (params) => {
      params.onRunStarted?.({
        run_id: 'run-live-456',
        thread_id: params.thread_id,
        model: params.model,
      });
      params.onPlanning?.(mockTodos);
      params.onPlanUpdated?.(mockTodos);
      params.onToken?.('Here is the structured');
      params.onToken?.(' Power BI measure analysis.');
      params.onCheckpointSaved?.('checkpoint-1');
      params.onRunCompleted?.({
        run_id: 'run-live-456',
        content: 'Here is the structured Power BI measure analysis.',
        todos: mockTodos,
        usage: {
          prompt_tokens: 40,
          completion_tokens: 15,
          total_tokens: 55,
          cost_usd: 0.00002,
          upstream_cost: 0.00002,
          selected_model: 'openrouter/auto',
        },
      });
    });

    localStorage.setItem('javed_interaction_mode', 'agent');
    renderWithProviders(<ChatView />);

    const suggestionChip = await screen.findByText(/Create a five-step implementation plan/i);
    await user.click(suggestionChip);

    // Verify task plan panel rendered with planning items
    await waitFor(() => {
      expect(screen.getByText('Structured Agent Plan')).toBeInTheDocument();
      expect(screen.getByText('Analyze schema requirements')).toBeInTheDocument();
      expect(screen.getByText('Generate DAX formulas')).toBeInTheDocument();
    });

    // Verify streamed response rendered
    await waitFor(() => {
      expect(screen.getByText(/Here is the structured Power BI measure analysis/i)).toBeInTheDocument();
    });

    // Verify status badge shows completed
    await waitFor(() => {
      expect(screen.getByTestId('agent-status-badge')).toHaveTextContent(/completed/i);
    });
  });

  it('restores thread messages and todos from saved checkpoint state', async () => {
    const mockState: AgentThreadStateResponse = {
      thread_id: 'saved-thread-1',
      exists: true,
      checkpoint_id: 'cp-abc-999',
      messages: [
        { role: 'user', content: 'What is Project Orchid?' },
        { role: 'assistant', content: 'Project Orchid is our test BI project.' },
      ],
      todos: [
        { id: '1', content: 'Setup Project Orchid', status: 'completed' },
      ],
    };

    localStorage.setItem('javed_interaction_mode', 'agent');
    localStorage.setItem('javed_active_thread_id', 'saved-thread-1');

    vi.spyOn(agentService, 'getThreadState').mockResolvedValue(mockState);

    renderWithProviders(<ChatView />);

    await waitFor(() => {
      expect(screen.getByText('What is Project Orchid?')).toBeInTheDocument();
      expect(screen.getByText('Project Orchid is our test BI project.')).toBeInTheDocument();
      expect(screen.getByText('Setup Project Orchid')).toBeInTheDocument();
    });
  });

  it('supports starting a new thread and clearing state', async () => {
    const user = userEvent.setup();
    localStorage.setItem('javed_interaction_mode', 'agent');

    renderWithProviders(<ChatView />);

    const newThreadBtn = screen.getByTestId('new-thread-button');
    expect(newThreadBtn).toBeInTheDocument();

    await user.click(newThreadBtn);
    expect(screen.getByText('Stateful Agent Runtime')).toBeInTheDocument();
  });
});
