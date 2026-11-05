import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ModelSelector } from '../components/chat/ModelSelector';
import { TokenCostMeter } from '../components/chat/TokenCostMeter';
import type { ModelInfo } from '../types/chat';

const mockModels: ModelInfo[] = [
  {
    id: 'openrouter/auto',
    name: 'Auto Router',
    provider: 'OpenRouter',
    is_router: true,
    is_favorite: true,
    context_length: 128000,
    pricing_prompt: 0.000001,
    pricing_completion: 0.000002,
    description: 'Auto Router',
    is_default: true,
  },
  {
    id: 'openai/gpt-4o',
    name: 'GPT-4o',
    provider: 'OpenAI',
    is_router: false,
    is_favorite: true,
    context_length: 128000,
    pricing_prompt: 0.000005,
    pricing_completion: 0.000015,
    description: 'GPT-4o',
    is_default: false,
  },
  {
    id: 'anthropic/claude-3-5-sonnet',
    name: 'Claude 3.5 Sonnet',
    provider: 'Anthropic',
    is_router: false,
    is_favorite: true,
    context_length: 200000,
    pricing_prompt: 0.000003,
    pricing_completion: 0.000015,
    description: 'Claude 3.5 Sonnet',
    is_default: false,
  },
  {
    id: 'deepseek-v4.1-flash-1017',
    name: 'DeepSeek Flash',
    provider: 'Cheaper Inference',
    is_router: false,
    is_favorite: false,
    context_length: 64000,
    pricing_prompt: 0.0000005,
    pricing_completion: 0.000001,
    description: 'DeepSeek Flash',
    is_default: false,
  },
];

describe('Provider-Aware ModelSelector Component', () => {
  it('renders read-only Backend Controlled pill when provider is cheaper_inference', () => {
    const onSelectModel = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="deepseek-v4.1-flash-1017"
        onSelectModel={onSelectModel}
        selectedProviderId="cheaper_inference"
        cheaperInferenceModel="deepseek-v4.1-flash-1017"
      />
    );

    // Read-only container rendered
    const readonlyBox = screen.getByTestId('model-selector-cheaper-readonly');
    expect(readonlyBox).toBeInTheDocument();
    expect(screen.getByText('deepseek-v4.1-flash-1017')).toBeInTheDocument();
    expect(screen.getByText('Backend Controlled')).toBeInTheDocument();

    // Trigger button and OpenRouter dropdown must NOT exist
    expect(screen.queryByRole('button', { name: /Select Model|Auto Router/i })).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Search models/i)).not.toBeInTheDocument();
  });

  it('filters out Cheaper Inference models when provider is openrouter', () => {
    const onSelectModel = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="openai/gpt-4o"
        onSelectModel={onSelectModel}
        selectedProviderId="openrouter"
      />
    );

    // Trigger is present
    const trigger = screen.getByRole('button');
    expect(trigger).toBeInTheDocument();
    expect(screen.getByText('GPT-4o')).toBeInTheDocument();

    // Click trigger to open dropdown
    fireEvent.click(trigger);

    // Cheaper Inference model should be excluded from OpenRouter catalog
    expect(screen.queryByText('DeepSeek Flash')).not.toBeInTheDocument();
    expect(screen.queryByText('deepseek-v4.1-flash-1017')).not.toBeInTheDocument();

    // OpenRouter models should be present
    expect(screen.getAllByText('Claude 3.5 Sonnet').length).toBeGreaterThanOrEqual(1);
  });

  it('renders Auto Router and cost tier when provider is auto', () => {
    const onSelectModel = vi.fn();
    const onSelectCostTier = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="openrouter/auto"
        onSelectModel={onSelectModel}
        costTier="low"
        onSelectCostTier={onSelectCostTier}
        selectedProviderId="auto"
      />
    );

    expect(screen.getByText('Auto Router')).toBeInTheDocument();
    expect(screen.getAllByText('low').length).toBeGreaterThanOrEqual(1);
  });

  it('triggers onSelectModel with backend-controlled model if selectedModelId is stale', () => {
    const onSelectModel = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="openrouter/auto"
        onSelectModel={onSelectModel}
        selectedProviderId="cheaper_inference"
        cheaperInferenceModel="deepseek-v4.1-flash-1017"
      />
    );

    // Defense-in-depth effect dispatches onSelectModel to synchronize state
    expect(onSelectModel).toHaveBeenCalledWith('deepseek-v4.1-flash-1017');
  });

  it('renders Auto Router routing controls and last route without OpenRouter dropdown label', () => {
    const onSelectModel = vi.fn();
    const onSelectCostTier = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="openrouter/auto"
        onSelectModel={onSelectModel}
        costTier="medium"
        onSelectCostTier={onSelectCostTier}
        selectedProviderId="auto"
        lastRoute={{ provider: 'Cheaper Inference', model: 'deepseek-v4.1-flash-1017' }}
      />
    );

    expect(screen.getByText('Auto Router')).toBeInTheDocument();
    expect(screen.getByTestId('tier-btn-low')).toBeInTheDocument();
    expect(screen.getByTestId('tier-btn-medium')).toBeInTheDocument();
    expect(screen.getByTestId('tier-btn-high')).toBeInTheDocument();
    expect(screen.getByTestId('tier-btn-xhigh')).toBeInTheDocument();
    expect(screen.getByTestId('tier-btn-max')).toBeInTheDocument();

    // Must show last route label
    expect(screen.getByTestId('auto-router-last-route')).toHaveTextContent(
      /Last route:\s*Cheaper Inference\s*·\s*deepseek-v4\.1-flash-1017/i
    );

    // Must not show OpenRouter catalog label or dropdown
    expect(screen.queryByText('OpenRouter Catalog')).not.toBeInTheDocument();
  });

  it('labels dropdown as OpenRouter Catalog when provider is openrouter', () => {
    const onSelectModel = vi.fn();

    render(
      <ModelSelector
        models={mockModels}
        selectedModelId="openai/gpt-4o"
        onSelectModel={onSelectModel}
        selectedProviderId="openrouter"
      />
    );

    expect(screen.getByText('OpenRouter Catalog')).toBeInTheDocument();
  });

  it('renders TokenCostMeter with honest dash when uninitialized rather than fake zeros', () => {
    const { rerender } = render(<TokenCostMeter />);

    // Honest dash when uninitialized
    expect(screen.getByTestId('meter-display-tokens')).toHaveTextContent('—');
    expect(screen.getByTestId('meter-display-cost')).toHaveTextContent('—');

    // Populated when totals or usage arrives
    rerender(
      <TokenCostMeter
        totals={{
          totalTokens: 1500,
          totalCostUsd: 0.00045,
          totalPromptTokens: 1200,
          totalCompletionTokens: 300,
          messageCount: 1,
        }}
      />
    );

    expect(screen.getByTestId('meter-display-tokens')).toHaveTextContent('1,500');
    expect(screen.getByTestId('meter-display-cost')).toHaveTextContent('$0.000450');
  });
});
