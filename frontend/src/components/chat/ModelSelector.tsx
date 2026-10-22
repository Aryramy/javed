import React, { useState, useRef, useEffect } from 'react';
import { Cpu, ChevronDown, Check, Sparkles } from 'lucide-react';
import type { ModelInfo } from '../../types/chat';

interface ModelSelectorProps {
  models: ModelInfo[];
  selectedModelId: string;
  onSelectModel: (modelId: string) => void;
  disabled?: boolean;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  models,
  selectedModelId,
  onSelectModel,
  disabled = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const selectedModel = models.find((m) => m.id === selectedModelId) || models[0];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

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
      default:
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
    }
  };

  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      <button
        type="button"
        id="model-selector-trigger"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
          disabled
            ? 'opacity-50 cursor-not-allowed bg-zinc-900/50 border-zinc-800 text-zinc-500'
            : 'bg-zinc-900/80 hover:bg-zinc-800/90 border-zinc-700/80 hover:border-cyan-500/40 text-zinc-200 shadow-sm'
        }`}
        aria-haspopup="true"
        aria-expanded={isOpen}
      >
        <Cpu className="w-3.5 h-3.5 text-cyan-400" />
        <span className="font-semibold text-zinc-100">{selectedModel?.name ?? 'Select Model'}</span>
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
          className="absolute right-0 z-50 mt-1.5 w-72 origin-top-right rounded-xl border border-zinc-700/80 bg-zinc-950/95 p-1.5 shadow-2xl backdrop-blur-xl ring-1 ring-black/40 focus:outline-none"
        >
          <div className="px-2.5 py-1.5 mb-1 border-b border-zinc-800 text-[11px] font-medium text-zinc-400 flex items-center justify-between">
            <span>Available Frontier Models</span>
            <span className="text-[10px] text-zinc-500">OpenRouter</span>
          </div>
          <div className="space-y-1 max-h-72 overflow-y-auto pr-1">
            {models.map((model) => {
              const isSelected = model.id === selectedModelId;
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
                      ? 'bg-cyan-500/15 border border-cyan-500/30 text-cyan-200'
                      : 'hover:bg-zinc-900/90 text-zinc-300 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-zinc-100 flex items-center gap-1.5">
                      {model.name}
                      {model.is_default && (
                        <span className="flex items-center gap-0.5 text-[9px] px-1 py-0.2 text-cyan-400 bg-cyan-950/60 rounded border border-cyan-800/40">
                          <Sparkles className="w-2.5 h-2.5" /> default
                        </span>
                      )}
                    </span>
                    {isSelected && <Check className="w-3.5 h-3.5 text-cyan-400" />}
                  </div>

                  <p className="text-[11px] text-zinc-400 line-clamp-1">{model.description}</p>

                  <div className="flex items-center gap-2 mt-0.5 text-[10px] text-zinc-500">
                    <span className={`px-1 rounded border ${getProviderBadgeColor(model.provider)}`}>
                      {model.provider}
                    </span>
                    <span>{(model.context_length / 1000).toFixed(0)}k ctx</span>
                    <span>${model.pricing_prompt}/M in</span>
                    <span>${model.pricing_completion}/M out</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
