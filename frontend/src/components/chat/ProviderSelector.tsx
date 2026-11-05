/**
 * ProviderSelector Component.
 *
 * Implements a secure, owner-selectable inference provider switch for Chat Mode and Agent Mode.
 * Renders read-only model metadata, health state indicators, capability badges, and
 * developer-mode telemetry without exposing secret keys or allowing arbitrary parameter editing.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Layers,
  ChevronDown,
  Check,
  AlertTriangle,
  Lock,
  Cpu,
  Mic,
  Volume2,
  Radio,
  Sparkles,
} from 'lucide-react';
import type { ProviderId, ProviderInfo, ProviderHealthState } from '../../types/chat';

export interface ProviderSelectorProps {
  providers: ProviderInfo[];
  selectedProviderId: ProviderId;
  onSelectProvider: (providerId: ProviderId) => void;
  disabled?: boolean;
  interactionMode?: 'chat' | 'agent';
  isDeveloperMode?: boolean;
}

const getHealthBadgeStyle = (health: ProviderHealthState): { bg: string; text: string; dot: string; label: string } => {
  switch (health) {
    case 'available':
      return { bg: 'bg-emerald-500/10 border-emerald-500/30', text: 'text-emerald-400', dot: 'bg-emerald-400', label: 'AVAILABLE' };
    case 'degraded':
      return { bg: 'bg-amber-500/10 border-amber-500/30', text: 'text-amber-400', dot: 'bg-amber-400', label: 'DEGRADED' };
    case 'capability_mismatch':
      return { bg: 'bg-orange-500/10 border-orange-500/30', text: 'text-orange-400', dot: 'bg-orange-400', label: 'TOOL CALLING LIMITATION' };
    case 'not_configured':
      return { bg: 'bg-zinc-800 border-zinc-700', text: 'text-zinc-400', dot: 'bg-zinc-500', label: 'NOT CONFIGURED' };
    case 'model_unavailable':
      return { bg: 'bg-rose-500/10 border-rose-500/30', text: 'text-rose-400', dot: 'bg-rose-400', label: 'MODEL UNAVAILABLE' };
    case 'unavailable':
    default:
      return { bg: 'bg-rose-500/10 border-rose-500/30', text: 'text-rose-400', dot: 'bg-rose-400', label: 'UNAVAILABLE' };
  }
};

export const ProviderSelector: React.FC<ProviderSelectorProps> = ({
  providers,
  selectedProviderId,
  onSelectProvider,
  disabled = false,
  interactionMode = 'chat',
  isDeveloperMode = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Resolve currently active provider
  const activeProvider = providers.find((p) => p.id === selectedProviderId) || {
    id: selectedProviderId,
    display_name:
      selectedProviderId === 'openrouter'
        ? 'OpenRouter'
        : selectedProviderId === 'cheaper_inference'
        ? 'Cheaper Inference'
        : 'Auto Router',
    configured: true,
    health: 'available' as ProviderHealthState,
    chat_model: selectedProviderId === 'cheaper_inference' ? 'deepseek-v4.1-flash-1017' : 'Claude 3.5 Sonnet',
    capabilities: { chat: true, agent: true },
  };

  const healthStyle = getHealthBadgeStyle(activeProvider.health);

  const handleSelect = (provider: ProviderInfo) => {
    if (disabled) return;

    // Agent mode capability check: if provider lacks agent support, do not select
    if (interactionMode === 'agent' && !provider.capabilities.agent && provider.id !== 'auto') {
      return;
    }

    onSelectProvider(provider.id);
    setIsOpen(false);
  };

  return (
    <div className="relative inline-block text-left" ref={containerRef}>
      {/* Trigger Button */}
      <button
        type="button"
        id="provider-selector-trigger"
        data-testid="provider-selector-trigger"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        disabled={disabled}
        aria-label="Select inference provider"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        title={
          disabled
            ? 'Provider switching is locked during active execution or pending approval'
            : `Selected Provider: ${activeProvider.display_name}`
        }
        className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
          disabled
            ? 'bg-zinc-900/50 border-zinc-800/60 text-zinc-500 cursor-not-allowed opacity-60'
            : isOpen
            ? 'bg-zinc-800 border-zinc-700 text-zinc-100 shadow-sm'
            : 'bg-zinc-900 border-zinc-800 text-zinc-300 hover:bg-zinc-800/80 hover:border-zinc-700'
        }`}
      >
        <Layers className="w-3.5 h-3.5 text-blue-400 group-hover:text-blue-300 transition-colors" />
        <span className="font-semibold text-zinc-200" data-testid="selected-provider-name">
          {activeProvider.display_name}
        </span>

        {/* Live health dot indicator */}
        <span
          data-testid="provider-health-dot"
          className={`w-2 h-2 rounded-full inline-block ${healthStyle.dot} transition-colors`}
          title={`Status: ${healthStyle.label}`}
        />

        {disabled ? (
          <Lock className="w-3 h-3 text-zinc-500 ml-0.5" />
        ) : (
          <ChevronDown
            className={`w-3.5 h-3.5 text-zinc-400 transition-transform duration-150 ${
              isOpen ? 'transform rotate-180' : ''
            }`}
          />
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          id="provider-selector-dropdown"
          data-testid="provider-selector-dropdown"
          role="listbox"
          aria-label="Inference Provider Switch"
          className="absolute left-0 mt-1.5 w-80 sm:w-96 rounded-xl bg-zinc-950 border border-zinc-800 shadow-2xl p-1.5 z-50 animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="px-3 py-2 border-b border-zinc-800/80 mb-1 flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
              Inference Provider Switch
            </span>
            <span className="text-[10px] text-zinc-400 font-mono">Backend Controlled</span>
          </div>

          <div className="space-y-1">
            {providers.map((p) => {
              const isSelected = p.id === selectedProviderId;
              const pHealth = getHealthBadgeStyle(p.health);
              const agentSupported = p.capabilities.agent || p.id === 'auto';
              const isAgentBlocked = interactionMode === 'agent' && !agentSupported;

              return (
                <div
                  key={p.id}
                  role="option"
                  aria-selected={isSelected}
                  aria-disabled={isAgentBlocked}
                  data-testid={`provider-option-${p.id}`}
                  onClick={() => !isAgentBlocked && handleSelect(p)}
                  className={`p-2.5 rounded-lg border transition-all cursor-pointer ${
                    isAgentBlocked
                      ? 'bg-zinc-950/60 border-zinc-900 opacity-50 cursor-not-allowed'
                      : isSelected
                      ? 'bg-blue-950/30 border-blue-500/40 text-blue-200'
                      : 'bg-zinc-900/40 border-transparent hover:bg-zinc-900 hover:border-zinc-800 text-zinc-300'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${pHealth.dot}`}
                        title={`Status: ${pHealth.label}`}
                      />
                      <span className="font-semibold text-xs text-zinc-100">{p.display_name}</span>
                      {p.id === 'auto' && (
                        <span className="px-1.5 py-0.2 bg-blue-500/20 border border-blue-500/30 text-blue-400 text-[10px] font-mono rounded">
                          SMART
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      {/* Health badge */}
                      <span
                        className={`px-1.5 py-0.5 rounded border text-[9px] font-mono font-medium ${pHealth.bg} ${pHealth.text}`}
                      >
                        {pHealth.label}
                      </span>
                      {isSelected && <Check className="w-3.5 h-3.5 text-blue-400" />}
                    </div>
                  </div>

                  {/* Read-only model display */}
                  <div className="flex items-center justify-between text-[11px] text-zinc-400 mt-1">
                    <div className="flex items-center gap-1.5 font-mono truncate max-w-[200px]">
                      <Cpu className="w-3 h-3 text-zinc-500 flex-shrink-0" />
                      <span className="truncate" title={p.chat_model || 'Configured Model'}>
                        {p.chat_model || (p.id === 'auto' ? 'Dynamic routing' : 'Standard model')}
                      </span>
                    </div>

                    {/* Chat / Agent Capability Badges */}
                    <div className="flex items-center gap-1">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${
                          p.capabilities.chat
                            ? 'bg-zinc-800 text-zinc-300'
                            : 'bg-zinc-900 text-zinc-600'
                        }`}
                      >
                        Chat
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-mono ${
                          p.capabilities.agent
                            ? 'bg-blue-900/30 text-blue-300 border border-blue-500/30'
                            : 'bg-zinc-900 text-zinc-600'
                        }`}
                      >
                        Agent
                      </span>
                    </div>
                  </div>

                  {/* Tool-calling warning if in Agent Mode */}
                  {isAgentBlocked && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded">
                      <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                      <span>Model lacks tool-calling capabilities required by Agent Mode</span>
                    </div>
                  )}

                  {/* Developer Mode Capability Inspection */}
                  {isDeveloperMode && p.id !== 'auto' && (
                    <div
                      data-testid={`dev-capabilities-${p.id}`}
                      className="mt-2 pt-2 border-t border-zinc-800/80 space-y-1 text-[10px] font-mono text-zinc-400"
                    >
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1">
                          <Mic className="w-3 h-3 text-zinc-500" /> STT (/v1/audio/transcriptions):
                        </span>
                        <span
                          className={
                            p.capabilities.transcription ? 'text-emerald-400' : 'text-zinc-500'
                          }
                        >
                          {p.capabilities.transcription ? 'REGISTERED' : 'NOT CONFIGURED'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1">
                          <Volume2 className="w-3 h-3 text-zinc-500" /> TTS (/v1/audio/speech):
                        </span>
                        <span
                          className={p.capabilities.speech ? 'text-emerald-400' : 'text-zinc-500'}
                        >
                          {p.capabilities.speech ? 'REGISTERED' : 'NOT CONFIGURED'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="flex items-center gap-1">
                          <Radio className="w-3 h-3 text-zinc-500" /> Realtime Voice:
                        </span>
                        <span className="text-amber-400/90 font-semibold">
                          DEFERRED TO BRICK-012
                        </span>
                      </div>
                      <div className="mt-1 text-[9px] text-zinc-400 italic">
                        Voice UI deferred to BRICK-012 (backend registration active)
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Footer Safety Notice */}
          <div className="mt-2 pt-2 border-t border-zinc-900 px-2 text-[10px] text-zinc-400 flex items-center justify-between">
            <span className="flex items-center gap-1 text-zinc-400">
              <Sparkles className="w-3 h-3 text-blue-400" /> Strict zero-fallback on explicit selection
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
