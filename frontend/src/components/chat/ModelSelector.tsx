import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Cpu, ChevronDown, Check, Search, Star, Globe, Route } from 'lucide-react';
import type { CostTier, ModelInfo } from '../../types/chat';
import { COST_TIERS } from '../../types/chat';

interface ModelSelectorProps {
  models: ModelInfo[];
  selectedModelId: string;
  onSelectModel: (modelId: string) => void;
  costTier?: CostTier;
  onSelectCostTier?: (tier: CostTier) => void;
  disabled?: boolean;
  selectedProviderId?: string;
  cheaperInferenceModel?: string;
  lastRoute?: { provider: string; model: string } | null;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  selectedModelId,
  onSelectModel,
  costTier = 'low',
  onSelectCostTier,
  disabled = false,
  selectedProviderId = 'auto',
  cheaperInferenceModel = 'deepseek-v4.1-flash-1017',
  lastRoute,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'favorites' | 'all'>('favorites');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Filter models for OpenRouter (strictly no Cheaper Inference models)
  const availableModels = useMemo(() => {
    if (selectedProviderId === 'openrouter') {
      return models.filter((m) => m.id !== 'deepseek-v4.1-flash-1017' && !m.id.includes('cheaper'));
    }
    return models;
  }, [models, selectedProviderId]);

