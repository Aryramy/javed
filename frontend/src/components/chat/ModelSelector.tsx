import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Cpu, ChevronDown, Check, Sparkles, Search, Star, Globe, Route } from 'lucide-react';
import type { CostTier, ModelInfo } from '../../types/chat';
import { COST_TIERS } from '../../types/chat';

interface ModelSelectorProps {
  models: ModelInfo[];
  selectedModelId: string;
  onSelectModel: (modelId: string) => void;
  costTier?: CostTier;
  onSelectCostTier?: (tier: CostTier) => void;
  disabled?: boolean;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  selectedModelId,
  onSelectModel,
  costTier = 'low',
  onSelectCostTier,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<'favorites' | 'all'>('favorites');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const selectedModel = models.find((m) => m.id === selectedModelId) || models[0];
  const isRouter = selectedModel?.id === 'openrouter/auto' || !!selectedModel?.is_router;

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
    let list = models;
    if (activeTab === 'favorites') {
      const favs = list.filter((m) => m.is_favorite);
      // Fallback to top 5 if no favorites flagged
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
  }, [models, activeTab, searchQuery]);

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
      <div className="relative inline-block text-left">
        <button
          type="button"
          id="model-selector-trigger"
          onClick={() => !disabled && setIsOpen(!isOpen)}
          disabled={disabled}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
            disabled
              ? 'opacity-50 cursor-not-allowed bg-zinc-900/50 border-zinc-800 text-zinc-500'
              : isRouter
              ? 'bg-zinc-900/90 hover:bg-zinc-800 border-emerald-500/40 text-emerald-300 shadow-sm'
              : 'bg-zinc-900/80 hover:bg-zinc-800/90 border-zinc-700/80 hover:border-cyan-500/40 text-zinc-200 shadow-sm'
          }`}
          aria-haspopup="true"
          aria-expanded={isOpen}
        >
          {isRouter ? (
            <Route className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <Cpu className="w-3.5 h-3.5 text-cyan-400" />
          )}
          <span className="font-semibold text-zinc-100">
            {isRouter ? 'Auto Router' : selectedModel?.name ?? 'Select Model'}
          </span>
          {isRouter ? (
            <span
              id="model-selector-tier-badge"
              className="px-1.5 py-0.5 rounded text-[10px] font-mono border bg-emerald-500/15 text-emerald-400 border-emerald-500/30 font-semibold uppercase"
            >
              {costTier}
            </span>
          ) : (
            selectedModel?.provider && (
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] border ${getProviderBadgeColor(
                  selectedModel.provider
                )}`}
              >
                {selectedModel.provider}
              </span>
            )
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
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    activeTab === 'favorites'
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
                  className={`flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    activeTab === 'all'
                      ? 'bg-zinc-800 text-cyan-300 border border-cyan-500/30'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  <Globe className="w-3 h-3 text-cyan-400" />
                  All ({models.length})
                </button>
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">OpenRouter</span>
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
                  const itemIsRouter = model.id === 'openrouter/auto' || !!model.is_router;
                  return (
                    <button
                      key={model.id}
                      type="button"
                      onClick={() => {
                        onSelectModel(model.id);
                        setIsOpen(false);
                      }}
                      className={`w-full text-left px-2.5 py-2 rounded-lg text-xs transition-colors flex flex-col gap-1 ${
                        isSelected
                          ? itemIsRouter
                            ? 'bg-emerald-500/15 border border-emerald-500/40 text-emerald-200'
                            : 'bg-cyan-500/15 border border-cyan-500/30 text-cyan-200'
                          : 'hover:bg-zinc-900/90 text-zinc-300 border border-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-zinc-100 flex items-center gap-1.5">
                          {itemIsRouter ? (
                            <Route className="w-3 h-3 text-emerald-400" />
                          ) : null}
                          {model.name}
                          {itemIsRouter ? (
                            <span className="text-[9px] px-1 py-0.2 text-emerald-400 bg-emerald-950/60 rounded border border-emerald-800/40 font-mono">
                              AUTO ROUTER
                            </span>
                          ) : model.is_default ? (
                            <span className="flex items-center gap-0.5 text-[9px] px-1 py-0.2 text-cyan-400 bg-cyan-950/60 rounded border border-cyan-800/40">
                              <Sparkles className="w-2.5 h-2.5" /> default
                            </span>
                          ) : null}
                        </span>
                        {isSelected && (
                          <Check className={`w-3.5 h-3.5 ${itemIsRouter ? 'text-emerald-400' : 'text-cyan-400'}`} />
                        )}
                      </div>

                      <p className="text-[11px] text-zinc-400 line-clamp-1">{model.description}</p>

                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-zinc-500 font-mono">
                        <span className={`px-1 rounded border ${getProviderBadgeColor(model.provider)}`}>
                          {model.provider}
                        </span>
                        {itemIsRouter ? (
                          <span className="text-emerald-400">Dynamic Multi-Tier Routing</span>
                        ) : (
                          <>
                            <span>{(model.context_length / 1000).toFixed(0)}k ctx</span>
                            <span>${model.pricing_prompt}/M in</span>
                            <span>${model.pricing_completion}/M out</span>
                          </>
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

      {/* Quick Cost Tier Selector when Auto Router is active */}
      {isRouter && onSelectCostTier && (
        <div
          id="cost-tier-selector"
          className="flex items-center gap-1 bg-zinc-900/90 border border-zinc-700/80 rounded-lg p-0.5 text-[11px]"
          title="OpenRouter Auto Router Cost Tier"
        >
          <span className="px-1.5 text-[10px] font-mono text-zinc-400 uppercase hidden sm:inline">Tier:</span>
          {COST_TIERS.map((tier) => (
            <button
              key={tier}
              type="button"
              id={`cost-tier-button-${tier}`}
              disabled={disabled}
              onClick={() => onSelectCostTier(tier)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-all ${
                costTier === tier
                  ? 'bg-emerald-500 text-zinc-950 font-bold shadow-sm'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
              }`}
            >
              {tier}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
