import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProviderSelector } from '../components/chat/ProviderSelector';
import type { ProviderInfo } from '../types/chat';

const MOCK_PROVIDERS: ProviderInfo[] = [
  {
    id: 'auto',
    display_name: 'Auto Router',
    health: 'available',
    configured: true,
    capabilities: {
      chat: true,
      agent: true,
      transcription: false,
      translation: false,
      speech: false,
      realtime_voice: false,
    },
    chat_model: 'deepseek-v4.1-flash-1017',
  },
  {
    id: 'openrouter',
    display_name: 'OpenRouter',
    health: 'available',
    configured: true,
    capabilities: {
      chat: true,
      agent: true,
      transcription: false,
      translation: false,
      speech: false,
      realtime_voice: false,
    },
    chat_model: 'openai/gpt-4o-mini',
  },
  {
    id: 'cheaper_inference',
    display_name: 'Cheaper Inference',
    health: 'available',
    configured: true,
    capabilities: {
      chat: true,
      agent: true,
      transcription: false,
      translation: false,
      speech: false,
      realtime_voice: false,
    },
    chat_model: 'deepseek-v4.1-flash-1017',
  },
];

describe('ProviderSelector Component', () => {
  it('renders trigger button with active provider and health indicator', () => {
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    expect(trigger).toBeInTheDocument();
    expect(screen.getByText('Auto Router')).toBeInTheDocument();
  });

  it('renders dropdown menu when trigger is clicked', async () => {
    const user = userEvent.setup();
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    expect(screen.getByText(/Inference Provider Switch/i)).toBeInTheDocument();
    expect(screen.getByText('OpenRouter')).toBeInTheDocument();
    expect(screen.getByText('Cheaper Inference')).toBeInTheDocument();
  });

  it('calls onSelectProvider when an option is selected', async () => {
    const user = userEvent.setup();
    const handleSelect = vi.fn();

    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={handleSelect}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    const cheaperOption = screen.getByTestId('provider-option-cheaper_inference');
    await user.click(cheaperOption);

    expect(handleSelect).toHaveBeenCalledWith('cheaper_inference');
  });

  it('renders read-only model name and does not contain any input/editable fields', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="cheaper_inference"
        onSelectProvider={vi.fn()}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    // Verify model name is rendered as plain text
    expect(screen.getAllByText(/deepseek-v4.1-flash-1017/i).length).toBeGreaterThanOrEqual(1);

    // Verify ZERO inputs, textareas, or form controls exist inside the dropdown
    const inputs = container.querySelectorAll('input, textarea, select');
    expect(inputs.length).toBe(0);
  });

  it('renders capability badges for chat and agent', async () => {
    const user = userEvent.setup();
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    expect(screen.getAllByText('Chat').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Agent').length).toBeGreaterThanOrEqual(1);
  });

  it('disables trigger when disabled prop is true', () => {
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
        disabled={true}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    expect(trigger).toBeDisabled();
  });

  it('disables option in agent mode if provider agent capability is false', async () => {
    const user = userEvent.setup();
    const providersWithNoAgent: ProviderInfo[] = [
      ...MOCK_PROVIDERS.slice(0, 2),
      {
        ...MOCK_PROVIDERS[2],
        capabilities: {
          chat: true,
          agent: false,
          transcription: false,
          translation: false,
          speech: false,
          realtime_voice: false,
        },
      },
    ];

    render(
      <ProviderSelector
        providers={providersWithNoAgent}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
        interactionMode="agent"
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    const cheaperOption = screen.getByTestId('provider-option-cheaper_inference');
    expect(cheaperOption).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/Model lacks tool-calling capabilities/i)).toBeInTheDocument();
  });

  it('shows voice capability indicator in developer mode with deferral note', async () => {
    const user = userEvent.setup();
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
        isDeveloperMode={true}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    expect(screen.getAllByText(/Voice UI deferred to BRICK-012/i).length).toBeGreaterThanOrEqual(1);
  });

  it('hides voice deferral note in user mode', async () => {
    const user = userEvent.setup();
    render(
      <ProviderSelector
        providers={MOCK_PROVIDERS}
        selectedProviderId="auto"
        onSelectProvider={vi.fn()}
        isDeveloperMode={false}
      />
    );

    const trigger = screen.getByRole('button', { name: /Select inference provider/i });
    await user.click(trigger);

    expect(screen.queryByText(/Voice UI deferred to BRICK-012/i)).not.toBeInTheDocument();
  });
});