  const selectedModel = availableModels.find((m) => m.id === selectedModelId) || availableModels[0];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isOpen]);

  const filteredModels = useMemo(() => {
    let list = availableModels;
    if (activeTab === 'favorites') {
      const favs = list.filter((m) => m.is_favorite);
      list = favs.length > 0 ? favs : list.slice(0, 5);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (m) =>
          m.name.toLowerCase().includes(q) ||
          m.id.toLowerCase().includes(q) ||
          m.provider.toLowerCase().includes(q)
      );
    }
    return list;
  }, [availableModels, activeTab, searchQuery]);

  // Defense-in-depth: sync selectedModelId to backend-controlled model if Cheaper Inference is selected
  useEffect(() => {
    if (selectedProviderId === 'cheaper_inference') {
      const targetModel = cheaperInferenceModel || 'deepseek-v4.1-flash-1017';
      if (selectedModelId !== targetModel) {
        onSelectModel(targetModel);
      }
    }
  }, [selectedProviderId, cheaperInferenceModel, selectedModelId, onSelectModel]);


  // 1. If Cheaper Inference is explicitly selected, render a backend-controlled read-only pill
  if (selectedProviderId === 'cheaper_inference') {
    const modelDisplayName = cheaperInferenceModel || 'deepseek-v4.1-flash-1017';
    return (
      <div
        id="model-selector-cheaper-readonly"
        data-testid="model-selector-cheaper-readonly"
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium bg-zinc-900/90 border-purple-500/30 text-purple-300 shadow-sm"
        title="Cheaper Inference model is backend-controlled"
      >
        <Cpu className="w-3.5 h-3.5 text-purple-400" />
        <span className="font-semibold text-zinc-100">{modelDisplayName}</span>
        <span
          id="backend-controlled-badge"
          data-testid="backend-controlled-badge"
          className="px-1.5 py-0.5 rounded text-[10px] font-mono border bg-purple-500/15 text-purple-300 border-purple-500/30 font-semibold uppercase"
        >
          Backend Controlled
        </span>
      </div>
    );
  }

  // 2. If Auto Router is selected, show routing-policy controls, selected tier, and last-route without misleading OpenRouter catalog
  if (selectedProviderId === 'auto') {
    return (
      <div className="relative inline-flex flex-wrap items-center gap-2" id="auto-router-controls-container">
        {/* Auto Router Policy Badge */}
        <div
          id="model-selector-auto-badge"
          data-testid="model-selector-auto-badge"
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium bg-zinc-900/90 border-emerald-500/40 text-emerald-300 shadow-sm"
          title="Auto Router dynamically selects the best provider and model per request based on routing policy"
        >
          <Route className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span className="font-semibold text-zinc-100">Auto Router</span>
          <span
            id="model-selector-tier-badge"
            className="px-1.5 py-0.5 rounded text-[10px] font-mono border bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-semibold uppercase"
          >
            {costTier}
          </span>
        </div>

        {/* Routing-Policy Tier Controls */}
        {onSelectCostTier && (
          <div
            id="cost-tier-selector"
            className="flex items-center gap-1 bg-zinc-900/90 border border-zinc-700/80 rounded-lg p-0.5 text-[11px]"
            title="Auto Router Routing Policy Cost Tier"
          >
            <span className="px-1.5 text-[10px] font-mono text-zinc-400 uppercase hidden sm:inline">Tier:</span>
            {COST_TIERS.map((tier) => (
              <button
                key={tier}
                type="button"
                id={`cost-tier-button-${tier}`}
                data-testid={`tier-btn-${tier}`}
                disabled={disabled}
                onClick={() => onSelectCostTier(tier)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-all ${costTier === tier
                    ? 'bg-emerald-500 text-zinc-950 font-bold shadow-sm'
                    : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
                  }`}
              >
                {tier}
              </button>
            ))}
          </div>
        )}

        {/* Last Routed Provider & Model Presentation */}
        {lastRoute && lastRoute.provider && lastRoute.model && (
          <div
            id="auto-router-last-route"
            data-testid="auto-router-last-route"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-[11px] font-mono bg-zinc-900/90 border-emerald-500/30 text-emerald-300 shadow-sm"
            title="Provider and model dynamically resolved by Auto Router for previous response"
          >
            <span className="text-zinc-400 font-sans text-[10px]">Last route:</span>
            <span className="font-semibold text-zinc-100">
              {lastRoute.provider} · {lastRoute.model}
            </span>
          </div>
        )}
      </div>
    );
  }

  // 3. OpenRouter mode: show approved OpenRouter model catalog
  const getProviderBadgeColor = (provider: string) => {
    switch (provider.toLowerCase()) {
      case 'openai':
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
      case 'anthropic':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
      case 'google':
        return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
      case 'deepseek':
        return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
      case 'openrouter':
        return 'bg-teal-500/10 text-teal-400 border-teal-500/20';
      default:
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
    }
  };

  return (
    <div className="relative inline-flex items-center gap-2" ref={dropdownRef}>
      <span
        data-testid="openrouter-catalog-label"
        className="px-1 text-[10px] font-mono text-zinc-400 uppercase hidden sm:inline"
      >
        OpenRouter Catalog
      </span>
      <div className="relative inline-block text-left">
        <button
          type="button"
          id="model-selector-trigger"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${disabled
              ? 'opacity-50 cursor-not-allowed bg-zinc-900/50 border-zinc-800 text-zinc-500'
              : 'bg-zinc-900/80 hover:bg-zinc-800/90 border-zinc-700/80 hover:border-cyan-500/40 text-zinc-200 shadow-sm'
            }`}
          aria-haspopup="true"
          aria-expanded={isOpen}
        >
          <Cpu className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-semibold text-zinc-100">
            {selectedModel?.name ?? 'Select Model'}
          </span>
          {selectedModel?.provider && (
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] border ${getProviderBadgeColor(
                selectedModel.provider
              )}`}
            >
              {selectedModel.provider}
            </span>
          )}
          <ChevronDown className={`w-3.5 h-3.5 text-zinc-400 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {isOpen && (
          <div
            id="model-selector-dropdown"
            className="absolute left-0 sm:right-auto z-50 mt-1.5 w-80 origin-top-left rounded-xl border border-zinc-700/80 bg-zinc-950/95 p-2 shadow-2xl backdrop-blur-xl ring-1 ring-black/40 focus:outline-none"
          >
            {/* Header & Tabs */}
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800 text-xs">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setActiveTab('favorites')}
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors ${activeTab === 'favorites'
                      ? 'bg-zinc-800 text-cyan-300 border border-cyan-500/30'
                      : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                >
                  <Star className="w-3 h-3 text-amber-400 fill-amber-400/30" />
                  Favorites
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('all')}
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors ${activeTab === 'all'
                      ? 'bg-zinc-800 text-cyan-300 border border-cyan-500/30'
                      : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                >
                  <Globe className="w-3 h-3 text-cyan-400" />
                  All ({availableModels.length})
                </button>
              </div>
              <span className="text-[10px] text-zinc-400 font-mono" id="openrouter-catalog-label">
                OpenRouter Catalog
              </span>
            </div>

            {/* Search Input */}
            <div className="relative mb-2">
              <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                ref={searchInputRef}
                type="text"
                placeholder="Search model by name or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-2.5 py-1.5 bg-zinc-900/90 border border-zinc-700/80 rounded-lg text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-cyan-500/60"
              />
            </div>

            {/* Models List */}
            <div className="space-y-1 max-h-72 overflow-y-auto pr-1">
              {filteredModels.length === 0 ? (
                <div className="text-center py-6 text-xs text-zinc-500">
                  No matching models found.
                </div>
              ) : (
                filteredModels.map((model) => {
                  const isSelected = model.id === selectedModelId;
                  return (
                    <button
                      key={model.id}
                      type="button"
                      onClick={() => {
                        onSelectModel(model.id);
                        setIsOpen(false);
                      }}
                      className={`w-full text-left px-2.5 py-2 rounded-lg text-xs transition-colors flex flex-col gap-1 ${isSelected
                          ? 'bg-cyan-500/15 border border-cyan-500/30 text-cyan-200'
                          : 'hover:bg-zinc-900/90 text-zinc-300 border border-transparent'
                        }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium truncate">{model.name}</span>
                        {isSelected && <Check className="w-3.5 h-3.5 text-cyan-400 shrink-0" />}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-zinc-500">
                        <span className="font-mono">{model.id}</span>
                        {model.context_length && (
                          <span>{(model.context_length / 1000).toFixed(0)}k ctx</span>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
